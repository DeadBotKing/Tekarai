import { ApiClient } from "../../core/api/apiClient";
import { apiEndpoints } from "../../core/api/endpoints";
import type { Project } from "../../shared/types/domain";

/** Wire shape returned by GET/POST/PATCH /api/v1/projects (Phase 18b DTO). */
interface ProjectDto {
  id: string;
  code: string;
  name: string;
  description: string;
  status: string;
  health: number;
  progress: number;
  ownerName: string;
  dueDate: string;
}

const colorFor = (code: string): string => {
  const palette = ["#2878ff", "#27b27e", "#e6a23c", "#8b5cf6", "#ec6b9d"];
  const seed = code.split("").reduce((total, char) => total + char.charCodeAt(0), 0);
  return palette[seed % palette.length];
};

const toProject = (dto: ProjectDto): Project => ({
  id: dto.id,
  name: dto.name,
  code: dto.code,
  description: dto.description ?? "",
  owner: dto.ownerName ?? "",
  status: (dto.status as Project["status"]) ?? "active",
  health: dto.health ?? 100,
  progress: dto.progress ?? 0,
  dueDate: dto.dueDate ?? "",
  members: 0,
  tasks: 0,
  color: colorFor(dto.code),
});

/** Derive a tenant business code (BR-PRJ-001: A-Z, 0-9, dashes) from a name. */
const deriveCode = (name: string): string => {
  const letters = name.trim().split(/\s+/).map((word) => word[0]?.toUpperCase() ?? "").join("").replace(/[^A-Z0-9]/g, "").slice(0, 4);
  const suffix = Date.now().toString(36).slice(-4).toUpperCase();
  return `${letters || "PRJ"}-${suffix}`;
};

export interface ProjectService {
  list: (signal?: AbortSignal) => Promise<Project[]>;
  create: (input: Pick<Project, "name" | "description" | "owner" | "dueDate">, signal?: AbortSignal) => Promise<Project>;
  update: (id: string, input: Partial<Project>, signal?: AbortSignal) => Promise<Project>;
}

export const createProjectService = (api: ApiClient): ProjectService => ({
  list: async (signal) => {
    const dtos = await api.get<ProjectDto[]>(apiEndpoints.projects.list, { signal, query: { page: 1, pageSize: 100 } });
    return dtos.map(toProject);
  },
  create: async (input, signal) => {
    const dto = await api.post<ProjectDto>(
      apiEndpoints.projects.create,
      {
        code: deriveCode(input.name),
        name: input.name,
        description: input.description,
        ownerName: input.owner,
        dueDate: input.dueDate,
      },
      { signal, retry: 0 },
    );
    return toProject(dto);
  },
  update: async (id, input, signal) => {
    const dto = await api.patch<ProjectDto>(
      apiEndpoints.projects.update(id),
      {
        name: input.name,
        description: input.description,
        ownerName: input.owner,
        dueDate: input.dueDate,
        progress: input.progress,
        health: input.health,
      },
      { signal, retry: 0 },
    );
    return toProject(dto);
  },
});
