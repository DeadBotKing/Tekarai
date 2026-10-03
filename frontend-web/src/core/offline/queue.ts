/**
 * صف عملیات آفلاین.
 *
 * Invariants this class exists to hold:
 *
 * 1. **An operation is written to storage before the UI claims success.**
 *    If the tab dies between the tap and the flush, the work is still there.
 * 2. **Order is preserved.** A "stop timer" replayed before its "start timer"
 *    would be rejected, so the queue is FIFO by `createdAt` and the flush
 *    sends one batch in that order.
 * 3. **`clientRequestId` is minted once, at capture time, and never
 *    regenerated.** Re-minting on retry is the classic way to turn an
 *    idempotent replay into a double charge.
 * 4. **Rejected items are kept, not deleted.** The technician must be able
 *    to see "this failed and why" — silently dropping their work is the one
 *    unforgivable bug in an offline system.
 */

import { CACHE_STORE, META_STORE, QUEUE_STORE, type KeyValueStore } from "./storage";
import { isParked } from "./types";
import type { CachedRead, QueuedOperation, SyncKind } from "./types";

export type QueueListener = (operations: QueuedOperation[]) => void;

const newId = (): string => {
  const cryptoApi = globalThis.crypto;
  if (cryptoApi && typeof cryptoApi.randomUUID === "function") return cryptoApi.randomUUID();
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 12)}`;
};

export interface EnqueueInput {
  kind: SyncKind;
  payload: Record<string, unknown>;
  label: string;
  occurredAt?: string;
  clientRequestId?: string;
}

export class OfflineQueue {
  private readonly store: KeyValueStore;
  private readonly listeners = new Set<QueueListener>();
  private cache: QueuedOperation[] = [];
  private loaded = false;

  constructor(store: KeyValueStore) {
    this.store = store;
  }

  async load(): Promise<QueuedOperation[]> {
    const rows = await this.store.getAll<QueuedOperation & { id?: string }>(QUEUE_STORE);
    this.cache = rows
      .map(({ id: _id, ...rest }) => rest as QueuedOperation)
      .sort((left, right) => left.createdAt.localeCompare(right.createdAt));
    this.loaded = true;
    this.emit();
    return this.cache;
  }

  private async ensureLoaded(): Promise<void> {
    if (!this.loaded) await this.load();
  }

  subscribe(listener: QueueListener): () => void {
    this.listeners.add(listener);
    listener(this.cache);
    return () => this.listeners.delete(listener);
  }

  private emit(): void {
    const snapshot = [...this.cache];
    this.listeners.forEach((listener) => listener(snapshot));
  }

  list(): QueuedOperation[] {
    return [...this.cache];
  }

  /** Items eligible for the next flush (rejected ones are parked). */
  pending(): QueuedOperation[] {
    return this.cache.filter((item) => !isParked(item));
  }

  countPending(): number {
    return this.pending().length;
  }

  countRejected(): number {
    return this.cache.filter(isParked).length;
  }

  async enqueue(input: EnqueueInput): Promise<QueuedOperation> {
    await this.ensureLoaded();
    const now = new Date().toISOString();
    const operation: QueuedOperation = {
      clientRequestId: input.clientRequestId ?? newId(),
      kind: input.kind,
      payload: input.payload,
      occurredAt: input.occurredAt ?? now,
      label: input.label,
      state: "pending",
      attempts: 0,
      lastError: "",
      lastErrorCode: "",
      createdAt: now,
    };
    await this.store.put(QUEUE_STORE, operation.clientRequestId, {
      ...operation,
    } as unknown as Record<string, unknown>);
    this.cache = [...this.cache, operation];
    this.emit();
    return operation;
  }

  async remove(clientRequestId: string): Promise<void> {
    await this.store.remove(QUEUE_STORE, clientRequestId);
    this.cache = this.cache.filter((item) => item.clientRequestId !== clientRequestId);
    this.emit();
  }

  async update(clientRequestId: string, patch: Partial<QueuedOperation>): Promise<void> {
    const current = this.cache.find((item) => item.clientRequestId === clientRequestId);
    if (!current) return;
    const next = { ...current, ...patch };
    await this.store.put(QUEUE_STORE, clientRequestId, next as unknown as Record<string, unknown>);
    this.cache = this.cache.map((item) =>
      item.clientRequestId === clientRequestId ? next : item,
    );
    this.emit();
  }

  /** Drop the permanently-refused items once the technician has seen them. */
  async clearRejected(): Promise<void> {
    const rejected = this.cache.filter(isParked);
    await Promise.all(
      rejected.map((item) => this.store.remove(QUEUE_STORE, item.clientRequestId)),
    );
    this.cache = this.cache.filter((item) => !isParked(item));
    this.emit();
  }

  async clearAll(): Promise<void> {
    await this.store.clear(QUEUE_STORE);
    this.cache = [];
    this.emit();
  }

  // -- read-through cache for offline reads -----------------------------------
  async cacheRead(key: string, payload: unknown): Promise<void> {
    const record: CachedRead = { key, payload, cachedAt: new Date().toISOString() };
    await this.store.put(CACHE_STORE, key, record as unknown as Record<string, unknown>);
  }

  async readCached<T>(key: string): Promise<{ payload: T; cachedAt: string } | undefined> {
    const row = await this.store.get<CachedRead>(CACHE_STORE, key);
    if (!row) return undefined;
    return { payload: row.payload as T, cachedAt: row.cachedAt };
  }

  async setMeta(key: string, value: unknown): Promise<void> {
    await this.store.put(META_STORE, key, { value } as unknown as Record<string, unknown>);
  }

  async getMeta<T>(key: string): Promise<T | undefined> {
    const row = await this.store.get<{ value: T }>(META_STORE, key);
    return row?.value;
  }
}
