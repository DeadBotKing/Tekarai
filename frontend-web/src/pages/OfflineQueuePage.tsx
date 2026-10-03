import { useCallback, useEffect, useMemo, useState } from "react";
import { useApiClient } from "../core/api/apiContext";
import { faText as t } from "../core/localization/i18n";
import { useOffline } from "../core/offline/offlineContext";
import type { QueuedOperation } from "../core/offline/types";
import {
  createFieldOpsService,
  type SyncLedgerEntry,
} from "../features/maintenance/fieldOpsService";
import { Icon } from "../shared/components/Icon";
import { Toast } from "../shared/components/overlays";
import {
  Badge,
  Button,
  Card,
  EmptyState,
  SectionHeader,
} from "../shared/components/primitives";

/**
 * صفحه‌ی صف آفلاین — everything the device still owes the server.
 *
 * This page exists because an invisible queue is a liability: the technician
 * must be able to answer "did my work save?" without calling the office. It
 * shows three things, in order of how much they need attention:
 *
 * 1. **ردشده** — the server refused it. Nothing will fix this by itself, so
 *    the reason is printed verbatim and the only choices are retry or
 *    discard.
 * 2. **در انتظار** — not sent yet. Normal when offline.
 * 3. **تاریخچه** — what the server recorded from this tenant's devices,
 *    fetched live. It is the independent confirmation that a replay landed.
 */

const kindLabel = (kind: string): string => {
  switch (kind) {
    case "workOrder.status":
      return t("offline.kind.workOrder.status");
    case "workOrder.labour":
      return t("offline.kind.workOrder.labour");
    case "workOrder.partUsage":
      return t("offline.kind.workOrder.partUsage");
    case "workTimer.start":
      return t("offline.kind.workTimer.start");
    case "workTimer.stop":
      return t("offline.kind.workTimer.stop");
    case "device.status":
      return t("offline.kind.device.status");
    case "meter.reading":
      return t("offline.kind.meter.reading");
    default:
      return kind;
  }
};

const statusLabel = (status: string): string => {
  switch (status) {
    case "pending":
      return t("offline.status.pending");
    case "syncing":
      return t("offline.status.syncing");
    case "rejected":
      return t("offline.status.rejected");
    case "applied":
      return t("offline.status.applied");
    case "duplicate":
      return t("offline.status.duplicate");
    case "failed":
      return t("offline.status.failed");
    default:
      return status;
  }
};

const statusTone = (
  status: string,
): "neutral" | "success" | "warning" | "danger" | "info" => {
  switch (status) {
    case "applied":
      return "success";
    case "duplicate":
      return "info";
    case "rejected":
      return "danger";
    case "failed":
      return "warning";
    default:
      return "neutral";
  }
};

const moment = (iso: string): string => {
  if (!iso) return "—";
  const value = new Date(iso);
  if (Number.isNaN(value.getTime())) return "—";
  return new Intl.DateTimeFormat("fa-IR", {
    dateStyle: "short",
    timeStyle: "short",
  }).format(value);
};

function OperationRow({
  operation,
  onRetry,
  onDiscard,
}: {
  operation: QueuedOperation;
  onRetry: (id: string) => void;
  onDiscard: (id: string) => void;
}): JSX.Element {
  return (
    <li className="offline-queue__row">
      <div className="offline-queue__row-main">
        <strong>{operation.label || kindLabel(operation.kind)}</strong>
        <span className="muted-cell">{kindLabel(operation.kind)}</span>
      </div>
      <div className="offline-queue__row-meta">
        <span className="muted-cell">
          {t("offline.capturedAt")}: {moment(operation.occurredAt)}
        </span>
        {operation.attempts > 0 && (
          <span className="muted-cell">
            {t("offline.attempts")}: {operation.attempts.toLocaleString("fa-IR")}
          </span>
        )}
        <Badge tone={statusTone(operation.state)}>{statusLabel(operation.state)}</Badge>
      </div>
      {operation.lastError && (
        <p className="offline-queue__error">
          {operation.lastErrorCode && <code dir="ltr">{operation.lastErrorCode}</code>}{" "}
          {operation.lastError}
        </p>
      )}
      <div className="offline-queue__row-actions">
        <Button size="sm" variant="secondary" onClick={() => onRetry(operation.clientRequestId)}>
          {t("offline.retry")}
        </Button>
        <Button size="sm" variant="ghost" onClick={() => onDiscard(operation.clientRequestId)}>
          {t("offline.discard")}
        </Button>
      </div>
    </li>
  );
}

export function OfflineQueuePage(): JSX.Element {
  const api = useApiClient();
  const {
    operations,
    isOnline,
    isSyncing,
    lastSyncAt,
    flush,
    discard,
    retry,
    clearRejected,
  } = useOffline();
  const service = useMemo(() => createFieldOpsService(api), [api]);
  const [history, setHistory] = useState<SyncLedgerEntry[]>([]);
  const [toast, setToast] = useState("");

  const pending = operations.filter((item) => item.state !== "rejected");
  const rejected = operations.filter((item) => item.state === "rejected");

  const loadHistory = useCallback(async (): Promise<void> => {
    try {
      setHistory(await service.syncHistory(50));
    } catch {
      setHistory([]);
    }
  }, [service]);

  useEffect(() => {
    void loadHistory();
  }, [loadHistory]);

  const syncNow = async (): Promise<void> => {
    const outcome = await flush();
    setToast(
      outcome.offline
        ? t("offline.syncOffline")
        : t("offline.syncResult", {
            applied: outcome.applied.toLocaleString("fa-IR"),
            duplicate: outcome.duplicate.toLocaleString("fa-IR"),
            rejected: outcome.rejected.toLocaleString("fa-IR"),
            failed: outcome.failed.toLocaleString("fa-IR"),
          }),
    );
    await loadHistory();
  };

  const handleDiscard = (clientRequestId: string): void => {
    if (!window.confirm(t("offline.discardConfirm"))) return;
    void discard(clientRequestId);
  };

  return (
    <div className="page" dir="rtl">
      <SectionHeader
        title={t("offline.queueTitle")}
        subtitle={t("offline.queueSubtitle")}
        actions={
          <>
            <Badge tone={isOnline ? "success" : "warning"} dot>
              {isOnline ? t("offline.online") : t("offline.offline")}
            </Badge>
            <Button
              variant="primary"
              icon="refresh"
              loading={isSyncing}
              disabled={pending.length === 0}
              onClick={() => void syncNow()}
            >
              {t("offline.syncNow")}
            </Button>
          </>
        }
      />

      <Card padding="md">
        <div className="detail-stats">
          <div>
            <span>{t("offline.pendingSection")}</span>
            <strong>{pending.length.toLocaleString("fa-IR")}</strong>
          </div>
          <div>
            <span>{t("offline.rejectedSection")}</span>
            <strong>{rejected.length.toLocaleString("fa-IR")}</strong>
          </div>
          <div>
            <span>{t("offline.lastSync")}</span>
            <strong>{lastSyncAt ? moment(lastSyncAt) : t("offline.never")}</strong>
          </div>
        </div>
      </Card>

      {rejected.length > 0 && (
        <Card padding="md">
          <div className="offline-queue__head">
            <h3>
              <Icon name="warning" /> {t("offline.rejectedSection")}
            </h3>
            <Button size="sm" variant="ghost" onClick={() => void clearRejected()}>
              {t("offline.clearRejected")}
            </Button>
          </div>
          <ul className="offline-queue__list">
            {rejected.map((operation) => (
              <OperationRow
                key={operation.clientRequestId}
                operation={operation}
                onRetry={(id) => void retry(id)}
                onDiscard={handleDiscard}
              />
            ))}
          </ul>
        </Card>
      )}

      <Card padding="md">
        <div className="offline-queue__head">
          <h3>
            <Icon name="upload" /> {t("offline.pendingSection")}
          </h3>
        </div>
        {pending.length === 0 ? (
          <EmptyState icon="checkCircle" title={t("offline.empty")} />
        ) : (
          <ul className="offline-queue__list">
            {pending.map((operation) => (
              <OperationRow
                key={operation.clientRequestId}
                operation={operation}
                onRetry={(id) => void retry(id)}
                onDiscard={handleDiscard}
              />
            ))}
          </ul>
        )}
      </Card>

      <Card padding="md">
        <div className="offline-queue__head">
          <h3>
            <Icon name="activity" /> {t("offline.historySection")}
          </h3>
        </div>
        {history.length === 0 ? (
          <p className="detail-panel__description">{t("offline.empty")}</p>
        ) : (
          <ul className="offline-queue__list offline-queue__list--compact">
            {history.map((entry) => (
              <li key={`${entry.clientRequestId}-${entry.receivedAt}`}>
                <Badge tone={statusTone(entry.status)}>{statusLabel(entry.status)}</Badge>
                <span>{kindLabel(entry.kind)}</span>
                <span className="muted-cell">{moment(entry.receivedAt)}</span>
                {entry.errorMessage && (
                  <span className="offline-queue__error">{entry.errorMessage}</span>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Toast message={toast} onClose={() => setToast("")} />
    </div>
  );
}

export default OfflineQueuePage;
