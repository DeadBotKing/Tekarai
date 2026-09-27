"""Django reader for the maintenance cost report (time & cost tracking).

The report is scoped by *work-order creation date* (like the device report),
then joins the device's code/name for grouping and flattens labour entries for
the technician breakdown. Everything is read-only; the numbers it returns were
already maintained transactionally by the labour/part-usage rollups.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from apps.maintenance.domain.services.maintenanceCosting import (
    LabourCostReading,
    WorkOrderCostReading,
)
from apps.maintenance.infrastructure.models import (
    DeviceModel,
    WorkOrderLabourEntryModel,
    WorkOrderModel,
)


class MaintenanceCostRepositoryDjango:
    @staticmethod
    def _baseOrders(
        tenantId: uuid.UUID,
        fromDate: datetime,
        toDate: datetime,
        deviceId: uuid.UUID | None,
        department: str,
    ):
        queryset = WorkOrderModel.objects.filter(
            tenantId=tenantId,
            deletedAt__isnull=True,
            createdAt__gte=fromDate,
            createdAt__lte=toDate,
        )
        if deviceId is not None:
            queryset = queryset.filter(deviceId=deviceId)
        if department.strip():
            queryset = queryset.filter(department=department.strip())
        return queryset

    def readWorkOrderCosts(
        self,
        tenantId: uuid.UUID,
        fromDate: datetime,
        toDate: datetime,
        deviceId: uuid.UUID | None = None,
        department: str = "",
    ) -> list[WorkOrderCostReading]:
        orders = list(self._baseOrders(tenantId, fromDate, toDate, deviceId, department))
        devices = {
            str(device.id): device
            for device in DeviceModel.objects.filter(
                tenantId=tenantId, id__in={order.deviceId for order in orders}
            )
        }
        readings: list[WorkOrderCostReading] = []
        for order in orders:
            device = devices.get(str(order.deviceId))
            readings.append(
                WorkOrderCostReading(
                    workOrderId=str(order.id),
                    title=order.title,
                    orderType=order.orderType,
                    status=order.status,
                    department=order.department,
                    deviceId=str(order.deviceId),
                    deviceCode=device.code if device else "",
                    deviceName=device.name if device else "",
                    assignedToName=order.assignedToName,
                    labourHours=order.labourHours,
                    labourCost=order.labourCost,
                    partsCost=order.partsCost,
                    createdAtIso=order.createdAt.isoformat(),
                    closedAtIso=order.closedAt.isoformat() if order.closedAt else "",
                )
            )
        return readings

    def readLabourCosts(
        self,
        tenantId: uuid.UUID,
        fromDate: datetime,
        toDate: datetime,
        deviceId: uuid.UUID | None = None,
        department: str = "",
    ) -> list[LabourCostReading]:
        orderIds = [
            order.id for order in self._baseOrders(tenantId, fromDate, toDate, deviceId, department)
        ]
        if not orderIds:
            return []
        entries = WorkOrderLabourEntryModel.objects.filter(
            tenantId=tenantId, workOrderId__in=orderIds
        )
        return [
            LabourCostReading(
                workOrderId=str(entry.workOrderId),
                technicianName=entry.technicianName,
                hours=entry.hours,
                cost=(entry.hours * entry.hourlyRate),
            )
            for entry in entries
        ]
