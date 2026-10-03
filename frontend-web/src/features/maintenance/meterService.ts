import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type {
  MeterCaptureMode,
  MeterKind,
  MeterPmStatusRow,
  MeterPoint,
  MeterPointSummary,
  MeterQuality,
  MeterReading,
  MeterStatus,
  PmTriggerType,
  RecordMeterReadingInput,
  SaveMeterPointInput,
} from "../../shared/types/domain";

/**
 * Meter-reading client — ثبت قرائت دستی و سنسوری.
 *
 * Every decimal arrives as a *string*: a running-hour counter at
 * `124578901.2345` does not survive a JSON double. Parsing happens here, once,
 * at the boundary, so pages work with numbers and never re-parse. Values sent
 * back to the server are strings for the same reason.
 */

const text = (value: unknown): string =>
  value === null || value === undefined ? "" : String(value);

/** Empty string means "not measured", which is different from zero. */
const optionalNum = (value: unknown): number | null => {
  if (value === null || value === undefined || value === "") return null;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : null;
};

const num = (value: unknown): number => optionalNum(value) ?? 0;

interface MeterPointDto {
  id: string;
  deviceId: string;
  code: string;
  name: string;
  unit: string;
  kind: string;
  sensorKey: string;
  minimumValue: string;
  maximumValue: string;
  rolloverMaximum: string;
  maximumStepPerHour: string;
  drivesRunningHours: boolean;
  active: boolean;
  lastValue: string;
  lastReadingAt: string;
  lastCaptureMode: string;
  readingCount: number;
}

interface MeterReadingDto {
  id: string;
  deviceId: string;
  meterPointId: string;
  meterCode: string;
  meterName: string;
  unit: string;
  value: string;
  delta: string;
  capturedAt: string;
  captureMode: string;
  quality: string;
  rolloverApplied: boolean;
  note: string;
  sensorKey: string;
  recordedByName: string;
  provenance: string;
  correctsReadingId: string;
  supersededByReadingId: string;
  superseded: boolean;
  createdAt: string;
}

interface MeterPointSummaryDto {
  meterPointId: string;
  code: string;
  name: string;
  unit: string;
  kind: string;
  readingCount: number;
  manualCount: number;
  sensorCount: number;
  suspectCount: number;
  firstValue: string;
  lastValue: string;
  minimumValue: string;
  maximumValue: string;
  averageValue: string;
  totalConsumption: string;
  firstCapturedAt: string;
  lastCapturedAt: string;
}

interface MeterTriggerStatusDto {
  planId: string;
  deviceId: string;
  deviceCode: string;
  deviceName: string;
  title: string;
  discipline: string;
  triggerType: string;
  metricType: string;
  metricUnit: string;
  status: string;
  currentValue: string;
  dueAtValue: string;
  remaining: string;
  interval: string;
  thresholdOperator: string;
  thresholdValue: string;
  lastReadingAt: string;
  reason: string;
}

const toMeterPoint = (dto: MeterPointDto): MeterPoint => ({
  id: dto.id,
  deviceId: dto.deviceId,
  code: dto.code,
  name: dto.name,
  unit: text(dto.unit),
  kind: (dto.kind === "cumulative" ? "cumulative" : "gauge") as MeterKind,
  sensorKey: text(dto.sensorKey),
  drivesRunningHours: Boolean(dto.drivesRunningHours),
  active: Boolean(dto.active),
  rolloverMaximum: optionalNum(dto.rolloverMaximum),
  minimumValue: optionalNum(dto.minimumValue),
  maximumValue: optionalNum(dto.maximumValue),
  maximumStepPerHour: optionalNum(dto.maximumStepPerHour),
  lastValue: optionalNum(dto.lastValue),
  lastReadingAt: text(dto.lastReadingAt),
  lastCaptureMode: text(dto.lastCaptureMode) as MeterCaptureMode | "",
  readingCount: Number(dto.readingCount ?? 0),
});

const toMeterReading = (dto: MeterReadingDto): MeterReading => ({
  id: dto.id,
  deviceId: dto.deviceId,
  meterPointId: dto.meterPointId,
  meterCode: text(dto.meterCode),
  meterName: text(dto.meterName),
  unit: text(dto.unit),
  value: num(dto.value),
  // A null delta is meaningful: the first reading of a series, or a value the
  // rules refused to trust. Showing 0 there would invent consumption.
  delta: optionalNum(dto.delta),
  capturedAt: text(dto.capturedAt),
  captureMode: (dto.captureMode === "sensor" ? "sensor" : "manual") as MeterCaptureMode,
  quality: text(dto.quality || "good") as MeterQuality,
  rolloverApplied: Boolean(dto.rolloverApplied),
  note: text(dto.note),
  sensorKey: text(dto.sensorKey),
  recordedByName: text(dto.recordedByName),
  provenance: text(dto.provenance),
  correctsReadingId: text(dto.correctsReadingId),
  supersededByReadingId: text(dto.supersededByReadingId),
  createdAt: text(dto.createdAt),
});

const toSummary = (dto: MeterPointSummaryDto): MeterPointSummary => ({
  meterPointId: dto.meterPointId,
  code: dto.code,
  name: dto.name,
  unit: text(dto.unit),
  kind: (dto.kind === "cumulative" ? "cumulative" : "gauge") as MeterKind,
  readingCount: Number(dto.readingCount ?? 0),
  manualCount: Number(dto.manualCount ?? 0),
  sensorCount: Number(dto.sensorCount ?? 0),
  suspectCount: Number(dto.suspectCount ?? 0),
  firstValue: optionalNum(dto.firstValue),
  lastValue: optionalNum(dto.lastValue),
  minimumValue: optionalNum(dto.minimumValue),
  maximumValue: optionalNum(dto.maximumValue),
  averageValue: optionalNum(dto.averageValue),
  totalConsumption: optionalNum(dto.totalConsumption),
  firstCapturedAt: text(dto.firstCapturedAt),
  lastCapturedAt: text(dto.lastCapturedAt),
});

const toPmStatus = (dto: MeterTriggerStatusDto): MeterPmStatusRow => ({
  planId: dto.planId,
  deviceId: dto.deviceId,
  deviceCode: text(dto.deviceCode),
  deviceName: text(dto.deviceName),
  title: text(dto.title),
  discipline: text(dto.discipline),
  triggerType: text(dto.triggerType || "meter") as PmTriggerType,
  metricType: text(dto.metricType),
  metricUnit: text(dto.metricUnit),
  interval: optionalNum(dto.interval),
  thresholdOperator: text(dto.thresholdOperator),
  thresholdValue: optionalNum(dto.thresholdValue),
  currentValue: optionalNum(dto.currentValue),
  dueAtValue: optionalNum(dto.dueAtValue),
  remaining: optionalNum(dto.remaining),
  lastReadingAt: text(dto.lastReadingAt),
  status: text(dto.status || "unknown") as MeterStatus,
  reason: text(dto.reason),
});

export interface MeterReadingQuery {
  deviceId?: string;
  meterPointId?: string;
  captureMode?: MeterCaptureMode | "";
  quality?: MeterQuality | "";
  fromDate?: string;
  toDate?: string;
  includeSuperseded?: boolean;
  page?: number;
  pageSize?: number;
}

export interface MeterService {
  listDeviceMeterPoints: (deviceId: string, signal?: AbortSignal) => Promise<MeterPoint[]>;
  listMeterPoints: (
    query?: { search?: string; kind?: MeterKind | ""; activeOnly?: boolean },
    signal?: AbortSignal,
  ) => Promise<MeterPoint[]>;
  createMeterPoint: (
    deviceId: string,
    input: SaveMeterPointInput,
    signal?: AbortSignal,
  ) => Promise<MeterPoint>;
  updateMeterPoint: (
    meterPointId: string,
    input: Partial<SaveMeterPointInput>,
    signal?: AbortSignal,
  ) => Promise<MeterPoint>;
  retireMeterPoint: (meterPointId: string, signal?: AbortSignal) => Promise<void>;
  recordReading: (
    deviceId: string,
    input: RecordMeterReadingInput,
    signal?: AbortSignal,
  ) => Promise<MeterReading>;
  /** Append a replacement for a mistyped reading; the original is kept. */
  correctReading: (
    readingId: string,
    input: { value: string; note: string; quality?: MeterQuality },
    signal?: AbortSignal,
  ) => Promise<MeterReading>;
  listReadings: (query?: MeterReadingQuery, signal?: AbortSignal) => Promise<MeterReading[]>;
  getSummary: (
    meterPointId: string,
    query?: { fromDate?: string; toDate?: string },
    signal?: AbortSignal,
  ) => Promise<MeterPointSummary>;
  getPmStatus: (
    query?: { deviceId?: string; status?: MeterStatus | "" },
    signal?: AbortSignal,
  ) => Promise<MeterPmStatusRow[]>;
}

export const createMeterService = (api: ApiClient): MeterService => ({
  listDeviceMeterPoints: async (deviceId, signal) => {
    const dtos = await api.get<MeterPointDto[]>(
      apiEndpoints.maintenance.deviceMeterPoints(deviceId),
      { signal },
    );
    return dtos.map(toMeterPoint);
  },

  listMeterPoints: async (query = {}, signal) => {
    const dtos = await api.get<MeterPointDto[]>(apiEndpoints.maintenance.meterPoints, {
      query: {
        search: query.search || undefined,
        kind: query.kind || undefined,
        activeOnly: query.activeOnly ? "true" : undefined,
      },
      signal,
    });
    return dtos.map(toMeterPoint);
  },

  createMeterPoint: async (deviceId, input, signal) => {
    const dto = await api.post<MeterPointDto>(
      apiEndpoints.maintenance.deviceMeterPoints(deviceId),
      input,
      { signal },
    );
    return toMeterPoint(dto);
  },

  updateMeterPoint: async (meterPointId, input, signal) => {
    const dto = await api.patch<MeterPointDto>(
      apiEndpoints.maintenance.meterPoint(meterPointId),
      input,
      { signal },
    );
    return toMeterPoint(dto);
  },

  retireMeterPoint: async (meterPointId, signal) => {
    await api.delete<unknown>(apiEndpoints.maintenance.meterPoint(meterPointId), { signal });
  },

  recordReading: async (deviceId, input, signal) => {
    const dto = await api.post<MeterReadingDto>(
      apiEndpoints.maintenance.deviceMeterReadings(deviceId),
      input,
      { signal },
    );
    return toMeterReading(dto);
  },

  correctReading: async (readingId, input, signal) => {
    const dto = await api.post<MeterReadingDto>(
      apiEndpoints.maintenance.meterReadingCorrect(readingId),
      input,
      { signal },
    );
    return toMeterReading(dto);
  },

  listReadings: async (query = {}, signal) => {
    const dtos = await api.get<MeterReadingDto[]>(apiEndpoints.maintenance.meterReadings, {
      query: {
        deviceId: query.deviceId || undefined,
        meterPointId: query.meterPointId || undefined,
        captureMode: query.captureMode || undefined,
        quality: query.quality || undefined,
        from: query.fromDate || undefined,
        to: query.toDate || undefined,
        includeSuperseded: query.includeSuperseded === false ? "false" : undefined,
        page: query.page ? String(query.page) : undefined,
        pageSize: query.pageSize ? String(query.pageSize) : undefined,
      },
      signal,
    });
    return dtos.map(toMeterReading);
  },

  getSummary: async (meterPointId, query = {}, signal) => {
    const dto = await api.get<MeterPointSummaryDto>(
      apiEndpoints.maintenance.meterPointSummary(meterPointId),
      {
        query: { from: query.fromDate || undefined, to: query.toDate || undefined },
        signal,
      },
    );
    return toSummary(dto);
  },

  getPmStatus: async (query = {}, signal) => {
    const dtos = await api.get<MeterTriggerStatusDto[]>(apiEndpoints.maintenance.meterPmStatus, {
      query: { deviceId: query.deviceId || undefined, status: query.status || undefined },
      signal,
    });
    return dtos.map(toPmStatus);
  },
});
