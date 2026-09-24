"""Transactional Django repository for spare-parts inventory."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.maintenance.domain.entities.sparePart import SparePart, WorkOrderPartUsage
from apps.maintenance.infrastructure.models import (
    SparePartModel,
    WorkOrderModel,
    WorkOrderPartUsageModel,
)
from apps.sharedKernel.domain.errors import (
    ConflictError,
    DuplicateBusinessCodeError,
    EntityNotFoundError,
)


class SparePartRepositoryDjango:
    @staticmethod
    def _part(model: SparePartModel) -> SparePart:
        return SparePart(
            id=model.id,
            tenantId=model.tenantId,
            code=model.code,
            name=model.name,
            unit=model.unit,
            quantityOnHand=model.quantityOnHand,
            minimumStock=model.minimumStock,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
        )

    @staticmethod
    def _usage(model: WorkOrderPartUsageModel) -> WorkOrderPartUsage:
        return WorkOrderPartUsage(
            id=model.id,
            tenantId=model.tenantId,
            workOrderId=model.workOrderId,
            partId=model.partId,
            partCode=model.partCode,
            partName=model.partName,
            unit=model.unit,
            quantity=model.quantity,
            note=model.note,
            consumedAt=model.consumedAt,
        )

    def create(
        self,
        tenantId: uuid.UUID,
        code: str,
        name: str,
        unit: str,
        quantityOnHand: Decimal,
        minimumStock: Decimal,
    ) -> SparePart:
        try:
            model = SparePartModel.objects.create(
                tenantId=tenantId,
                code=code.strip().upper(),
                name=name.strip(),
                unit=unit.strip() or "عدد",
                quantityOnHand=quantityOnHand,
                minimumStock=minimumStock,
            )
        except IntegrityError as error:
            raise DuplicateBusinessCodeError("Spare-part code already exists.") from error
        return self._part(model)

    def update(
        self,
        tenantId: uuid.UUID,
        partId: uuid.UUID,
        name: str,
        unit: str,
        quantityOnHand: Decimal,
        minimumStock: Decimal,
    ) -> SparePart:
        with transaction.atomic():
            model = (
                SparePartModel.objects.select_for_update()
                .filter(id=partId, tenantId=tenantId, deletedAt__isnull=True)
                .first()
            )
            if model is None:
                raise EntityNotFoundError("SparePart", str(partId))
            model.name = name.strip()
            model.unit = unit.strip() or "عدد"
            model.quantityOnHand = quantityOnHand
            model.minimumStock = minimumStock
            model.updatedAt = datetime.now().astimezone()
            model.save(
                update_fields=["name", "unit", "quantityOnHand", "minimumStock", "updatedAt"]
            )
        return self._part(model)

    def list(self, tenantId: uuid.UUID, search: str = "") -> list[SparePart]:
        queryset = SparePartModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if search.strip():
            queryset = queryset.filter(
                Q(code__icontains=search.strip()) | Q(name__icontains=search.strip())
            )
        return [self._part(item) for item in queryset.order_by("code")]

    def consume(
        self,
        tenantId: uuid.UUID,
        workOrderId: uuid.UUID,
        partId: uuid.UUID,
        quantity: Decimal,
        note: str,
        consumedAt: datetime,
    ) -> WorkOrderPartUsage:
        with transaction.atomic():
            if not WorkOrderModel.objects.filter(
                id=workOrderId, tenantId=tenantId, deletedAt__isnull=True
            ).exists():
                raise EntityNotFoundError("WorkOrder", str(workOrderId))
            part = (
                SparePartModel.objects.select_for_update()
                .filter(id=partId, tenantId=tenantId, deletedAt__isnull=True)
                .first()
            )
            if part is None:
                raise EntityNotFoundError("SparePart", str(partId))
            if part.quantityOnHand < quantity:
                raise ConflictError(
                    "Insufficient spare-part stock.",
                    details={
                        "partId": str(part.id),
                        "available": str(part.quantityOnHand),
                        "requested": str(quantity),
                    },
                )
            part.quantityOnHand -= quantity
            part.updatedAt = consumedAt
            part.save(update_fields=["quantityOnHand", "updatedAt"])
            usage = WorkOrderPartUsageModel.objects.create(
                tenantId=tenantId,
                workOrderId=workOrderId,
                partId=part.id,
                partCode=part.code,
                partName=part.name,
                unit=part.unit,
                quantity=quantity,
                note=note.strip(),
                consumedAt=consumedAt,
            )
        return self._usage(usage)

    def listUsage(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID
    ) -> list[WorkOrderPartUsage]:
        if not WorkOrderModel.objects.filter(
            id=workOrderId, tenantId=tenantId, deletedAt__isnull=True
        ).exists():
            raise EntityNotFoundError("WorkOrder", str(workOrderId))
        rows = WorkOrderPartUsageModel.objects.filter(
            tenantId=tenantId, workOrderId=workOrderId
        ).order_by("-consumedAt")
        return [self._usage(item) for item in rows]
