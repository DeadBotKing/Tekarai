import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type { Task } from "../../shared/types/domain";

/** Wire shape returned by GET/POST/PATCH /api/v1/tasks (Phase 18b DTO). */
interface TaskDto {
  id: string;
  projectId: string;
  title: string;
  status: string;
  priority: string;
  assigneeName: string;
  dueDate: string;
  estimate: string;
}

const toTask = (dto: TaskDto, projectNames: Map<string, string>): Task => ({
  id: dto.id,
  title: dto.title,
  project: projectNames.get(dto.projectId) ?? dto.projectId ?? "",
  status: (dto.status === "todo" ? "backlog" : dto.status) as Task["status"],
  priority: (dto.priority as Task["priority"]) ?? "normal",
  assignee: dto.assigneeName ?? "",
  dueDate: dto.dueDate ?? "",
  estimate: dto.estimate ?? "",
});

export interface TaskService {
  list: (filters?: { status?: string; search?: string }, signal?: AbortSignal) => Promise<Task[]>;
  create: (input: { title: string; priority: string; assignee?: string; dueDate?: string; estimate?: string; projectId?: string }, signal?: AbortSignal) => Promise<Task>;
  changeStatus: (id: string, status: Task["status"], signal?: AbortSignal) => Promise<Task>;
}

export const createTaskService = (api: ApiClient): TaskService => ({
  list: async (filters = {}, signal) => {
    const [taskDtos, projectDtos] = await Promise.all([
      api.get<TaskDto[]>(apiEndpoints.tasks.list, { signal, query: { ...filters, page: 1, pageSize: 100 } }),
      api.get<Array<{ id: string; name: string }>>(apiEndpoints.projects.list, { signal, query: { page: 1, pageSize: 100 } }).catch(() => [] as Array<{ id: string; name: string }>),
    ]);
    const names = new Map(projectDtos.map((project) => [project.id, project.name]));
    return taskDtos.map((dto) => toTask(dto, names));
  },
  create: async (input, signal) => {
    const dto = await api.post<TaskDto>(
      apiEndpoints.tasks.create,
      {
        projectId: input.projectId ?? "",
        title: input.title,
        priority: input.priority,
        assigneeName: input.assignee ?? "",
        dueDate: input.dueDate ?? "",
        estimate: input.estimate ?? "",
      },
      { signal, retry: 0 },
    );
    return toTask(dto, new Map());
  },
  changeStatus: async (id, status, signal) => {
    const dto = await api.post<TaskDto>(
      apiEndpoints.tasks.status(id),
      { target: status },
      { signal, retry: 0 },
    );
    return toTask(dto, new Map());
  },
});
