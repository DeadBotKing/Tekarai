"""Inventory and work-order spare-part consumption use cases."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation

from apps.maintenance.application.commands.sparePartCommands import (
    ConsumeSparePartCommand,
    CreateSparePartCommand,
    ListSparePartsQuery,
    ListWorkOrderPartUsageQuery,
    UpdateSparePartCommand,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.sparePart import SparePart, WorkOrderPartUsage
from apps.maintenance.domain.repositories.maintenanceRepositories import SparePartRepository
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import ValidationFailedError


@dataclass(frozen=True)
class SparePartDto:
    id: str
    code: str
    name: str
    unit: str
    quantityOnHand: str
    minimumStock: str
    lowStock: bool
    createdAt: str
    updatedAt: str = ""


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
        raise ValidationFailedError(
            "Invalid quantity.", fieldErrors={field: "invalid"}
        ) from error
    if (positive and parsed <= 0) or (not positive and parsed < 0):
        raise ValidationFailedError(
            "Quantity is outside the allowed range.", fieldErrors={field: "invalid"}
        )
    if parsed.as_tuple().exponent < -3:
        raise ValidationFailedError(
            "At most three decimal places are allowed.", fieldErrors={field: "precision"}
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
        lowStock=part.lowStock,
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
            for item in self.repository.listUsage(
                resolveTenantId(""), uuid.UUID(query.workOrderId)
            )
        ]
        return WorkOrderPartUsageListDto(items=items, totalCount=len(items))
