import { describe, expect, it, vi } from "vitest";
import { ApiClient } from "../core/api/apiClient";
import type { TokenPair } from "../core/api/apiTypes";
import { createMetricReadingService } from "../features/analytics/metricReadingService";

const responseOf = (data: unknown, status = 200): Response =>
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

const reading = {
  id: "reading-1",
  metricId: "metric-1",
  metricCode: "DEVICE.TEMPERATURE",
  value: "72.125000",
  unit: "°C",
  periodStart: "2026-09-29T10:00:00Z",
  periodEnd: "2026-09-29T10:00:00Z",
  dimensions: { deviceId: "PUMP-01" },
  quality: "GOOD",
  sourceType: "device",
  sourceId: "PUMP-01",
  ingestionKey: "gateway:1",
  recordedAt: "2026-09-29T10:00:01Z",
  recordedById: "user-1",
  replayed: false,
} as const;

describe("metricReadingService", () => {
  it("records a precise reading with an optional HTTP idempotency key", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf(reading, 201));
    const service = createMetricReadingService(makeClient(fetcher));
    const result = await service.record(
      {
        metricCode: "DEVICE.TEMPERATURE",
        value: "72.125",
        occurredAt: "2026-09-29T10:00:00Z",
        ingestionKey: "gateway:1",
      },
      "http-request-1",
    );
    expect(result.value).toBe("72.125000");
    expect(String(fetcher.mock.calls[0][0])).toContain("analytics/metric-readings");
    const request = fetcher.mock.calls[0][1] as RequestInit;
    expect(new Headers(request.headers).get("Idempotency-Key")).toBe("http-request-1");
  });

  it("sends time-series filters without assembling versioned URLs in the feature", async () => {
    const fetcher = vi.fn<typeof fetch>().mockResolvedValue(responseOf([reading]));
    const service = createMetricReadingService(makeClient(fetcher));
    const rows = await service.listReadings({
      metricCode: "DEVICE.TEMPERATURE",
      quality: "GOOD",
      from: "2026-09-01T00:00:00Z",
      ordering: "-periodStart",
    });
    expect(rows).toHaveLength(1);
    const url = String(fetcher.mock.calls[0][0]);
    expect(url).toContain("metricCode=DEVICE.TEMPERATURE");
    expect(url).toContain("quality=GOOD");
    expect(url).toContain("ordering=-periodStart");
  });

  it("uses the batch and summary contracts", async () => {
    const fetcher = vi
      .fn<typeof fetch>()
      .mockResolvedValueOnce(responseOf([reading], 201))
      .mockResolvedValueOnce(
        responseOf({
          count: 1,
          minimum: "72.125000",
          maximum: "72.125000",
          average: "72.125000",
          total: "72.125000",
          first: reading,
          last: reading,
        }),
      );
    const service = createMetricReadingService(makeClient(fetcher));
    await service.recordBatch([
      {
        metricCode: "DEVICE.TEMPERATURE",
        value: "72.125",
        occurredAt: "2026-09-29T10:00:00Z",
      },
    ]);
    const summary = await service.summarize({ metricCode: "DEVICE.TEMPERATURE" });
    expect(summary.count).toBe(1);
    expect(String(fetcher.mock.calls[0][0])).toContain("metric-readings/batch");
    expect(String(fetcher.mock.calls[1][0])).toContain("metric-readings/summary");
  });
});
