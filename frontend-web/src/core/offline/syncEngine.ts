/**
 * موتور همگام‌سازی — replay the queue, then act on each verdict.
 *
 * The engine owns exactly one decision per item: **keep it or drop it.**
 *
 * | verdict     | meaning                                   | queue action      |
 * |-------------|-------------------------------------------|-------------------|
 * | `applied`   | the server performed it                   | delete            |
 * | `duplicate` | the server already had it (replay)        | delete            |
 * | `rejected`  | permanently refused — bad data, no rights | park as `rejected`|
 * | `conflict`  | the record changed while we were away     | park as `conflict`|
 * | `failed`    | transient (server/db hiccup)              | keep as `pending` |
 *
 * `rejected` and `conflict` survive a flush as user-visible problems;
 * `failed` just waits for the next attempt, behind a growing delay so a
 * permanently broken item cannot hammer the server (or the battery) on every
 * reconnect. After `MAX_ATTEMPTS` it is parked rather than retried forever.
 * Items missing from the response are treated as `failed`, never as applied —
 * losing a technician's work to an optimistic assumption is unacceptable.
 *
 * An expired session stops the flush outright: the queue is left exactly as
 * it was and `authRequired` tells the UI to ask for a login instead of
 * burning attempts on requests that cannot succeed.
 *
 * A flush is single-flight: the second caller gets the first caller's promise
 * instead of a second batch with the same ids.
 */

import type { OfflineQueue } from "./queue";
import type { QueuedOperation, SyncOperationResult, SyncOutcome } from "./types";

export const LAST_SYNC_META_KEY = "lastSyncAt";

export interface SyncTransport {
  pushSync(
    operations: QueuedOperation[],
    deviceLabel: string,
  ): Promise<SyncOperationResult[]>;
}

const emptyOutcome = (offline: boolean): SyncOutcome => ({
  applied: 0,
  duplicate: 0,
  rejected: 0,
  conflict: 0,
  failed: 0,
  rejectedItems: [],
  offline,
  authRequired: false,
});

/** Give up auto-retrying after this many server-side failures. */
export const MAX_ATTEMPTS = 8;

/** 30s, 1m, 2m, 4m … capped at 30 minutes. */
export function retryDelayMs(attempts: number): number {
  const base = 30_000 * 2 ** Math.max(0, attempts - 1);
  return Math.min(base, 30 * 60_000);
}

const isAuthFailure = (error: unknown): boolean => {
  const status = (error as { status?: number } | null)?.status;
  return status === 401 || status === 403;
};

/** The server caps a batch at 200; stay under it and flush in waves. */
export const SYNC_BATCH_SIZE = 50;

export function describeDevice(): string {
  if (typeof navigator === "undefined") return "tekarai-web";
  const agent = navigator.userAgent ?? "";
  const platform = /Android/i.test(agent)
    ? "Android"
    : /iPhone|iPad|iPod/i.test(agent)
      ? "iOS"
      : /Windows/i.test(agent)
        ? "Windows"
        : /Mac/i.test(agent)
          ? "macOS"
          : "web";
  return `tekarai-web/${platform}`;
}

export class SyncEngine {
  private readonly queue: OfflineQueue;
  private readonly transport: SyncTransport;
  private inFlight: Promise<SyncOutcome> | null = null;

  constructor(queue: OfflineQueue, transport: SyncTransport) {
    this.queue = queue;
    this.transport = transport;
  }

  get isRunning(): boolean {
    return this.inFlight !== null;
  }

  flush(): Promise<SyncOutcome> {
    if (this.inFlight) return this.inFlight;
    const run = this.runFlush().finally(() => {
      this.inFlight = null;
    });
    this.inFlight = run;
    return run;
  }

  private async runFlush(): Promise<SyncOutcome> {
    const now = Date.now();
    const pending = this.queue
      .pending()
      .filter((item) => !item.nextAttemptAt || Date.parse(item.nextAttemptAt) <= now);
    if (pending.length === 0) return emptyOutcome(false);

    const total = emptyOutcome(false);
    for (let index = 0; index < pending.length; index += SYNC_BATCH_SIZE) {
      const wave = pending.slice(index, index + SYNC_BATCH_SIZE);
      await Promise.all(
        wave.map((item) => this.queue.update(item.clientRequestId, { state: "syncing" })),
      );
      let results: SyncOperationResult[];
      try {
        results = await this.transport.pushSync(wave, describeDevice());
      } catch (error) {
        // Network down, token expired, server unreachable: nothing was
        // decided, so everything goes back to pending untouched. Attempts are
        // deliberately *not* incremented — the item never reached the server.
        await Promise.all(
          wave.map((item) =>
            this.queue.update(item.clientRequestId, {
              state: "pending",
              lastError: error instanceof Error ? error.message : String(error),
            }),
          ),
        );
        if (isAuthFailure(error)) {
          total.authRequired = true;
        } else {
          total.offline = true;
        }
        total.failed += wave.length;
        return total;
      }
      const byId = new Map(results.map((row) => [row.clientRequestId, row]));
      for (const item of wave) {
        const verdict = byId.get(item.clientRequestId);
        if (!verdict) {
          await this.deferOrPark(item, "پاسخی برای این مورد دریافت نشد.", "");
          total.failed += 1;
          continue;
        }
        if (verdict.status === "applied" || verdict.status === "duplicate") {
          await this.queue.remove(item.clientRequestId);
          total[verdict.status] += 1;
          continue;
        }
        if (verdict.status === "rejected" || verdict.status === "conflict") {
          const parked: QueuedOperation = {
            ...item,
            state: verdict.status,
            attempts: item.attempts + 1,
            lastError: verdict.errorMessage ?? "",
            lastErrorCode: verdict.errorCode ?? "",
          };
          await this.queue.update(item.clientRequestId, parked);
          total[verdict.status] += 1;
          total.rejectedItems.push(parked);
          continue;
        }
        await this.deferOrPark(
          item,
          verdict.errorMessage ?? "",
          verdict.errorCode ?? "",
        );
        total.failed += 1;
      }
    }
    await this.queue.setMeta(LAST_SYNC_META_KEY, new Date().toISOString());
    return total;
  }

  /**
   * A transient failure: wait longer before the next try, and stop trying
   * altogether once the item has proved itself hopeless. Parking beats an
   * infinite loop — the technician can see it and decide.
   */
  private async deferOrPark(
    item: QueuedOperation,
    message: string,
    code: string,
  ): Promise<void> {
    const attempts = item.attempts + 1;
    if (attempts >= MAX_ATTEMPTS) {
      await this.queue.update(item.clientRequestId, {
        state: "rejected",
        attempts,
        lastError: message || "پس از چند تلاش ناموفق متوقف شد.",
        lastErrorCode: code,
      });
      return;
    }
    await this.queue.update(item.clientRequestId, {
      state: "pending",
      attempts,
      lastError: message,
      lastErrorCode: code,
      nextAttemptAt: new Date(Date.now() + retryDelayMs(attempts)).toISOString(),
    });
  }
}
