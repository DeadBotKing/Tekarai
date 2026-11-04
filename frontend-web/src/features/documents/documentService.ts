import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";

export interface RelatedDevice { id: string; code: string; name: string; }
export interface LibraryDocument {
  id: string; name: string; contentType: string; sizeBytes: number; category: string; description: string;
  uploadedByIdentifier: string; uploadedAt: string;
  relatedDevices?: RelatedDevice[];
  legacyDeviceDocument?: boolean;
}
export interface DocumentMetadata { category?: string; description?: string; deviceIds?: string[]; }
export interface DocumentService {
  list: (filters?: { search?: string; category?: string; deviceId?: string }, signal?: AbortSignal) => Promise<LibraryDocument[]>;
  upload: (file: File, meta?: DocumentMetadata, onProgress?: (progress: number) => void, signal?: AbortSignal) => Promise<LibraryDocument>;
  update: (id: string, meta: DocumentMetadata, signal?: AbortSignal) => Promise<LibraryDocument>;
  download: (id: string, signal?: AbortSignal) => Promise<Blob>;
  remove: (id: string, signal?: AbortSignal) => Promise<LibraryDocument>;
}
export const createDocumentService = (api: ApiClient): DocumentService => ({
  list: async (filters = {}, signal) => {
    const all: LibraryDocument[] = [];
    for (let offset = 0; ; offset += 100) {
      const batch = await api.get<LibraryDocument[]>(apiEndpoints.documents, { signal, query: { ...filters, limit: 100, offset } });
      all.push(...batch);
      if (batch.length < 100) return all;
    }
  },
  upload: (file, meta = {}, onProgress, signal) => api.upload<LibraryDocument>(apiEndpoints.documents, file, {
    fields: { category: meta.category ?? "", description: meta.description ?? "", ...Object.fromEntries((meta.deviceIds ?? []).map((id, i) => [`deviceIds[${i}]`, id])) }, onProgress, signal,
  }),
  update: (id, meta, signal) => api.patch<LibraryDocument>(`documents/${id}`, meta, { signal, retry: 0 }),
  download: (id, signal) => api.download(`documents/${id}/download`, { signal }),
  remove: (id, signal) => api.delete<LibraryDocument>(`documents/${id}`, { signal }),
});
