"""ORM implementation of TaskRepository (Phase 18b)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.db.models import Q

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.tasks.domain.entities.task import Task
from apps.tasks.domain.repositories.taskRepository import TaskFilters, TaskPage
from apps.tasks.domain.valueObjects.taskState import TaskPriority, TaskStatus
from apps.tasks.infrastructure.models import TaskModel

SORTABLE_COLUMNS = {"createdAt": "createdAt", "title": "title", "status": "status", "priority": "priority"}


class TaskRepositoryDjango:
    def create(self, task: Task) -> None:
        TaskModel.objects.create(
            id=task.id,
            tenantId=task.tenantId,
            projectId=task.projectId,
            title=task.title,
            status=str(task.status),
            priority=str(task.priority),
            assigneeName=task.assigneeName,
            dueDate=task.dueDate,
            estimate=task.estimate,
            createdAt=task.createdAt,
        )

    def update(self, task: Task) -> None:
        TaskModel.objects.filter(id=task.id).update(
            title=task.title,
            status=str(task.status),
            priority=str(task.priority),
            assigneeName=task.assigneeName,
            dueDate=task.dueDate,
            estimate=task.estimate,
            updatedAt=task.updatedAt or datetime.now(tz=None),
        )

    def getById(self, tenantId: uuid.UUID, taskId: uuid.UUID) -> Task | None:
        model = TaskModel.objects.filter(id=taskId, tenantId=tenantId, deletedAt__isnull=True).first()
        return self.toDomain(model) if model else None

    def countByTenant(self, tenantId: uuid.UUID) -> int:
        return TaskModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True).count()

    def list(self, filters: TaskFilters) -> TaskPage:
        queryset = TaskModel.objects.filter(tenantId=filters.tenantId, deletedAt__isnull=True)
        if filters.projectId:
            queryset = queryset.filter(projectId=filters.projectId)
        if filters.status:
            queryset = queryset.filter(status=filters.status)
        if filters.search:
            queryset = queryset.filter(
                Q(title__icontains=filters.search) | Q(assigneeName__icontains=filters.search)
            )
        requestedField = filters.ordering.lstrip("-").split(",")[0].strip()
        if requestedField and requestedField not in SORTABLE_COLUMNS:
            raise ValidationFailedError("Field is not sortable.", fieldErrors={"ordering": requestedField})
        orderingColumn = SORTABLE_COLUMNS.get(requestedField, "createdAt")
        orderBy = f"-{orderingColumn}" if filters.ordering.startswith("-") else orderingColumn
        totalCount = queryset.count()
        pageSize = min(100, max(1, filters.pageSize))
        items = [
            self.toDomain(model)
            for model in queryset.order_by(orderBy)[
                (max(1, filters.page) - 1) * pageSize : max(1, filters.page) * pageSize
            ]
        ]
        return TaskPage(items=items, totalCount=totalCount)

    @staticmethod
    def toDomain(model: TaskModel) -> Task:
        return Task(
            id=model.id,
            tenantId=model.tenantId,
            projectId=model.projectId,
            title=model.title,
            status=TaskStatus(model.status),
            priority=TaskPriority(model.priority),
            assigneeName=model.assigneeName,
            dueDate=model.dueDate,
            estimate=model.estimate,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )

    @staticmethod
    def toModelFields(task: Task) -> dict[str, Any]:  # pragma: no cover — helper
        return {"id": task.id, "tenantId": task.tenantId, "title": task.title}
