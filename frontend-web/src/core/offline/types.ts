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
export type SyncStatus =
  | "applied"
  | "duplicate"
  | "rejected"
  | "conflict"
  | "failed";

/** Local lifecycle of a queued item (never sent to the server). */
export type QueueState = "pending" | "syncing" | "rejected" | "conflict";

/**
 * Parked = the server has spoken and no retry will help. Both states stay in
 * the list so the technician can read why; neither is ever re-sent.
 */
export const isParked = (item: { state: QueueState }): boolean =>
  item.state === "rejected" || item.state === "conflict";

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
  /**
   * Earliest moment this item may be retried (ISO). Set after a transient
   * failure so a broken item cannot spin against the server on every
   * reconnect, which on a phone means a flat battery.
   */
  nextAttemptAt?: string;
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
  /** Someone changed the same record while this device was away. */
  conflict: number;
  failed: number;
  /** Items the server refused permanently, kept locally so the user sees why. */
  rejectedItems: QueuedOperation[];
  /** True when the flush could not reach the server at all. */
  offline: boolean;
  /** The session expired mid-flush: nothing was lost, but a login is needed. */
  authRequired: boolean;
}

export interface CachedRead {
  key: string;
  payload: unknown;
  cachedAt: string;
}
