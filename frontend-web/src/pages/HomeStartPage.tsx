import { useEffect, useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useAuth } from "../core/auth/authContext";
import { formatJalali, toPersianDigits } from "../core/localization/jalali";
import { useLocalization } from "../core/localization/localizationContext";
import type { TranslationKey } from "../core/localization/i18n";
import { PERMISSIONS } from "../core/permissions/permissionContext";
import { runtimeConfig } from "../app/configuration/runtimeConfig";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import { demoDevices, demoWorkOrders } from "../features/maintenance/maintenanceDemoData";
import { persianDayIndex } from "./maintenanceDashboardViews";
import { Icon, type IconName } from "../shared/components/Icon";
import { Badge, Card, CardHeader, PermissionGuard, SectionHeader } from "../shared/components/primitives";
import type { MaintenanceDevice, WorkOrder } from "../shared/types/domain";

/**
 * The simple home page (v0.17.0) — the first screen a newcomer sees.
 *
 * The old home was an analyst's dashboard: project pulse, task throughput,
 * health scores. Useful later, bewildering on day one. A first-time user
 * needs three questions answered: what can I do here, how do I start, and
 * is anything burning today. This page answers exactly those, in plain
 * language, with big targets. The full analytics view moved to
 * /app/overview («داشبورد پروژه‌ها») for the people who want it.
 */

interface HomeData {
  orders: WorkOrder[];
  devices: MaintenanceDevice[];
}

// Full weekday names — JALALI_WEEKDAYS carries the one-letter column
// headers calendars use, not names you would say out loud.
const WEEKDAY_NAMES = ["شنبه", "یکشنبه", "دوشنبه", "سه‌شنبه", "چهارشنبه", "پنجشنبه", "جمعه"];

const isOpenOrder = (order: WorkOrder): boolean =>
  order.status !== "completed" && order.status !== "cancelled";

const priorityRank: Record<WorkOrder["priority"], number> = {
  critical: 0,
  high: 1,
  normal: 2,
  low: 3,
};

const statusTone = (status: WorkOrder["status"]): "success" | "info" | "warning" | "danger" | "neutral" | "purple" =>
  status === "completed" ? "success" : status === "inProgress" ? "info" : status === "onHold" ? "warning" : status === "cancelled" ? "danger" : status === "assigned" ? "purple" : "neutral";

interface QuickAction {
  id: string;
  icon: IconName;
  titleKey: "home.action.wo" | "home.action.myWork" | "home.action.calendar" | "home.action.devices";
  captionKey:
    | "home.action.woCaption"
    | "home.action.myWorkCaption"
    | "home.action.calendarCaption"
    | "home.action.devicesCaption";
  path: string;
  permission: string;
}

const QUICK_ACTIONS: QuickAction[] = [
  {
    id: "wo",
    icon: "plus",
    titleKey: "home.action.wo",
    captionKey: "home.action.woCaption",
    path: "/app/maintenance/work-orders?create=1",
    permission: PERMISSIONS.maintenanceWorkOrderList,
  },
  {
    id: "myWork",
    icon: "checkSquare",
    titleKey: "home.action.myWork",
    captionKey: "home.action.myWorkCaption",
    path: "/app/maintenance/dashboard/user",
    permission: PERMISSIONS.maintenanceWorkOrderList,
  },
  {
    id: "calendar",
    icon: "calendar",
    titleKey: "home.action.calendar",
    captionKey: "home.action.calendarCaption",
    path: "/app/maintenance/dashboard/calendar",
    permission: PERMISSIONS.maintenanceWorkOrderList,
  },
  {
    id: "devices",
    icon: "cpu",
    titleKey: "home.action.devices",
    captionKey: "home.action.devicesCaption",
    path: "/app/maintenance/registry",
    permission: PERMISSIONS.maintenanceDeviceList,
  },
];

export function HomeStartPage(): JSX.Element {
  const { t, locale } = useLocalization();
  const api = useApiClient();
  const { session } = useAuth();
  const navigate = useNavigate();
  // Demo fixtures vs. the live API — picked once, in one place.
  const demo = runtimeConfig.demoMode;
  const maintenance = useMemo(() => createMaintenanceService(api), [api]);
  const [data, setData] = useState<HomeData>(() =>
    demo ? { orders: demoWorkOrders, devices: demoDevices } : { orders: [], devices: [] },
  );

  useEffect(() => {
    if (demo) return;
    let cancelled = false;
    void (async () => {
      // The home page must never greet a newcomer with an error card: if
      // the backend hiccups, the strip just shows zeroes.
      const [orders, devices] = await Promise.allSettled([
        maintenance.listWorkOrders(),
        maintenance.listDevices(),
      ]);
      if (cancelled) return;
      setData({
        orders: orders.status === "fulfilled" ? orders.value : [],
        devices: devices.status === "fulfilled" ? devices.value : [],
      });
    })();
    return () => {
      cancelled = true;
    };
  }, [demo, maintenance]);

  const firstName = (session?.user.displayName ?? "").split(" ").slice(0, 1).join(" ") || t("home.friend");
  const today = new Date();
  const dateLine =
    locale === "fa"
      ? `${WEEKDAY_NAMES[persianDayIndex(today)]} ${formatJalali(today, { style: "long" })}`
      : today.toLocaleDateString("en-US", { weekday: "long", month: "long", day: "numeric", year: "numeric" });

  const openOrders = data.orders.filter(isOpenOrder);
  const myName = session?.user.displayName ?? "";
  const myOpen = openOrders.filter(
    (order) => order.assignedToName === myName || order.assignedToUserId === session?.user.id,
  );

  const queue = [...openOrders].sort((a, b) => priorityRank[a.priority] - priorityRank[b.priority]).slice(0, 3);
  const attentionCount = openOrders.filter((order) => order.priority === "critical" || order.priority === "high").length;
  const attentionPercent = openOrders.length === 0 ? 0 : Math.max(12, Math.round((attentionCount / openOrders.length) * 100));

  const todayRows = [
    { id: "open", label: t("home.today.open"), value: openOrders.length, path: "/app/maintenance/work-orders" },
    { id: "mine", label: t("home.today.mine"), value: myOpen.length, path: "/app/maintenance/dashboard/user" },
    { id: "devices", label: t("home.today.devices"), value: data.devices.length, path: "/app/maintenance/registry" },
  ];

  const steps = [
    { id: "1", title: t("home.step1"), caption: t("home.step1Caption"), path: "/app/maintenance/work-orders?create=1" },
    { id: "2", title: t("home.step2"), caption: t("home.step2Caption"), path: "/app/maintenance/work-orders" },
    { id: "3", title: t("home.step3"), caption: t("home.step3Caption"), path: "/app/maintenance/dashboard" },
  ];

  return (
    <div className="page page--home">
      <SectionHeader
        eyebrow={t("nav.workspace")}
        title={t("home.greeting", { name: firstName })}
        subtitle={t("home.dateLine", { date: dateLine })}
      />

      <section className="home-cards" aria-labelledby="home-actions-title">
        <div className="home-section-head">
          <h2 id="home-actions-title">{t("home.quickTitle")}</h2>
          <p>{t("home.quickSubtitle")}</p>
        </div>
        <div className="home-cards__grid">
          {QUICK_ACTIONS.map((action) => (
            <PermissionGuard key={action.id} permission={action.permission}>
              <button type="button" className="home-card" onClick={() => navigate(action.path)}>
                <span className="home-card__icon">
                  <Icon name={action.icon} size={22} />
                </span>
                <strong>{t(action.titleKey)}</strong>
                <span>{t(action.captionKey)}</span>
              </button>
            </PermissionGuard>
          ))}
        </div>
      </section>

      <section className="home-focus" aria-labelledby="home-focus-title">
        <div className="home-section-head home-section-head--focus">
          <div>
            <h2 id="home-focus-title">{t("home.focusTitle")}</h2>
            <p>{t("home.focusSubtitle")}</p>
          </div>
          <button type="button" className="home-link-button" onClick={() => navigate("/app/maintenance/work-orders")}>
            {t("home.viewAll")}
            <Icon name="arrowLeft" size={14} />
          </button>
        </div>
        <div className="home-focus__grid">
          <Card className="home-queue" padding="none">
            <CardHeader
              title={t("home.queueTitle")}
              subtitle={t("home.queueSubtitle")}
              icon="archive"
            />
            {queue.length === 0 ? (
              <div className="home-queue__empty">
                <span><Icon name="checkCircle" size={21} /></span>
                <strong>{t("home.emptyQueue")}</strong>
              </div>
            ) : (
              <ul className="home-queue__list">
                {queue.map((order) => (
                  <li key={order.id}>
                    <button type="button" onClick={() => navigate(`/app/maintenance/work-orders?search=${encodeURIComponent(order.title)}`)}>
                      <span className={`home-queue__priority home-queue__priority--${order.priority}`} aria-hidden="true" />
                      <span className="home-queue__main">
                        <strong>{order.title}</strong>
                        <span>{order.assignedToName || t("home.unassigned")} · {formatJalali(order.createdAt, { style: "short" })}</span>
                      </span>
                      <Badge tone={statusTone(order.status)} dot>{t(`cmms.woStatus.${order.status}` as TranslationKey)}</Badge>
                      <Icon name="chevronLeft" size={15} className="home-queue__arrow" />
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </Card>
          <Card className="home-rhythm" padding="md">
            <div className="home-rhythm__eyebrow"><span><Icon name="activity" size={16} /></span>{t("home.rhythmTitle")}</div>
            <strong className="home-rhythm__value">{locale === "fa" ? toPersianDigits(openOrders.length) : openOrders.length}</strong>
            <span className="home-rhythm__label">{t("home.rhythmOpen")}</span>
            <p>{t("home.rhythmCaption", { count: attentionCount })}</p>
            <div className="home-rhythm__meter" role="progressbar" aria-valuenow={attentionPercent} aria-valuemin={0} aria-valuemax={100} aria-label={t("home.rhythmTitle")}>
              <span style={{ width: `${attentionPercent}%` }} />
            </div>
            <div className="home-rhythm__footer"><span>{t("home.rhythmAttention")}</span><strong>{locale === "fa" ? toPersianDigits(attentionCount) : attentionCount}</strong></div>
          </Card>
        </div>
      </section>

      <section className="home-steps" aria-labelledby="home-steps-title">
        <div className="home-section-head">
          <h2 id="home-steps-title">{t("home.stepsTitle")}</h2>
        </div>
        <ol className="home-steps__list">
          {steps.map((step) => (
            <li key={step.id}>
              <button type="button" onClick={() => navigate(step.path)}>
                <span className="home-steps__number">{step.id}</span>
                <span className="home-steps__body">
                  <strong>{step.title}</strong>
                  <span>{step.caption}</span>
                </span>
                <Icon name="arrowLeft" size={15} className="home-steps__arrow" />
              </button>
            </li>
          ))}
        </ol>
      </section>

      <section className="home-today" aria-labelledby="home-today-title">
        <div className="home-section-head">
          <h2 id="home-today-title">{t("home.todayTitle")}</h2>
        </div>
        <div className="home-today__grid">
          {todayRows.map((row) => (
            <button
              key={row.id}
              type="button"
              className="home-today__cell"
              onClick={() => navigate(row.path)}
            >
              <strong>{locale === "fa" ? toPersianDigits(row.value) : row.value}</strong>
              <span>{row.label}</span>
            </button>
          ))}
        </div>
      </section>

      <button type="button" className="home-overview-link" onClick={() => navigate("/app/overview")}>
        <Icon name="chart" size={15} />
        <span>{t("home.overviewLink")}</span>
        <Icon name="arrowLeft" size={14} />
      </button>
    </div>
  );
}
