"""Tenant-scoped read model for equipment lifecycle analysis."""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.maintenance.domain.services.equipmentLifecycle import (
    EquipmentLifecycleSnapshot,
    LifecycleMeterReading,
    LifecyclePartUse,
    LifecyclePerformancePoint,
    LifecycleWorkOrder,
    PART_IMPACT_UNKNOWN,
    PERFORMANCE_ROLE_NONE,
)
from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MeterPointModel,
    MeterReadingModel,
    SparePartModel,
    WorkOrderModel,
    WorkOrderPartUsageModel,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError


class EquipmentLifecycleRepositoryDjango:
    """Fetch a bounded snapshot; all queries are constrained to one tenant."""

    MAX_PERFORMANCE_POINTS = 40
    MAX_READINGS_PER_POINT = 1000
    MAX_RETIRED_PEERS = 1000

    def getSnapshot(
        self, tenantId: uuid.UUID, deviceId: uuid.UUID, asOf: datetime
    ) -> EquipmentLifecycleSnapshot:
        device = DeviceModel.objects.filter(
            tenantId=tenantId,
            id=deviceId,
            deletedAt__isnull=True,
        ).first()
        if device is None:
            raise EntityNotFoundError("Device")

        orderModels = list(
            WorkOrderModel.objects.filter(
                tenantId=tenantId,
                deviceId=deviceId,
                deletedAt__isnull=True,
                createdAt__lte=asOf,
            ).order_by("createdAt").only(
                "id",
                "orderType",
                "status",
                "repairScope",
                "createdAt",
                "downtimeMinutes",
                "labourHours",
                "repeatFailure",
                "title",
                "description",
                "failureSymptom",
                "rootCause",
                "actionTaken",
            )
        )
        workOrders = tuple(
            LifecycleWorkOrder(
                id=str(row.id),
                orderType=row.orderType,
                status=row.status,
                repairScope=row.repairScope or "unclassified",
                createdAt=row.createdAt,
                downtimeMinutes=row.downtimeMinutes,
                labourHours=row.labourHours,
                repeatFailure=row.repeatFailure,
                title=row.title,
                description=row.description,
                failureSymptom=row.failureSymptom,
                rootCause=row.rootCause,
                actionTaken=row.actionTaken,
            )
            for row in orderModels
        )

        orderIds = [row.id for row in orderModels]
        usageModels = WorkOrderPartUsageModel.objects.filter(
            tenantId=tenantId,
            workOrderId__in=orderIds,
        ).order_by("consumedAt").only(
            "workOrderId", "partCode", "partName", "quantity", "lifecycleImpact", "consumedAt"
        )
        partUses = tuple(
            LifecyclePartUse(
                workOrderId=str(row.workOrderId),
                partCode=row.partCode,
                partName=row.partName,
                quantity=row.quantity,
                lifecycleImpact=row.lifecycleImpact or PART_IMPACT_UNKNOWN,
                consumedAt=row.consumedAt,
            )
            for row in usageModels
        )

        pointModels = list(
            MeterPointModel.objects.filter(
                tenantId=tenantId,
                deviceId=deviceId,
                active=True,
                deletedAt__isnull=True,
            )
            .exclude(performanceRole=PERFORMANCE_ROLE_NONE)
            .order_by("code")[: self.MAX_PERFORMANCE_POINTS]
        )
        performancePoints = tuple(
            LifecyclePerformancePoint(
                id=str(point.id),
                name=point.name,
                unit=point.unit,
                role=point.performanceRole,
                minimumValue=point.minimumValue,
                maximumValue=point.maximumValue,
            )
            for point in pointModels
        )
        performanceReadings: list[LifecycleMeterReading] = []
        for point in pointModels:
            rows = list(
                MeterReadingModel.objects.filter(
                    tenantId=tenantId,
                    deviceId=deviceId,
                    meterPoint_id=point.id,
                    quality__in=("good", "estimated"),
                    supersededByReadingId__isnull=True,
                    capturedAt__lte=asOf,
                )
                .order_by("-capturedAt")
                .values_list("value", "capturedAt")[: self.MAX_READINGS_PER_POINT]
            )
            performanceReadings.extend(
                LifecycleMeterReading(
                    meterPointId=str(point.id),
                    value=value,
                    capturedAt=capturedAt,
                )
                for value, capturedAt in reversed(rows)
            )

        cohortType = "none"
        cohortLabel = ""
        retiredPeers = DeviceModel.objects.filter(
            tenantId=tenantId,
            status__iexact="retired",
            retiredOn__isnull=False,
            deletedAt__isnull=True,
        ).exclude(id=deviceId)
        if device.modelNumber.strip():
            cohortType = "modelNumber"
            cohortLabel = device.modelNumber.strip()
            retiredPeers = retiredPeers.filter(modelNumber__iexact=cohortLabel)
        elif device.assetType.strip():
            cohortType = "assetType"
            cohortLabel = device.assetType.strip()
            retiredPeers = retiredPeers.filter(assetType__iexact=cohortLabel)
        else:
            retiredPeers = retiredPeers.none()

        peerRows = list(
            retiredPeers.order_by("retiredOn", "id")[: self.MAX_RETIRED_PEERS].values(
                "id", "retiredOn"
            )
        )
        peerRetiredDates = {row["id"]: row["retiredOn"] for row in peerRows}
        peerCorrectiveCounts = {assetId: 0 for assetId in peerRetiredDates}
        peerClassifiedCounts = {assetId: 0 for assetId in peerRetiredDates}
        peerMajorRepairCounts = {assetId: 0 for assetId in peerRetiredDates}
        if peerRetiredDates:
            peerOrderRows = WorkOrderModel.objects.filter(
                tenantId=tenantId,
                deviceId__in=tuple(peerRetiredDates),
                orderType="corrective",
                deletedAt__isnull=True,
            ).exclude(status="cancelled").order_by("deviceId", "createdAt").values_list(
                "deviceId", "createdAt", "repairScope"
            )
            for peerId, createdAt, repairScope in peerOrderRows.iterator(chunk_size=2000):
                retiredOn = peerRetiredDates.get(peerId)
                if retiredOn is None or createdAt.date() > retiredOn:
                    continue
                peerCorrectiveCounts[peerId] += 1
                if repairScope in ("minor", "major", "overhaul"):
                    peerClassifiedCounts[peerId] += 1
                if repairScope in ("major", "overhaul"):
                    peerMajorRepairCounts[peerId] += 1
        # A comparison peer is usable only when all of its corrective events
        # are human-classified and it has at least one confirmed major repair.
        # Otherwise legacy/unclassified history could make the major-repair
        # count look artificially low, or minor consumables could dominate it.
        comparableMajorRepairCounts = tuple(
            peerMajorRepairCounts[assetId]
            for assetId in peerRetiredDates
            if peerCorrectiveCounts[assetId] > 0
            and peerClassifiedCounts[assetId] == peerCorrectiveCounts[assetId]
            and peerMajorRepairCounts[assetId] > 0
        )

        return EquipmentLifecycleSnapshot(
            workOrders=workOrders,
            partUses=partUses,
            performancePoints=performancePoints,
            performanceReadings=tuple(performanceReadings),
            retiredPeerMajorRepairCounts=comparableMajorRepairCounts,
            cohortType=cohortType if comparableMajorRepairCounts else "none",
            cohortLabel=cohortLabel if comparableMajorRepairCounts else "",
            modelNumber=device.modelNumber,
            assetType=device.assetType,
        )
