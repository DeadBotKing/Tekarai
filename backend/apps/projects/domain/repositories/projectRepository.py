"""ProjectRepository contract (Phase 18b §10)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Protocol, runtime_checkable

from apps.projects.domain.entities.project import Project


@dataclass(frozen=True)
class ProjectFilters:
    tenantId: uuid.UUID
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class ProjectPage:
    items: list[Project]
    totalCount: int


@runtime_checkable
class ProjectRepository(Protocol):
    def create(self, project: Project) -> None: ...

    def update(self, project: Project) -> None: ...

    def getById(self, tenantId: uuid.UUID, projectId: uuid.UUID) -> Project | None: ...

    def existsByCode(self, tenantId: uuid.UUID, code: str) -> bool: ...

    def countByTenant(self, tenantId: uuid.UUID) -> int: ...

    def list(self, filters: ProjectFilters) -> ProjectPage: ...
