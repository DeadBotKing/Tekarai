import { ApiClient } from "../../core/api/apiClient";
import type { Report } from "../../shared/types/domain";

export interface ReportService { list: (signal?: AbortSignal) => Promise<Report[]>; run: (id: string, signal?: AbortSignal) => Promise<{ jobId: string; status: "queued" | "running" }>; }
export const createReportService = (api: ApiClient): ReportService => ({
  list: (signal) => api.get<Report[]>("reports", { signal, query: { page: 1, pageSize: 50 } }),
  run: (id, signal) => api.post<{ jobId: string; status: "queued" | "running" }>(`reports/${id}/run`, undefined, { signal, retry: 0 }),
});
