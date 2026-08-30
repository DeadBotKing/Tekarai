"""ORM implementation of TenantRepository (Phase 06 §10 rule 5).

Maps between the pure domain aggregate and ``TenantModel``; all tenant
uniqueness goes through the database constraint (UQG_Tenant_code), mapped
to ``DuplicateBusinessCodeError`` for predictable error codes.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from django.db import IntegrityError

from apps.sharedKernel.domain.errors import DuplicateBusinessCodeError
from apps.tenancy.domain.entities.tenant import Tenant
from apps.tenancy.domain.repositories.tenantRepository import (
    TenantFilters,
    TenantPage,
)
from apps.tenancy.domain.valueObjects.tenantState import TenantCode, TenantStatus
from apps.tenancy.infrastructure.models import TenantModel

SORTABLE_COLUMNS = {
    "createdAt": "createdAt",
    "name": "name",
    "code": "code",
    "status": "status",
}


class TenantRepositoryDjango:
    def create(self, tenant: Tenant) -> None:
        try:
            TenantModel.objects.create(
                id=tenant.id,
                code=str(tenant.code),
                name=tenant.name,
                status=str(tenant.status),
                createdAt=tenant.createdAt,
            )
        except IntegrityError as exc:
            raise DuplicateBusinessCodeError(
                "Tenant code already exists.",
                details={"ruleId": "BR-TEN-004"},
            ) from exc

    def update(self, tenant: Tenant) -> None:
        TenantModel.objects.filter(id=tenant.id).update(
            name=tenant.name,
            status=str(tenant.status),
            updatedAt=tenant.updatedAt or datetime.now(tz=None),
        )

    def getById(self, tenantId: uuid.UUID) -> Tenant | None:
        model = TenantModel.objects.filter(id=tenantId, deletedAt__isnull=True).first()
        return self.toDomain(model) if model else None

    def getByCode(self, code: str) -> Tenant | None:
        model = TenantModel.objects.filter(code=code, deletedAt__isnull=True).first()
        return self.toDomain(model) if model else None

    def existsByCode(self, code: str) -> bool:
        return TenantModel.objects.filter(code=code, deletedAt__isnull=True).exists()

    def list(self, filters: TenantFilters) -> TenantPage:
        queryset = TenantModel.objects.filter(deletedAt__isnull=True)
        if filters.status:
            queryset = queryset.filter(status=filters.status)
        if filters.search:
            from django.db.models import Q

            queryset = queryset.filter(
                Q(name__icontains=filters.search) | Q(code__icontains=filters.search)
            )
        requestedField = filters.ordering.lstrip("-").split(",")[0].strip()
        if requestedField and requestedField not in SORTABLE_COLUMNS:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Field is not sortable.",
                fieldErrors={"ordering": requestedField},
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
        return TenantPage(items=items, totalCount=totalCount)

    @staticmethod
    def toDomain(model: TenantModel) -> Tenant:
        return Tenant(
            id=model.id,
            code=TenantCode(model.code),
            name=model.name,
            status=TenantStatus(model.status),
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )

    @staticmethod
    def toModelFields(tenant: Tenant) -> dict[str, Any]:  # pragma: no cover — helper
        return {"id": tenant.id, "code": str(tenant.code), "name": tenant.name}
