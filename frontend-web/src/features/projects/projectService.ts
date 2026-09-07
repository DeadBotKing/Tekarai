import { ApiClient } from "../../core/api/apiClient";
import type { Project } from "../../shared/types/domain";

export interface ProjectService { list: (signal?: AbortSignal) => Promise<Project[]>; create: (input: Pick<Project, "name" | "description" | "owner" | "dueDate">, signal?: AbortSignal) => Promise<Project>; update: (id: string, input: Partial<Project>, signal?: AbortSignal) => Promise<Project>; }

export const createProjectService = (api: ApiClient): ProjectService => ({
  list: (signal) => api.get<Project[]>("projects", { signal, query: { page: 1, pageSize: 50 } }),
  create: (input, signal) => api.post<Project>("projects", input, { signal, retry: 0 }),
  update: (id, input, signal) => api.patch<Project>(`projects/${id}`, input, { signal, retry: 0 }),
});
