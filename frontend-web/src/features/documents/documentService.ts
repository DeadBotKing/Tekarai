import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";

export interface LibraryDocument {
  id: string;
  name: string;
  contentType: string;
  sizeBytes: number;
  category: string;
  description: string;
  uploadedByIdentifier: string;
  uploadedAt: string;
}

export interface DocumentService {
  list: (filters?: { search?: string; category?: string }, signal?: AbortSignal) => Promise<LibraryDocument[]>;
  upload: (file: File, meta?: { category?: string; description?: string }, onProgress?: (progress: number) => void, signal?: AbortSignal) => Promise<LibraryDocument>;
  download: (id: string, signal?: AbortSignal) => Promise<Blob>;
  remove: (id: string, signal?: AbortSignal) => Promise<LibraryDocument>;
}

export const createDocumentService = (api: ApiClient): DocumentService => ({
  list: async (filters = {}, signal) => {
    const all: LibraryDocument[] = [];
    for (let offset = 0; offset < 1000; offset += 100) {
      const batch = await api.get<LibraryDocument[]>(apiEndpoints.documents, {
        signal,
        query: { ...filters, limit: 100, offset },
      });
      all.push(...batch);
      if (batch.length < 100) break;
    }
    return all;
  },
  upload: (file, meta = {}, onProgress, signal) =>
    api.upload<LibraryDocument>(apiEndpoints.documents, file, {
      fields: { category: meta.category ?? "", description: meta.description ?? "" },
      onProgress,
      signal,
    }),
  download: (id, signal) => api.download(`documents/${id}/download`, { signal }),
  remove: (id, signal) => api.delete<LibraryDocument>(`documents/${id}`, { signal }),
});
