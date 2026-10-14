/**
 * The calendar and user dashboards of the maintenance-dashboard family
 * (v0.15.0). Presentational components only: the page owns the data and
 * the filter state, these two render it. No demo-mode flag in here — the
 * page passes everything through props, demo or live alike.
 */

import { useLocalization } from "../core/localization/localizationContext";
import {
  JALALI_MONTHS,
  JALALI_WEEKDAYS,
  formatJalali,
  isoToJalaliParts,
  toPersianDigits,
  todayIso,
} from "../core/localization/jalali";
import { taxonomyLabel } from "../core/localization/taxonomyLabel";
import type {
  MaintenanceDepartment,
  WorkOrder,
  WorkOrderStatus,
} from "../shared/types/domain";
import { Badge, Card, CardHeader } from "../shared/components/primitives";
import { Icon } from "../shared/components/Icon";

export type Translate = ReturnType<typeof useLocalization>["t"];

/** A Jalali month cursor: year + month (1..12). */
export interface DashCalMonth {
  year: number;
  month: number;
}

// Status colours for the calendar dots and the user-view rows.
export const STATUS_DOT_COLORS: Record<WorkOrderStatus, string> = {
  submitted: "#64748b",
  routed: "#8b5cf6",
  assigned: "#1f7ae0",
  inProgress: "#e6a23c",
  onHold: "#ef4444",
  pendingApproval: "#0ea5e9",
  completed: "#22c55e",
  cancelled: "#94a3b8",
};

export const currentDashMonth = (): DashCalMonth => {
  const parts = isoToJalaliParts(todayIso());
  return parts ? { year: parts[0], month: parts[1] } : { year: 1405, month: 7 };
};

export const stepDashMonth = (current: DashCalMonth, delta: number): DashCalMonth => {
  const next = current.month + delta;
  if (next < 1) return { year: current.year - 1, month: 12 };
  if (next > 12) return { year: current.year + 1, month: 1 };
  return { year: current.year, month: next };
};

/** Map JS weekday (Sun=0..Sat=6) onto the Persian week, which starts Saturday. */
export const persianDayIndex = (date: Date): number => (date.getDay() + 1) % 7;

export interface CalendarDashboardProps {
  month: DashCalMonth;
  onMonthChange: (next: DashCalMonth) => void;
  cells: Array<{ iso: string; day: number } | null>;
  ordersByDay: Map<string, WorkOrder[]>;
  monthOrders: WorkOrder[];
  deptCounts: Map<MaintenanceDepartment, number>;
  departments: MaintenanceDepartment[];
  deptFilter: Set<MaintenanceDepartment>;
  onToggleDept: (department: MaintenanceDepartment) => void;
  onClearDepts: () => void;
  selectedDay: string | null;
  onSelectDay: (iso: string | null) => void;
  todayIsoValue: string;
  t: Translate;
}

/**
 * داشبورد تقویم — a Jalali month grid of the requests, with the
 * department filter rail beside it. In RTL the rail is the first grid
 * column, so it sits on the RIGHT of the calendar, exactly as asked.
 */
export function CalendarDashboard(props: CalendarDashboardProps): JSX.Element {
  const { t } = props;
  const monthLabel = `${JALALI_MONTHS[props.month.month - 1]} ${toPersianDigits(props.month.year)}`;
  const allCount = [...props.deptCounts.values()].reduce((sum, value) => sum + value, 0);
  const dayOrders = props.selectedDay ? props.ordersByDay.get(props.selectedDay) ?? [] : [];
  return (
    <div className="dash-cal">
      <Card className="dash-cal__rail" padding="sm">
        <div className="dash-cal__rail-head">
          <Icon name="building" size={15} />
          <span>{t("cmms.dash.cal.departments")}</span>
        </div>
        <button
          type="button"
          className={`dash-cal__chip${props.deptFilter.size === 0 ? " is-active" : ""}`}
          aria-pressed={props.deptFilter.size === 0}
          onClick={props.onClearDepts}
        >
          <span>{t("cmms.dash.cal.all")}</span>
          <strong>{toPersianDigits(String(allCount))}</strong>
        </button>
        {props.departments.map((department) => {
          const count = props.deptCounts.get(department) ?? 0;
          const active = props.deptFilter.has(department);
          return (
            <button
              key={department}
              type="button"
              className={`dash-cal__chip${active ? " is-active" : ""}`}
              aria-pressed={active}
              onClick={() => props.onToggleDept(department)}
            >
              <span>{taxonomyLabel(t, "cmms.department.", department)}</span>
              <strong>{toPersianDigits(String(count))}</strong>
            </button>
          );
        })}
        <p className="dash-cal__rail-note">{t("cmms.dash.cal.railNote")}</p>
      </Card>

      <div className="dash-cal__main">
        <div className="dash-cal__toolbar">
          <button
            type="button"
            className="icon-button icon-button--sm"
            aria-label={t("cmms.dash.cal.prevMonth")}
            onClick={() => props.onMonthChange(stepDashMonth(props.month, -1))}
          >
            <Icon name="chevronRight" size={16} />
          </button>
          <strong className="dash-cal__month">{monthLabel}</strong>
          <button
            type="button"
            className="icon-button icon-button--sm"
            aria-label={t("cmms.dash.cal.nextMonth")}
            onClick={() => props.onMonthChange(stepDashMonth(props.month, 1))}
          >
            <Icon name="chevronLeft" size={16} />
          </button>
          <span className="dash-cal__count">
            {t("cmms.dash.cal.monthCount")}: {toPersianDigits(String(props.monthOrders.length))}
          </span>
          <button
            type="button"
            className="button button--sm"
            onClick={() => {
              props.onMonthChange(currentDashMonth());
              props.onSelectDay(null);
            }}
          >
            {t("cmms.dash.cal.today")}
          </button>
        </div>

        <div className="dash-cal__grid" role="grid" aria-label={monthLabel}>
          {JALALI_WEEKDAYS.map((weekday) => (
            <div key={weekday} className="dash-cal__weekday">
              {weekday}
            </div>
          ))}
          {props.cells.map((cell, index) => {
            if (cell === null) {
              return <div key={`blank-${index}`} className="dash-cal__cell dash-cal__cell--blank" />;
            }
            const items = props.ordersByDay.get(cell.iso) ?? [];
            const isSelected = cell.iso === props.selectedDay;
            const clickable = items.length > 0;
            return (
              <div
                key={cell.iso}
                className={[
                  "dash-cal__cell",
                  index % 7 === 6 ? "dash-cal__cell--fri" : "",
                  cell.iso === props.todayIsoValue ? "dash-cal__cell--today" : "",
                  isSelected ? "dash-cal__cell--selected" : "",
                  clickable ? "is-clickable" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
                role={clickable ? "button" : undefined}
                tabIndex={clickable ? 0 : undefined}
                aria-label={`${toPersianDigits(cell.day)} ${monthLabel}`}
                onClick={() => props.onSelectDay(isSelected ? null : cell.iso)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" || event.key === " ") {
                    event.preventDefault();
                    props.onSelectDay(isSelected ? null : cell.iso);
                  }
                }}
              >
                <span className="dash-cal__day">{toPersianDigits(cell.day)}</span>
                {items.length > 0 && (
                  <span className="dash-cal__badge">{toPersianDigits(String(items.length))}</span>
                )}
                <span className="dash-cal__dots">
                  {items.slice(0, 4).map((order) => (
                    <i
                      key={order.id}
                      className="dash-cal__dot"
                      style={{ background: STATUS_DOT_COLORS[order.status] }}
                      title={order.title}
                    />
                  ))}
                </span>
              </div>
            );
          })}
        </div>

        {props.monthOrders.length === 0 ? (
          <p className="dash-cal__empty">{t("cmms.dash.cal.emptyMonth")}</p>
        ) : null}

        {props.selectedDay ? (
          <Card className="dash-cal__day" padding="sm">
            <div className="dash-cal__day-head">
              <strong>{t("cmms.dash.cal.dayTitle", { date: formatJalali(props.selectedDay) })}</strong>
              <button type="button" className="dash-cal__day-close" onClick={() => props.onSelectDay(null)}>
                {t("cmms.dash.cal.close")}
              </button>
            </div>
            {dayOrders.length === 0 ? (
              <p className="dash-cal__empty">{t("cmms.dash.cal.dayEmpty")}</p>
            ) : (
              <ul className="dash-cal__day-list">
                {dayOrders.map((order) => (
                  <li key={order.id}>
                    <span className="dash-cal__day-title">
                      <i className="dash-cal__dot" style={{ background: STATUS_DOT_COLORS[order.status] }} />
                      {order.title}
                    </span>
                    <span className="dash-cal__day-meta">
                      <Badge tone="neutral">{taxonomyLabel(t, "cmms.department.", order.department)}</Badge>
                      <Badge tone="info">{t(`cmms.woStatus.${order.status}`)}</Badge>
                      <Badge tone="warning">{t(`cmms.priority.${order.priority}`)}</Badge>
                    </span>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        ) : null}
      </div>
    </div>
  );
}

export interface UserDashboardProps {
  userName: string;
  stats: {
    assignedTotal: number;
    assignedOpen: number;
    assignedInProgress: number;
    assignedCompleted: number;
    requestedTotal: number;
    requestedOpen: number;
  };
  orders: WorkOrder[];
  requests: WorkOrder[];
  /** Demo-only: colleagues whose desk the preview may show. Empty in live mode. */
  candidates: string[];
  viewAs: string | null;
  onViewAs: (name: string | null) => void;
  t: Translate;
}

/** داشبورد کاربری — the signed-in user's own desk. */
export function UserDashboard(props: UserDashboardProps): JSX.Element {
  const { t } = props;
  const row = (order: WorkOrder): JSX.Element => (
    <li key={order.id} className="dash-user__row">
      <span className="dash-user__title">
        <i className="dash-cal__dot" style={{ background: STATUS_DOT_COLORS[order.status] }} />
        {order.title}
      </span>
      <span className="dash-user__meta">
        <Badge tone="neutral">{taxonomyLabel(t, "cmms.department.", order.department)}</Badge>
        <Badge tone="info">{t(`cmms.woStatus.${order.status}`)}</Badge>
        <span className="dash-user__date">{formatJalali(order.createdAt)}</span>
      </span>
    </li>
  );
  return (
    <div className="dash-user">
      <Card className="dash-user__head" padding="sm">
        <span className="dash-user__avatar">
          <Icon name="users" size={18} />
        </span>
        <div className="dash-user__greeting">
          <strong>{t("cmms.dash.user.greeting", { name: props.userName || "—" })}</strong>
          <span>{t("cmms.dash.user.caption")}</span>
        </div>
        {props.candidates.length > 0 && (
          <label className="dash-user__viewas">
            {t("cmms.dash.user.viewAs")}
            <select
              value={props.viewAs ?? props.userName}
              onChange={(event) => props.onViewAs(event.target.value)}
            >
              {props.candidates.map((name) => (
                <option key={name} value={name}>
                  {name}
                </option>
              ))}
            </select>
          </label>
        )}
      </Card>

      <div className="dash-user__stats">
        <div>
          <span>{t("cmms.dash.user.assignedOpen")}</span>
          <strong>{toPersianDigits(String(props.stats.assignedOpen))}</strong>
        </div>
        <div>
          <span>{t("cmms.dash.user.assignedInProgress")}</span>
          <strong>{toPersianDigits(String(props.stats.assignedInProgress))}</strong>
        </div>
        <div>
          <span>{t("cmms.dash.user.assignedCompleted")}</span>
          <strong>{toPersianDigits(String(props.stats.assignedCompleted))}</strong>
        </div>
        <div>
          <span>{t("cmms.dash.user.requestedTotal")}</span>
          <strong>{toPersianDigits(String(props.stats.requestedTotal))}</strong>
        </div>
      </div>

      <div className="duo-grid">
        <Card padding="sm">
          <CardHeader title={t("cmms.dash.user.assigned")} icon="checkSquare" />
          {props.orders.length === 0 ? (
            <p className="dash-cal__empty">{t("cmms.dash.user.empty")}</p>
          ) : (
            <ul className="dash-user__list">{props.orders.map(row)}</ul>
          )}
        </Card>
        <Card padding="sm">
          <CardHeader title={t("cmms.dash.user.requested")} icon="file" />
          {props.requests.length === 0 ? (
            <p className="dash-cal__empty">{t("cmms.dash.user.empty")}</p>
          ) : (
            <ul className="dash-user__list">{props.requests.map(row)}</ul>
          )}
        </Card>
      </div>
    </div>
  );
}
