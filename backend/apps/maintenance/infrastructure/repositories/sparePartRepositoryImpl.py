"""Transactional Django repository for spare-parts inventory."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.db.models import Q

from apps.maintenance.domain.entities.sparePart import (
    PartTransaction,
    SparePart,
    WorkOrderPartUsage,
)
from apps.maintenance.infrastructure.models import (
    PartTransactionModel,
    SparePartModel,
    WorkOrderModel,
    WorkOrderPartUsageModel,
)
from apps.sharedKernel.domain.errors import (
    ConflictError,
    DuplicateBusinessCodeError,
    EntityNotFoundError,
    ValidationFailedError,
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
            unitCost=model.unitCost,
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
            unitCost=model.unitCost,
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
        unitCost: Decimal,
    ) -> SparePart:
        try:
            model = SparePartModel.objects.create(
                tenantId=tenantId,
                code=code.strip().upper(),
                name=name.strip(),
                unit=unit.strip() or "عدد",
                quantityOnHand=quantityOnHand,
                minimumStock=minimumStock,
                unitCost=unitCost,
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
        unitCost: Decimal,
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
            model.unitCost = unitCost
            model.updatedAt = datetime.now().astimezone()
            model.save(
                update_fields=[
                    "name",
                    "unit",
                    "quantityOnHand",
                    "minimumStock",
                    "unitCost",
                    "updatedAt",
                ]
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
                # Snapshot the current price: later price edits must not
                # rewrite the maintenance cost history of closed orders.
                unitCost=part.unitCost,
                note=note.strip(),
                consumedAt=consumedAt,
            )
            self._rollupWorkOrderPartsCost(tenantId, workOrderId)
        return self._usage(usage)

    @staticmethod
    def _rollupWorkOrderPartsCost(tenantId: uuid.UUID, workOrderId: uuid.UUID) -> None:
        """Rewrite the work order's cached parts cost from its usage rows."""
        total = Decimal("0")
        rows = WorkOrderPartUsageModel.objects.filter(
            tenantId=tenantId, workOrderId=workOrderId
        ).values_list("quantity", "unitCost")
        for quantity, unitCost in rows:
            total += quantity * unitCost
        WorkOrderModel.objects.filter(id=workOrderId, tenantId=tenantId).update(
            partsCost=total.quantize(Decimal("0.01")),
            updatedAt=datetime.now().astimezone(),
        )

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


    # ---------- دفتر تراکنش انبار ----------

    @staticmethod
    def _transaction(model: PartTransactionModel) -> PartTransaction:
        return PartTransaction(
            id=model.id,
            tenantId=model.tenantId,
            partId=model.partId,
            partCode=model.partCode,
            partName=model.partName,
            unit=model.unit,
            transactionType=model.transactionType,
            quantity=model.quantity,
            balanceAfter=model.balanceAfter,
            note=model.note,
            reference=model.reference,
            actorId=model.actorId,
            createdAt=model.createdAt,
        )

    def getById(self, tenantId: uuid.UUID, partId: uuid.UUID) -> SparePart:
        model = SparePartModel.objects.filter(
            tenantId=tenantId, id=partId, deletedAt__isnull=True
        ).first()
        if model is None:
            raise EntityNotFoundError("Spare part not found.")
        return self._part(model)

    def recordTransaction(
        self,
        tenantId: uuid.UUID,
        partId: uuid.UUID,
        transactionType: str,
        quantity: Decimal,
        note: str,
        reference: str,
        actorId: uuid.UUID | None,
        at: datetime,
    ) -> PartTransaction:
        """ثبت اتمیک تراکنش — موجودی با قفل سطر به‌روز می‌شود تا دو ثبت هم‌زمان
        هرگز موجودی منفی یا مانده‌ی نادرست نسازند."""
        with transaction.atomic():
            part = (
                SparePartModel.objects.select_for_update()
                .filter(tenantId=tenantId, id=partId, deletedAt__isnull=True)
                .first()
            )
            if part is None:
                raise EntityNotFoundError("Spare part not found.")
            balance = part.quantityOnHand + quantity
            if balance < 0:
                raise ValidationFailedError(
                    "موجودی برای این تراکنش کافی نیست.",
                    fieldErrors={"quantity": "insufficient-stock"},
                )
            part.quantityOnHand = balance
            part.updatedAt = at
            part.save(update_fields=["quantityOnHand", "updatedAt"])
            model = PartTransactionModel.objects.create(
                tenantId=tenantId,
                partId=part.id,
                partCode=part.code,
                partName=part.name,
                unit=part.unit,
                transactionType=transactionType,
                quantity=quantity,
                balanceAfter=balance,
                note=note,
                reference=reference,
                actorId=actorId,
            )
        return self._transaction(model)

    def listTransactions(
        self, tenantId: uuid.UUID, partId: uuid.UUID | None = None
    ) -> list[PartTransaction]:
        rows = PartTransactionModel.objects.filter(tenantId=tenantId)
        if partId is not None:
            rows = rows.filter(partId=partId)
        return [self._transaction(model) for model in rows[:400]]
