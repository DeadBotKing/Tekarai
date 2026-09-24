import { useCallback, useEffect, useMemo, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { useApiClient } from "../core/api/apiContext";
import { useLocalization } from "../core/localization/localizationContext";
import { createMaintenanceService } from "../features/maintenance/maintenanceService";
import type { DeviceTimeline, DeviceTimelineItem } from "../shared/types/domain";
import { Badge, Button, Card, SectionHeader } from "../shared/components/primitives";
import { Icon, type IconName } from "../shared/components/Icon";

const formatDateTime = (value: string, locale: string): string => {
  if (!value) return "";
  const time = new Date(value).getTime();
  if (Number.isNaN(time)) return value;
  return new Intl.DateTimeFormat(locale, { dateStyle: "medium", timeStyle: "short" }).format(
    new Date(time),
  );
};

const ACTION_ICON: Record<DeviceTimelineItem["action"], IconName> = {
  registered: "plus",
  updated: "edit",
  statusChanged: "refresh",
  pmCompleted: "checkCircle",
  workOrderRaised: "filePlus",
  workOrderClosed: "check",
};

const ACTION_TONE: Record<
  DeviceTimelineItem["action"],
  "neutral" | "success" | "warning" | "danger" | "info" | "purple"
> = {
  registered: "info",
  updated: "neutral",
  statusChanged: "warning",
  pmCompleted: "success",
  workOrderRaised: "purple",
  workOrderClosed: "success",
};

export function DeviceTimelinePage(): JSX.Element {
  const { t, locale } = useLocalization();
  const navigate = useNavigate();
  const api = useApiClient();
  const service = useMemo(() => createMaintenanceService(api), [api]);
  const { deviceId = "" } = useParams<{ deviceId: string }>();

  const [timeline, setTimeline] = useState<DeviceTimeline | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const load = useCallback(
    async (signal?: AbortSignal): Promise<void> => {
      if (!deviceId) return;
      setLoading(true);
      setError("");
      try {
        const result = await service.getDeviceTimeline(deviceId, signal);
        setTimeline(result);
      } catch (err) {
        setError(err instanceof Error ? err.message : t("cmms.timeline.loadFailed"));
      } finally {
        setLoading(false);
      }
    },
    [deviceId, service, t],
  );

  useEffect(() => {
    const controller = new AbortController();
    void load(controller.signal);
    return () => controller.abort();
  }, [load]);

  const describe = (item: DeviceTimelineItem): string => {
    switch (item.action) {
      case "statusChanged":
        return t("cmms.timeline.desc.statusChanged")
          .replace("{from}", statusLabel(item.fromStatus))
          .replace("{to}", statusLabel(item.toStatus));
      case "pmCompleted":
        return t("cmms.timeline.desc.pmCompleted").replace(
          "{date}",
          item.note || t("cmms.common.none"),
        );
      case "workOrderRaised":
        return t("cmms.timeline.desc.workOrderRaised").replace(
          "{title}",
          item.workOrderTitle || item.note || t("cmms.common.none"),
        );
      case "workOrderClosed":
        return t("cmms.timeline.desc.workOrderClosed").replace(
          "{title}",
          item.workOrderTitle || item.note || t("cmms.common.none"),
        );
      case "updated":
        return t("cmms.timeline.desc.updated");
      case "registered":
      default:
        return t("cmms.timeline.desc.registered");
    }
  };

  const statusLabel = (status: string): string =>
    status ? t(`cmms.status.${status}` as never) : t("cmms.common.none");

  const device = timeline?.device ?? null;
  const items = timeline?.items ?? [];

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        eyebrow={t("nav.maintenance")}
        title={
          device ? `${t("cmms.timeline.title")} — ${device.name}` : t("cmms.timeline.title")
        }
        subtitle={t("cmms.timeline.subtitle")}
        actions={
          <div className="section-actions">
            <Button variant="ghost" icon="arrowRight" onClick={() => navigate(-1)}>
              {t("cmms.common.back")}
            </Button>
            {device && (
              <Button
                variant="secondary"
                icon="chart"
                onClick={() =>
                  navigate(`/app/maintenance/devices/${device.id}/report`)
                }
              >
                {t("cmms.timeline.viewReport")}
              </Button>
            )}
          </div>
        }
      />

      {loading && <p className="detail-panel__description">{t("cmms.common.loading")}</p>}
      {error && !loading && <p className="detail-panel__description">{error}</p>}

      {device && !loading && (
        <>
          <Card className="content-card" padding="md">
            <h3 className="cmms-report__section-title">{t("cmms.timeline.deviceInfo")}</h3>
            <div className="detail-stats">
              <div>
                <span>{t("cmms.device.code")}</span>
                <strong>{device.code}</strong>
              </div>
              <div>
                <span>{t("cmms.device.name")}</span>
                <strong>{device.name}</strong>
              </div>
              <div>
                <span>{t("cmms.device.location")}</span>
                <strong>{device.location || t("cmms.common.none")}</strong>
              </div>
              <div>
                <span>{t("cmms.device.department")}</span>
                <strong>{t(`cmms.department.${device.department}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.device.status")}</span>
                <strong>{t(`cmms.status.${device.status}`)}</strong>
              </div>
              <div>
                <span>{t("cmms.device.nextPm")}</span>
                <strong>{device.nextDueDate || t("cmms.common.none")}</strong>
              </div>
            </div>
          </Card>

          <Card className="content-card" padding="md">
            <div className="cmms-timeline__head">
              <h3 className="cmms-report__section-title">{t("cmms.timeline.title")}</h3>
              <Badge tone="info">
                {t("cmms.timeline.count").replace("{count}", String(items.length))}
              </Badge>
            </div>

            {items.length === 0 ? (
              <p className="detail-panel__description">{t("cmms.timeline.empty")}</p>
            ) : (
              <ol className="cmms-timeline">
                {items.map((item) => (
                  <li className="cmms-timeline__item" key={item.id}>
                    <span
                      className={`cmms-timeline__marker cmms-timeline__marker--${ACTION_TONE[item.action]}`}
                      aria-hidden="true"
                    >
                      <Icon name={ACTION_ICON[item.action]} size={16} />
                    </span>
                    <div className="cmms-timeline__body">
                      <div className="cmms-timeline__row">
                        <strong className="cmms-timeline__title">
                          {t(`cmms.timeline.action.${item.action}` as never)}
                        </strong>
                        <time className="cmms-timeline__time">
                          {formatDateTime(item.at, locale)}
                        </time>
                      </div>
                      <p className="cmms-timeline__desc">{describe(item)}</p>
                      <div className="cmms-timeline__meta">
                        {item.actorName && (
                          <span className="cmms-timeline__actor">
                            {t("cmms.timeline.by").replace("{actor}", item.actorName)}
                          </span>
                        )}
                        {item.source === "workOrder" && item.priority && (
                          <Badge
                            tone={
                              item.priority === "critical"
                                ? "danger"
                                : item.priority === "high"
                                  ? "warning"
                                  : "neutral"
                            }
                          >
                            {t(`cmms.priority.${item.priority}` as never)}
                          </Badge>
                        )}
                        {item.source === "workOrder" && item.orderType && (
                          <Badge tone="neutral">
                            {t(`cmms.type.${item.orderType}` as never)}
                          </Badge>
                        )}
                        {item.source === "workOrder" && item.workOrderId && (
                          <Button
                            variant="ghost"
                            icon="external"
                            onClick={() =>
                              navigate(`/app/maintenance/work-orders?highlight=${item.workOrderId}`)
                            }
                          >
                            {t("cmms.timeline.openWorkOrder")}
                          </Button>
                        )}
                      </div>
                    </div>
                  </li>
                ))}
              </ol>
            )}
          </Card>
        </>
      )}
    </div>
  );
}
