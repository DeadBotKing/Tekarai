import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { useEffect } from "react";
import { describe, expect, it, vi } from "vitest";
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { useOffline } from "../core/offline/offlineContext";
import { translate } from "../core/localization/i18n";
import { OfflineQueuePage } from "../pages/OfflineQueuePage";
import { WorkTimerPanel } from "../features/maintenance/WorkTimerPanel";
import { ScannerModal } from "../features/scanning/ScannerModal";

/**
 * کار میدانی — رفتار رابط کاربری.
 *
 * The three promises made to a technician, verified end to end against a
 * stubbed `fetch`: the timer records real time, a lost connection queues the
 * work instead of dropping it, and the scanner still resolves a code when
 * the camera is unavailable.
 */

const fa = (key: Parameters<typeof translate>[1], vars?: Record<string, string | number>): string =>
  translate("fa", key, vars);

const envelope = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify({ success: status < 400, data, meta: {}, errors: [] }), {
    status,
    headers: { "content-type": "application/json" },
  });

const timerDto = {
  id: "timer-1",
  workOrderId: "wo-1",
  technicianName: "حسینی",
  startedAt: new Date(Date.now() - 3_600_000).toISOString(),
  endedAt: "",
  running: true,
  elapsedSeconds: 3600,
  billableHours: "1.00",
  hourlyRate: "250000",
  startNote: "",
  endNote: "",
  labourEntryId: "",
  capturedOffline: false,
  startedVia: "manual",
};

/** A signed-in technician; the offline queue only replays with a session. */
const signIn = (): void =>
  sessionStore.set({
    accessToken: "test-access",
    refreshToken: "test-refresh",
    user: {
      id: "u1",
      displayName: "حسینی",
      email: "tech@example.test",
      role: "Technician",
      permissions: [
        "maintenance.workorder.view",
        "maintenance.workorder.logTime",
        "maintenance.device.view",
      ],
    },
  });

const renderInApp = (ui: JSX.Element, route = "/app/maintenance/work-orders"): void => {
  signIn();
  render(
    <AppProviders>
      <MemoryRouter initialEntries={[route]}>
        <Routes>
          <Route path="*" element={ui} />
        </Routes>
      </MemoryRouter>
    </AppProviders>,
  );
};

describe("WorkTimerPanel — ساعت واقعی به‌جای حدس", () => {
  it("starts a timer, posts the real wall clock, and shows it running", async () => {
    const calls: Array<{ url: string; body: unknown }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST" && url.includes("/timer/start")) {
        calls.push({ url, body: JSON.parse(String(init.body)) });
        return envelope(timerDto);
      }
      if (url.includes("/timers")) return envelope([]);
      return envelope([]);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);

    renderInApp(<WorkTimerPanel workOrderId="wo-1" technicianName="حسینی" />);

    const startButton = await screen.findByRole("button", { name: fa("timer.start") });
    await userEvent.click(startButton);

    await waitFor(() => expect(calls).toHaveLength(1));
    expect(calls[0].url).toContain("maintenance/work-orders/wo-1/timer/start");
    const body = calls[0].body as Record<string, string>;
    expect(body.technicianName).toBe("حسینی");
    // The start instant is sent explicitly so the server records when the
    // technician actually began, not when the request happened to arrive.
    expect(Number.isNaN(Date.parse(body.startedAt))).toBe(false);

    await screen.findByRole("button", { name: fa("timer.stop") });
    expect(screen.getByText(fa("timer.running"))).toBeTruthy();

    vi.unstubAllGlobals();
  });

  it("queues the start when the network is gone instead of losing it", async () => {
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (init?.method === "POST") throw new TypeError("Failed to fetch");
      if (url.includes("/timers")) return envelope([]);
      return envelope([]);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);
    const toast = vi.fn();

    renderInApp(
      <WorkTimerPanel workOrderId="wo-1" technicianName="حسینی" onToast={toast} />,
    );

    await userEvent.click(await screen.findByRole("button", { name: fa("timer.start") }));

    await waitFor(() => expect(toast).toHaveBeenCalledWith(fa("timer.queuedStart")));
    // The UI must show the stopwatch as running: a tap that appears to do
    // nothing gets tapped again, and then the span is wrong.
    await screen.findByRole("button", { name: fa("timer.stop") });
    expect(screen.getAllByText(fa("timer.capturedOffline")).length).toBeGreaterThan(0);

    vi.unstubAllGlobals();
  });
});

function Enqueue(): JSX.Element {
  const { enqueue } = useOffline();
  useEffect(() => {
    void enqueue({
      kind: "workTimer.stop",
      payload: { workOrderId: "wo-1", technicianName: "حسینی" },
      label: "پایان تایمر — حسینی",
    });
  }, [enqueue]);
  return <OfflineQueuePage />;
}

describe("OfflineQueuePage — صف قابل دیدن و قابل ارسال", () => {
  it("shows what is still unsent while the device has no connection", async () => {
    // navigator.onLine false ⇒ the provider must not even try to push, so
    // the row stays on screen for the technician to inspect.
    const onLine = vi.spyOn(navigator, "onLine", "get").mockReturnValue(false);
    const posted: unknown[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (String(input).includes("maintenance/sync") && init?.method === "POST") {
        posted.push(init.body);
      }
      return envelope([]);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);

    renderInApp(<Enqueue />, "/app/maintenance/offline-queue");

    expect(await screen.findByText("پایان تایمر — حسینی")).toBeTruthy();
    expect(screen.getAllByText(fa("offline.status.pending")).length).toBeGreaterThan(0);
    expect(screen.getAllByText(fa("offline.offline")).length).toBeGreaterThan(0);
    expect(posted).toHaveLength(0);

    onLine.mockRestore();
    vi.unstubAllGlobals();
  });

  it("replays the queue once a connection exists and clears what the server applied", async () => {
    const posted: Array<{ operations: Array<{ clientRequestId: string; kind: string }>; deviceLabel: string }> = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("maintenance/sync/history")) return envelope([]);
      if (url.includes("maintenance/sync") && init?.method === "POST") {
        const body = JSON.parse(String(init.body));
        posted.push(body);
        return envelope(
          body.operations.map((operation: { clientRequestId: string; kind: string }) => ({
            clientRequestId: operation.clientRequestId,
            kind: operation.kind,
            status: "applied",
            resultId: "labour-1",
          })),
        );
      }
      return envelope([]);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);

    renderInApp(<Enqueue />, "/app/maintenance/offline-queue");

    await waitFor(() => expect(posted.length).toBeGreaterThan(0));
    expect(posted[0].operations[0].kind).toBe("workTimer.stop");
    expect(posted[0].deviceLabel).toContain("tekarai-web");
    // Applied ⇒ the item is gone from the device; it is the server's now.
    await waitFor(() => expect(screen.queryByText("پایان تایمر — حسینی")).toBeNull());

    vi.unstubAllGlobals();
  });
});

describe("OfflineQueuePage — دکمهٔ «تلاش مجدد» باید واقعاً کار کند", () => {
  it("overrides the backoff a failed item is sitting behind", async () => {
    // The server fails the item once. The engine then holds it behind a
    // delay — correct automatically, but the user asking by hand must not
    // be told to wait: a button that does nothing gets pressed forever.
    const posted: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      const url = String(input);
      if (url.includes("maintenance/sync/history")) return envelope([]);
      if (url.includes("maintenance/sync") && init?.method === "POST") {
        const body = JSON.parse(String(init.body)) as {
          operations: Array<{ clientRequestId: string; kind: string }>;
        };
        posted.push(body.operations[0]?.clientRequestId ?? "");
        return envelope(
          body.operations.map((operation) => ({
            clientRequestId: operation.clientRequestId,
            kind: operation.kind,
            status: "failed",
            errorMessage: "سرور موقتاً در دسترس نیست.",
          })),
        );
      }
      return envelope([]);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);

    renderInApp(<Enqueue />, "/app/maintenance/offline-queue");

    await waitFor(() => expect(posted.length).toBe(1));
    const sentOnce = posted.length;

    const retryButton = await screen.findByRole("button", { name: fa("offline.retry") });
    await userEvent.click(retryButton);

    await waitFor(() => expect(posted.length).toBeGreaterThan(sentOnce));
    vi.unstubAllGlobals();
  });
});

describe("ScannerModal — وقتی دوربین نیست، کار متوقف نمی‌شود", () => {
  it("falls back to manual entry and resolves the code through the server", async () => {
    vi.stubGlobal("navigator", {
      ...navigator,
      mediaDevices: {
        getUserMedia: vi.fn(async () => {
          throw new DOMException("Permission denied", "NotAllowedError");
        }),
        enumerateDevices: vi.fn(async () => []),
      },
    });
    const resolved: string[] = [];
    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("maintenance/scan")) {
        resolved.push(url);
        return envelope({
          kind: "workOrder",
          id: "wo-9",
          code: "WO-1042",
          title: "تعویض بلبرینگ",
          subtitle: "پمپ خنک‌کننده",
          route: "/app/maintenance/work-orders/wo-9",
          status: "inProgress",
          symbology: "manual",
          scannedText: "WO-1042",
        });
      }
      return envelope([]);
    }) as unknown as typeof fetch;
    vi.stubGlobal("fetch", fetcher);

    const onResolved = vi.fn();
    renderInApp(<ScannerModal open onClose={() => undefined} onResolved={onResolved} />);

    // Permission refused: the modal says so rather than showing a dead frame.
    expect(await screen.findByText(fa("scan.denied"))).toBeTruthy();

    await userEvent.type(screen.getByLabelText(fa("scan.manualLabel")), "WO-1042");
    await userEvent.click(screen.getByRole("button", { name: fa("scan.go") }));

    await waitFor(() => expect(onResolved).toHaveBeenCalled());
    expect(resolved[0]).toContain("code=WO-1042");
    expect(onResolved.mock.calls[0][0]).toMatchObject({ kind: "workOrder", id: "wo-9" });

    vi.unstubAllGlobals();
  });
});
