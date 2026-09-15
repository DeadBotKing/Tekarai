"""Task queries (Phase 18b)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Query


@dataclass(frozen=True)
class ListTasksQuery(Query):
    projectId: str = ""
    status: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class GetTaskQuery(Query):
    taskId: str
