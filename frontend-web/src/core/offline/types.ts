/**
 * کار بدون اینترنت — انواع مشترک صف آفلاین.
 *
 * Every write a technician makes with no network becomes a `QueuedOperation`
 * in IndexedDB. The queue is the contract between "the tap happened" and
 * "the server knows": nothing in the UI may assume a mutation reached the
 * backend, and nothing in the queue may be replayed without an idempotency
 * key the server can recognise.
 */

/** Kinds the server's `/maintenance/sync` endpoint understands. */
export const SYNC_KINDS = [
  "workOrder.status",
  "workOrder.labour",
  "workOrder.partUsage",
  "workTimer.start",
  "workTimer.stop",
  "device.status",
  "meter.reading",
] as const;

export type SyncKind = (typeof SYNC_KINDS)[number];

/** Per-item verdict returned by the server. */
export type SyncStatus = "applied" | "duplicate" | "rejected" | "failed";

/** Local lifecycle of a queued item (never sent to the server). */
export type QueueState = "pending" | "syncing" | "rejected";

export interface QueuedOperation {
  /** Idempotency key minted on the device; the server dedupes on it. */
  clientRequestId: string;
  kind: SyncKind;
  payload: Record<string, unknown>;
  /** When the technician actually did it — not when it was synced. */
  occurredAt: string;
  /** Persian one-liner shown in the queue page. */
  label: string;
  state: QueueState;
  attempts: number;
  lastError: string;
  lastErrorCode: string;
  createdAt: string;
}

export interface SyncOperationResult {
  clientRequestId: string;
  kind: string;
  status: SyncStatus;
  resultId?: string;
  result?: Record<string, unknown>;
  errorCode?: string;
  errorMessage?: string;
}

export interface SyncOutcome {
  applied: number;
  duplicate: number;
  rejected: number;
  failed: number;
  /** Items the server refused permanently, kept locally so the user sees why. */
  rejectedItems: QueuedOperation[];
  /** True when the flush could not reach the server at all. */
  offline: boolean;
}

export interface CachedRead {
  key: string;
  payload: unknown;
  cachedAt: string;
}
