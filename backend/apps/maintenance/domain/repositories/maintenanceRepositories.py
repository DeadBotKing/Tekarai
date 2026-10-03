"""Maintenance repository contracts (Phase 21).

Devices and WorkOrders are separate aggregates in the same bounded context.
Each has its own repository protocol; both stay tenant-scoped.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime  # noqa: TC003 — used in dataclass field annotations
from decimal import Decimal  # noqa: TC003 — used in protocol annotations
from typing import Protocol, runtime_checkable

from apps.maintenance.domain.entities.device import Device
from apps.maintenance.domain.entities.deviceHistory import DeviceHistoryEntry
from apps.maintenance.domain.entities.labourEntry import LabourEntry
from apps.maintenance.domain.entities.maintenanceAttachment import MaintenanceAttachment
from apps.maintenance.domain.entities.sparePart import SparePart, WorkOrderPartUsage
from apps.maintenance.domain.entities.workOrder import WorkOrder
from apps.maintenance.domain.entities.workOrderHistory import WorkOrderHistoryEntry
from apps.maintenance.domain.services.maintenanceCosting import (
    LabourCostReading,
    WorkOrderCostReading,
)


@dataclass(frozen=True)
class DeviceFilters:
    tenantId: uuid.UUID
    status: str = ""
    department: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class DevicePage:
    items: list[Device]
    totalCount: int


@dataclass(frozen=True)
class WorkOrderFilters:
    tenantId: uuid.UUID
    deviceId: str = ""
    status: str = ""
    orderType: str = ""
    priority: str = ""
    department: str = ""
    search: str = ""
    ordering: str = "-createdAt"
    page: int = 1
    pageSize: int = 50
    # Optional inclusive creation-date bounds (aware datetimes); Phase 23.
    createdFrom: datetime | None = None
    createdTo: datetime | None = None


@dataclass(frozen=True)
class WorkOrderPage:
    items: list[WorkOrder]
    totalCount: int


@dataclass(frozen=True)
class WorkOrderAlertRow:
    """Flat row read by the scheduled alert scan — intentionally NOT the
    WorkOrder aggregate: legacy rows (old vocabularies) must not break an
    ops cron job; the scan only reads raw status/priority strings."""

    id: uuid.UUID
    deviceId: uuid.UUID
    tenantId: uuid.UUID
    title: str
    status: str
    priority: str
    department: str
    createdAt: datetime


@runtime_checkable
class DeviceRepository(Protocol):
    def create(self, device: Device) -> None: ...

    def update(self, device: Device) -> None: ...

    def getById(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> Device | None: ...

    def getByCode(self, tenantId: uuid.UUID, code: str) -> Device | None: ...

    def countByTenant(self, tenantId: uuid.UUID) -> int: ...

    def listDueForPm(self, tenantId: uuid.UUID) -> list[Device]: ...

    def list(self, filters: DeviceFilters) -> DevicePage: ...


@runtime_checkable
class WorkOrderRepository(Protocol):
    def create(self, order: WorkOrder) -> None: ...

    def update(self, order: WorkOrder) -> None: ...

    def getById(self, tenantId: uuid.UUID, orderId: uuid.UUID) -> WorkOrder | None: ...

    def countByTenant(self, tenantId: uuid.UUID) -> int: ...

    def countOpenByTenant(self, tenantId: uuid.UUID) -> int: ...

    def hasOpenPreventiveOrder(self, tenantId: uuid.UUID, deviceId: uuid.UUID) -> bool: ...

    def countOpenByAssignee(self, tenantId: uuid.UUID, department: str) -> dict[str, int]: ...

    def list(self, filters: WorkOrderFilters) -> WorkOrderPage: ...

    def listAlertRows(self, tenantId: uuid.UUID) -> list[WorkOrderAlertRow]: ...


@runtime_checkable
class MaintenanceAttachmentRepository(Protocol):
    def targetExists(
        self, tenantId: uuid.UUID, targetType: str, targetId: uuid.UUID
    ) -> bool: ...

    def create(
        self,
        tenantId: uuid.UUID,
        targetType: str,
        targetId: uuid.UUID,
        category: str,
        originalName: str,
        mimeType: str,
        sizeBytes: int,
        uploadedFile: object,
    ) -> MaintenanceAttachment: ...

    def listForTarget(
        self, tenantId: uuid.UUID, targetType: str, targetId: uuid.UUID
    ) -> list[MaintenanceAttachment]: ...

    def getById(
        self, tenantId: uuid.UUID, attachmentId: uuid.UUID
    ) -> MaintenanceAttachment | None: ...

    def openFile(self, tenantId: uuid.UUID, attachmentId: uuid.UUID) -> object: ...

    def delete(self, tenantId: uuid.UUID, attachmentId: uuid.UUID, deletedAt: datetime) -> None: ...


@runtime_checkable
class SparePartRepository(Protocol):
    def create(
        self,
        tenantId: uuid.UUID,
        code: str,
        name: str,
        unit: str,
        quantityOnHand: Decimal,
        minimumStock: Decimal,
        unitCost: Decimal,
    ) -> SparePart: ...

    def update(
        self,
        tenantId: uuid.UUID,
        partId: uuid.UUID,
        name: str,
        unit: str,
        quantityOnHand: Decimal,
        minimumStock: Decimal,
        unitCost: Decimal,
    ) -> SparePart: ...

    def list(self, tenantId: uuid.UUID, search: str = "") -> list[SparePart]: ...

    def getById(self, tenantId: uuid.UUID, partId: uuid.UUID) -> SparePart: ...

    def recordTransaction(
        self,
        tenantId: uuid.UUID,
        partId: uuid.UUID,
        transactionType: str,
        quantity: Decimal,
        note: str,
        reference: str,
        actorId: uuid.UUID | None,
        at,
    ): ...

    def listTransactions(self, tenantId: uuid.UUID, partId: uuid.UUID | None = None) -> list: ...

    def consume(
        self,
        tenantId: uuid.UUID,
        workOrderId: uuid.UUID,
        partId: uuid.UUID,
        quantity: Decimal,
        note: str,
        consumedAt: datetime,
    ) -> WorkOrderPartUsage: ...

    def listUsage(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID
    ) -> list[WorkOrderPartUsage]: ...


@runtime_checkable
class LabourEntryRepository(Protocol):
    """Technician time logs + the cost roll-up they drive on the work order."""

    def log(
        self,
        tenantId: uuid.UUID,
        workOrderId: uuid.UUID,
        technicianName: str,
        hours: Decimal,
        hourlyRate: Decimal,
        workedAt: datetime,
        note: str,
    ) -> LabourEntry: ...

    def listForWorkOrder(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID
    ) -> list[LabourEntry]: ...

    def delete(self, tenantId: uuid.UUID, entryId: uuid.UUID) -> LabourEntry: ...


@runtime_checkable
class MaintenanceCostRepository(Protocol):
    """Reads the cost facts the maintenance cost report aggregates."""

    def readWorkOrderCosts(
        self,
        tenantId: uuid.UUID,
        fromDate: datetime,
        toDate: datetime,
        deviceId: uuid.UUID | None = None,
        department: str = "",
    ) -> list[WorkOrderCostReading]: ...

    def readLabourCosts(
        self,
        tenantId: uuid.UUID,
        fromDate: datetime,
        toDate: datetime,
        deviceId: uuid.UUID | None = None,
        department: str = "",
    ) -> list[LabourCostReading]: ...


@runtime_checkable
class WorkOrderHistoryRepository(Protocol):
    def append(self, entry: WorkOrderHistoryEntry) -> None: ...

    def listForOrder(
        self, tenantId: uuid.UUID, workOrderId: uuid.UUID
    ) -> list[WorkOrderHistoryEntry]: ...


@runtime_checkable
class DeviceHistoryRepository(Protocol):
    def append(self, entry: DeviceHistoryEntry) -> None: ...

    def listForDevice(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID
    ) -> list[DeviceHistoryEntry]: ...


from apps.maintenance.domain.entities.teamSync import (
    InspectionRecord,
    InspectionTemplate,
    PartReservation,
)


class PartReservationRepository(Protocol):
    def listForTenant(self, tenantId: uuid.UUID, workOrderId: uuid.UUID | None = None) -> list[PartReservation]:
        ...

    def upsert(self, reservation: PartReservation) -> PartReservation:
        ...

    def close(self, tenantId: uuid.UUID, reservationId: str, status: str, closedAt: datetime) -> PartReservation | None:
        ...


class InspectionSyncRepository(Protocol):
    def listTemplates(self, tenantId: uuid.UUID) -> list[InspectionTemplate]:
        ...

    def upsertTemplate(self, template: InspectionTemplate) -> InspectionTemplate:
        ...

    def commitTemplate(self, tenantId: uuid.UUID, templateId: str) -> InspectionTemplate | None:
        ...

    def createRecord(self, record: InspectionRecord) -> InspectionRecord:
        ...

    def listRecords(self, tenantId: uuid.UUID, workOrderId: uuid.UUID | None = None) -> list[InspectionRecord]:
        ...

    def getTemplate(self, tenantId: uuid.UUID, templateId: str) -> InspectionTemplate | None:
        ...

    def deleteTemplate(self, tenantId: uuid.UUID, templateId: str) -> bool:
        ...


# =====================================================================================
# Meter readings — manual + sensor capture (ثبت قرائت دستی و سنسوری)
# =====================================================================================
from apps.maintenance.domain.entities.meterReading import (  # noqa: E402
    MeterPoint,
    MeterPointSummary,
    MeterReading,
)


@runtime_checkable
class MeterPointRepository(Protocol):
    """Definition side: what is measured on a device, and how it behaves."""

    def getById(self, tenantId: uuid.UUID, pointId: uuid.UUID) -> MeterPoint | None:
        ...

    def getByCode(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID, code: str
    ) -> MeterPoint | None:
        ...

    def getBySensorKey(self, tenantId: uuid.UUID, sensorKey: str) -> MeterPoint | None:
        ...

    def listForDevice(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID, *, includeInactive: bool = True
    ) -> list[MeterPoint]:
        ...

    def listForTenant(
        self,
        tenantId: uuid.UUID,
        *,
        search: str = "",
        kind: str = "",
        activeOnly: bool = False,
        limit: int = 500,
    ) -> list[MeterPoint]:
        ...

    def runningHoursPoint(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID
    ) -> MeterPoint | None:
        ...

    def create(
        self,
        tenantId: uuid.UUID,
        deviceId: uuid.UUID,
        payload: dict[str, object],
        now: datetime,
    ) -> MeterPoint:
        ...

    def update(
        self,
        tenantId: uuid.UUID,
        pointId: uuid.UUID,
        payload: dict[str, object],
        now: datetime,
    ) -> MeterPoint:
        ...

    def softDelete(self, tenantId: uuid.UUID, pointId: uuid.UUID, now: datetime) -> None:
        ...


@runtime_checkable
class MeterReadingRepository(Protocol):
    """Append-only stream of observations: no update, no delete, by design.

    Corrections are new rows that supersede old ones, so the only mutation the
    contract exposes is ``markSuperseded`` — bookkeeping about a row, never a
    change to the observation it records.
    """

    def getById(self, tenantId: uuid.UUID, readingId: uuid.UUID) -> MeterReading | None:
        ...

    def findByIngestionKey(
        self, tenantId: uuid.UUID, ingestionKey: str
    ) -> MeterReading | None:
        ...

    def previousReading(
        self, tenantId: uuid.UUID, pointId: uuid.UUID, capturedAt: datetime
    ) -> MeterReading | None:
        ...

    def latestReading(
        self, tenantId: uuid.UUID, pointId: uuid.UUID
    ) -> MeterReading | None:
        ...

    def listReadings(
        self,
        tenantId: uuid.UUID,
        *,
        deviceId: uuid.UUID | None = None,
        pointId: uuid.UUID | None = None,
        captureMode: str = "",
        quality: str = "",
        fromMoment: datetime | None = None,
        toMoment: datetime | None = None,
        includeSuperseded: bool = True,
        offset: int = 0,
        limit: int = 100,
    ) -> tuple[list[MeterReading], int]:
        ...

    def summarise(
        self,
        tenantId: uuid.UUID,
        point: MeterPoint,
        *,
        fromMoment: datetime | None = None,
        toMoment: datetime | None = None,
    ) -> MeterPointSummary:
        ...

    def currentValuesByCode(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID
    ) -> dict[str, Decimal]:
        ...

    def append(
        self,
        tenantId: uuid.UUID,
        point: MeterPoint,
        payload: dict[str, object],
        now: datetime,
    ) -> MeterReading:
        ...

    def lockPoint(self, tenantId: uuid.UUID, pointId: uuid.UUID) -> MeterPoint:
        ...

    def markSuperseded(
        self, tenantId: uuid.UUID, readingId: uuid.UUID, correctionId: uuid.UUID
    ) -> bool:
        ...
