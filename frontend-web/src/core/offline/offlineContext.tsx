import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { useApiClient } from "../api/apiContext";
import { useAuth } from "../auth/authContext";
import { createFieldOpsService } from "../../features/maintenance/fieldOpsService";
import { OfflineQueue, type EnqueueInput } from "./queue";
import { createDefaultStore } from "./storage";
import { LAST_SYNC_META_KEY, SyncEngine } from "./syncEngine";
import { isParked } from "./types";
import type { QueuedOperation, SyncOutcome } from "./types";

/**
 * وضعیت آفلاین برنامه — one source of truth for "are we connected", "what is
 * still unsent", and "push it now".
 *
 * Connectivity is *not* `navigator.onLine` alone. That flag only knows
 * whether the OS has a link; a site Wi‑Fi access point with no uplink reports
 * online and then times out every request. So the context starts from
 * `navigator.onLine` and lets the sync engine correct it: a flush that cannot
 * reach the server marks us offline until the next successful round trip.
 *
 * Auto-flush fires on three triggers — the browser's `online` event, a login,
 * and a slow poll while items are waiting — never on every render.
 */

export interface OfflineContextValue {
  isOnline: boolean;
  pendingCount: number;
  rejectedCount: number;
  operations: QueuedOperation[];
  lastSyncAt: string;
  isSyncing: boolean;
  enqueue: (input: EnqueueInput) => Promise<QueuedOperation>;
  flush: () => Promise<SyncOutcome>;
  discard: (clientRequestId: string) => Promise<void>;
  retry: (clientRequestId: string) => Promise<void>;
  clearRejected: () => Promise<void>;
  queue: OfflineQueue;
}

const OfflineContext = createContext<OfflineContextValue | null>(null);

/** Poll interval while the queue is non-empty and we believe we are online. */
const RETRY_INTERVAL_MS = 30_000;

export function OfflineProvider({ children }: { children: ReactNode }): JSX.Element {
  const api = useApiClient();
  const { isAuthenticated, session } = useAuth();
  const service = useMemo(() => createFieldOpsService(api), [api]);
  const queue = useMemo(() => new OfflineQueue(createDefaultStore()), []);
  const engine = useMemo(() => new SyncEngine(queue, service), [queue, service]);

  const [operations, setOperations] = useState<QueuedOperation[]>([]);
  const [isOnline, setIsOnline] = useState<boolean>(
    typeof navigator === "undefined" ? true : navigator.onLine,
  );
  const [isSyncing, setIsSyncing] = useState(false);
  const [lastSyncAt, setLastSyncAt] = useState("");
  const authenticated = useRef(isAuthenticated);
  authenticated.current = isAuthenticated;

  // Storage is only touched once a session exists: the sign-in screen has
  // no queue to show, and opening IndexedDB there would be work done for a
  // user who may never log in.
  const ownerId = session?.user.id ?? "";
  useEffect(() => {
    const unsubscribe = queue.subscribe(setOperations);
    // Scope the queue to whoever is signed in *before* loading it, so a
    // shared phone never shows — or sends — the previous shift's backlog.
    queue.setOwner(ownerId);
    if (!isAuthenticated) return unsubscribe;
    void queue.load();
    void queue.getMeta<string>(LAST_SYNC_META_KEY).then((value) => {
      if (value) setLastSyncAt(value);
    });
    return unsubscribe;
  }, [isAuthenticated, ownerId, queue]);

  const flush = useCallback(async (): Promise<SyncOutcome> => {
    if (!authenticated.current) {
      // Not logged in: the queue survives untouched until someone is.
      return {
        applied: 0,
        duplicate: 0,
        rejected: 0,
        conflict: 0,
        failed: 0,
        rejectedItems: [],
        offline: true,
        authRequired: true,
      };
    }
    setIsSyncing(true);
    try {
      const outcome = await engine.flush();
      setIsOnline(!outcome.offline);
      if (!outcome.offline) {
        const stamp = await queue.getMeta<string>(LAST_SYNC_META_KEY);
        if (stamp) setLastSyncAt(stamp);
      }
      return outcome;
    } finally {
      setIsSyncing(false);
    }
  }, [engine, queue]);

  // Browser connectivity events.
  useEffect(() => {
    const goOnline = (): void => {
      setIsOnline(true);
      void flush();
    };
    const goOffline = (): void => setIsOnline(false);
    window.addEventListener("online", goOnline);
    window.addEventListener("offline", goOffline);
    return () => {
      window.removeEventListener("online", goOnline);
      window.removeEventListener("offline", goOffline);
    };
  }, [flush]);

  // Drain whatever survived the last session as soon as a session exists.
  // Skipped while the OS reports no link: `navigator.onLine === false` is
  // rarely wrong in that direction, and a doomed push costs a 30 s timeout
  // and a wake-up on a phone that is trying to save battery.
  useEffect(() => {
    if (isAuthenticated && isOnline && queue.countPending() > 0) void flush();
  }, [flush, isAuthenticated, isOnline, queue, operations.length]);

  // Slow retry while work is waiting — covers "the link came back but the
  // browser never fired an event", which is the normal case on mobile.
  useEffect(() => {
    const pending = operations.filter((item) => !isParked(item)).length;
    if (pending === 0 || !isAuthenticated || !isOnline) return undefined;
    const handle = window.setInterval(() => {
      void flush();
    }, RETRY_INTERVAL_MS);
    return () => window.clearInterval(handle);
  }, [flush, isAuthenticated, isOnline, operations]);

  const enqueue = useCallback(
    async (input: EnqueueInput): Promise<QueuedOperation> => {
      const operation = await queue.enqueue(input);
      if (isOnline && authenticated.current) void flush();
      return operation;
    },
    [flush, isOnline, queue],
  );

  const retry = useCallback(
    async (clientRequestId: string): Promise<void> => {
      await queue.update(clientRequestId, {
        state: "pending",
        lastError: "",
        lastErrorCode: "",
        // Asking by hand overrides the backoff: without clearing these the
        // button looks broken, because the engine skips items whose retry
        // window has not opened and re-parks anything already at the cap.
        attempts: 0,
        nextAttemptAt: "",
      });
      await flush();
    },
    [flush, queue],
  );

  const value = useMemo<OfflineContextValue>(
    () => ({
      isOnline,
      pendingCount: operations.filter((item) => !isParked(item)).length,
      rejectedCount: operations.filter(isParked).length,
      operations,
      lastSyncAt,
      isSyncing,
      enqueue,
      flush,
      discard: (clientRequestId: string) => queue.remove(clientRequestId),
      retry,
      clearRejected: () => queue.clearRejected(),
      queue,
    }),
    [enqueue, flush, isOnline, isSyncing, lastSyncAt, operations, queue, retry],
  );

  return <OfflineContext.Provider value={value}>{children}</OfflineContext.Provider>;
}

export const useOffline = (): OfflineContextValue => {
  const context = useContext(OfflineContext);
  if (!context) throw new Error("useOffline must be used inside OfflineProvider");
  return context;
};

/**
 * Optional variant for components that may render outside the provider
 * (standalone tests, the login screen). Returns `null` instead of throwing.
 */
export const useOptionalOffline = (): OfflineContextValue | null =>
  useContext(OfflineContext);
