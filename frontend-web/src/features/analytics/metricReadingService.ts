import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";

export type MetricQuality = "GOOD" | "SUSPECT" | "BAD" | "UNKNOWN";
export type MetricAggregation = "LAST" | "SUM" | "AVERAGE" | "MIN" | "MAX" | "COUNT";

export interface MetricDefinition {
  id: string;
  code: string;
  name: string;
  description: string;
  formula: string;
  unit: string;
  aggregation: MetricAggregation;
  minimumValue: string | null;
  maximumValue: string | null;
  isActive: boolean;
  createdAt: string;
  updatedAt: string | null;
}

export interface MetricReading {
  id: string;
  metricId: string;
  metricCode: string;
  value: string;
  unit: string;
  periodStart: string;
  periodEnd: string;
  dimensions: Record<string, string | number | boolean | null>;
  quality: MetricQuality;
  sourceType: string;
  sourceId: string;
  ingestionKey: string;
  recordedAt: string;
  recordedById: string | null;
  replayed: boolean;
}

export interface MetricReadingInput {
  metricId?: string;
  metricCode?: string;
  value: string | number;
  occurredAt?: string;
  periodStart?: string;
  periodEnd?: string;
  dimensions?: Record<string, string | number | boolean | null>;
  quality?: MetricQuality;
  sourceType?: string;
  sourceId?: string;
  ingestionKey?: string;
}

export interface MetricReadingFilters {
  metricId?: string;
  metricCode?: string;
  quality?: MetricQuality;
  sourceType?: string;
  sourceId?: string;
  from?: string;
  to?: string;
  ordering?: "periodStart" | "-periodStart" | "recordedAt" | "-recordedAt" | "value" | "-value";
  page?: number;
  pageSize?: number;
}

export interface MetricReadingSummary {
  count: number;
  minimum: string | null;
  maximum: string | null;
  average: string | null;
  total: string | null;
  first: MetricReading | null;
  last: MetricReading | null;
}

export interface MetricReadingService {
  listDefinitions: (search?: string, signal?: AbortSignal) => Promise<MetricDefinition[]>;
  createDefinition: (
    input: Omit<MetricDefinition, "id" | "createdAt" | "updatedAt" | "isActive">,
    idempotencyKey?: string,
  ) => Promise<MetricDefinition>;
  updateDefinition: (id: string, input: Partial<MetricDefinition>) => Promise<MetricDefinition>;
  listReadings: (filters?: MetricReadingFilters, signal?: AbortSignal) => Promise<MetricReading[]>;
  getReading: (id: string, signal?: AbortSignal) => Promise<MetricReading>;
  record: (input: MetricReadingInput, idempotencyKey?: string) => Promise<MetricReading>;
  recordBatch: (inputs: MetricReadingInput[], idempotencyKey?: string) => Promise<MetricReading[]>;
  summarize: (
    filters: Pick<MetricReadingFilters, "metricId" | "metricCode" | "quality" | "sourceType" | "sourceId" | "from" | "to">,
    signal?: AbortSignal,
  ) => Promise<MetricReadingSummary>;
}

const idempotencyHeaders = (key?: string): Record<string, string> | undefined =>
  key ? { "Idempotency-Key": key } : undefined;

export const createMetricReadingService = (api: ApiClient): MetricReadingService => ({
  listDefinitions: (search = "", signal) =>
    api.get<MetricDefinition[]>(apiEndpoints.analytics.metricDefinitions, {
      signal,
      query: { search, page: 1, pageSize: 200 },
    }),
  createDefinition: (input, idempotencyKey) =>
    api.post<MetricDefinition>(apiEndpoints.analytics.metricDefinitions, input, {
      retry: 0,
      headers: idempotencyHeaders(idempotencyKey),
    }),
  updateDefinition: (id, input) =>
    api.patch<MetricDefinition>(apiEndpoints.analytics.metricDefinition(id), input, { retry: 0 }),
  listReadings: (filters = {}, signal) =>
    api.get<MetricReading[]>(apiEndpoints.analytics.metricReadings, {
      signal,
      query: { ...filters },
    }),
  getReading: (id, signal) =>
    api.get<MetricReading>(apiEndpoints.analytics.metricReading(id), { signal }),
  record: (input, idempotencyKey) =>
    api.post<MetricReading>(apiEndpoints.analytics.metricReadings, input, {
      retry: 0,
      headers: idempotencyHeaders(idempotencyKey),
    }),
  recordBatch: (inputs, idempotencyKey) =>
    api.post<MetricReading[]>(apiEndpoints.analytics.metricReadingBatch, { readings: inputs }, {
      retry: 0,
      headers: idempotencyHeaders(idempotencyKey),
    }),
  summarize: (filters, signal) =>
    api.get<MetricReadingSummary>(apiEndpoints.analytics.metricReadingSummary, {
      signal,
      query: { ...filters },
    }),
});
