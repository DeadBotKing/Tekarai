import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useApiClient } from "../../core/api/apiContext";
import { faText as t } from "../../core/localization/i18n";
import { useOptionalOffline } from "../../core/offline/offlineContext";
import { isConnectivityFailure } from "../../core/offline/offlineActions";
import { Badge, Button, TextInput } from "../../shared/components/primitives";
import { Icon } from "../../shared/components/Icon";
import { createFieldOpsService, type WorkTimer } from "./fieldOpsService";

/**
 * تایمر کار — start/stop a stopwatch on a work order.
 *
 * Why a timer at all: the labour form asks for *hours*, and a technician
 * who finishes at 16:40 writes "2" because nobody remembers they started at
 * 14:05. The stopwatch records `startedAt`/`endedAt` on the server and the
 * labour entry is derived from them, so the number is observed instead of
 * recalled.
 *
 * Three behaviours are load-bearing:
 *
 * * **The elapsed display is computed from `startedAt`, never accumulated.**
 *   A counter incremented by `setInterval` drifts, and stops dead when the
 *   phone sleeps in a pocket — exactly when the timer is running.
 * * **Start and stop work offline.** Both are queued with the real wall
 *   clock, so the recorded span is when the work happened, not when the
 *   signal came back.
 * * **A queued timer is shown as running locally** (optimistic state) so the
 *   technician is not left wondering whether the tap registered.
 */

const two = (value: number): string => String(value).padStart(2, "0");

/** 7384 → «۰۲:۰۳:۰۴» in Persian digits, because this is read at a glance. */
export function formatElapsed(totalSeconds: number): string {
  const safe = Math.max(0, Math.floor(totalSeconds));
  const hours = Math.floor(safe / 3600);
  const minutes = Math.floor((safe % 3600) / 60);
  const seconds = safe % 60;
  const latin = `${two(hours)}:${two(minutes)}:${two(seconds)}`;
  return latin.replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[Number(digit)]);
}

const shortTime = (iso: string): string => {
  if (!iso) return "—";
  const moment = new Date(iso);
  if (Number.isNaN(moment.getTime())) return "—";
  return new Intl.DateTimeFormat("fa-IR", {
    hour: "2-digit",
    minute: "2-digit",
    month: "2-digit",
    day: "2-digit",
  }).format(moment);
};

export interface WorkTimerPanelProps {
  workOrderId: string;
  technicianName: string;
  /** Called after a stop lands so the page can refresh labour/cost totals. */
  onLabourRecorded?: () => void;
  onToast?: (message: string) => void;
}

export function WorkTimerPanel({
  workOrderId,
  technicianName,
  onLabourRecorded,
  onToast,
}: WorkTimerPanelProps): JSX.Element {
  const api = useApiClient();
  const offline = useOptionalOffline();
  const service = useMemo(() => createFieldOpsService(api), [api]);
  const [timers, setTimers] = useState<WorkTimer[]>([]);
  const [note, setNote] = useState("");
  const [pausedMinutes, setPausedMinutes] = useState("0");
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);
  const [tick, setTick] = useState(0);
  /** Set when a start was queued offline and the server has not confirmed. */
  const [queuedStartAt, setQueuedStartAt] = useState("");
  const mounted = useRef(true);

  useEffect(() => {
    mounted.current = true;
    return () => {
      mounted.current = false;
    };
  }, []);

  const technician = technicianName.trim();

  const load = useCallback(async (): Promise<void> => {
    if (!workOrderId) return;
    try {
      const rows = await service.listTimers(workOrderId);
      if (mounted.current) setTimers(rows);
    } catch {
      // Offline or forbidden: keep whatever we last knew rather than
      // flashing an empty panel.
    }
  }, [service, workOrderId]);

  useEffect(() => {
    void load();
  }, [load]);

  const running = useMemo(
    () => timers.find((timer) => timer.running && (!technician || timer.technicianName === technician)),
    [technician, timers],
  );
  const isRunning = Boolean(running) || Boolean(queuedStartAt);
  const startedAt = running?.startedAt ?? queuedStartAt;

  // One ticker, only while something is running.
  useEffect(() => {
    if (!isRunning) return undefined;
    const handle = window.setInterval(() => setTick((value) => value + 1), 1000);
    return () => window.clearInterval(handle);
  }, [isRunning]);

  const elapsedSeconds = useMemo(() => {
    void tick;
    if (!startedAt) return 0;
    const began = new Date(startedAt).getTime();
    if (Number.isNaN(began)) return 0;
    return Math.max(0, Math.round((Date.now() - began) / 1000));
  }, [startedAt, tick]);

  const start = async (): Promise<void> => {
    if (!technician) {
      setError(t("timer.failed"));
      return;
    }
    setBusy(true);
    setError("");
    const startedNow = new Date().toISOString();
    try {
      const timer = await service.startTimer({
        workOrderId,
        technicianName: technician,
        startedAt: startedNow,
        note,
        startedVia: "manual",
      });
      setTimers((current) => [timer, ...current]);
      setQueuedStartAt("");
      setNote("");
      onToast?.(t("timer.started"));
    } catch (caught) {
      if (offline && isConnectivityFailure(caught)) {
        await offline.enqueue({
          kind: "workTimer.start",
          payload: {
            workOrderId,
            technicianName: technician,
            startedAt: startedNow,
            note,
            startedVia: "offline",
          },
          occurredAt: startedNow,
          label: `${t("timer.start")} — ${technician}`,
        });
        setQueuedStartAt(startedNow);
        onToast?.(t("timer.queuedStart"));
      } else {
        setError(caught instanceof Error ? caught.message : t("timer.failed"));
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const stop = async (): Promise<void> => {
    setBusy(true);
    setError("");
    const endedNow = new Date().toISOString();
    const pausedSeconds = Math.max(0, Math.round(Number(pausedMinutes) || 0) * 60);
    try {
      const stopped = await service.stopTimer({
        workOrderId,
        technicianName: technician,
        endedAt: endedNow,
        note,
        pausedSeconds,
      });
      setQueuedStartAt("");
      setNote("");
      setPausedMinutes("0");
      await load();
      onLabourRecorded?.();
      onToast?.(
        t("timer.stopped", {
          hours: stopped.hours.toLocaleString("fa-IR", { maximumFractionDigits: 2 }),
        }),
      );
    } catch (caught) {
      if (offline && isConnectivityFailure(caught)) {
        await offline.enqueue({
          kind: "workTimer.stop",
          payload: {
            workOrderId,
            technicianName: technician,
            endedAt: endedNow,
            note,
            pausedSeconds: String(pausedSeconds),
          },
          occurredAt: endedNow,
          label: `${t("timer.stop")} — ${technician}`,
        });
        setQueuedStartAt("");
        onToast?.(t("timer.queuedStop"));
      } else {
        setError(caught instanceof Error ? caught.message : t("timer.failed"));
      }
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const cancel = async (): Promise<void> => {
    if (!running) return;
    if (!window.confirm(t("timer.cancelConfirm"))) return;
    setBusy(true);
    try {
      await service.cancelTimer(running.id);
      await load();
      onToast?.(t("timer.cancelled"));
    } catch (caught) {
      setError(caught instanceof Error ? caught.message : t("timer.failed"));
    } finally {
      if (mounted.current) setBusy(false);
    }
  };

  const finished = timers.filter((timer) => !timer.running);

  return (
    <div className="work-timer" dir="rtl">
      <div className="work-timer__head">
        <h4 className="cmms-timeline__title">
          <Icon name="clock" /> {t("timer.title")}
        </h4>
        {isRunning ? (
          <Badge tone="success" dot>
            {t("timer.running")}
          </Badge>
        ) : (
          <span className="muted-cell">{t("timer.hint")}</span>
        )}
      </div>

      <div className={`work-timer__clock ${isRunning ? "work-timer__clock--live" : ""}`}>
        <strong dir="ltr">{formatElapsed(elapsedSeconds)}</strong>
        {startedAt && (
          <span className="muted-cell">
            {t("timer.startedAt")}: {shortTime(startedAt)}
          </span>
        )}
        {queuedStartAt && <Badge tone="warning">{t("timer.capturedOffline")}</Badge>}
      </div>

      <div className="work-timer__controls">
        {!isRunning ? (
          <Button variant="primary" onClick={() => void start()} disabled={busy || !technician}>
            <Icon name="activity" /> {t("timer.start")}
          </Button>
        ) : (
          <>
            <Button variant="primary" onClick={() => void stop()} disabled={busy}>
              <Icon name="checkCircle" /> {t("timer.stop")}
            </Button>
            {running && (
              <Button variant="ghost" size="sm" onClick={() => void cancel()} disabled={busy}>
                {t("timer.cancel")}
              </Button>
            )}
          </>
        )}
      </div>

      <div className="form-grid form-grid--compact">
        <TextInput
          label={t("timer.note")}
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />
        {isRunning && (
          <TextInput
            label={t("timer.pausedSeconds")}
            type="number"
            min="0"
            step="5"
            value={pausedMinutes}
            onChange={(event) => setPausedMinutes(event.target.value)}
          />
        )}
      </div>

      {error && <p className="form-error">{error}</p>}

      <div className="work-timer__history">
        <span className="muted-cell">{t("timer.history")}</span>
        {finished.length === 0 ? (
          <p className="detail-panel__description">{t("timer.none")}</p>
        ) : (
          <ul className="work-timer__list">
            {finished.map((timer) => (
              <li key={timer.id}>
                <strong>{timer.technicianName}</strong>
                <span dir="ltr">
                  {shortTime(timer.startedAt)} → {shortTime(timer.endedAt)}
                </span>
                <Badge tone="info">
                  {timer.billableHours.toLocaleString("fa-IR", { maximumFractionDigits: 2 })}{" "}
                  {t("timer.billable")}
                </Badge>
                {timer.capturedOffline && (
                  <Badge tone="warning">{t("timer.capturedOffline")}</Badge>
                )}
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
