import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { ApiClientError } from "../core/api/apiClient";
import { useLocalization } from "../core/localization/localizationContext";
import { createMeterService } from "../features/maintenance/meterService";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { formatJalali, toPersianDigits } from "../core/localization/jalali";
import type {
  MaintenanceDevice,
  MeterPmStatusRow,
  MeterPoint,
  MeterPointSummary,
  MeterReading,
  MeterStatus,
} from "../shared/types/domain";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  CardHeader,
  EmptyState,
  LoadingState,
  MetricCard,
  SectionHeader,
  SelectInput,
  TextArea,
  TextInput,
} from "../shared/components/primitives";

/**
 * ثبت قرائت دستی و سنسوری — the capture page for meter readings.
 *
 * The page keeps three promises the backend makes visible to the operator:
 * a reading is never edited (only superseded by a correction), an untrusted
 * value never reports consumption, and a meter-driven PM plan shows exactly
 * how far it is from its trigger.
 */

const QUALITY_TONE: Record<string, "success" | "warning" | "danger" | "neutral"> = {
  good: "success",
  estimated: "info" as "success",
  suspect: "warning",
  bad: "danger",
};

const STATUS_TONE: Record<MeterStatus, "success" | "warning" | "danger" | "neutral"> = {
  ok: "success",
  warning: "warning",
  due: "danger",
  unknown: "neutral",
};

/** Persian digits, grouped, with the precision the meter actually carries. */
const formatValue = (value: number | null, unit = ""): string => {
  if (value === null) return "—";
  const rendered = toPersianDigits(
    value.toLocaleString("en-US", { maximumFractionDigits: 4, useGrouping: true }),
  );
  return unit ? `${rendered} ${unit}` : rendered;
};

const formatMoment = (iso: string): string => {
  if (!iso) return "—";
  const date = iso.slice(0, 10);
  const time = iso.slice(11, 16);
  const jalali = formatJalali(date);
  return time ? `${jalali} ${toPersianDigits(time)}` : jalali;
};

/** `datetime-local` wants `YYYY-MM-DDTHH:mm` in local time. */
const nowForInput = (): string => {
  const now = new Date();
  const pad = (part: number): string => String(part).padStart(2, "0");
  return `${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}T${pad(now.getHours())}:${pad(now.getMinutes())}`;
};

interface PointFormState {
  id: string;
  code: string;
  name: string;
  unit: string;
  kind: "cumulative" | "gauge";
  sensorKey: string;
  drivesRunningHours: boolean;
  rolloverMaximum: string;
  minimumValue: string;
  maximumValue: string;
  maximumStepPerHour: string;
  active: boolean;
}

const emptyPointForm = (): PointFormState => ({
  id: "",
  code: "",
  name: "",
  unit: "",
  kind: "cumulative",
  sensorKey: "",
  drivesRunningHours: false,
  rolloverMaximum: "",
  minimumValue: "",
  maximumValue: "",
  maximumStepPerHour: "",
  active: true,
});

export function MeterReadingsPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const meters = useMemo(() => createMeterService(api), [api]);
  const maintenance = useMemo(() => createMaintenanceService(api), [api]);

  const [devices, setDevices] = useState<MaintenanceDevice[]>([]);
  const [deviceId, setDeviceId] = useState("");
  const [points, setPoints] = useState<MeterPoint[]>([]);
  const [selectedPointId, setSelectedPointId] = useState("");
  const [readings, setReadings] = useState<MeterReading[]>([]);
  const [summary, setSummary] = useState<MeterPointSummary | null>(null);
  const [pmStatus, setPmStatus] = useState<MeterPmStatusRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState<{ message: string; tone: "success" | "error" } | null>(null);

  const [readingForm, setReadingForm] = useState({ value: "", capturedAt: "", note: "" });
  const [readingError, setReadingError] = useState("");
  const [pointForm, setPointForm] = useState<PointFormState | null>(null);
  const [pointError, setPointError] = useState("");
  const [correcting, setCorrecting] = useState<MeterReading | null>(null);
  const [correctionForm, setCorrectionForm] = useState({ value: "", note: "" });
  const [correctionError, setCorrectionError] = useState("");

  const selectedPoint = useMemo(
    () => points.find((point) => point.id === selectedPointId) ?? null,
    [points, selectedPointId],
  );

  const fail = useCallback((error: unknown, fallback: string): string => {
    if (error instanceof ApiClientError) return error.message || fallback;
    return fallback;
  }, []);

  // -- loading ----------------------------------------------------------------
  useEffect(() => {
    let cancelled = false;
    const controller = new AbortController();
    void (async () => {
      try {
        const list = await maintenance.listDevices({}, controller.signal);
        if (cancelled) return;
        setDevices(list);
        setDeviceId((current) => current || list[0]?.id || "");
      } catch (error) {
        if (!cancelled) setToast({ message: fail(error, t("meter.loadFailed")), tone: "error" });
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
      controller.abort();
    };
  }, [maintenance, fail, t]);

  const loadPoints = useCallback(
    async (signal?: AbortSignal) => {
      if (!deviceId) {
        setPoints([]);
        setSelectedPointId("");
        return;
      }
      const list = await meters.listDeviceMeterPoints(deviceId, signal);
      setPoints(list);
      setSelectedPointId((current) =>
        list.some((point) => point.id === current) ? current : list[0]?.id || "",
      );
    },
    [deviceId, meters],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadPoints(controller.signal).catch((error) => {
      if (!controller.signal.aborted) {
        setToast({ message: fail(error, t("meter.loadFailed")), tone: "error" });
      }
    });
    return () => controller.abort();
  }, [loadPoints, fail, t]);

  const loadPointDetail = useCallback(
    async (signal?: AbortSignal) => {
      if (!selectedPointId) {
        setReadings([]);
        setSummary(null);
        return;
      }
      const [history, stats] = await Promise.all([
        meters.listReadings({ meterPointId: selectedPointId, pageSize: 50 }, signal),
        meters.getSummary(selectedPointId, {}, signal),
      ]);
      setReadings(history);
      setSummary(stats);
    },
    [meters, selectedPointId],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadPointDetail(controller.signal).catch((error) => {
      if (!controller.signal.aborted) {
        setToast({ message: fail(error, t("meter.loadFailed")), tone: "error" });
      }
    });
    return () => controller.abort();
  }, [loadPointDetail, fail, t]);

  const loadPmStatus = useCallback(
    async (signal?: AbortSignal) => {
      if (!deviceId) {
        setPmStatus([]);
        return;
      }
      setPmStatus(await meters.getPmStatus({ deviceId }, signal));
    },
    [deviceId, meters],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadPmStatus(controller.signal).catch(() => {
      /* the PM strip is informational; a failure must not block capture */
    });
    return () => controller.abort();
  }, [loadPmStatus]);

  // -- actions ----------------------------------------------------------------
  const submitReading = async (): Promise<void> => {
    if (!selectedPoint || !deviceId) return;
    if (!readingForm.value.trim()) {
      setReadingError(t("meter.value"));
      return;
    }
    setBusy(true);
    setReadingError("");
    try {
      await meters.recordReading(deviceId, {
        meterPointId: selectedPoint.id,
        value: readingForm.value.trim(),
        capturedAt: readingForm.capturedAt
          ? new Date(readingForm.capturedAt).toISOString()
          : undefined,
        note: readingForm.note.trim() || undefined,
      });
      setReadingForm({ value: "", capturedAt: "", note: "" });
      await Promise.all([loadPoints(), loadPointDetail(), loadPmStatus()]);
      setToast({ message: t("meter.saved"), tone: "success" });
    } catch (error) {
      setReadingError(fail(error, t("meter.saveFailed")));
    } finally {
      setBusy(false);
    }
  };

  const submitPoint = async (): Promise<void> => {
    if (!pointForm || !deviceId) return;
    setBusy(true);
    setPointError("");
    const payload = {
      code: pointForm.code.trim(),
      name: pointForm.name.trim(),
      unit: pointForm.unit.trim(),
      kind: pointForm.kind,
      sensorKey: pointForm.sensorKey.trim(),
      drivesRunningHours: pointForm.drivesRunningHours,
      active: pointForm.active,
      rolloverMaximum: pointForm.rolloverMaximum.trim(),
      minimumValue: pointForm.minimumValue.trim(),
      maximumValue: pointForm.maximumValue.trim(),
      maximumStepPerHour: pointForm.maximumStepPerHour.trim(),
    };
    try {
      if (pointForm.id) {
        await meters.updateMeterPoint(pointForm.id, payload);
      } else {
        await meters.createMeterPoint(deviceId, payload);
      }
      setPointForm(null);
      await loadPoints();
      setToast({ message: t("meter.pointSaved"), tone: "success" });
    } catch (error) {
      setPointError(fail(error, t("meter.saveFailed")));
    } finally {
      setBusy(false);
    }
  };

  const retirePoint = async (point: MeterPoint): Promise<void> => {
    if (!window.confirm(t("meter.retireConfirm"))) return;
    setBusy(true);
    try {
      await meters.retireMeterPoint(point.id);
      await loadPoints();
      setToast({ message: t("meter.pointRetired"), tone: "success" });
    } catch (error) {
      setToast({ message: fail(error, t("meter.saveFailed")), tone: "error" });
    } finally {
      setBusy(false);
    }
  };

  const submitCorrection = async (): Promise<void> => {
    if (!correcting) return;
    if (!correctionForm.value.trim() || !correctionForm.note.trim()) {
      setCorrectionError(t("meter.correctReason"));
      return;
    }
    setBusy(true);
    setCorrectionError("");
    try {
      await meters.correctReading(correcting.id, {
        value: correctionForm.value.trim(),
        note: correctionForm.note.trim(),
      });
      setCorrecting(null);
      setCorrectionForm({ value: "", note: "" });
      await Promise.all([loadPoints(), loadPointDetail(), loadPmStatus()]);
      setToast({ message: t("meter.corrected"), tone: "success" });
    } catch (error) {
      setCorrectionError(fail(error, t("meter.saveFailed")));
    } finally {
      setBusy(false);
    }
  };

  if (loading) return <LoadingState label={t("common.loading")} />;

  return (
    <div className="page-stack">
      <SectionHeader
        title={t("meter.title")}
        subtitle={t("meter.subtitle")}
        actions={
          <Button
            variant="primary"
            onClick={() => {
              setPointForm(emptyPointForm());
              setPointError("");
            }}
            disabled={!deviceId}
          >
            {t("meter.addPoint")}
          </Button>
        }
      />

      <Card>
        <SelectInput
          label={t("meter.device")}
          value={deviceId}
          onChange={(event) => setDeviceId(event.currentTarget.value)}
          options={[
            { value: "", label: t("meter.selectDevice") },
            ...devices.map((device) => ({
              value: device.id,
              label: `${device.code} — ${device.name}`,
            })),
          ]}
        />
      </Card>

      {/* -- meter points ---------------------------------------------------- */}
      <Card>
        <CardHeader title={t("meter.points")} icon="activity" />
        {points.length === 0 ? (
          <EmptyState icon="activity" title={t("meter.pointsEmpty")} />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("meter.code")}</th>
                  <th>{t("meter.name")}</th>
                  <th>{t("meter.kind")}</th>
                  <th>{t("meter.lastValue")}</th>
                  <th>{t("meter.lastReadingAt")}</th>
                  <th>{t("meter.readingCount")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {points.map((point) => (
                  <tr
                    key={point.id}
                    className={point.id === selectedPointId ? "is-selected" : ""}
                    onClick={() => setSelectedPointId(point.id)}
                  >
                    <td>
                      <strong>{point.code}</strong>
                      {point.drivesRunningHours ? (
                        <Badge tone="info">{t("meter.drivesRunningHours")}</Badge>
                      ) : null}
                      {!point.active ? <Badge tone="neutral">{t("meter.inactive")}</Badge> : null}
                    </td>
                    <td>{point.name}</td>
                    <td>{t(point.kind === "cumulative" ? "meter.kind.cumulative" : "meter.kind.gauge")}</td>
                    <td>{formatValue(point.lastValue, point.unit)}</td>
                    <td>{formatMoment(point.lastReadingAt)}</td>
                    <td>{toPersianDigits(String(point.readingCount))}</td>
                    <td className="table-actions">
                      <Button
                        variant="ghost"
                        onClick={(event) => {
                          event.stopPropagation();
                          setPointForm({
                            id: point.id,
                            code: point.code,
                            name: point.name,
                            unit: point.unit,
                            kind: point.kind,
                            sensorKey: point.sensorKey,
                            drivesRunningHours: point.drivesRunningHours,
                            rolloverMaximum:
                              point.rolloverMaximum === null ? "" : String(point.rolloverMaximum),
                            minimumValue:
                              point.minimumValue === null ? "" : String(point.minimumValue),
                            maximumValue:
                              point.maximumValue === null ? "" : String(point.maximumValue),
                            maximumStepPerHour:
                              point.maximumStepPerHour === null
                                ? ""
                                : String(point.maximumStepPerHour),
                            active: point.active,
                          });
                          setPointError("");
                        }}
                      >
                        {t("common.edit")}
                      </Button>
                      <Button
                        variant="ghost"
                        onClick={(event) => {
                          event.stopPropagation();
                          void retirePoint(point);
                        }}
                      >
                        {t("meter.retirePoint")}
                      </Button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* -- capture --------------------------------------------------------- */}
      {selectedPoint ? (
        <Card>
          <CardHeader
            title={`${t("meter.recordTitle")} — ${selectedPoint.name}`}
            subtitle={selectedPoint.unit}
            icon="plus"
          />
          <div className="form-grid">
            <TextInput
              label={`${t("meter.value")} (${selectedPoint.unit || "—"})`}
              inputMode="decimal"
              value={readingForm.value}
              error={readingError || undefined}
              onChange={(event) =>
                setReadingForm((form) => ({ ...form, value: event.currentTarget.value }))
              }
            />
            <TextInput
              label={t("meter.capturedAt")}
              type="datetime-local"
              max={nowForInput()}
              value={readingForm.capturedAt}
              onChange={(event) =>
                setReadingForm((form) => ({ ...form, capturedAt: event.currentTarget.value }))
              }
            />
            <TextInput
              label={t("meter.note")}
              value={readingForm.note}
              onChange={(event) =>
                setReadingForm((form) => ({ ...form, note: event.currentTarget.value }))
              }
            />
          </div>
          <Button variant="primary" onClick={() => void submitReading()} disabled={busy}>
            {t("meter.record")}
          </Button>
        </Card>
      ) : null}

      {/* -- summary --------------------------------------------------------- */}
      {summary ? (
        <div className="metric-grid">
          <MetricCard
            label={t("meter.summary.total")}
            value={formatValue(summary.totalConsumption, summary.unit)}
            icon="activity"
          />
          <MetricCard
            label={t("meter.summary.manual")}
            value={toPersianDigits(String(summary.manualCount))}
            icon="edit"
            tone="purple"
          />
          <MetricCard
            label={t("meter.summary.sensor")}
            value={toPersianDigits(String(summary.sensorCount))}
            icon="cpu"
            tone="green"
          />
          <MetricCard
            label={t("meter.summary.suspect")}
            value={toPersianDigits(String(summary.suspectCount))}
            icon="bell"
            tone="amber"
          />
        </div>
      ) : null}

      {/* -- PM status ------------------------------------------------------- */}
      <Card>
        <CardHeader title={t("meter.pmStatus")} icon="calendar" />
        {pmStatus.length === 0 ? (
          <EmptyState icon="calendar" title={t("meter.pmStatusEmpty")} />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("registry.pm.title")}</th>
                  <th>{t("meter.pmCurrent")}</th>
                  <th>{t("meter.pmDueAt")}</th>
                  <th>{t("meter.pmRemaining")}</th>
                  <th>{t("meter.statusLabel")}</th>
                </tr>
              </thead>
              <tbody>
                {pmStatus.map((row) => (
                  <tr key={row.planId}>
                    <td>
                      <strong>{row.title}</strong>
                      <div className="muted">{row.metricType}</div>
                    </td>
                    <td>{formatValue(row.currentValue, row.metricUnit)}</td>
                    <td>{formatValue(row.dueAtValue, row.metricUnit)}</td>
                    <td>{formatValue(row.remaining, row.metricUnit)}</td>
                    <td>
                      <Badge tone={STATUS_TONE[row.status]}>{t(`meter.status.${row.status}`)}</Badge>
                      {row.reason === "noReadings" || row.reason === "noBaseline" ? (
                        <div className="muted">{t(`meter.reason.${row.reason}`)}</div>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* -- history --------------------------------------------------------- */}
      <Card>
        <CardHeader title={t("meter.history")} icon="clock" />
        {readings.length === 0 ? (
          <EmptyState icon="clock" title={t("meter.historyEmpty")} />
        ) : (
          <div className="table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>{t("meter.capturedAt")}</th>
                  <th>{t("meter.value")}</th>
                  <th>{t("meter.delta")}</th>
                  <th>{t("meter.captureMode")}</th>
                  <th>{t("meter.quality")}</th>
                  <th>{t("meter.recordedBy")}</th>
                  <th />
                </tr>
              </thead>
              <tbody>
                {readings.map((reading) => (
                  <tr key={reading.id} className={reading.supersededByReadingId ? "is-muted" : ""}>
                    <td>{formatMoment(reading.capturedAt)}</td>
                    <td>
                      {formatValue(reading.value, reading.unit)}
                      {reading.rolloverApplied ? (
                        <Badge tone="info">{t("meter.rolloverApplied")}</Badge>
                      ) : null}
                    </td>
                    <td>{formatValue(reading.delta, reading.unit)}</td>
                    <td>{t(`meter.captureMode.${reading.captureMode}`)}</td>
                    <td>
                      <Badge tone={QUALITY_TONE[reading.quality] ?? "neutral"}>
                        {t(`meter.quality.${reading.quality}`)}
                      </Badge>
                    </td>
                    <td>{reading.recordedByName || reading.sensorKey || "—"}</td>
                    <td className="table-actions">
                      {reading.supersededByReadingId ? (
                        <Badge tone="neutral">{t("meter.superseded")}</Badge>
                      ) : (
                        <Button
                          variant="ghost"
                          onClick={() => {
                            setCorrecting(reading);
                            setCorrectionForm({ value: String(reading.value), note: "" });
                            setCorrectionError("");
                          }}
                        >
                          {t("meter.correct")}
                        </Button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      {/* -- meter point editor ---------------------------------------------- */}
      <Modal
        open={pointForm !== null}
        title={pointForm?.id ? t("meter.editPoint") : t("meter.addPoint")}
        onClose={() => setPointForm(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setPointForm(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" onClick={() => void submitPoint()} disabled={busy}>
              {t("common.save")}
            </Button>
          </>
        }
      >
        {pointForm ? (
          <div className="form-grid">
            <TextInput
              label={t("meter.code")}
              value={pointForm.code}
              error={pointError || undefined}
              onChange={(event) =>
                setPointForm({ ...pointForm, code: event.currentTarget.value })
              }
            />
            <TextInput
              label={t("meter.name")}
              value={pointForm.name}
              onChange={(event) => setPointForm({ ...pointForm, name: event.currentTarget.value })}
            />
            <TextInput
              label={t("meter.unit")}
              value={pointForm.unit}
              onChange={(event) => setPointForm({ ...pointForm, unit: event.currentTarget.value })}
            />
            <SelectInput
              label={t("meter.kind")}
              value={pointForm.kind}
              disabled={Boolean(pointForm.id)}
              onChange={(event) =>
                setPointForm({
                  ...pointForm,
                  kind: event.currentTarget.value === "gauge" ? "gauge" : "cumulative",
                })
              }
              options={[
                { value: "cumulative", label: t("meter.kind.cumulative") },
                { value: "gauge", label: t("meter.kind.gauge") },
              ]}
            />
            <TextInput
              label={t("meter.sensorKey")}
              hint={t("meter.sensorKeyHint")}
              value={pointForm.sensorKey}
              onChange={(event) =>
                setPointForm({ ...pointForm, sensorKey: event.currentTarget.value })
              }
            />
            <TextInput
              label={t("meter.rolloverMaximum")}
              inputMode="decimal"
              disabled={pointForm.kind !== "cumulative"}
              value={pointForm.rolloverMaximum}
              onChange={(event) =>
                setPointForm({ ...pointForm, rolloverMaximum: event.currentTarget.value })
              }
            />
            <TextInput
              label={t("meter.minimumValue")}
              inputMode="decimal"
              value={pointForm.minimumValue}
              onChange={(event) =>
                setPointForm({ ...pointForm, minimumValue: event.currentTarget.value })
              }
            />
            <TextInput
              label={t("meter.maximumValue")}
              inputMode="decimal"
              value={pointForm.maximumValue}
              onChange={(event) =>
                setPointForm({ ...pointForm, maximumValue: event.currentTarget.value })
              }
            />
            <TextInput
              label={t("meter.maximumStepPerHour")}
              inputMode="decimal"
              value={pointForm.maximumStepPerHour}
              onChange={(event) =>
                setPointForm({ ...pointForm, maximumStepPerHour: event.currentTarget.value })
              }
            />
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={pointForm.drivesRunningHours}
                disabled={pointForm.kind !== "cumulative"}
                onChange={(event) =>
                  setPointForm({
                    ...pointForm,
                    drivesRunningHours: event.currentTarget.checked,
                  })
                }
              />
              <span>{t("meter.drivesRunningHours")}</span>
            </label>
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={pointForm.active}
                onChange={(event) =>
                  setPointForm({ ...pointForm, active: event.currentTarget.checked })
                }
              />
              <span>{t("meter.active")}</span>
            </label>
          </div>
        ) : null}
      </Modal>

      {/* -- correction ------------------------------------------------------ */}
      <Modal
        open={correcting !== null}
        title={t("meter.correctTitle")}
        description={t("meter.correctHint")}
        onClose={() => setCorrecting(null)}
        footer={
          <>
            <Button variant="ghost" onClick={() => setCorrecting(null)}>
              {t("common.cancel")}
            </Button>
            <Button variant="primary" onClick={() => void submitCorrection()} disabled={busy}>
              {t("common.save")}
            </Button>
          </>
        }
      >
        <div className="form-grid">
          <TextInput
            label={t("meter.value")}
            inputMode="decimal"
            value={correctionForm.value}
            error={correctionError || undefined}
            onChange={(event) =>
              setCorrectionForm((form) => ({ ...form, value: event.currentTarget.value }))
            }
          />
          <TextArea
            label={t("meter.correctReason")}
            value={correctionForm.note}
            onChange={(event) =>
              setCorrectionForm((form) => ({ ...form, note: event.currentTarget.value }))
            }
          />
        </div>
      </Modal>

      {toast ? (
        <Toast message={toast.message} tone={toast.tone} onClose={() => setToast(null)} />
      ) : null}
    </div>
  );
}
