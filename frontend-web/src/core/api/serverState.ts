import { useCallback, useEffect, useRef, useState } from "react";

export type AsyncStatus = "idle" | "loading" | "success" | "error";

export interface AsyncState<T> {
  status: AsyncStatus;
  data: T | null;
  error: unknown;
  updatedAt: number | null;
}

interface CacheEntry<T> { value: T; expiresAt: number; }

/** Tenant-aware in-memory server-state cache. Persistent business truth stays in the API. */
export class TenantAwareCache<T> {
  private readonly entries = new Map<string, CacheEntry<T>>();

  constructor(private readonly now: () => number = () => Date.now()) {}

  key(tenantId: string, resource: string, parameters = ""): string { return `${tenantId}:${resource}:${parameters}`; }

  get(key: string): T | null {
    const entry = this.entries.get(key);
    if (!entry) return null;
    if (entry.expiresAt <= this.now()) { this.entries.delete(key); return null; }
    return entry.value;
  }

  set(key: string, value: T, ttlMs: number): void { this.entries.set(key, { value, expiresAt: this.now() + ttlMs }); }
  invalidate(keyPrefix?: string): void { if (!keyPrefix) { this.entries.clear(); return; } for (const key of this.entries.keys()) if (key.startsWith(keyPrefix)) this.entries.delete(key); }
  size(): number { return this.entries.size; }
}

export const serverCache = new TenantAwareCache();

export interface UseAsyncResourceOptions<T> {
  enabled?: boolean;
  initialData?: T | null;
  cacheKey?: string;
  cacheTtlMs?: number;
  cache?: TenantAwareCache<T>;
}

export interface AsyncResourceResult<T> extends AsyncState<T> {
  reload: () => Promise<void>;
}

export function useAsyncResource<T>(
  loader: (signal: AbortSignal) => Promise<T>,
  dependencies: readonly unknown[],
  options: UseAsyncResourceOptions<T> = {},
): AsyncResourceResult<T> {
  const { enabled = true, initialData = null, cacheKey, cacheTtlMs = 30_000, cache = serverCache as TenantAwareCache<T> } = options;
  const cached = cacheKey ? cache.get(cacheKey) : null;
  const [state, setState] = useState<AsyncState<T>>({ status: cached ? "success" : initialData ? "success" : "idle", data: cached ?? initialData, error: null, updatedAt: cached ? Date.now() : null });
  const requestId = useRef(0);
  const controller = useRef<AbortController | null>(null);
  const load = useCallback(async (): Promise<void> => {
    if (!enabled) return;
    controller.current?.abort();
    const activeController = new AbortController();
    controller.current = activeController;
    const id = ++requestId.current;
    setState((current) => ({ ...current, status: "loading", error: null }));
    try {
      const value = await loader(activeController.signal);
      if (id !== requestId.current) return;
      if (cacheKey) cache.set(cacheKey, value, cacheTtlMs);
      setState({ status: "success", data: value, error: null, updatedAt: Date.now() });
    } catch (error) {
      if (id !== requestId.current || (error instanceof DOMException && error.name === "AbortError")) return;
      setState((current) => ({ ...current, status: "error", error }));
    }
  // The caller controls stable dependencies; a loader closure is intentionally evaluated per request.
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cache, cacheKey, cacheTtlMs, enabled, ...dependencies]);

  useEffect(() => { void load(); return () => { requestId.current += 1; controller.current?.abort(); controller.current = null; }; }, [load]);
  return { ...state, reload: load };
}
