/**
 * ذخیره‌سازی محلی صف آفلاین.
 *
 * Two drivers behind one tiny interface:
 *
 * * **IndexedDB** in the browser — survives a reload, a crash, a battery
 *   death and days of being offline. `localStorage` was rejected: it is
 *   synchronous (it janks the UI on every write), capped around 5 MB, and
 *   string-only, so a queue with photos or long notes would silently hit the
 *   wall mid-shift.
 * * **in-memory** for tests and for the rare browser where IndexedDB is
 *   blocked (private mode on some engines). Losing the queue when the tab
 *   closes is bad, but refusing to let the technician work is worse — so we
 *   degrade instead of failing.
 *
 * Nothing here knows about work orders. It stores records with an `id` in a
 * named store; the queue and the read-cache both sit on top.
 */

export interface KeyValueStore {
  getAll<T>(store: string): Promise<T[]>;
  get<T>(store: string, id: string): Promise<T | undefined>;
  put<T extends { [key: string]: unknown }>(store: string, id: string, value: T): Promise<void>;
  remove(store: string, id: string): Promise<void>;
  clear(store: string): Promise<void>;
}

export const QUEUE_STORE = "operations";
export const CACHE_STORE = "reads";
export const META_STORE = "meta";
const DATABASE_NAME = "tekarai-offline";
const DATABASE_VERSION = 1;

/** In-memory fallback; also the driver used by unit tests. */
export function createMemoryStore(): KeyValueStore {
  const tables = new Map<string, Map<string, unknown>>();
  const table = (name: string): Map<string, unknown> => {
    const existing = tables.get(name);
    if (existing) return existing;
    const created = new Map<string, unknown>();
    tables.set(name, created);
    return created;
  };
  return {
    async getAll<T>(store: string): Promise<T[]> {
      return [...table(store).values()] as T[];
    },
    async get<T>(store: string, id: string): Promise<T | undefined> {
      return table(store).get(id) as T | undefined;
    },
    async put(store: string, id: string, value): Promise<void> {
      table(store).set(id, value);
    },
    async remove(store: string, id: string): Promise<void> {
      table(store).delete(id);
    },
    async clear(store: string): Promise<void> {
      table(store).clear();
    },
  };
}

const openDatabase = (): Promise<IDBDatabase> =>
  new Promise((resolve, reject) => {
    const request = window.indexedDB.open(DATABASE_NAME, DATABASE_VERSION);
    request.onupgradeneeded = () => {
      const database = request.result;
      [QUEUE_STORE, CACHE_STORE, META_STORE].forEach((name) => {
        if (!database.objectStoreNames.contains(name)) {
          database.createObjectStore(name, { keyPath: "id" });
        }
      });
    };
    request.onsuccess = () => resolve(request.result);
    request.onerror = () => reject(request.error);
  });

export function createIndexedDbStore(): KeyValueStore {
  let handle: Promise<IDBDatabase> | null = null;
  const database = (): Promise<IDBDatabase> => {
    if (!handle) handle = openDatabase();
    return handle;
  };

  const run = async <T>(
    store: string,
    mode: IDBTransactionMode,
    action: (objectStore: IDBObjectStore) => IDBRequest,
  ): Promise<T> => {
    const connection = await database();
    return new Promise<T>((resolve, reject) => {
      const transaction = connection.transaction(store, mode);
      const request = action(transaction.objectStore(store));
      request.onsuccess = () => resolve(request.result as T);
      request.onerror = () => reject(request.error);
    });
  };

  return {
    getAll: <T,>(store: string) => run<T[]>(store, "readonly", (table) => table.getAll()),
    get: <T,>(store: string, id: string) =>
      run<T | undefined>(store, "readonly", (table) => table.get(id)),
    put: (store, id, value) =>
      run<void>(store, "readwrite", (table) => table.put({ ...value, id })),
    remove: (store, id) => run<void>(store, "readwrite", (table) => table.delete(id)),
    clear: (store) => run<void>(store, "readwrite", (table) => table.clear()),
  };
}

/** Pick the durable driver when the browser offers one. */
export function createDefaultStore(): KeyValueStore {
  try {
    if (typeof window !== "undefined" && window.indexedDB) return createIndexedDbStore();
  } catch {
    /* private mode / blocked storage — fall through */
  }
  return createMemoryStore();
}
