import { NavLink } from "react-router-dom";
import { faText as t } from "../../core/localization/i18n";
import { useOptionalOffline } from "../../core/offline/offlineContext";
import { Icon } from "./Icon";
import { formatNumber } from "../../core/localization/format";

/**
 * نشانگر اتصال و صف — the one always-visible truth about connectivity.
 *
 * It is deliberately a link to the queue page, not a decoration: when a
 * technician sees «۳ در انتظار» the next question is always "which three?".
 *
 * It renders nothing when everything is normal (online, empty queue) so the
 * toolbar stays quiet; a permanent green dot teaches people to ignore it,
 * and then they ignore the red one too.
 */
export function OfflineIndicator(): JSX.Element | null {
  const offline = useOptionalOffline();
  if (!offline) return null;

  const { isOnline, pendingCount, rejectedCount, isSyncing } = offline;
  if (isOnline && pendingCount === 0 && rejectedCount === 0) return null;

  const tone = !isOnline ? "offline" : rejectedCount > 0 ? "warn" : "pending";
  const label = !isOnline
    ? t("offline.offline")
    : isSyncing
      ? t("offline.syncing")
      : t("offline.pending", { count: formatNumber(pendingCount, "fa") });

  return (
    <NavLink
      to="/app/maintenance/offline-queue"
      className={`offline-indicator offline-indicator--${tone}`}
      aria-label={`${label}${pendingCount ? ` — ${pendingCount}` : ""}`}
      title={t("offline.queueTitle")}
    >
      <Icon name={!isOnline ? "cloud" : isSyncing ? "refresh" : "upload"} size={16} />
      <span>{label}</span>
      {pendingCount > 0 && <strong>{formatNumber(pendingCount, "fa")}</strong>}
    </NavLink>
  );
}
