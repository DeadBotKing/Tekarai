import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type { QueuedOperation, SyncOperationResult } from "../../core/offline/types";

/**
 * Field-operations client — کار میدانی: تایمر، اسکن و همگام‌سازی.
 *
 * Decimals cross the wire as strings (hours, rates, meter values) and are
 * parsed exactly once, here. `elapsedSeconds` is an integer and stays one.
 */

export interface WorkTimer {
  id: string;
  workOrderId: string;
  technicianName: string;
  startedAt: string;
  endedAt: string;
  running: boolean;
  elapsedSeconds: number;
  billableHours: number;
  hourlyRate: number;
  startNote: string;
  endNote: string;
  labourEntryId: string;
  capturedOffline: boolean;
  startedVia: string;
}

export interface StoppedTimer {
  timer: WorkTimer;
  labourEntryId: string;
  hours: number;
  labourCost: number;
}

export interface ScanResult {
  kind: "device" | "workOrder" | "sparePart" | "location" | "";
  id: string;
  code: string;
  title: string;
  subtitle: string;
  route: string;
  status: string;
  symbology: string;
  scannedText: string;
}

export interface SyncLedgerEntry {
  clientRequestId: string;
  kind: string;
  status: string;
  resultId: string;
  errorCode: string;
  errorMessage: string;
  receivedAt: string;
}

export interface StartTimerInput {
  workOrderId: string;
  technicianName?: string;
  startedAt?: string;
  note?: string;
  startedVia?: string;
  hourlyRate?: string;
}

export interface StopTimerInput {
  workOrderId: string;
  technicianName?: string;
  endedAt?: string;
  note?: string;
  pausedSeconds?: number;
  hourlyRate?: string;
}

const text = (value: unknown): string =>
  value === null || value === undefined ? "" : String(value);

const num = (value: unknown): number => {
  if (value === null || value === undefined || value === "") return 0;
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed : 0;
};

interface WorkTimerDto {
  id: string;
  workOrderId: string;
  technicianName: string;
  startedAt: string;
  endedAt: string;
  running: boolean;
  elapsedSeconds: number;
  billableHours: string;
  hourlyRate: string;
  startNote: string;
  endNote: string;
  labourEntryId: string;
  capturedOffline: boolean;
  startedVia: string;
}

export const toWorkTimer = (dto: WorkTimerDto): WorkTimer => ({
  id: text(dto.id),
  workOrderId: text(dto.workOrderId),
  technicianName: text(dto.technicianName),
  startedAt: text(dto.startedAt),
  endedAt: text(dto.endedAt),
  running: Boolean(dto.running),
  elapsedSeconds: Math.max(0, Math.trunc(num(dto.elapsedSeconds))),
  billableHours: num(dto.billableHours),
  hourlyRate: num(dto.hourlyRate),
  startNote: text(dto.startNote),
  endNote: text(dto.endNote),
  labourEntryId: text(dto.labourEntryId),
  capturedOffline: Boolean(dto.capturedOffline),
  startedVia: text(dto.startedVia),
});

export interface FieldOpsService {
  startTimer(input: StartTimerInput): Promise<WorkTimer>;
  stopTimer(input: StopTimerInput): Promise<StoppedTimer>;
  listTimers(workOrderId: string, runningOnly?: boolean): Promise<WorkTimer[]>;
  activeTimers(technicianName?: string): Promise<WorkTimer[]>;
  cancelTimer(timerId: string): Promise<void>;
  resolveScan(code: string, symbology?: string): Promise<ScanResult>;
  pushSync(
    operations: QueuedOperation[],
    deviceLabel: string,
  ): Promise<SyncOperationResult[]>;
  syncHistory(limit?: number): Promise<SyncLedgerEntry[]>;
}

export function createFieldOpsService(api: ApiClient): FieldOpsService {
  return {
    async startTimer(input) {
      const dto = await api.post<WorkTimerDto>(
        apiEndpoints.maintenance.workOrderTimerStart(input.workOrderId),
        {
          technicianName: input.technicianName ?? "",
          startedAt: input.startedAt ?? "",
          note: input.note ?? "",
          startedVia: input.startedVia ?? "manual",
          hourlyRate: input.hourlyRate ?? "",
        },
      );
      return toWorkTimer(dto);
    },

    async stopTimer(input) {
      const dto = await api.post<{
        timer: WorkTimerDto;
        labourEntryId: string;
        hours: string;
        labourCost: string;
      }>(apiEndpoints.maintenance.workOrderTimerStop(input.workOrderId), {
        technicianName: input.technicianName ?? "",
        endedAt: input.endedAt ?? "",
        note: input.note ?? "",
        pausedSeconds: String(input.pausedSeconds ?? 0),
        hourlyRate: input.hourlyRate ?? "",
      });
      return {
        timer: toWorkTimer(dto.timer),
        labourEntryId: text(dto.labourEntryId),
        hours: num(dto.hours),
        labourCost: num(dto.labourCost),
      };
    },

    async listTimers(workOrderId, runningOnly = false) {
      const rows = await api.get<WorkTimerDto[]>(
        apiEndpoints.maintenance.workOrderTimers(workOrderId),
        { query: runningOnly ? { runningOnly: "true" } : undefined },
      );
      return (rows ?? []).map(toWorkTimer);
    },

    async activeTimers(technicianName) {
      const rows = await api.get<WorkTimerDto[]>(
        apiEndpoints.maintenance.workTimerActive,
        { query: technicianName ? { technicianName } : undefined },
      );
      return (rows ?? []).map(toWorkTimer);
    },

    async cancelTimer(timerId) {
      await api.delete<unknown>(apiEndpoints.maintenance.workTimer(timerId));
    },

    async resolveScan(code, symbology) {
      const dto = await api.get<ScanResult>(apiEndpoints.maintenance.scanResolve, {
        query: { code, symbology: symbology ?? "" },
      });
      return {
        kind: (text(dto.kind) || "") as ScanResult["kind"],
        id: text(dto.id),
        code: text(dto.code),
        title: text(dto.title),
        subtitle: text(dto.subtitle),
        route: text(dto.route),
        status: text(dto.status),
        symbology: text(dto.symbology),
        scannedText: text(dto.scannedText),
      };
    },

    async pushSync(operations, deviceLabel) {
      const rows = await api.post<SyncOperationResult[]>(
        apiEndpoints.maintenance.offlineSync,
        {
          deviceLabel,
          atomic: false,
          operations: operations.map((operation) => ({
            clientRequestId: operation.clientRequestId,
            kind: operation.kind,
            payload: operation.payload,
            occurredAt: operation.occurredAt,
          })),
        },
        // A replay must not be retried blindly by the transport: the server is
        // idempotent per item, but a half-read response plus a transport retry
        // would double the round trip for nothing.
        { retry: 0, timeoutMs: 45_000 },
      );
      return rows ?? [];
    },

    async syncHistory(limit = 50) {
      const rows = await api.get<SyncLedgerEntry[]>(
        apiEndpoints.maintenance.offlineSyncHistory,
        { query: { limit: String(limit) } },
      );
      return rows ?? [];
    },
  };
}
