import { useCallback, useEffect, useMemo, useState } from "react";

import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createWorkCalendarService } from "../features/maintenance/workCalendarService";
import type { SaveCalendarInput } from "../features/maintenance/workCalendarService";
import { createDemoWorkCalendarService } from "../features/maintenance/workCalendarDemoData";
import { capacityTone, monthGridOffset } from "../features/maintenance/workCalendarMath";
import {
  HOLIDAY_KINDS,
  ROLL_POLICIES,
  SHIFT_KINDS,
  WEEKDAY_ORDER_IR,
  type CalendarHoliday,
  type CapacityPlan,
  type HolidayKind,
  type RollPolicy,
  type ShiftKind,
  type WorkCalendar,
} from "../shared/types/domain";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  ErrorState,
  LoadingState,
  MetricCard,
  PermissionGuard,
  SectionHeader,
  SelectInput,
  TextInput,
} from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import {
  JALALI_MONTHS,
  JALALI_WEEKDAYS,
  formatJalali,
  isoToJalaliParts,
  jalaliMonthLength,
  jalaliPartsToIso,
  toPersianDigits,
  todayIso,
} from "../core/localization/jalali";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";

/**
 * Work calendar, shifts and crew capacity (Phase 28).
 *
 * The plant already had a Jalali date *display*; what it did not have was a
 * notion of when it is actually open. This page is that notion: which days are
 * weekend at this site, which are holidays, who is on shift, and therefore how
 * many maintenance hours exist on a given day versus how many the PM plan is
 * asking for.
 *
 * The capacity grid walks Jalali months, like the PM calendar beside it, so the
 * two read as one calendar rather than two.
 */

type TabKey = "calendars" | "holidays" | "shifts" | "capacity";

const TAB_KEYS: TabKey[] = ["calendars", "holidays", "shifts", "capacity"];

/**
 * Weekend pickers speak in python weekdays (Mon 0 … جمعه 4) because that is
 * what the backend stores, but they must *read* شنبه-first like the grid.
 * `WEEKDAY_ORDER_IR` holds that display order; the label comes from the
 * existing Jalali dictionary so there is one source of weekday names.
 */
const weekdayLabel = (py: number): string => {
  const column = WEEKDAY_ORDER_IR.indexOf(py);
  return column >= 0 ? JALALI_WEEKDAYS[column] : String(py);
};

interface JalaliMonth {
  year: number;
  month: number;
}

const currentJalaliMonth = (): JalaliMonth => {
  const parts = isoToJalaliParts(todayIso());
  return parts ? { year: parts[0], month: parts[1] } : { year: 1405, month: 7 };
};

const stepMonth = (current: JalaliMonth, delta: number): JalaliMonth => {
  const next = current.month + delta;
  if (next < 1) return { year: current.year - 1, month: 12 };
  if (next > 12) return { year: current.year + 1, month: 1 };
  return { year: current.year, month: next };
};

const emptyCalendarForm: SaveCalendarInput = {
  code: "",
  name: "",
  locationId: "",
  timezone: "Asia/Tehran",
  weekendDays: [4],
  rollPolicy: "forward",
  isDefault: false,
  note: "",
};

export function WorkCalendarPage(): JSX.Element {
  const { t } = useLocalization();
  const api = useApiClient();
  const service = useMemo(
    () =>
      runtimeConfig.demoMode
        ? createDemoWorkCalendarService()
        : createWorkCalendarService(api),
    [api],
  );

  const [tab, setTab] = useState<TabKey>("calendars");
  const [calendars, setCalendars] = useState<WorkCalendar[]>([]);
  const [selectedId, setSelectedId] = useState("");
  const [holidays, setHolidays] = useState<CalendarHoliday[]>([]);
  const [plan, setPlan] = useState<CapacityPlan | null>(null);
  const [month, setMonth] = useState<JalaliMonth>(currentJalaliMonth);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState("");
  const [busy, setBusy] = useState(false);
  const [toast, setToast] = useState("");
  const [toastTone, setToastTone] = useState<"success" | "error">("success");

  const [calendarModal, setCalendarModal] = useState(false);
  const [calendarForm, setCalendarForm] = useState<SaveCalendarInput>(emptyCalendarForm);
  const [holidayModal, setHolidayModal] = useState(false);
  const [holidayForm, setHolidayForm] = useState({
    onDate: todayIso(),
    name: "",
    kind: "official" as HolidayKind,
    recursAnnually: false,
  });
  const [shiftModal, setShiftModal] = useState(false);
  const [shiftForm, setShiftForm] = useState({
    code: "",
    name: "",
    kind: "general" as ShiftKind,
    startTime: "08:00",
    endTime: "16:00",
    headcount: 1,
  });

  const selected = useMemo(
    () => calendars.find((row) => row.id === selectedId) ?? calendars[0],
    [calendars, selectedId],
  );

  const monthStartIso = jalaliPartsToIso(month.year, month.month, 1);
  const monthEndIso = jalaliPartsToIso(
    month.year,
    month.month,
    jalaliMonthLength(month.year, month.month),
  );

  const fail = useCallback(
    (error: unknown) => {
      setToastTone("error");
      setToast((error as Error)?.message || t("error.networkBody"));
    },
    [t],
  );

  const succeed = useCallback((message: string) => {
    setToastTone("success");
    setToast(message);
  }, []);

  const loadCalendars = useCallback(
    async (signal?: AbortSignal) => {
      setLoading(true);
      setLoadError("");
      try {
        const rows = await service.listCalendars(signal);
        setCalendars(rows);
        setSelectedId((previous) =>
          previous && rows.some((row) => row.id === previous)
            ? previous
            : (rows.find((row) => row.isDefault)?.id ?? rows[0]?.id ?? ""),
        );
      } catch (error) {
        if ((error as Error)?.name !== "AbortError") {
          setLoadError((error as Error)?.message || t("error.networkBody"));
        }
      } finally {
        setLoading(false);
      }
    },
    [service, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    void loadCalendars(controller.signal);
    return () => controller.abort();
  }, [loadCalendars]);

  // Holidays and the capacity plan both hang off the selected calendar, so they
  // reload together whenever it — or the month on display — changes.
  const loadDetail = useCallback(
    async (calendarId: string, fromDate: string, toDate: string, signal?: AbortSignal) => {
      try {
        const [holidayRows, planRow] = await Promise.all([
          service.listHolidays({ calendarId }, signal),
          service.getCapacityPlan({ calendarId, fromDate, toDate }, signal),
        ]);
        setHolidays(holidayRows);
        setPlan(planRow);
      } catch (error) {
        if ((error as Error)?.name !== "AbortError") fail(error);
      }
    },
    [service, fail],
  );

  useEffect(() => {
    if (!selected) return undefined;
    const controller = new AbortController();
    void loadDetail(selected.id, monthStartIso, monthEndIso, controller.signal);
    return () => controller.abort();
  }, [loadDetail, selected, monthStartIso, monthEndIso]);

  const reload = useCallback(async () => {
    await loadCalendars();
    if (selected) await loadDetail(selected.id, monthStartIso, monthEndIso);
  }, [loadCalendars, loadDetail, selected, monthStartIso, monthEndIso]);

  /** Every write follows the same shape: run it, report it, reload. */
  const runWrite = async (action: () => Promise<unknown>, message: string): Promise<void> => {
    setBusy(true);
    try {
      await action();
      succeed(message);
      await reload();
    } catch (error) {
      fail(error);
    } finally {
      setBusy(false);
    }
  };

  const holidayByDate = useMemo(
    () => new Map(holidays.map((holiday) => [holiday.onDate, holiday])),
    [holidays],
  );

  /** Capacity for one ordinary open week — the headline figure of the page. */
  const weeklyCapacity = useMemo(() => {
    if (!selected) return 0;
    const perDay = selected.shifts
      .filter((shift) => shift.active)
      .reduce((total, shift) => total + Number(shift.capacityHours || 0), 0);
    return Math.round(perDay * (7 - selected.weekendDays.length));
  }, [selected]);

  // -- tabs ---------------------------------------------------------------------

  const renderCalendars = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader
        title={t("calendar.tab.calendars")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button
              variant="primary"
              icon="plus"
              onClick={() => {
                setCalendarForm(emptyCalendarForm);
                setCalendarModal(true);
              }}
            >
              {t("calendar.add")}
            </Button>
          </PermissionGuard>
        }
      />
      {calendars.length === 0 ? (
        <EmptyState icon="calendar" title={t("calendar.empty")} />
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("calendar.field.code")}</th>
                <th>{t("calendar.field.name")}</th>
                <th>{t("calendar.field.site")}</th>
                <th>{t("calendar.field.timezone")}</th>
                <th>{t("calendar.field.weekend")}</th>
                <th>{t("calendar.field.rollPolicy")}</th>
                <th aria-label={t("calendar.choose")} />
              </tr>
            </thead>
            <tbody>
              {calendars.map((calendar) => (
                <tr key={calendar.id} className={calendar.id === selected?.id ? "is-active" : ""}>
                  <td><code className="plaintext">{calendar.code}</code></td>
                  <td>
                    {calendar.name}{" "}
                    {calendar.isDefault && <Badge tone="info">{t("calendar.default")}</Badge>}
                  </td>
                  <td>{calendar.locationPath || "—"}</td>
                  <td><code className="plaintext">{calendar.timezone}</code></td>
                  <td>{calendar.weekendDays.map(weekdayLabel).join("، ") || "—"}</td>
                  <td>{taxonomyLabel(t, "calendar.roll.", calendar.rollPolicy)}</td>
                  <td>
                    <Button
                      variant="subtle"
                      size="sm"
                      disabled={calendar.id === selected?.id}
                      onClick={() => setSelectedId(calendar.id)}
                    >
                      {t("calendar.choose")}
                    </Button>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );

  const renderHolidays = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader
        title={t("calendar.tab.holidays")}
        subtitle={t("calendar.holiday.lunarNote")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button
              variant="primary"
              icon="plus"
              disabled={!selected}
              onClick={() => {
                setHolidayForm({
                  onDate: todayIso(),
                  name: "",
                  kind: "official",
                  recursAnnually: false,
                });
                setHolidayModal(true);
              }}
            >
              {t("calendar.holiday.add")}
            </Button>
          </PermissionGuard>
        }
      />
      {holidays.length === 0 ? (
        <EmptyState icon="calendar" title={t("calendar.holiday.empty")} />
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("calendar.holiday.date")}</th>
                <th>{t("calendar.holiday.name")}</th>
                <th>{t("calendar.holiday.kind")}</th>
                <th>{t("calendar.holiday.recurs")}</th>
                <th aria-label={t("common.delete")} />
              </tr>
            </thead>
            <tbody>
              {holidays.map((holiday) => (
                <tr key={holiday.id}>
                  <td>{formatJalali(holiday.onDate)}</td>
                  <td>{holiday.name}</td>
                  <td>
                    <Badge tone={holiday.kind === "shutdown" ? "warning" : "neutral"}>
                      {taxonomyLabel(t, "calendar.holidayKind.", holiday.kind)}
                    </Badge>
                  </td>
                  <td>{holiday.recursAnnually ? "✓" : "—"}</td>
                  <td>
                    <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          void runWrite(
                            () => service.deleteHoliday(holiday.id),
                            t("calendar.holiday.deleted"),
                          )
                        }
                      >
                        {t("common.delete")}
                      </Button>
                    </PermissionGuard>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );

  const renderShifts = (): JSX.Element => (
    <Card className="content-card" padding="md">
      <SectionHeader
        title={t("calendar.tab.shifts")}
        actions={
          <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
            <Button
              variant="primary"
              icon="plus"
              disabled={!selected}
              onClick={() => setShiftModal(true)}
            >
              {t("calendar.shift.add")}
            </Button>
          </PermissionGuard>
        }
      />
      {!selected || selected.shifts.length === 0 ? (
        <EmptyState icon="clock" title={t("calendar.shift.empty")} />
      ) : (
        <div className="table-scroll">
          <table className="data-table">
            <thead>
              <tr>
                <th>{t("calendar.shift.code")}</th>
                <th>{t("calendar.shift.name")}</th>
                <th>{t("calendar.shift.kind")}</th>
                <th>{t("calendar.shift.start")}</th>
                <th>{t("calendar.shift.end")}</th>
                <th>{t("calendar.shift.duration")}</th>
                <th>{t("calendar.shift.headcount")}</th>
                <th>{t("calendar.shift.capacity")}</th>
                <th aria-label={t("common.delete")} />
              </tr>
            </thead>
            <tbody>
              {selected.shifts.map((shift) => (
                <tr key={shift.id}>
                  <td><code className="plaintext">{shift.code}</code></td>
                  <td>{shift.name}</td>
                  <td>
                    <Badge tone="purple">
                      {taxonomyLabel(t, "calendar.shiftKind.", shift.kind)}
                    </Badge>
                  </td>
                  <td><code className="plaintext">{shift.startTime}</code></td>
                  <td>
                    <code className="plaintext">{shift.endTime}</code>{" "}
                    {shift.crossesMidnight && (
                      <Badge tone="warning">{t("calendar.shift.crossesMidnight")}</Badge>
                    )}
                  </td>
                  <td>{toPersianDigits(shift.durationHours)}</td>
                  <td>
                    {toPersianDigits(shift.effectiveHeadcount)}
                    {shift.assignedCount > 0 && (
                      <span className="muted-cell">
                        {" "}
                        ({t("calendar.shift.assigned")}: {toPersianDigits(shift.assignedCount)})
                      </span>
                    )}
                  </td>
                  <td><strong>{toPersianDigits(shift.capacityHours)}</strong></td>
                  <td>
                    <PermissionGuard permission={PERMISSIONS.maintenanceDeviceManage}>
                      <Button
                        variant="danger"
                        size="sm"
                        disabled={busy}
                        onClick={() =>
                          void runWrite(
                            () => service.deleteShift(shift.id),
                            t("calendar.shift.deleted"),
                          )
                        }
                      >
                        {t("common.delete")}
                      </Button>
                    </PermissionGuard>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );

  const renderCapacity = (): JSX.Element => {
    if (!plan) return <LoadingState label={t("calendar.capacity.title")} />;
    const byDate = new Map(plan.days.map((day) => [day.onDate, day]));
    const offset = monthGridOffset(monthStartIso);
    const length = jalaliMonthLength(month.year, month.month);
    const cells: (string | null)[] = [
      ...Array.from({ length: offset }, () => null),
      ...Array.from({ length }, (_unused, index) =>
        jalaliPartsToIso(month.year, month.month, index + 1),
      ),
    ];

    return (
      <>
        <Card className="content-card" padding="md">
          <div className="wcal__toolbar">
            <h2 className="wcal__month-title">
              <Icon name="calendar" size={20} />
              {JALALI_MONTHS[month.month - 1]}
              <span className="wcal__year">{toPersianDigits(month.year)}</span>
            </h2>
            <div className="wcal__nav">
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setMonth(stepMonth(month, -1))}
              >
                {t("calendar.capacity.prev")}
              </Button>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => setMonth(stepMonth(month, 1))}
              >
                {t("calendar.capacity.next")}
              </Button>
            </div>
            <div className="wcal__legend">
              {(["closed", "idle", "ok", "tight", "over"] as const).map((tone) => (
                <span key={tone}>
                  <b className={`wcal__dot wcal__dot--${tone}`} />
                  {taxonomyLabel(t, "calendar.legend.", tone)}
                </span>
              ))}
            </div>
          </div>
          <p className="wcal__hint">{t("calendar.capacity.subtitle")}</p>

          <div
            className="wcal__grid"
            role="grid"
            aria-label={`${JALALI_MONTHS[month.month - 1]} ${toPersianDigits(month.year)}`}
          >
            {JALALI_WEEKDAYS.map((weekday) => (
              <div key={weekday} className="wcal__weekday">
                {weekday}
              </div>
            ))}
            {cells.map((iso, index) => {
              if (iso === null) {
                return <div key={`blank-${index}`} className="wcal__cell wcal__cell--blank" />;
              }
              const day = byDate.get(iso);
              if (!day) {
                return <div key={iso} className="wcal__cell wcal__cell--blank" />;
              }
              const tone = capacityTone(day);
              const parts = isoToJalaliParts(iso);
              const holiday = holidayByDate.get(iso);
              return (
                <div
                  key={iso}
                  className={`wcal__cell wcal__cell--${tone} ${iso === todayIso() ? "is-today" : ""}`}
                  title={
                    day.isWorkingDay
                      ? `${day.demandHours} / ${day.capacityHours} — ${day.utilisationPercent}%`
                      : (holiday?.name ?? t("calendar.capacity.closed"))
                  }
                >
                  <span className="wcal__day">{toPersianDigits(parts ? parts[2] : "")}</span>
                  {day.isWorkingDay ? (
                    <>
                      <div className="wcal__bar">
                        <span
                          style={{
                            width: `${Math.min(100, Number(day.utilisationPercent) || 0)}%`,
                          }}
                        />
                      </div>
                      <span className="wcal__figures">
                        {toPersianDigits(day.demandHours)} / {toPersianDigits(day.capacityHours)}
                      </span>
                      {day.jobCount > 0 && (
                        <span className="wcal__jobs">
                          {toPersianDigits(day.jobCount)} {t("calendar.capacity.jobs")}
                        </span>
                      )}
                    </>
                  ) : (
                    <span className="wcal__closed">
                      {holiday?.name ?? t("calendar.capacity.closed")}
                    </span>
                  )}
                </div>
              );
            })}
          </div>
        </Card>

        <Card className="content-card" padding="md">
          <SectionHeader
            title={t("calendar.capacity.title")}
            subtitle={`${t("calendar.capacity.demand")} ${toPersianDigits(plan.summary.totalDemandHours)} · ${t("calendar.capacity.available")} ${toPersianDigits(plan.summary.totalCapacityHours)} · ${toPersianDigits(plan.summary.utilisationPercent)}%`}
          />
          {plan.days.every((day) => day.jobCount === 0) ? (
            <EmptyState icon="calendar" title={t("calendar.capacity.empty")} />
          ) : (
            <div className="table-scroll">
              <table className="data-table">
                <thead>
                  <tr>
                    <th>{t("calendar.holiday.date")}</th>
                    <th>{t("registry.column.code")}</th>
                    <th>{t("registry.column.name")}</th>
                    <th>{t("calendar.capacity.demand")}</th>
                  </tr>
                </thead>
                <tbody>
                  {plan.days.flatMap((day) =>
                    day.jobs.map((job, index) => (
                      <tr key={`${day.onDate}-${job.deviceId}-${index}`}>
                        <td>
                          {formatJalali(day.onDate)}{" "}
                          {job.rolled && (
                            <Badge tone="warning">
                              {t("calendar.capacity.rolled")} {formatJalali(job.dueOn)}
                            </Badge>
                          )}
                        </td>
                        <td><code className="plaintext">{job.deviceCode}</code></td>
                        <td>{job.title || job.deviceName}</td>
                        <td>{toPersianDigits(job.estimatedHours)}</td>
                      </tr>
                    )),
                  )}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </>
    );
  };

  return (
    <PermissionGuard permission={PERMISSIONS.maintenanceDeviceList} fallback="denied">
      <div className="page">
        <SectionHeader title={t("calendar.title")} subtitle={t("calendar.subtitle")} />

        <div className="metric-grid">
          <MetricCard
            icon="calendar"
            label={t("calendar.metric.calendars")}
            value={toPersianDigits(calendars.length)}
          />
          <MetricCard
            icon="sun"
            tone="purple"
            label={t("calendar.metric.holidays")}
            value={toPersianDigits(holidays.length)}
          />
          <MetricCard
            icon="clock"
            tone="green"
            label={t("calendar.metric.capacity")}
            value={toPersianDigits(weeklyCapacity)}
          />
          <MetricCard
            icon="warning"
            tone={plan && plan.summary.overloadedDays > 0 ? "amber" : "blue"}
            label={t("calendar.metric.overloaded")}
            value={toPersianDigits(plan?.summary.overloadedDays ?? 0)}
          />
        </div>

        {calendars.length > 1 && (
          <Card className="content-card" padding="sm">
            <SelectInput
              label={t("calendar.field.site")}
              value={selected?.id ?? ""}
              onChange={(event) => setSelectedId(event.target.value)}
              options={calendars.map((calendar) => ({
                value: calendar.id,
                label: calendar.locationPath
                  ? `${calendar.name} — ${calendar.locationPath}`
                  : calendar.name,
              }))}
            />
          </Card>
        )}

        <div className="segmented-control">
          {TAB_KEYS.map((key) => (
            <button
              key={key}
              type="button"
              className={tab === key ? "is-active" : ""}
              onClick={() => setTab(key)}
            >
              {taxonomyLabel(t, "calendar.tab.", key)}
            </button>
          ))}
        </div>

        {loading ? (
          <LoadingState label={t("calendar.title")} />
        ) : loadError ? (
          <ErrorState
            title={t("error.networkTitle")}
            description={loadError}
            retry={() => void loadCalendars()}
          />
        ) : tab === "calendars" ? (
          renderCalendars()
        ) : tab === "holidays" ? (
          renderHolidays()
        ) : tab === "shifts" ? (
          renderShifts()
        ) : (
          renderCapacity()
        )}

        <Modal
          open={calendarModal}
          title={t("calendar.add")}
          onClose={() => setCalendarModal(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setCalendarModal(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="primary"
                loading={busy}
                onClick={() =>
                  void runWrite(async () => {
                    await service.saveCalendar(calendarForm);
                    setCalendarModal(false);
                  }, t("calendar.saved"))
                }
              >
                {t("calendar.save")}
              </Button>
            </>
          }
        >
          <TextInput
            label={t("calendar.field.code")}
            value={calendarForm.code}
            onChange={(event) => setCalendarForm({ ...calendarForm, code: event.target.value })}
          />
          <TextInput
            label={t("calendar.field.name")}
            value={calendarForm.name}
            onChange={(event) => setCalendarForm({ ...calendarForm, name: event.target.value })}
          />
          <TextInput
            label={t("calendar.field.timezone")}
            value={calendarForm.timezone ?? ""}
            onChange={(event) =>
              setCalendarForm({ ...calendarForm, timezone: event.target.value })
            }
          />
          <SelectInput
            label={t("calendar.field.rollPolicy")}
            value={calendarForm.rollPolicy ?? "forward"}
            onChange={(event) =>
              setCalendarForm({ ...calendarForm, rollPolicy: event.target.value as RollPolicy })
            }
            options={ROLL_POLICIES.map((policy) => ({
              value: policy,
              label: taxonomyLabel(t, "calendar.roll.", policy),
            }))}
          />
          <fieldset className="wcal__weekend-picker">
            <legend>{t("calendar.field.weekend")}</legend>
            {WEEKDAY_ORDER_IR.map((py) => {
              const checked = (calendarForm.weekendDays ?? []).includes(py);
              return (
                <label key={py} className="checkbox-field">
                  <input
                    type="checkbox"
                    checked={checked}
                    onChange={() =>
                      setCalendarForm({
                        ...calendarForm,
                        weekendDays: checked
                          ? (calendarForm.weekendDays ?? []).filter((day) => day !== py)
                          : [...(calendarForm.weekendDays ?? []), py],
                      })
                    }
                  />
                  <span>{weekdayLabel(py)}</span>
                </label>
              );
            })}
          </fieldset>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={calendarForm.isDefault ?? false}
              onChange={(event) =>
                setCalendarForm({ ...calendarForm, isDefault: event.target.checked })
              }
            />
            <span>{t("calendar.field.isDefault")}</span>
          </label>
        </Modal>

        <Modal
          open={holidayModal}
          title={t("calendar.holiday.add")}
          onClose={() => setHolidayModal(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setHolidayModal(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="primary"
                loading={busy}
                onClick={() =>
                  void runWrite(async () => {
                    if (!selected) return;
                    await service.saveHoliday({ calendarId: selected.id, ...holidayForm });
                    setHolidayModal(false);
                  }, t("calendar.holiday.saved"))
                }
              >
                {t("common.save")}
              </Button>
            </>
          }
        >
          <TextInput
            label={t("calendar.holiday.date")}
            value={holidayForm.onDate}
            placeholder="2026-03-21"
            hint={holidayForm.onDate ? formatJalali(holidayForm.onDate) : undefined}
            onChange={(event) => setHolidayForm({ ...holidayForm, onDate: event.target.value })}
          />
          <TextInput
            label={t("calendar.holiday.name")}
            value={holidayForm.name}
            onChange={(event) => setHolidayForm({ ...holidayForm, name: event.target.value })}
          />
          <SelectInput
            label={t("calendar.holiday.kind")}
            value={holidayForm.kind}
            onChange={(event) =>
              setHolidayForm({ ...holidayForm, kind: event.target.value as HolidayKind })
            }
            options={HOLIDAY_KINDS.map((kind) => ({
              value: kind,
              label: taxonomyLabel(t, "calendar.holidayKind.", kind),
            }))}
          />
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={holidayForm.recursAnnually}
              onChange={(event) =>
                setHolidayForm({ ...holidayForm, recursAnnually: event.target.checked })
              }
            />
            <span>{t("calendar.holiday.recurs")}</span>
          </label>
        </Modal>

        <Modal
          open={shiftModal}
          title={t("calendar.shift.add")}
          onClose={() => setShiftModal(false)}
          footer={
            <>
              <Button variant="secondary" onClick={() => setShiftModal(false)}>
                {t("common.cancel")}
              </Button>
              <Button
                variant="primary"
                loading={busy}
                onClick={() =>
                  void runWrite(async () => {
                    if (!selected) return;
                    await service.saveShift({ calendarId: selected.id, ...shiftForm });
                    setShiftModal(false);
                  }, t("calendar.shift.saved"))
                }
              >
                {t("common.save")}
              </Button>
            </>
          }
        >
          <TextInput
            label={t("calendar.shift.code")}
            value={shiftForm.code}
            onChange={(event) => setShiftForm({ ...shiftForm, code: event.target.value })}
          />
          <TextInput
            label={t("calendar.shift.name")}
            value={shiftForm.name}
            onChange={(event) => setShiftForm({ ...shiftForm, name: event.target.value })}
          />
          <SelectInput
            label={t("calendar.shift.kind")}
            value={shiftForm.kind}
            onChange={(event) =>
              setShiftForm({ ...shiftForm, kind: event.target.value as ShiftKind })
            }
            options={SHIFT_KINDS.map((kind) => ({
              value: kind,
              label: taxonomyLabel(t, "calendar.shiftKind.", kind),
            }))}
          />
          <TextInput
            label={t("calendar.shift.start")}
            value={shiftForm.startTime}
            placeholder="06:00"
            onChange={(event) => setShiftForm({ ...shiftForm, startTime: event.target.value })}
          />
          <TextInput
            label={t("calendar.shift.end")}
            value={shiftForm.endTime}
            placeholder="14:00"
            onChange={(event) => setShiftForm({ ...shiftForm, endTime: event.target.value })}
          />
          <TextInput
            label={t("calendar.shift.headcount")}
            inputMode="numeric"
            value={String(shiftForm.headcount)}
            onChange={(event) =>
              setShiftForm({ ...shiftForm, headcount: Number(event.target.value) || 0 })
            }
          />
        </Modal>

        {toast && <Toast message={toast} tone={toastTone} onClose={() => setToast("")} />}
      </div>
    </PermissionGuard>
  );
}
