import { beforeEach, describe, expect, it, vi } from "vitest";
import { OfflineQueue } from "../core/offline/queue";
import { createMemoryStore, QUEUE_STORE } from "../core/offline/storage";
import { MAX_ATTEMPTS, SyncEngine, describeDevice, retryDelayMs } from "../core/offline/syncEngine";
import { sessionStore } from "../core/auth/sessionStore";
import { isConnectivityFailure } from "../core/offline/offlineActions";
import { ApiClientError } from "../core/api/apiClient";
import type { QueuedOperation, SyncOperationResult } from "../core/offline/types";
import { isResolvable, parseScan, scanQrPayload, scanTargetPath } from "../features/scanning/scanCodes";
import { chooseEngine, preferredCamera } from "../features/scanning/codeScanner";
import { formatElapsed } from "../features/maintenance/WorkTimerPanel";

/**
 * کار میدانی — منطق خالص.
 *
 * These are the parts that decide whether a technician's work survives: the
 * queue, the replay verdicts, and the code parser. They are tested without
 * React, a camera or a server, so a regression here is unambiguous.
 */

describe("parseScan — چهار شکل ورودی", () => {
  it("reads an absolute work-order deep link", () => {
    const intent = parseScan(
      "https://tekarai.example.com/app/maintenance/work-orders/3f2504e0-4f89-11d3-9a0c-0305e82c3301?from=qr",
    );
    expect(intent.kind).toBe("workOrder");
    expect(intent.id).toBe("3f2504e0-4f89-11d3-9a0c-0305e82c3301");
  });

  it("reads a relative device link and a spare-part link", () => {
    expect(parseScan("/maintenance/devices/3f2504e0-4f89-11d3-9a0c-0305e82c3301").kind).toBe("device");
    expect(parseScan("/app/maintenance/spare-parts/3f2504e0-4f89-11d3-9a0c-0305e82c3301").kind).toBe(
      "sparePart",
    );
  });

  it("reads the legacy tekarai:// scheme printed on older labels", () => {
    const intent = parseScan("tekarai://work-order/3f2504e0-4f89-11d3-9a0c-0305e82c3301");
    expect(intent.kind).toBe("workOrder");
    expect(intent.id).toBe("3f2504e0-4f89-11d3-9a0c-0305e82c3301");
  });

  it("normalises a bare UUID, dashless or braced, and leaves the kind open", () => {
    const intent = parseScan("{3F2504E04F8911D39A0C0305E82C3301}");
    expect(intent.id).toBe("3f2504e0-4f89-11d3-9a0c-0305e82c3301");
    // Kind unknown on purpose: the server probes every register.
    expect(intent.kind).toBe("");
  });

  it("upper-cases a business code such as a barcode on an old asset tag", () => {
    expect(parseScan("pump-204").code).toBe("PUMP-204");
    expect(parseScan("line1/pmp.204").code).toBe("LINE1/PMP.204");
  });

  it("refuses things that are not our codes", () => {
    // Free text, somebody else's URL, empty frames and absurd lengths must
    // not be guessed into a navigation.
    expect(isResolvable(parseScan("سلام دنیا"))).toBe(false);
    expect(isResolvable(parseScan("https://example.com/promo"))).toBe(false);
    expect(isResolvable(parseScan(""))).toBe(false);
    expect(isResolvable(parseScan("A".repeat(600)))).toBe(false);
  });

  it("builds printable payloads that point at routes the app actually has", () => {
    // These mirror the server's `route` field; a label printed today must
    // still resolve offline, when the server cannot correct us.
    expect(scanTargetPath("device", "d1")).toBe("/app/maintenance/devices/d1/profile");
    expect(scanTargetPath("workOrder", "w1")).toBe("/app/maintenance/work-orders?focus=w1");
    expect(scanTargetPath("sparePart", "p1")).toBe("/app/maintenance/warehouse?focus=p1");
    expect(scanTargetPath("location", "l1")).toBe("/app/maintenance/locations?focus=l1");
    expect(scanQrPayload("workOrder", "w1")).toContain("/app/maintenance/work-orders?focus=w1");
  });
});

describe("chooseEngine — بومی فقط وقتی همه‌چیز را می‌خواند", () => {
  it("falls back to the bundled decoder when BarcodeDetector is absent", () => {
    expect(chooseEngine(null)).toBe("zxing");
    expect(chooseEngine([])).toBe("zxing");
  });

  it("falls back when the native decoder misses a symbology we print", () => {
    // Safari ≤16 reads QR but not ITF — a partial engine is a trap.
    expect(chooseEngine(["qr_code", "code_128", "code_39", "ean_13", "ean_8"])).toBe("zxing");
  });

  it("uses the native decoder when it covers every format", () => {
    expect(
      chooseEngine([
        "qr_code",
        "code_128",
        "code_39",
        "ean_13",
        "ean_8",
        "itf",
        "data_matrix",
        "pdf417",
      ]),
    ).toBe("native");
  });

  it("prefers a rear camera by label", () => {
    expect(
      preferredCamera([
        { deviceId: "front", label: "FaceTime HD Camera (front)" },
        { deviceId: "rear", label: "Back Triple Camera" },
      ]),
    ).toBe("rear");
  });
});

describe("formatElapsed — ساعت‌شمار خوانا", () => {
  it("renders hours, minutes and seconds in Persian digits", () => {
    expect(formatElapsed(0)).toBe("۰۰:۰۰:۰۰");
    expect(formatElapsed(7384)).toBe("۰۲:۰۳:۰۴");
    expect(formatElapsed(-5)).toBe("۰۰:۰۰:۰۰");
  });
});

const operation = (overrides: Partial<QueuedOperation> = {}): QueuedOperation => ({
  clientRequestId: "op-1",
  kind: "workTimer.stop",
  payload: { workOrderId: "w1" },
  occurredAt: "2026-10-01T08:00:00.000Z",
  label: "پایان تایمر",
  state: "pending",
  attempts: 0,
  lastError: "",
  lastErrorCode: "",
  createdAt: "2026-10-01T08:00:00.000Z",
  ...overrides,
});

describe("OfflineQueue — دوام و ترتیب", () => {
  let store = createMemoryStore();

  beforeEach(() => {
    store = createMemoryStore();
  });

  it("persists an operation so a reload does not lose the work", async () => {
    const queue = new OfflineQueue(store);
    await queue.enqueue({ kind: "device.status", payload: { deviceId: "d1" }, label: "وضعیت" });
    const reopened = new OfflineQueue(store);
    const restored = await reopened.load();
    expect(restored).toHaveLength(1);
    expect(restored[0].kind).toBe("device.status");
  });

  it("mints one idempotency key per capture and never changes it", async () => {
    const queue = new OfflineQueue(store);
    const first = await queue.enqueue({ kind: "meter.reading", payload: {}, label: "قرائت" });
    await queue.update(first.clientRequestId, { attempts: 3, state: "pending" });
    const [stored] = await queue.load();
    expect(stored.clientRequestId).toBe(first.clientRequestId);
    expect(stored.attempts).toBe(3);
  });

  it("replays in capture order, not insertion-into-memory order", async () => {
    await store.put(QUEUE_STORE, "late", { ...operation({ clientRequestId: "late", createdAt: "2026-10-01T09:00:00.000Z" }), id: "late" });
    await store.put(QUEUE_STORE, "early", { ...operation({ clientRequestId: "early", createdAt: "2026-10-01T07:00:00.000Z" }), id: "early" });
    const queue = new OfflineQueue(store);
    const rows = await queue.load();
    expect(rows.map((row) => row.clientRequestId)).toEqual(["early", "late"]);
  });

  it("serves the last good list when a read fails, with the time it was captured", async () => {
    const queue = new OfflineQueue(store);
    await queue.cacheRead("maintenance:workOrders", [{ id: "wo-1", title: "تعویض بلبرینگ" }]);
    const cached = await queue.readCached<Array<{ id: string }>>("maintenance:workOrders");
    expect(cached?.payload[0].id).toBe("wo-1");
    // The capture time is what lets the UI label the copy as stale instead of
    // passing it off as live.
    expect(Number.isNaN(Date.parse(cached?.cachedAt ?? ""))).toBe(false);
    expect(await queue.readCached("maintenance:nothing")).toBeUndefined();
  });

  it("keeps rejected items out of the next flush but visible to the user", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({ kind: "device.status", payload: {}, label: "وضعیت" });
    await queue.update(item.clientRequestId, { state: "rejected" });
    expect(queue.countPending()).toBe(0);
    expect(queue.countRejected()).toBe(1);
    expect(queue.list()).toHaveLength(1);
  });
});

const engineFor = (
  queue: OfflineQueue,
  results: SyncOperationResult[] | Error,
  capture?: (ops: QueuedOperation[]) => void,
): SyncEngine =>
  new SyncEngine(queue, {
    pushSync: async (operations) => {
      capture?.(operations);
      if (results instanceof Error) throw results;
      return results;
    },
  });

describe("SyncEngine — رأی سرور، سرنوشت صف", () => {
  let store = createMemoryStore();

  beforeEach(() => {
    store = createMemoryStore();
  });

  it("drops applied and duplicate items, parks rejected, keeps failed", async () => {
    const queue = new OfflineQueue(store);
    const applied = await queue.enqueue({ kind: "workTimer.start", payload: {}, label: "a" });
    const duplicate = await queue.enqueue({ kind: "workTimer.stop", payload: {}, label: "b" });
    const rejected = await queue.enqueue({ kind: "device.status", payload: {}, label: "c" });
    const failed = await queue.enqueue({ kind: "meter.reading", payload: {}, label: "d" });

    const engine = engineFor(queue, [
      { clientRequestId: applied.clientRequestId, kind: "workTimer.start", status: "applied" },
      { clientRequestId: duplicate.clientRequestId, kind: "workTimer.stop", status: "duplicate" },
      {
        clientRequestId: rejected.clientRequestId,
        kind: "device.status",
        status: "rejected",
        errorCode: "PERM_PERMISSION_DENIED",
        errorMessage: "دسترسی ندارید",
      },
      {
        clientRequestId: failed.clientRequestId,
        kind: "meter.reading",
        status: "failed",
        errorCode: "SYS_REQUEST_FAILED",
        errorMessage: "خطای سرور",
      },
    ]);

    const outcome = await engine.flush();
    expect(outcome).toMatchObject({ applied: 1, duplicate: 1, rejected: 1, failed: 1, offline: false });

    const remaining = queue.list();
    expect(remaining.map((item) => item.clientRequestId).sort()).toEqual(
      [rejected.clientRequestId, failed.clientRequestId].sort(),
    );
    const parked = remaining.find((item) => item.clientRequestId === rejected.clientRequestId);
    expect(parked?.state).toBe("rejected");
    expect(parked?.lastErrorCode).toBe("PERM_PERMISSION_DENIED");
    // The retryable one stays eligible for the next attempt.
    expect(remaining.find((item) => item.clientRequestId === failed.clientRequestId)?.state).toBe(
      "pending",
    );
  });

  it("keeps everything when the server cannot be reached, and says it is offline", async () => {
    const queue = new OfflineQueue(store);
    await queue.enqueue({ kind: "workTimer.start", payload: {}, label: "a" });
    const engine = engineFor(queue, new ApiClientError("شبکه در دسترس نیست", { isNetworkError: true }));
    const outcome = await engine.flush();
    expect(outcome.offline).toBe(true);
    expect(queue.countPending()).toBe(1);
    expect(queue.list()[0].state).toBe("pending");
  });

  it("never assumes success for an item the server did not mention", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({ kind: "workOrder.labour", payload: {}, label: "a" });
    const engine = engineFor(queue, []);
    const outcome = await engine.flush();
    expect(outcome.failed).toBe(1);
    expect(queue.list()).toHaveLength(1);
    expect(queue.list()[0].clientRequestId).toBe(item.clientRequestId);
  });

  it("sends the same clientRequestId on a retry so the server can dedupe", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({ kind: "workTimer.stop", payload: {}, label: "a" });
    const sent: string[][] = [];
    const failing = engineFor(queue, new ApiClientError("down", { isNetworkError: true }), (ops) =>
      sent.push(ops.map((operationItem) => operationItem.clientRequestId)),
    );
    await failing.flush();
    const succeeding = engineFor(
      queue,
      [{ clientRequestId: item.clientRequestId, kind: "workTimer.stop", status: "duplicate" }],
      (ops) => sent.push(ops.map((operationItem) => operationItem.clientRequestId)),
    );
    await succeeding.flush();
    expect(sent).toEqual([[item.clientRequestId], [item.clientRequestId]]);
    expect(queue.list()).toHaveLength(0);
  });

  it("collapses concurrent flushes into one batch", async () => {
    const queue = new OfflineQueue(store);
    await queue.enqueue({ kind: "device.status", payload: {}, label: "a" });
    let calls = 0;
    const engine = new SyncEngine(queue, {
      pushSync: async (operations) => {
        calls += 1;
        await new Promise((resolve) => setTimeout(resolve, 10));
        return operations.map((item) => ({
          clientRequestId: item.clientRequestId,
          kind: item.kind,
          status: "applied" as const,
        }));
      },
    });
    await Promise.all([engine.flush(), engine.flush(), engine.flush()]);
    expect(calls).toBe(1);
  });

  it("labels the device so the server ledger shows where a replay came from", () => {
    vi.stubGlobal("navigator", { userAgent: "Mozilla/5.0 (Linux; Android 14; SM-A546B)" });
    expect(describeDevice()).toBe("tekarai-web/Android");
    vi.unstubAllGlobals();
  });
});

describe("isConnectivityFailure — صف یا خطا", () => {
  it("queues on network, timeout and server faults", () => {
    expect(isConnectivityFailure(new ApiClientError("x", { isNetworkError: true }))).toBe(true);
    expect(isConnectivityFailure(new ApiClientError("x", { status: 408 }))).toBe(true);
    expect(isConnectivityFailure(new ApiClientError("x", { status: 503 }))).toBe(true);
    expect(isConnectivityFailure(new TypeError("Failed to fetch"))).toBe(true);
  });

  it("does not queue a refusal — replaying a 422 forever hides the real problem", () => {
    expect(isConnectivityFailure(new ApiClientError("x", { status: 422 }))).toBe(false);
    expect(isConnectivityFailure(new ApiClientError("x", { status: 403 }))).toBe(false);
  });
});

describe("SyncEngine — تعارض، نشست منقضی و تلاش مجدد", () => {
  let store = createMemoryStore();

  beforeEach(() => {
    store = createMemoryStore();
  });

  it("parks a conflict separately from a rejection and never replays it", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({
      kind: "workOrder.status",
      payload: { workOrderId: "w1", target: "done", baselineStatus: "assigned" },
      label: "پمپ ۱ → انجام‌شده",
    });

    const outcome = await engineFor(queue, [
      {
        clientRequestId: item.clientRequestId,
        kind: "workOrder.status",
        status: "conflict",
        errorCode: "MAINT_SYNC_CONFLICT",
        errorMessage: "در این فاصله تغییر کرد.",
      },
    ]).flush();

    expect(outcome.conflict).toBe(1);
    expect(outcome.rejected).toBe(0);
    const stored = queue.list()[0];
    expect(stored.state).toBe("conflict");
    expect(stored.lastErrorCode).toBe("MAINT_SYNC_CONFLICT");
    // Parked, so a later flush must not send it a second time.
    expect(queue.pending()).toHaveLength(0);
    expect(queue.countPending()).toBe(0);
  });

  it("stops on an expired session without burning attempts", async () => {
    const queue = new OfflineQueue(store);
    await queue.enqueue({ kind: "workTimer.stop", payload: {}, label: "x" });
    const expired = Object.assign(new Error("Unauthorized"), { status: 401 });

    const outcome = await engineFor(queue, expired as unknown as Error).flush();

    expect(outcome.authRequired).toBe(true);
    expect(outcome.offline).toBe(false);
    const stored = queue.list()[0];
    expect(stored.state).toBe("pending");
    // Nothing reached the server, so the item is no closer to being parked.
    expect(stored.attempts).toBe(0);
  });

  it("backs a transient failure off instead of retrying it immediately", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({ kind: "meter.reading", payload: {}, label: "m" });
    const verdict: SyncOperationResult[] = [
      { clientRequestId: item.clientRequestId, kind: "meter.reading", status: "failed" },
    ];

    await engineFor(queue, verdict).flush();
    const afterFirst = queue.list()[0];
    expect(afterFirst.attempts).toBe(1);
    expect(afterFirst.nextAttemptAt).toBeTruthy();
    expect(Date.parse(afterFirst.nextAttemptAt ?? "")).toBeGreaterThan(Date.now());

    // A flush during the backoff window must not touch the server at all.
    let sent = 0;
    await engineFor(queue, verdict, () => {
      sent += 1;
    }).flush();
    expect(sent).toBe(0);
    expect(queue.list()[0].attempts).toBe(1);
  });

  it("gives up and parks an item that keeps failing", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({ kind: "meter.reading", payload: {}, label: "m" });
    await queue.update(item.clientRequestId, { attempts: MAX_ATTEMPTS - 1 });

    await engineFor(queue, [
      { clientRequestId: item.clientRequestId, kind: "meter.reading", status: "failed" },
    ]).flush();

    const stored = queue.list()[0];
    expect(stored.state).toBe("rejected");
    expect(stored.attempts).toBe(MAX_ATTEMPTS);
  });

  it("grows the retry delay and caps it at half an hour", () => {
    expect(retryDelayMs(1)).toBe(30_000);
    expect(retryDelayMs(2)).toBe(60_000);
    expect(retryDelayMs(20)).toBe(30 * 60_000);
  });
});

describe("sessionStore — ماندگاری نشست انتخاب کاربر است", () => {
  const KEY = "tekarai.gui.session.v1";
  const session = {
    accessToken: "a",
    refreshToken: "r",
    user: {
      id: "u1",
      displayName: "مهندس حسینی",
      email: "h@example.com",
      role: "technician",
      permissions: [],
    },
  };

  it("keeps a plain sign-in inside the tab, so a shared PC forgets it", () => {
    sessionStore.set(session, false);

    expect(sessionStorage.getItem(KEY)).toContain("refreshToken");
    expect(localStorage.getItem(KEY)).toBeNull();
  });

  it("persists only when «keep me signed in» was ticked", () => {
    sessionStore.set(session, true);

    // What an installed app needs when it reopens with no signal.
    expect(localStorage.getItem(KEY)).toContain("refreshToken");
    expect(sessionStorage.getItem(KEY)).toBeNull();
  });

  it("does not promote a tab-only session when the token is refreshed", () => {
    sessionStore.set(session, false);
    sessionStore.updateTokens({ accessToken: "a2", refreshToken: "r2" });

    expect(localStorage.getItem(KEY)).toBeNull();
    expect(sessionStorage.getItem(KEY)).toContain("r2");
  });

  it("ignores a session persisted by the build that had no checkbox", () => {
    // Exactly what an upgrading user has in their browser: a localStorage
    // entry nobody opted into. It must not sign them in.
    localStorage.setItem(KEY, JSON.stringify(session));

    // A fresh read is what happens on page load.
    const restored = JSON.parse(localStorage.getItem(KEY) ?? "null") as {
      remember?: boolean;
    } | null;
    expect(restored?.remember).toBeUndefined();

    sessionStore.set(session, true);
    const stamped = JSON.parse(localStorage.getItem(KEY) ?? "null") as {
      remember?: boolean;
    };
    expect(stamped.remember).toBe(true);
  });

  it("clears both stores on logout", () => {
    sessionStore.set(session, true);
    sessionStore.clear();

    expect(localStorage.getItem(KEY)).toBeNull();
    expect(sessionStorage.getItem(KEY)).toBeNull();
    expect(sessionStore.get()).toBeNull();
  });
});

describe("OfflineQueue — صف هر کاربر مال خودش است", () => {
  let store = createMemoryStore();

  beforeEach(() => {
    store = createMemoryStore();
  });

  it("hides and never sends work captured by the previous shift", async () => {
    const queue = new OfflineQueue(store);
    queue.setOwner("tech-a");
    await queue.enqueue({ kind: "workTimer.stop", payload: {}, label: "کار نفر اول" });

    // Next shift signs in on the same phone.
    queue.setOwner("tech-b");
    expect(queue.list()).toHaveLength(0);
    expect(queue.pending()).toHaveLength(0);
    expect(queue.countForeign()).toBe(1);

    let sent: QueuedOperation[] = [];
    await engineFor(queue, [], (operations) => {
      sent = operations;
    }).flush();
    expect(sent).toHaveLength(0);

    // …and it is still there when its owner comes back.
    queue.setOwner("tech-a");
    expect(queue.pending()).toHaveLength(1);
    expect(queue.countForeign()).toBe(0);
  });

  it("a manual retry clears the backoff instead of looking broken", async () => {
    const queue = new OfflineQueue(store);
    const item = await queue.enqueue({ kind: "meter.reading", payload: {}, label: "m" });
    // State after a few transient failures: parked behind a long delay.
    await queue.update(item.clientRequestId, {
      state: "pending",
      attempts: MAX_ATTEMPTS - 1,
      nextAttemptAt: new Date(Date.now() + 25 * 60_000).toISOString(),
    });

    let sent: QueuedOperation[] = [];
    await engineFor(queue, [], (operations) => {
      sent = operations;
    }).flush();
    expect(sent).toHaveLength(0); // the backoff is respected…

    // …until the user asks explicitly, which is what the button must do.
    await queue.update(item.clientRequestId, {
      state: "pending",
      attempts: 0,
      nextAttemptAt: "",
    });
    await engineFor(queue, [], (operations) => {
      sent = operations;
    }).flush();
    expect(sent).toHaveLength(1);
  });
});
