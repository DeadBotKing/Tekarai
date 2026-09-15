"""Project DTOs (Phase 18b)."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.projects.domain.entities.project import Project


@dataclass(frozen=True)
class ProjectDto:
    id: str
    tenantId: str
    code: str
    name: str
    description: str
    status: str
    health: int
    progress: int
    ownerName: str
    dueDate: str
    createdAt: str
    updatedAt: str = ""


@dataclass(frozen=True)
class ProjectListDto:
    items: list[ProjectDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def projectDtoFromDomain(project: Project) -> ProjectDto:
    return ProjectDto(
        id=str(project.id),
        tenantId=str(project.tenantId),
        code=str(project.code),
        name=project.name,
        description=project.description,
        status=str(project.status),
        health=project.health,
        progress=project.progress,
        ownerName=project.ownerName,
        dueDate=project.dueDate.isoformat() if project.dueDate else "",
        createdAt=project.createdAt.isoformat(),
        updatedAt=project.updatedAt.isoformat() if project.updatedAt else "",
    )
