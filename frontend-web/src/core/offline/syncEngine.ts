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
 * | `failed`    | transient (server/db hiccup)              | keep as `pending` |
 *
 * `rejected` is the only state that survives a flush as a user-visible
 * problem; `failed` just waits for the next attempt. Items missing from the
 * response are treated as `failed`, never as applied — losing a technician's
 * work to an optimistic assumption is unacceptable.
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
  failed: 0,
  rejectedItems: [],
  offline,
});

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
    const pending = this.queue.pending();
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
        // decided, so everything goes back to pending untouched.
        await Promise.all(
          wave.map((item) =>
            this.queue.update(item.clientRequestId, {
              state: "pending",
              lastError: error instanceof Error ? error.message : String(error),
            }),
          ),
        );
        total.offline = true;
        total.failed += wave.length;
        return total;
      }
      const byId = new Map(results.map((row) => [row.clientRequestId, row]));
      for (const item of wave) {
        const verdict = byId.get(item.clientRequestId);
        if (!verdict) {
          await this.queue.update(item.clientRequestId, {
            state: "pending",
            attempts: item.attempts + 1,
            lastError: "پاسخی برای این مورد دریافت نشد.",
          });
          total.failed += 1;
          continue;
        }
        if (verdict.status === "applied" || verdict.status === "duplicate") {
          await this.queue.remove(item.clientRequestId);
          total[verdict.status] += 1;
          continue;
        }
        if (verdict.status === "rejected") {
          const parked: QueuedOperation = {
            ...item,
            state: "rejected",
            attempts: item.attempts + 1,
            lastError: verdict.errorMessage ?? "",
            lastErrorCode: verdict.errorCode ?? "",
          };
          await this.queue.update(item.clientRequestId, parked);
          total.rejected += 1;
          total.rejectedItems.push(parked);
          continue;
        }
        await this.queue.update(item.clientRequestId, {
          state: "pending",
          attempts: item.attempts + 1,
          lastError: verdict.errorMessage ?? "",
          lastErrorCode: verdict.errorCode ?? "",
        });
        total.failed += 1;
      }
    }
    await this.queue.setMeta(LAST_SYNC_META_KEY, new Date().toISOString());
    return total;
  }
}
