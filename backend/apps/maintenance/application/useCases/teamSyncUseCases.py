"""Use cases — رزرو قطعات تیمی + قالب‌ها/سوابق چک‌لیست بازرسی."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

from apps.maintenance.application.commands.teamSyncCommands import (
    CloseReservationCommand,
    CommitInspectionTemplateCommand,
    DeleteInspectionTemplateCommand,
    ListInspectionRecordsQuery,
    ListInspectionTemplatesQuery,
    ListReservationsQuery,
    SaveInspectionRecordCommand,
    SaveInspectionTemplateCommand,
    SaveReservationCommand,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.teamSync import (
    InspectionRecord,
    InspectionTemplate,
    PartReservation,
)
from apps.maintenance.domain.repositories.maintenanceRepositories import (
    InspectionSyncRepository,
    PartReservationRepository,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import ValidationFailedError


@dataclass(frozen=True)
class PartReservationDto:
    id: str
    orderId: str
    partCode: str
    quantity: str
    status: str
    at: str


@dataclass(frozen=True)
class PartReservationListDto:
    items: list[PartReservationDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass(frozen=True)
class InspectionTemplateDto:
    id: str
    name: str
    checks: list[str]
    description: str
    deviceCode: str
    isCommitted: bool


@dataclass(frozen=True)
class InspectionTemplateListDto:
    items: list[InspectionTemplateDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


@dataclass(frozen=True)
class InspectionRecordDto:
    id: str
    templateId: str
    workOrderId: str
    deviceId: str
    passedChecks: list[str]
    failedChecks: list[str]
    performedByName: str
    at: str


@dataclass(frozen=True)
class InspectionRecordListDto:
    items: list[InspectionRecordDto] = field(default_factory=list)
    totalCount: int = 0

    def asMeta(self) -> dict[str, object]:
        return {"totalCount": self.totalCount}


def _reservationDto(reservation: PartReservation) -> PartReservationDto:
    return PartReservationDto(
        id=reservation.id,
        orderId=str(reservation.workOrderId),
        partCode=reservation.partCode,
        quantity=str(reservation.quantity),
        status=reservation.status,
        at=reservation.createdAt,
    )


def _templateDto(template: InspectionTemplate) -> InspectionTemplateDto:
    return InspectionTemplateDto(
        id=template.id,
        name=template.name,
        checks=list(template.checks),
        description=template.description,
        deviceCode=template.deviceCode,
        isCommitted=template.isCommitted,
    )


def _recordDto(record: InspectionRecord) -> InspectionRecordDto:
    return InspectionRecordDto(
        id=record.id,
        templateId=record.templateId,
        workOrderId=str(record.workOrderId) if record.workOrderId else "",
        deviceId=str(record.deviceId),
        passedChecks=list(record.passedChecks),
        failedChecks=list(record.failedChecks),
        performedByName=record.performedByName,
        at=record.createdAt,
    )


def _quantity(value: str) -> Decimal:
    try:
        parsed = Decimal(str(value))
    except Exception as exc:  # noqa: BLE001 — decimal.InvalidOperation surfaced as validation
        raise ValidationFailedError("quantity must be numeric") from exc
    if parsed <= 0:
        raise ValidationFailedError("quantity must be positive")
    return parsed


def _uuid(value: str, field: str) -> uuid.UUID:
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise ValidationFailedError(f"{field} is not a valid id") from exc


# --------------------------- reservations ---------------------------


class ReservationUseCaseBase(UseCase):
    def __init__(self, repository: PartReservationRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.repository = repository


class ListReservationsUseCase(ReservationUseCaseBase):
    requiredAction = "maintenance.inventory.view"

    def perform(self, query: ListReservationsQuery) -> PartReservationListDto:
        tenantId = resolveTenantId("")
        workOrderId = _uuid(query.workOrderId, "workOrderId") if query.workOrderId else None
        items = [
            _reservationDto(item) for item in self.repository.listForTenant(tenantId, workOrderId)
        ]
        return PartReservationListDto(items=items, totalCount=len(items))


class SaveReservationUseCase(ReservationUseCaseBase):
    requiredAction = "maintenance.inventory.consume"

    def perform(self, command: SaveReservationCommand) -> PartReservationDto:
        tenantId = resolveTenantId("")
        saved = self.repository.upsert(
            PartReservation(
                id=command.id,
                tenantId=tenantId,
                workOrderId=_uuid(command.workOrderId, "workOrderId"),
                partCode=command.partCode.strip(),
                quantity=_quantity(command.quantity),
                status=command.status
                if command.status in ("active", "consumed", "released")
                else "active",
                reservedByName=command.reservedByName,
                createdAt="",
            )
        )
        self.audit(
            AUDIT_UPDATE,
            "PartReservation",
            saved.id,
            tenantId,
            after=_reservationDto(saved).__dict__,
        )
        return _reservationDto(saved)


class CloseReservationUseCase(ReservationUseCaseBase):
    requiredAction = "maintenance.inventory.consume"

    def perform(self, command: CloseReservationCommand) -> PartReservationDto:
        tenantId = resolveTenantId("")
        if command.status not in ("consumed", "released"):
            raise ValidationFailedError("status must be consumed or released")
        result = self.repository.close(
            tenantId, command.reservationId, command.status, self.clock.nowUtc()
        )
        if result is None:
            raise ValidationFailedError("Reservation not found")
        self.audit(
            AUDIT_UPDATE,
            "PartReservation",
            result.id,
            tenantId,
            after=_reservationDto(result).__dict__,
        )
        return _reservationDto(result)


# --------------------------- inspections ---------------------------


class InspectionUseCaseBase(UseCase):
    def __init__(self, repository: InspectionSyncRepository, **kwargs) -> None:
        super().__init__(**kwargs)
        self.repository = repository


class ListInspectionTemplatesUseCase(InspectionUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListInspectionTemplatesQuery) -> InspectionTemplateListDto:
        tenantId = resolveTenantId("")
        items = [_templateDto(item) for item in self.repository.listTemplates(tenantId)]
        return InspectionTemplateListDto(items=items, totalCount=len(items))


class SaveInspectionTemplateUseCase(InspectionUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def perform(self, command: SaveInspectionTemplateCommand) -> InspectionTemplateDto:
        tenantId = resolveTenantId("")
        name = command.name.strip()
        if not name:
            raise ValidationFailedError("name is required")
        checks = [check.strip() for check in command.checks if check.strip()]
        # قالب‌های جدید از همان لحظه قابل اجرا هستند؛ «قفل» فقط برای گردش‌کارهای
        # آینده است تا قالب‌های تثبیت‌شده دیگر ویرایش نشوند.
        existing = self.repository.getTemplate(tenantId, command.id)
        saved = self.repository.upsertTemplate(
            InspectionTemplate(
                id=command.id,
                tenantId=tenantId,
                name=name,
                description=command.description.strip(),
                deviceCode=command.deviceCode.strip(),
                checks=tuple(checks),
                isCommitted=existing.isCommitted if existing else True,
            )
        )
        self.audit(
            AUDIT_CREATE,
            "InspectionTemplate",
            saved.id,
            tenantId,
            after=_templateDto(saved).__dict__,
        )
        return _templateDto(saved)


class CommitInspectionTemplateUseCase(InspectionUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def perform(self, command: CommitInspectionTemplateCommand) -> InspectionTemplateDto:
        tenantId = resolveTenantId("")
        result = self.repository.commitTemplate(tenantId, command.templateId)
        if result is None:
            raise ValidationFailedError("Template not found")
        self.audit(
            AUDIT_UPDATE,
            "InspectionTemplate",
            result.id,
            tenantId,
            after=_templateDto(result).__dict__,
        )
        return _templateDto(result)


class ListInspectionRecordsUseCase(InspectionUseCaseBase):
    requiredAction = "maintenance.workorder.view"

    def perform(self, query: ListInspectionRecordsQuery) -> InspectionRecordListDto:
        tenantId = resolveTenantId("")
        workOrderId = _uuid(query.workOrderId, "workOrderId") if query.workOrderId else None
        items = [_recordDto(item) for item in self.repository.listRecords(tenantId, workOrderId)]
        return InspectionRecordListDto(items=items, totalCount=len(items))


class SaveInspectionRecordUseCase(InspectionUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def perform(self, command: SaveInspectionRecordCommand) -> InspectionRecordDto:
        tenantId = resolveTenantId("")
        template = self.repository.getTemplate(tenantId, command.templateId)
        if template is None:
            raise ValidationFailedError("Template not found")
        if not template.isCommitted:
            raise ValidationFailedError("Template must be committed before recording inspections")
        saved = self.repository.createRecord(
            InspectionRecord(
                id=command.id,
                tenantId=tenantId,
                templateId=command.templateId,
                workOrderId=(
                    _uuid(command.workOrderId, "workOrderId") if command.workOrderId else None
                ),
                deviceId=_uuid(command.deviceId, "deviceId"),
                passedChecks=tuple(command.passedChecks),
                failedChecks=tuple(command.failedChecks),
                performedByName=command.performedByName,
                createdAt="",
            )
        )
        self.audit(
            AUDIT_CREATE, "InspectionRecord", saved.id, tenantId, after=_recordDto(saved).__dict__
        )
        return _recordDto(saved)


class DeleteInspectionTemplateUseCase(InspectionUseCaseBase):
    requiredAction = "maintenance.workorder.update"

    def perform(self, command: DeleteInspectionTemplateCommand) -> str:
        tenantId = resolveTenantId("")
        if not self.repository.deleteTemplate(tenantId, command.templateId):
            raise ValidationFailedError("Template not found")
        self.audit(AUDIT_UPDATE, "InspectionTemplate", command.templateId, tenantId)
        return command.templateId
