"""Task aggregate root — workspace delivery item (Phase 18b)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.events import DomainEvent
from apps.tasks.domain.valueObjects.taskState import (
    TASK_TODO,
    TaskPriority,
    TaskStatus,
)


class Task(AggregateRoot):
    """A tenant-scoped work item, optionally linked to a project by id.

    ``projectId`` is stored as a plain UUID — Tasks is its own bounded
    context and never reaches into Projects infrastructure (RULE E).
    """

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        projectId: uuid.UUID | None,
        title: str,
        status: TaskStatus,
        priority: TaskPriority,
        assigneeName: str,
        dueDate: date | None,
        estimate: str,
        createdAt: datetime,
        updatedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.projectId = projectId
        self.title = title
        self.status = status
        self.priority = priority
        self.assigneeName = assigneeName
        self.dueDate = dueDate
        self.estimate = estimate
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        projectId: uuid.UUID | None,
        title: str,
        priority: TaskPriority,
        assigneeName: str,
        dueDate: date | None,
        estimate: str,
        now: datetime,
    ) -> Task:
        task = Task(
            id=newId(),
            tenantId=tenantId,
            projectId=projectId,
            title=title.strip(),
            status=TaskStatus(TASK_TODO),
            priority=priority,
            assigneeName=assigneeName.strip(),
            dueDate=dueDate,
            estimate=estimate.strip(),
            createdAt=now,
        )
        task.recordEvent(
            DomainEvent(
                name="taskCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"taskId": str(task.id), "projectId": str(projectId) if projectId else ""},
            )
        )
        return task

    def updateDetails(
        self,
        title: str,
        priority: TaskPriority,
        assigneeName: str,
        dueDate: date | None,
        estimate: str,
        now: datetime,
    ) -> None:
        self.title = title.strip()
        self.priority = priority
        self.assigneeName = assigneeName.strip()
        self.dueDate = dueDate
        self.estimate = estimate.strip()
        self.updatedAt = now

    def changeStatus(self, target: str, now: datetime) -> None:
        previous = str(self.status)
        self.status = TaskStatus(target)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="taskStatusChanged",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"from": previous, "to": target},
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "projectId": str(self.projectId) if self.projectId else "",
            "title": self.title,
            "status": str(self.status),
            "priority": str(self.priority),
        }
