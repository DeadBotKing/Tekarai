"""Django repositories for scanning and the offline-sync ledger."""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db import IntegrityError, transaction

from apps.maintenance.domain.repositories.maintenanceRepositories import SyncLedgerEntry
from apps.maintenance.domain.services.scanCodeRules import ScanIntent
from apps.maintenance.domain.valueObjects.fieldOpsTypes import (
    SCAN_TARGET_DEVICE,
    SCAN_TARGET_LOCATION,
    SCAN_TARGET_SPARE_PART,
    SCAN_TARGET_WORK_ORDER,
    ScanTarget,
)
from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MaintenanceLocationModel,
    OfflineSyncOperationModel,
    SparePartModel,
    WorkOrderModel,
)


class ScanResolutionRepositoryDjango:
    """Probes the tenant's tables for whatever the scanned text can mean.

    Order matters. A technician scanning in the field is overwhelmingly
    pointing at *equipment*, so devices are probed first; a code that matches
    both a device and a spare part resolves to the device. Within devices the
    business ``code`` beats the ``serialNumber``, because the plant's own
    label is authoritative over a vendor sticker.
    """

    # -- row → ScanTarget ------------------------------------------------------
    @staticmethod
    def _device(model: DeviceModel) -> ScanTarget:
        return ScanTarget(
            kind=SCAN_TARGET_DEVICE,
            id=str(model.id),
            code=model.code,
            title=model.name,
            subtitle=model.locationPath or model.location,
            route=f"/app/maintenance/devices/{model.id}/profile",
            status=model.status,
        )

    @staticmethod
    def _workOrder(model: WorkOrderModel) -> ScanTarget:
        return ScanTarget(
            kind=SCAN_TARGET_WORK_ORDER,
            id=str(model.id),
            code=str(model.id)[:8],
            title=model.title,
            subtitle=model.assignedToName,
            route=f"/app/maintenance/work-orders?focus={model.id}",
            status=model.status,
        )

    @staticmethod
    def _part(model: SparePartModel) -> ScanTarget:
        return ScanTarget(
            kind=SCAN_TARGET_SPARE_PART,
            id=str(model.id),
            code=model.code,
            title=model.name,
            subtitle=f"{model.quantityOnHand} {model.unit}",
            # The parts register is served by the warehouse page; a label that
            # points at /spare-parts would scan into a 404.
            route=f"/app/maintenance/warehouse?focus={model.id}",
            status="active",
        )

    @staticmethod
    def _location(model: MaintenanceLocationModel) -> ScanTarget:
        return ScanTarget(
            kind=SCAN_TARGET_LOCATION,
            id=str(model.id),
            code=model.code,
            title=model.name,
            subtitle=model.path,
            route=f"/app/maintenance/locations?focus={model.id}",
            status="active",
        )

    # -- lookups ---------------------------------------------------------------
    def _deviceBy(self, tenantId: uuid.UUID, intent: ScanIntent) -> ScanTarget | None:
        base = DeviceModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if intent.entityId is not None:
            model = base.filter(id=intent.entityId).first()
            return self._device(model) if model else None
        if not intent.code:
            return None
        model = base.filter(code__iexact=intent.code).first()
        if model is None:
            model = base.filter(serialNumber__iexact=intent.code).first()
        return self._device(model) if model else None

    def _workOrderBy(self, tenantId: uuid.UUID, intent: ScanIntent) -> ScanTarget | None:
        if intent.entityId is None:
            return None
        model = WorkOrderModel.objects.filter(
            tenantId=tenantId, id=intent.entityId, deletedAt__isnull=True
        ).first()
        return self._workOrder(model) if model else None

    def _partBy(self, tenantId: uuid.UUID, intent: ScanIntent) -> ScanTarget | None:
        base = SparePartModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if intent.entityId is not None:
            model = base.filter(id=intent.entityId).first()
            return self._part(model) if model else None
        if not intent.code:
            return None
        model = base.filter(code__iexact=intent.code).first()
        return self._part(model) if model else None

    def _locationBy(self, tenantId: uuid.UUID, intent: ScanIntent) -> ScanTarget | None:
        base = MaintenanceLocationModel.objects.filter(tenantId=tenantId, deletedAt__isnull=True)
        if intent.entityId is not None:
            model = base.filter(id=intent.entityId).first()
            return self._location(model) if model else None
        if not intent.code:
            return None
        model = base.filter(code__iexact=intent.code).first()
        return self._location(model) if model else None

    def resolve(self, tenantId: uuid.UUID, intent: ScanIntent) -> ScanTarget | None:
        if intent.isEmpty:
            return None
        probes = {
            SCAN_TARGET_DEVICE: self._deviceBy,
            SCAN_TARGET_WORK_ORDER: self._workOrderBy,
            SCAN_TARGET_SPARE_PART: self._partBy,
            SCAN_TARGET_LOCATION: self._locationBy,
        }
        if intent.kind:
            probe = probes.get(intent.kind)
            return probe(tenantId, intent) if probe else None
        for kind in (
            SCAN_TARGET_DEVICE,
            SCAN_TARGET_WORK_ORDER,
            SCAN_TARGET_SPARE_PART,
            SCAN_TARGET_LOCATION,
        ):
            found = probes[kind](tenantId, intent)
            if found is not None:
                return found
        return None


class OfflineSyncLedgerDjango:
    """Durable ``clientRequestId`` → outcome ledger (replay protection)."""

    @staticmethod
    def _entry(model: OfflineSyncOperationModel) -> SyncLedgerEntry:
        return SyncLedgerEntry(
            clientRequestId=model.clientRequestId,
            kind=model.kind,
            status=model.status,
            resultId=model.resultId,
            resultPayload=dict(model.resultPayload or {}),
            errorCode=model.errorCode,
            errorMessage=model.errorMessage,
            receivedAt=model.receivedAt,
        )

    def find(self, tenantId: uuid.UUID, clientRequestId: str) -> SyncLedgerEntry | None:
        model = OfflineSyncOperationModel.objects.filter(
            tenantId=tenantId, clientRequestId=clientRequestId.strip()
        ).first()
        return None if model is None else self._entry(model)

    def remember(
        self,
        tenantId: uuid.UUID,
        clientRequestId: str,
        kind: str,
        status: str,
        *,
        resultId: str = "",
        resultPayload: dict[str, object] | None = None,
        errorCode: str = "",
        errorMessage: str = "",
        actorName: str = "",
        capturedAt: datetime | None = None,
        receivedAt: datetime,
        deviceLabel: str = "",
    ) -> SyncLedgerEntry:
        """Store the outcome, or return the stored one if it already exists.

        ``get_or_create`` rather than ``create``: two phones (or two tabs)
        replaying the same queue concurrently both reach here, and the loser
        of the race must read the winner's row instead of exploding.
        """
        defaults = {
            "kind": kind,
            "status": status,
            "resultId": resultId[:64],
            "resultPayload": resultPayload or {},
            "errorCode": errorCode[:60],
            "errorMessage": errorMessage[:500],
            "actorName": actorName[:160],
            "capturedAt": capturedAt,
            "receivedAt": receivedAt,
            "deviceLabel": deviceLabel[:120],
        }
        try:
            with transaction.atomic():
                model, _created = OfflineSyncOperationModel.objects.get_or_create(
                    tenantId=tenantId,
                    clientRequestId=clientRequestId.strip(),
                    defaults=defaults,
                )
        except IntegrityError:  # pragma: no cover — concurrent replay
            model = OfflineSyncOperationModel.objects.get(
                tenantId=tenantId, clientRequestId=clientRequestId.strip()
            )
        return self._entry(model)

    def forget(self, tenantId: uuid.UUID, clientRequestId: str) -> None:
        """Drop a ``failed`` record so the next sync may retry it.

        Only transient failures are forgotten; applied and rejected outcomes
        are permanent by design.
        """
        OfflineSyncOperationModel.objects.filter(
            tenantId=tenantId, clientRequestId=clientRequestId.strip(), status="failed"
        ).delete()

    def recent(self, tenantId: uuid.UUID, limit: int = 50) -> list[SyncLedgerEntry]:
        rows = OfflineSyncOperationModel.objects.filter(tenantId=tenantId).order_by("-receivedAt")[
            : max(1, min(int(limit), 200))
        ]
        return [self._entry(item) for item in rows]
