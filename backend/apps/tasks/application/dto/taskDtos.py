"""Task DTOs (Phase 18b)."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.tasks.domain.entities.task import Task


@dataclass(frozen=True)
class TaskDto:
    id: str
    tenantId: str
    projectId: str
    title: str
    status: str
    priority: str
    assigneeName: str
    dueDate: str
    estimate: str
    createdAt: str
    updatedAt: str = ""


@dataclass(frozen=True)
class TaskListDto:
    items: list[TaskDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def taskDtoFromDomain(task: Task) -> TaskDto:
    return TaskDto(
        id=str(task.id),
        tenantId=str(task.tenantId),
        projectId=str(task.projectId) if task.projectId else "",
        title=task.title,
        status=str(task.status),
        priority=str(task.priority),
        assigneeName=task.assigneeName,
        dueDate=task.dueDate.isoformat() if task.dueDate else "",
        estimate=task.estimate,
        createdAt=task.createdAt.isoformat(),
        updatedAt=task.updatedAt.isoformat() if task.updatedAt else "",
    )
