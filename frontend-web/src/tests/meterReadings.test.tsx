import { render, screen, waitFor } from "@testing-library/react";
import { MemoryRouter, Route, Routes } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../core/api/apiClient";
import type { TokenPair } from "../core/api/apiTypes";
import { AppProviders } from "../app/providers/AppProviders";
import { sessionStore } from "../core/auth/sessionStore";
import { apiEndpoints } from "../core/api/endpoints";
import { createMeterService } from "../features/maintenance/meterService";
import { MeterReadingsPage } from "../pages/MeterReadingsPage";
import { translate } from "../core/localization/i18n";

const envelope = (data: unknown, status = 200): Response =>
  new Response(JSON.stringify({ success: true, data, meta: {}, errors: [] }), {
    status,
    headers: { "content-type": "application/json" },
  });

const makeClient = (fetcher: typeof fetch): ApiClient =>
  new ApiClient(
    { baseUrl: "", apiVersion: "v1", defaultTimeoutMs: 1000, defaultRetries: 0, fetcher },
    {
      getAccessToken: () => "access-token",
      getRefreshToken: () => "refresh-token",
      setTokens: (_tokens: TokenPair) => undefined,
      clearTokens: vi.fn(),
      getTenantId: () => "tenant-a",
      onUnauthorized: vi.fn(),
    },
  );

const pointDto = {
  id: "point-1",
  deviceId: "device-1",
  code: "RUNNING_HOURS",
  name: "ساعت کارکرد",
  unit: "ساعت",
  kind: "cumulative",
  sensorKey: "Line1/Pump01.Hours",
  minimumValue: "",
  maximumValue: "",
  rolloverMaximum: "999999",
  maximumStepPerHour: "1.2000",
  drivesRunningHours: true,
  active: true,
  lastValue: "124578901.2345",
  lastReadingAt: "2026-09-29T10:00:00+00:00",
  lastCaptureMode: "manual",
  readingCount: 3,
};

const readingDto = {
  id: "reading-1",
  deviceId: "device-1",
  meterPointId: "point-1",
  meterCode: "RUNNING_HOURS",
  meterName: "ساعت کارکرد",
  unit: "ساعت",
  value: "124578901.2345",
  delta: "",
  capturedAt: "2026-09-29T10:00:00+00:00",
  captureMode: "manual",
  quality: "good",
  rolloverApplied: false,
  note: "قرائت شیفت صبح",
  sensorKey: "",
  recordedByName: "رضا احمدی",
  provenance: "manual:رضا احمدی",
  correctsReadingId: "",
  supersededByReadingId: "",
  superseded: false,
  createdAt: "2026-09-29T10:01:00+00:00",
};

describe("meter service wire mapping", () => {
  it("keeps a large hour meter exact instead of rounding it as a JSON number", async () => {
    const fetcher = vi.fn(async () => envelope([pointDto])) as unknown as typeof fetch;
    const points = await createMeterService(makeClient(fetcher)).listDeviceMeterPoints("device-1");

    expect(points).toHaveLength(1);
    expect(points[0].lastValue).toBe(124578901.2345);
    expect(points[0].kind).toBe("cumulative");
    expect(points[0].rolloverMaximum).toBe(999999);
    expect(points[0].drivesRunningHours).toBe(true);
  });

  it("maps an unknown delta to null rather than zero", async () => {
    // The first reading of a series has no predecessor: reporting 0 hours of
    // consumption would be a fabricated fact, so the mapper must keep null.
    const fetcher = vi.fn(async () => envelope([readingDto])) as unknown as typeof fetch;
    const readings = await createMeterService(makeClient(fetcher)).listReadings();

    expect(readings[0].delta).toBeNull();
    expect(readings[0].value).toBe(124578901.2345);
    expect(readings[0].captureMode).toBe("manual");
    expect(readings[0].recordedByName).toBe("رضا احمدی");
  });

  it("maps an unmeasured summary field to null and a counted one to a number", async () => {
    const fetcher = vi.fn(async () =>
      envelope({
        meterPointId: "point-1",
        code: "BEARING_TEMP",
        name: "دما",
        unit: "°C",
        kind: "gauge",
        readingCount: 3,
        manualCount: 3,
        sensorCount: 0,
        suspectCount: 1,
        firstValue: "70.0000",
        lastValue: "74.0000",
        minimumValue: "70.0000",
        maximumValue: "74.0000",
        averageValue: "72.0000",
        totalConsumption: "",
        firstCapturedAt: "2026-09-29T08:00:00+00:00",
        lastCapturedAt: "2026-09-29T10:00:00+00:00",
      }),
    ) as unknown as typeof fetch;

    const summary = await createMeterService(makeClient(fetcher)).getSummary("point-1");

    // A gauge never accumulates, so consumption is absent — not zero.
    expect(summary.totalConsumption).toBeNull();
    expect(summary.averageValue).toBe(72);
    expect(summary.suspectCount).toBe(1);
  });

  it("sends the value as a string so the server receives the typed digits", async () => {
    const fetcher = vi.fn(async () => envelope(readingDto)) as unknown as typeof fetch;
    await createMeterService(makeClient(fetcher)).recordReading("device-1", {
      meterPointId: "point-1",
      value: "124578901.2345",
    });

    const [, init] = (fetcher as unknown as { mock: { calls: [string, RequestInit][] } }).mock
      .calls[0];
    expect(String(init.body)).toContain('"value":"124578901.2345"');
  });

  it("addresses every meter endpoint under the maintenance context", () => {
    expect(apiEndpoints.maintenance.deviceMeterReadings("d1")).toBe(
      "maintenance/devices/d1/meter-readings",
    );
    expect(apiEndpoints.maintenance.meterReadingCorrect("r1")).toBe(
      "maintenance/meter-readings/r1/correct",
    );
    expect(apiEndpoints.maintenance.meterPmStatus).toBe("maintenance/meter-pm-status");
  });
});

describe("meter readings page", () => {
  it("renders the capture page with its meters, history and PM status", async () => {
    sessionStore.set({
      accessToken: "test-access",
      refreshToken: "test-refresh",
      user: {
        id: "u1",
        displayName: "Test User",
        email: "test@example.test",
        role: "Maintenance",
        permissions: [
          "maintenance.device.list",
          "maintenance.device.view",
          "maintenance.meter.view",
          "maintenance.meter.record",
          "maintenance.meter.manage",
        ],
      },
    });

    const fetcher = vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.includes("meter-points/point-1/summary")) {
        return envelope({
          meterPointId: "point-1",
          code: "RUNNING_HOURS",
          name: "ساعت کارکرد",
          unit: "ساعت",
          kind: "cumulative",
          readingCount: 1,
          manualCount: 1,
          sensorCount: 0,
          suspectCount: 0,
          firstValue: "124578901.2345",
          lastValue: "124578901.2345",
          minimumValue: "124578901.2345",
          maximumValue: "124578901.2345",
          averageValue: "124578901.2345",
          totalConsumption: "0.0000",
          firstCapturedAt: "2026-09-29T10:00:00+00:00",
          lastCapturedAt: "2026-09-29T10:00:00+00:00",
        });
      }
      if (url.includes("meter-points")) return envelope([pointDto]);
      if (url.includes("meter-readings")) return envelope([readingDto]);
      if (url.includes("meter-pm-status")) {
        return envelope([
          {
            planId: "plan-1",
            deviceId: "device-1",
            deviceCode: "PUMP-01",
            deviceName: "پمپ",
            title: "تعویض روغن هر ۵۰۰ ساعت",
            discipline: "mechanical",
            triggerType: "meter",
            metricType: "RUNNING_HOURS",
            metricUnit: "ساعت",
            status: "due",
            currentValue: "8505.0000",
            dueAtValue: "8500.0000",
            remaining: "-5.0000",
            interval: "500.000",
            thresholdOperator: "",
            thresholdValue: "",
            lastReadingAt: "2026-09-29T10:00:00+00:00",
            reason: "",
          },
        ]);
      }
      if (url.includes("maintenance/devices")) {
        return envelope([
          {
            id: "device-1",
            code: "PUMP-01",
            name: "پمپ خنک‌کننده",
            location: "سالن A",
            status: "operational",
            department: "mechanical",
            pmIntervalDays: 30,
            lastPmDate: "",
            nextDueDate: "",
            pmDue: false,
            createdAt: "2026-01-01",
          },
        ]);
      }
      return envelope([]);
    }) as unknown as typeof fetch;

    vi.stubGlobal("fetch", fetcher);

    render(
      <AppProviders>
        <MemoryRouter initialEntries={["/app/maintenance/meter-readings"]}>
          <Routes>
            <Route path="/app/maintenance/meter-readings" element={<MeterReadingsPage />} />
          </Routes>
        </MemoryRouter>
      </AppProviders>,
    );

    await waitFor(() => {
      expect(screen.getByText(translate("fa", "meter.title"))).toBeTruthy();
    });
    await waitFor(() => {
      expect(screen.getAllByText("RUNNING_HOURS").length).toBeGreaterThan(0);
    });
    expect(screen.getByText("تعویض روغن هر ۵۰۰ ساعت")).toBeTruthy();
    // A due meter plan must be labelled as such — the whole point of the slice.
    expect(screen.getAllByText(translate("fa", "meter.status.due")).length).toBeGreaterThan(0);

    vi.unstubAllGlobals();
  });
});
