import { ApiClient } from "../../core/api/apiClient";
import type { DocumentRecord } from "../../shared/types/domain";

export interface UploadResult { id: string; name: string; status: "queued" | "running" | "completed" | "failed"; progress: number; }
export interface DocumentService { list: (signal?: AbortSignal) => Promise<DocumentRecord[]>; upload: (file: File, onProgress?: (progress: number) => void, signal?: AbortSignal) => Promise<UploadResult>; }

export const createDocumentService = (api: ApiClient): DocumentService => ({
  list: (signal) => api.get<DocumentRecord[]>("documents", { signal, query: { page: 1, pageSize: 50 } }),
  upload: (file, onProgress, signal) => api.upload<UploadResult>("documents", file, { onProgress, signal }),
});
