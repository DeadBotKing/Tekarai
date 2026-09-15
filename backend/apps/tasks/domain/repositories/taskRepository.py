"""TaskRepository contract (Phase 18b)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from apps.tasks.domain.entities.task import Task


@dataclass(frozen=True)
class TaskFilters:
    tenantId: uuid.UUID
    projectId: str = ""
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class TaskPage:
    items: list[Task]
    totalCount: int


@runtime_checkable
class TaskRepository(Protocol):
    def create(self, task: Task) -> None: ...

    def update(self, task: Task) -> None: ...

    def getById(self, tenantId: uuid.UUID, taskId: uuid.UUID) -> Task | None: ...

    def countByTenant(self, tenantId: uuid.UUID) -> int: ...

    def list(self, filters: TaskFilters) -> TaskPage: ...
