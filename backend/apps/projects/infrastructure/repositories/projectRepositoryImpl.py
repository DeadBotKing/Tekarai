"""ORM implementation of ProjectRepository (Phase 18b)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.db import IntegrityError
from django.db.models import Q

from apps.projects.domain.entities.project import Project
from apps.projects.domain.repositories.projectRepository import (
    ProjectFilters,
    ProjectPage,
)
from apps.projects.domain.valueObjects.projectState import ProjectCode, ProjectStatus
from apps.projects.infrastructure.models import ProjectModel
from apps.sharedKernel.domain.errors import DuplicateBusinessCodeError, ValidationFailedError

SORTABLE_COLUMNS = {"createdAt": "createdAt", "name": "name", "code": "code", "status": "status"}


class ProjectRepositoryDjango:
    def create(self, project: Project) -> None:
        try:
            ProjectModel.objects.create(
                id=project.id,
                tenantId=project.tenantId,
                code=str(project.code),
                name=project.name,
                description=project.description,
                status=str(project.status),
                health=project.health,
                progress=project.progress,
                ownerName=project.ownerName,
                dueDate=project.dueDate,
                createdAt=project.createdAt,
            )
        except IntegrityError as exc:
            raise DuplicateBusinessCodeError(
                "Project code already exists in this tenant.",
                details={"ruleId": "BR-PRJ-001"},
            ) from exc

    def update(self, project: Project) -> None:
        ProjectModel.objects.filter(id=project.id).update(
            name=project.name,
            description=project.description,
            status=str(project.status),
            health=project.health,
            progress=project.progress,
            ownerName=project.ownerName,
            dueDate=project.dueDate,
            updatedAt=project.updatedAt or datetime.now(tz=None),
        )

    def getById(self, tenantId: uuid.UUID, projectId: uuid.UUID) -> Project | None:
        model = ProjectModel.objects.filter(
            id=projectId, tenantId=tenantId, deletedAt__isnull=True
        ).first()
        return self.toDomain(model) if model else None

    def existsByCode(self, tenantId: uuid.UUID, code: str) -> bool:
        return ProjectModel.objects.filter(
            tenantId=tenantId, code=code, deletedAt__isnull=True
        ).exists()

    def countByTenant(self, tenantId: uuid.UUID) -> int:
        return ProjectModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True).count()

    def list(self, filters: ProjectFilters) -> ProjectPage:
        queryset = ProjectModel.objects.filter(tenantId=filters.tenantId, deletedAt__isnull=True)
        if filters.status:
            queryset = queryset.filter(status=filters.status)
        if filters.search:
            queryset = queryset.filter(
                Q(name__icontains=filters.search) | Q(code__icontains=filters.search)
            )
        requestedField = filters.ordering.lstrip("-").split(",")[0].strip()
        if requestedField and requestedField not in SORTABLE_COLUMNS:
            raise ValidationFailedError(
                "Field is not sortable.", fieldErrors={"ordering": requestedField}
            )
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
        return ProjectPage(items=items, totalCount=totalCount)

    @staticmethod
    def toDomain(model: ProjectModel) -> Project:
        return Project(
            id=model.id,
            tenantId=model.tenantId,
            code=ProjectCode(model.code),
            name=model.name,
            description=model.description,
            status=ProjectStatus(model.status),
            health=model.health,
            progress=model.progress,
            ownerName=model.ownerName,
            dueDate=model.dueDate,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )

    @staticmethod
    def toModelFields(project: Project) -> dict[str, Any]:  # pragma: no cover — helper
        return {
            "id": project.id,
            "tenantId": project.tenantId,
            "code": str(project.code),
            "name": project.name,
        }
