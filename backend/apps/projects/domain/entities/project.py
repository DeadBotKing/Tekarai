"""Project aggregate root — workspace delivery unit (Phase 18b)."""

from __future__ import annotations

import uuid
from datetime import date, datetime
from typing import Any

from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError
from apps.sharedKernel.domain.events import DomainEvent
from apps.projects.domain.valueObjects.projectState import (
    PROJECT_ACTIVE,
    ProjectCode,
    ProjectStatus,
    clampPercent,
)


class Project(AggregateRoot):
    """A tenant-scoped delivery unit (BR-PRJ-001)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        code: ProjectCode,
        name: str,
        description: str,
        status: ProjectStatus,
        health: int,
        progress: int,
        ownerName: str,
        dueDate: date | None,
        createdAt: datetime,
        updatedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.code = code
        self.name = name
        self.description = description
        self.status = status
        self.health = health
        self.progress = progress
        self.ownerName = ownerName
        self.dueDate = dueDate
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt

    # -- factory -----------------------------------------------------------

    @staticmethod
    def create(
        tenantId: uuid.UUID,
        code: ProjectCode,
        name: str,
        description: str,
        ownerName: str,
        dueDate: date | None,
        now: datetime,
    ) -> Project:
        project = Project(
            id=newId(),
            tenantId=tenantId,
            code=code,
            name=name.strip(),
            description=description.strip(),
            status=ProjectStatus(PROJECT_ACTIVE),
            health=100,
            progress=0,
            ownerName=ownerName.strip(),
            dueDate=dueDate,
            createdAt=now,
        )
        project.recordEvent(
            DomainEvent(
                name="projectCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"code": str(code), "name": project.name},
            )
        )
        return project

    # -- behaviour ---------------------------------------------------------

    def updateDetails(
        self,
        name: str,
        description: str,
        ownerName: str,
        dueDate: date | None,
        progress: int,
        health: int,
        now: datetime,
    ) -> None:
        self.name = name.strip()
        self.description = description.strip()
        self.ownerName = ownerName.strip()
        self.dueDate = dueDate
        self.progress = clampPercent(progress)
        self.health = clampPercent(health)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="projectUpdated",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"projectId": str(self.id)},
            )
        )

    def changeStatus(self, target: str, now: datetime) -> None:
        if not self.status.canTransitionTo(target):
            raise InvalidStateTransitionError(
                f"Project cannot move from {self.status} to {target}."
            )
        previous = str(self.status)
        self.status = ProjectStatus(target)
        self.updatedAt = now
        self.recordEvent(
            DomainEvent(
                name="projectStatusChanged",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"from": previous, "to": target},
            )
        )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "code": str(self.code),
            "name": self.name,
            "status": str(self.status),
            "health": self.health,
            "progress": self.progress,
        }
