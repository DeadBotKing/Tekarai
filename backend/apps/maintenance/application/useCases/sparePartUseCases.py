"""Inventory and work-order spare-part consumption use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from apps.maintenance.application.commands.sparePartCommands import (
    ConsumeSparePartCommand,
    CreateSparePartCommand,
    ListPartTransactionsQuery,
    ListSparePartsQuery,
    ListWorkOrderPartUsageQuery,
    RecordPartTransactionCommand,
    UpdateSparePartCommand,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.sparePart import (
    PART_TRANSACTION_ADJUSTMENT,
    PART_TRANSACTION_ISSUE,
    PART_TRANSACTION_RECEIPT,
    PART_TRANSACTION_TYPES,
    PartTransaction,
    SparePart,
    WorkOrderPartUsage,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import SparePartRepository
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import (
    AUDIT_CREATE,
    AUDIT_UPDATE,
    UseCase,
)
from apps.sharedKernel.domain.errors import ValidationFailedError


@dataclass(frozen=True)
class SparePartDto:
    id: str
    code: str
    name: str
    unit: str
    quantityOnHand: str
    minimumStock: str
    unitCost: str
    lowStock: bool
    createdAt: str
    updatedAt: str = ""
    reorderQuantity: str = "0"
    autoReorder: bool = True


@dataclass(frozen=True)
class SparePartListDto:
    items: list[SparePartDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass(frozen=True)
class WorkOrderPartUsageDto:
    id: str
    workOrderId: str
    partId: str
    partCode: str
    partName: str
    unit: str
    quantity: str
    unitCost: str
    totalCost: str
    note: str
    consumedAt: str


@dataclass(frozen=True)
class WorkOrderPartUsageListDto:
    items: list[WorkOrderPartUsageDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def _decimal(value: str, field: str, *, positive: bool = False) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, ValueError) as error:
        raise ValidationFailedError("Invalid quantity.", fieldErrors={field: "invalid"}) from error
    if (positive and parsed <= 0) or (not positive and parsed < 0):
        raise ValidationFailedError(
            "Quantity is outside the allowed range.", fieldErrors={field: "invalid"}
        )
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -3:
        raise ValidationFailedError(
            "At most three decimal places are allowed.", fieldErrors={field: "precision"}
        )
    return parsed


def _moneyValue(value: str, field: str) -> Decimal:
    """Price amounts: non-negative, at most two decimal places."""
    parsed = _decimal(value, field)
    exponent = parsed.as_tuple().exponent
    if isinstance(exponent, int) and exponent < -2:
        raise ValidationFailedError(
            "At most two decimal places are allowed.", fieldErrors={field: "precision"}
        )
    return parsed


def _partDto(part: SparePart) -> SparePartDto:
    return SparePartDto(
        id=str(part.id),
        code=part.code,
        name=part.name,
        unit=part.unit,
        quantityOnHand=str(part.quantityOnHand),
        minimumStock=str(part.minimumStock),
        unitCost=str(part.unitCost),
        lowStock=part.lowStock,
        reorderQuantity=str(part.reorderQuantity),
        autoReorder=part.autoReorder,
        createdAt=part.createdAt.isoformat(),
        updatedAt=part.updatedAt.isoformat() if part.updatedAt else "",
    )


def _usageDto(usage: WorkOrderPartUsage) -> WorkOrderPartUsageDto:
    return WorkOrderPartUsageDto(
        id=str(usage.id),
        workOrderId=str(usage.workOrderId),
        partId=str(usage.partId),
        partCode=usage.partCode,
        partName=usage.partName,
        unit=usage.unit,
        quantity=str(usage.quantity),
        unitCost=str(usage.unitCost),
        totalCost=str(usage.totalCost),
        note=usage.note,
        consumedAt=usage.consumedAt.isoformat(),
    )


class SparePartUseCaseBase(UseCase):
    def __init__(self, repository: SparePartRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.repository = repository


class CreateSparePartUseCase(SparePartUseCaseBase):
    requiredAction = "maintenance.inventory.manage"

    def perform(self, command: CreateSparePartCommand) -> SparePartDto:
        if not command.code.strip() or not command.name.strip():
            raise ValidationFailedError(
                "Part code and name are required.",
                fieldErrors={"code": "required", "name": "required"},
            )
        tenantId = resolveTenantId("")
        part = self.repository.create(
            tenantId,
            command.code,
            command.name,
            command.unit,
            _decimal(command.quantityOnHand, "quantityOnHand"),
            _decimal(command.minimumStock, "minimumStock"),
            _moneyValue(command.unitCost, "unitCost"),
            reorderQuantity=_decimal(command.reorderQuantity, "reorderQuantity"),
            autoReorder=bool(command.autoReorder),
        )
        self.audit(AUDIT_CREATE, "SparePart", str(part.id), tenantId, after=_partDto(part).__dict__)
        return _partDto(part)


class UpdateSparePartUseCase(SparePartUseCaseBase):
    requiredAction = "maintenance.inventory.manage"

    def perform(self, command: UpdateSparePartCommand) -> SparePartDto:
        if not command.name.strip():
            raise ValidationFailedError("Part name is required.", fieldErrors={"name": "required"})
        tenantId = resolveTenantId("")
        part = self.repository.update(
            tenantId,
            uuid.UUID(command.partId),
            command.name,
            command.unit,
            _decimal(command.quantityOnHand, "quantityOnHand"),
            _decimal(command.minimumStock, "minimumStock"),
            _moneyValue(command.unitCost, "unitCost"),
            reorderQuantity=_decimal(command.reorderQuantity, "reorderQuantity"),
            autoReorder=bool(command.autoReorder),
        )
        self.audit(AUDIT_UPDATE, "SparePart", str(part.id), tenantId, after=_partDto(part).__dict__)
        return _partDto(part)


class ListSparePartsUseCase(SparePartUseCaseBase):
    requiredAction = "maintenance.inventory.view"

    def perform(self, query: ListSparePartsQuery) -> SparePartListDto:
        items = [_partDto(item) for item in self.repository.list(resolveTenantId(""), query.search)]
        return SparePartListDto(items=items, totalCount=len(items))


class ConsumeSparePartUseCase(SparePartUseCaseBase):
    requiredAction = "maintenance.inventory.consume"

    def perform(self, command: ConsumeSparePartCommand) -> WorkOrderPartUsageDto:
        tenantId = resolveTenantId("")
        usage = self.repository.consume(
            tenantId,
            uuid.UUID(command.workOrderId),
            uuid.UUID(command.partId),
            _decimal(command.quantity, "quantity", positive=True),
            command.note,
            self.clock.nowUtc(),
        )
        self.audit(
            AUDIT_UPDATE,
            "WorkOrderPartUsage",
            str(usage.id),
            tenantId,
            after=_usageDto(usage).__dict__,
        )
        return _usageDto(usage)


class ListWorkOrderPartUsageUseCase(SparePartUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListWorkOrderPartUsageQuery) -> WorkOrderPartUsageListDto:
        items = [
            _usageDto(item)
            for item in self.repository.listUsage(resolveTenantId(""), uuid.UUID(query.workOrderId))
        ]
        return WorkOrderPartUsageListDto(items=items, totalCount=len(items))


# ---------- دفتر تراکنش انبار ----------

_TRANSACTION_FA = {
    PART_TRANSACTION_RECEIPT: "رسید",
    PART_TRANSACTION_ISSUE: "حواله",
    "RETURN": "برگشت",
    PART_TRANSACTION_ADJUSTMENT: "تعدیل",
}


@dataclass(frozen=True)
class PartTransactionDto:
    id: str
    partId: str
    partCode: str
    partName: str
    unit: str
    transactionType: str
    typeLabel: str
    quantity: str
    balanceAfter: str
    note: str
    reference: str
    actorId: str
    createdAt: str


@dataclass(frozen=True)
class PartTransactionListDto:
    items: list[PartTransactionDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def _transactionDto(row: PartTransaction) -> PartTransactionDto:
    return PartTransactionDto(
        id=str(row.id),
        partId=str(row.partId),
        partCode=row.partCode,
        partName=row.partName,
        unit=row.unit,
        transactionType=row.transactionType,
        typeLabel=_TRANSACTION_FA.get(row.transactionType, row.transactionType),
        quantity=str(row.quantity),
        balanceAfter=str(row.balanceAfter),
        note=row.note,
        reference=row.reference,
        actorId=str(row.actorId) if row.actorId else "",
        createdAt=row.createdAt.isoformat(),
    )


class RecordPartTransactionUseCase(SparePartUseCaseBase):
    """رسید/حواله/برگشت/تعدیل — ثبت در دفتر و به‌روزرسانی اتمیک موجودی."""

    requiredAction = "maintenance.inventory.manage"

    def perform(self, command: RecordPartTransactionCommand) -> PartTransactionDto:
        tenantId = resolveTenantId("")
        transactionType = command.transactionType.upper().strip()
        if transactionType not in PART_TRANSACTION_TYPES:
            raise ValidationFailedError(
                "نوع تراکنش نامعتبر است.", fieldErrors={"transactionType": "invalid"}
            )
        amount = _decimal(command.quantity, "quantity")
        if amount == 0:
            raise ValidationFailedError(
                "مقدار تراکنش نمی‌تواند صفر باشد.", fieldErrors={"quantity": "invalid"}
            )
        # علامت از نوع تراکنش مشتق می‌شود؛ کاربر فقط قدرمطلق را می‌فرستد.
        # تعدیل (انبارگردانی) تنها نوعی است که علامت‌دار پذیرفته می‌شود.
        if transactionType == PART_TRANSACTION_ISSUE:
            signed = -abs(amount)
        elif transactionType == PART_TRANSACTION_ADJUSTMENT:
            signed = amount
        else:
            signed = abs(amount)
        actorId = uuid.UUID(currentContext().actorId) if currentContext().actorId else None
        row = self.repository.recordTransaction(
            tenantId,
            uuid.UUID(command.partId),
            transactionType,
            signed,
            command.note.strip(),
            command.reference.strip(),
            actorId,
            self.clock.nowUtc(),
        )
        self.audit(
            AUDIT_CREATE,
            "PartTransaction",
            str(row.id),
            tenantId,
            after=_transactionDto(row).__dict__,
        )
        return _transactionDto(row)


class ListPartTransactionsUseCase(SparePartUseCaseBase):
    requiredAction = "maintenance.inventory.view"

    def perform(self, query: ListPartTransactionsQuery) -> PartTransactionListDto:
        tenantId = resolveTenantId("")
        partId = uuid.UUID(query.partId) if query.partId.strip() else None
        items = [_transactionDto(row) for row in self.repository.listTransactions(tenantId, partId)]
        return PartTransactionListDto(items=items, totalCount=len(items))
