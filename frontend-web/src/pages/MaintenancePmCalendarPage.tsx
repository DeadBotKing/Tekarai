import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createRegistryService } from "../features/maintenance/registryService";
import { createDemoRegistryService } from "../features/maintenance/registryDemoData";
import { rowsToCsvBlob, triggerDownload } from "../core/files/downloadUtils";
import { MAINTENANCE_DEPARTMENTS, type PmScheduleItem } from "../shared/types/domain";
import { Modal, Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  MetricCard,
  LoadingState,
  SectionHeader,
  SelectInput,
} from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";
import {
  JALALI_MONTHS,
  JALALI_WEEKDAYS,
  isoToJalaliParts,
  jalaliMonthLength,
  jalaliPartsToIso,
  toPersianDigits,
  formatJalali,
  todayIso,
} from "../core/localization/jalali";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import { createWorkCalendarService } from "../features/maintenance/workCalendarService";
import { createDemoWorkCalendarService } from "../features/maintenance/workCalendarDemoData";
import { isWeekendDay } from "../features/maintenance/workCalendarMath";
import { mergeOptions } from "../features/maintenance/optionCatalog";

interface JalaliMonth {
  year: number;
  month: number; // 1..12
}

const MAX_CHIPS_PER_CELL = 3;

/** Map JS weekday (Sun=0..Sat=6) onto the Persian week, which starts Saturday. */
const persianDayIndex = (date: Date): number => (date.getDay() + 1) % 7;

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

export function MaintenancePmCalendarPage(): JSX.Element {
  const { t } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const registry = useMemo(
    () => (runtimeConfig.demoMode ? createDemoRegistryService() : createRegistryService(api)),
    [api],
  );
  const workCalendar = useMemo(
    () => (runtimeConfig.demoMode ? createDemoWorkCalendarService() : createWorkCalendarService(api)),
    [api],
  );

  const [month, setMonth] = useState<JalaliMonth>(currentJalaliMonth);
  const [items, setItems] = useState<PmScheduleItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [toast, setToast] = useState("");
  const [disciplineFilter, setDisciplineFilter] = useState("");
  const [dayModal, setDayModal] = useState<{ iso: string; items: PmScheduleItem[] } | null>(null);
  const [downloading, setDownloading] = useState(false);
  /**
   * Days the plant is shut, as `iso -> label` ("" for an ordinary weekend).
   *
   * Phase 28 added a real work calendar; this grid predates it and used to
   * assume جمعه was the only closed day. Shading is read-only and additive:
   * if the calendar cannot be loaded the map stays empty and the page behaves
   * exactly as it did before.
   */
  const [closedDays, setClosedDays] = useState<Map<string, string>>(new Map());

  const downloadExport = async (format: "csv" | "xlsx" | "pdf"): Promise<void> => {
    setDownloading(true);
    try {
      const query = {
        fromDate: monthStartIso,
        toDate: monthEndIso,
        discipline: disciplineFilter || undefined,
      };
      const usedFormat = runtimeConfig.demoMode ? "csv" : format;
      const blob = runtimeConfig.demoMode
        ? rowsToCsvBlob([
            ["دستگاه", "عنوان PM", "موعد", "وضعیت"],
            ...items.map((item) => [
              `${item.deviceCode} — ${item.deviceName}`.trim(),
              item.title,
              item.dueOn || "بدون تاریخ",
              item.overdue ? "عقب‌افتاده" : "در برنامه",
            ]),
          ])
        : await registry.downloadPmScheduleExport(format, query);
      const stem = JALALI_MONTHS[month.month - 1];
      triggerDownload(blob, `pm-schedule-${stem}-${month.year}.${usedFormat}`);
      setToast(t("cmms.export.ready"));
    } catch {
      setToast(t("cmms.export.failed"));
    } finally {
      setDownloading(false);
    }
  };

  const monthStartIso = jalaliPartsToIso(month.year, month.month, 1);
  const monthLength = jalaliMonthLength(month.year, month.month);
  const monthEndIso = jalaliPartsToIso(month.year, month.month, monthLength);

  const refresh = useCallback(async (): Promise<void> => {
    setLoading(true);
    try {
      setItems(
        await registry.getPmSchedule({
          fromDate: monthStartIso,
          toDate: monthEndIso,
          discipline: disciplineFilter || undefined,
        }),
      );
    } catch {
      setToast(t("cmms.pmCal.loadFailed"));
    } finally {
      setLoading(false);
    }
  }, [registry, monthStartIso, monthEndIso, disciplineFilter, t]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  useEffect(() => {
    const controller = new AbortController();
    const run = async (): Promise<void> => {
      try {
        const calendars = await workCalendar.listCalendars(controller.signal);
        const active = calendars.find((row) => row.isDefault) ?? calendars[0];
        if (!active) return;
        const holidays = await workCalendar.listHolidays(
          { calendarId: active.id, fromDate: monthStartIso, toDate: monthEndIso },
          controller.signal,
        );
        const shape = { weekendDays: active.weekendDays, holidays: new Set<string>() };
        const closed = new Map<string, string>();
        for (let day = 1; day <= monthLength; day += 1) {
          const iso = jalaliPartsToIso(month.year, month.month, day);
          if (isWeekendDay(shape, iso)) closed.set(iso, "");
        }
        for (const holiday of holidays) closed.set(holiday.onDate, holiday.name);
        setClosedDays(closed);
      } catch {
        // A calendar is an enhancement here, not a dependency — stay quiet.
        setClosedDays(new Map());
      }
    };
    void run();
    return () => controller.abort();
  }, [workCalendar, month.year, month.month, monthLength, monthStartIso, monthEndIso]);

  const today = todayIso();

  const datedItems = useMemo(() => items.filter((item) => item.dueOn), [items]);
  const undatedItems = useMemo(() => items.filter((item) => !item.dueOn), [items]);
  const overdueCount = items.filter((item) => item.overdue).length;
  const upcomingCount = datedItems.filter((item) => !item.overdue).length;

  const itemsByDay = useMemo(() => {
    const grouped = new Map<string, PmScheduleItem[]>();
    for (const item of datedItems) {
      const dayItems = grouped.get(item.dueOn) ?? [];
      dayItems.push(item);
      grouped.set(item.dueOn, dayItems);
    }
    return grouped;
  }, [datedItems]);

  const cells = useMemo(() => {
    const leading = persianDayIndex(new Date(`${monthStartIso}T00:00:00`));
    const grid: Array<{ iso: string; day: number } | null> = [];
    for (let index = 0; index < leading; index += 1) grid.push(null);
    for (let day = 1; day <= monthLength; day += 1) {
      grid.push({ iso: jalaliPartsToIso(month.year, month.month, day), day });
    }
    while (grid.length % 7 !== 0) grid.push(null);
    return grid;
  }, [month.year, month.month, monthLength, monthStartIso]);

  const chipClass = (item: PmScheduleItem): string => {
    if (item.overdue) return "pm-cal__event pm-cal__event--overdue";
    if (item.dueOn === today) return "pm-cal__event pm-cal__event--today";
    return "pm-cal__event";
  };

  const openDay = (iso: string): void => {
    const dayItems = itemsByDay.get(iso) ?? [];
    if (dayItems.length === 0) return;
    setDayModal({ iso, items: dayItems });
  };

  return (
    <div className="page">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={t("cmms.pmCal.title")}
        subtitle={t("cmms.pmCal.subtitle")}
        actions={
          <div className="cmms-header-actions">
            <Button variant="ghost" icon="table" disabled={downloading} onClick={() => void downloadExport("xlsx")}>
              {t("cmms.export.excel")}
            </Button>
            <Button variant="ghost" icon="download" disabled={downloading} onClick={() => void downloadExport("pdf")}>
              {t("cmms.export.pdf")}
            </Button>
            <Button variant="secondary" icon="chevronLeft" onClick={() => setMonth(stepMonth(month, -1))}>
              {t("cmms.pmCal.prevMonth")}
            </Button>
            <Button variant="secondary" icon="calendar" onClick={() => setMonth(currentJalaliMonth())}>
              {t("cmms.pmCal.today")}
            </Button>
            <Button variant="secondary" icon="chevronRight" onClick={() => setMonth(stepMonth(month, 1))}>
              {t("cmms.pmCal.nextMonth")}
            </Button>
          </div>
        }
      />

      <div className="metric-grid">
        <MetricCard label={t("cmms.pmCal.overdue")} value={overdueCount} icon="warning" tone={overdueCount > 0 ? "amber" : "green"} />
        <MetricCard label={t("cmms.pmCal.thisMonth")} value={upcomingCount} icon="calendar" tone="blue" />
        <MetricCard label={t("cmms.pmCal.undated")} value={undatedItems.length} icon="clock" tone={undatedItems.length > 0 ? "amber" : "green"} />
      </div>

      <Card className="content-card" padding="md">
        <div className="pm-cal__toolbar">
          <h2 className="pm-cal__month-title">
            <Icon name="calendar" size={20} />
            {JALALI_MONTHS[month.month - 1]}
            <span className="pm-cal__year">{toPersianDigits(month.year)}</span>
          </h2>
          <SelectInput
            aria-label={t("cmms.pmCal.filterDiscipline")}
            value={disciplineFilter}
            onChange={(event) => setDisciplineFilter(event.target.value)}
            options={[
              { value: "", label: t("cmms.department.allUnits") },
              ...mergeOptions({
                canonical: MAINTENANCE_DEPARTMENTS,
                translate: (department) => taxonomyLabel(t, "cmms.department.", department),
                catalogKey: "device.department",
                current: disciplineFilter,
              }),
            ]}
          />
          <div className="pm-cal__legend">
            <span><b className="pm-cal__dot pm-cal__dot--overdue" /> {t("cmms.pmCal.overdue")}</span>
            <span><b className="pm-cal__dot pm-cal__dot--today" /> {t("cmms.pmCal.today")}</span>
            <span><b className="pm-cal__dot" /> PM پیشِ‌رو</span>
          </div>
        </div>

        {loading ? (
          <LoadingState label={t("cmms.common.loading")} />
        ) : (
          <div className="pm-cal__grid" role="grid" aria-label={`${JALALI_MONTHS[month.month - 1]} ${toPersianDigits(month.year)}`}>
            {JALALI_WEEKDAYS.map((weekday) => (
              <div key={weekday} className="pm-cal__weekday">
                {weekday}
              </div>
            ))}
            {cells.map((cell, index) => {
              if (cell === null) {
                return <div key={`blank-${index}`} className="pm-cal__cell pm-cal__cell--blank" />;
              }
              const dayItems = itemsByDay.get(cell.iso) ?? [];
              const overflow = dayItems.length - MAX_CHIPS_PER_CELL;
              const hasOverdue = dayItems.some((item) => item.overdue);
              return (
                <div
                  key={cell.iso}
                  className={[
                    "pm-cal__cell",
                    index % 7 === 6 ? "pm-cal__cell--fri" : "",
                    closedDays.has(cell.iso) ? "pm-cal__cell--closed" : "",
                    cell.iso === today ? "pm-cal__cell--today" : "",
                    hasOverdue ? "pm-cal__cell--has-overdue" : "",
                    dayItems.length > 0 ? "is-clickable" : "",
                  ].filter(Boolean).join(" ")}
                  onClick={() => openDay(cell.iso)}
                  role={dayItems.length > 0 ? "button" : undefined}
                  tabIndex={dayItems.length > 0 ? 0 : undefined}
                  onKeyDown={(event) => {
                    if (event.key === "Enter" || event.key === " ") {
                      event.preventDefault();
                      openDay(cell.iso);
                    }
                  }}
                >
                  <span className="pm-cal__day">{toPersianDigits(cell.day)}</span>
                  {closedDays.get(cell.iso) && (
                    <span className="pm-cal__holiday" title={closedDays.get(cell.iso)}>
                      {closedDays.get(cell.iso)}
                    </span>
                  )}
                  {closedDays.has(cell.iso) && dayItems.length > 0 && (
                    <span className="pm-cal__conflict" title={t("cmms.pmCal.closedConflictHint")}>
                      <Icon name="warning" size={11} /> {t("cmms.pmCal.closedConflict")}
                    </span>
                  )}
                  <div className="pm-cal__events">
                    {dayItems.slice(0, MAX_CHIPS_PER_CELL).map((item) => (
                      <span key={item.id} className={chipClass(item)} title={`${item.deviceCode} — ${item.title}`}>
                        {item.deviceCode} · {item.title}
                      </span>
                    ))}
                    {overflow > 0 && (
                      <span className="pm-cal__more">
                        +{toPersianDigits(overflow)} {t("cmms.pmCal.more")}
                      </span>
                    )}
                  </div>
                </div>
              );
            })}
          </div>
        )}

        {!loading && datedItems.length === 0 && (
          <p className="pm-cal__empty">{t("cmms.pmCal.empty")}</p>
        )}
      </Card>

      {undatedItems.length > 0 && (
        <Card className="content-card" padding="md">
          <h3 className="pm-cal__undated-title">
            <Icon name="clock" size={17} /> {t("cmms.pmCal.undated")} ({toPersianDigits(undatedItems.length)})
          </h3>
          <div className="pm-cal__undated-strip">
            {undatedItems.map((item) => (
              <button
                key={item.id}
                type="button"
                className="pm-cal__undated-chip"
                onClick={() => navigate(`/app/maintenance/devices/${item.deviceId}/profile`)}
              >
                <strong>{item.deviceCode}</strong>
                <span>{item.title}</span>
                <Badge tone="neutral">{taxonomyLabel(t, "cmms.department.", item.discipline)}</Badge>
              </button>
            ))}
          </div>
        </Card>
      )}

      <Modal
        open={dayModal !== null}
        title={dayModal ? `PM — ${formatJalali(dayModal.iso)}` : ""}
        onClose={() => setDayModal(null)}
        footer={
          <Button variant="secondary" onClick={() => setDayModal(null)}>
            {t("cmms.common.close")}
          </Button>
        }
      >
        {dayModal?.items.map((item) => (
          <div key={item.id} className="pm-cal__day-item">
            <div className="pm-cal__day-item-head">
              <strong>{item.deviceCode} — {item.deviceName}</strong>
              {item.overdue ? (
                <Badge tone="danger">{t("cmms.pmCal.overdue")}</Badge>
              ) : (
                <Badge tone={item.source === "plan" ? "info" : "neutral"}>
                  {item.source === "plan" ? t("cmms.pmCal.legendPlan") : t("cmms.pmCal.legendDevice")}
                </Badge>
              )}
            </div>
            <p>{item.title} · {taxonomyLabel(t, "cmms.department.", item.discipline)}</p>
            {(item.responsibleName || item.estimatedMinutes > 0) && (
              <p className="pm-cal__day-item-meta">
                {item.responsibleName && `${t("cmms.pmCal.responsible")}: ${item.responsibleName}`}
                {item.estimatedMinutes > 0 && ` · ${toPersianDigits(item.estimatedMinutes)} ${t("cmms.pmCal.minutes")}`}
              </p>
            )}
            <Button
              variant="ghost"
              size="sm"
              icon="arrowRight"
              onClick={() => navigate(`/app/maintenance/devices/${item.deviceId}/profile`)}
            >
              {t("cmms.pmCal.openDevice")}
            </Button>
          </div>
        ))}
      </Modal>

      {toast && <Toast message={toast} onClose={() => setToast("")} />}
    </div>
  );
}
