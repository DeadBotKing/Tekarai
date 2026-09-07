import { ApiClient } from "../../core/api/apiClient";
import type { Task } from "../../shared/types/domain";

export interface TaskService { list: (filters?: { status?: string; search?: string }, signal?: AbortSignal) => Promise<Task[]>; create: (input: Pick<Task, "title" | "project" | "priority" | "assignee" | "dueDate">, signal?: AbortSignal) => Promise<Task>; }

export const createTaskService = (api: ApiClient): TaskService => ({
  list: (filters = {}, signal) => api.get<Task[]>("tasks", { signal, query: { ...filters, page: 1, pageSize: 50 } }),
  create: (input, signal) => api.post<Task>("tasks", input, { signal, retry: 0 }),
});
