"""Maintenance persistence models (Phase 21)."""

from __future__ import annotations

import uuid

from django.db import models


class DeviceModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    location = models.CharField(max_length=200, blank=True, default="")
    status = models.CharField(max_length=24, default="operational")
    department = models.CharField(max_length=24, default="general")
    pmIntervalDays = models.IntegerField(default=0)
    lastPmDate = models.DateField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Device"
        ordering = ["-createdAt"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_device_tenant_code",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.code}:{self.name}"


class WorkOrderModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    title = models.CharField(max_length=300)
    description = models.TextField(blank=True, default="")
    orderType = models.CharField(max_length=20, default="corrective")
    priority = models.CharField(max_length=20, default="normal")
    status = models.CharField(max_length=20, default="submitted")
    department = models.CharField(max_length=24, default="general", db_index=True)
    requestedByName = models.CharField(max_length=160, blank=True, default="")
    assignedToName = models.CharField(max_length=160, blank=True, default="")
    resolutionNote = models.TextField(blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    closedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "WorkOrder"
        ordering = ["-createdAt"]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.status}:{self.title}"


class SparePartModel(models.Model):
    """Tenant-scoped spare-part stock balance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=30, default="عدد")
    quantityOnHand = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    minimumStock = models.DecimalField(max_digits=14, decimal_places=3, default=0)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "SparePart"
        ordering = ["code"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_spare_part_tenant_code",
            ),
            models.CheckConstraint(
                condition=models.Q(quantityOnHand__gte=0),
                name="ck_spare_part_stock_nonnegative",
            ),
            models.CheckConstraint(
                condition=models.Q(minimumStock__gte=0),
                name="ck_spare_part_minimum_nonnegative",
            ),
        ]


class WorkOrderPartUsageModel(models.Model):
    """Immutable record of stock consumed by a work order."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    workOrderId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    partCode = models.CharField(max_length=60)
    partName = models.CharField(max_length=200)
    unit = models.CharField(max_length=30)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    note = models.CharField(max_length=500, blank=True, default="")
    consumedAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "WorkOrderPartUsage"
        ordering = ["-consumedAt"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(quantity__gt=0),
                name="ck_work_order_part_usage_positive",
            )
        ]


class WorkOrderHistoryModel(models.Model):
    """Append-only audit of every work-order transition (Phase 22 workflow).

    One row per lifecycle event — submit, route, assign, status change,
    approval decision. Powers the per-order timeline the frontend renders.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    workOrderId = models.UUIDField(db_index=True)
    action = models.CharField(max_length=32)
    fromStatus = models.CharField(max_length=20, blank=True, default="")
    toStatus = models.CharField(max_length=20, blank=True, default="")
    fromDepartment = models.CharField(max_length=24, blank=True, default="")
    toDepartment = models.CharField(max_length=24, blank=True, default="")
    actorName = models.CharField(max_length=160, blank=True, default="")
    note = models.TextField(blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "WorkOrderHistory"
        ordering = ["createdAt"]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.action}:{self.workOrderId}"


class DeviceHistoryModel(models.Model):
    """Append-only history of every device lifecycle event (device timeline).

    One row per event — registration, detail update, status change, PM
    completion. Combined with the device's related work orders, this powers the
    per-device timeline the frontend renders on the device detail page.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    action = models.CharField(max_length=32)
    fromStatus = models.CharField(max_length=20, blank=True, default="")
    toStatus = models.CharField(max_length=20, blank=True, default="")
    note = models.TextField(blank=True, default="")
    actorName = models.CharField(max_length=160, blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "DeviceHistory"
        ordering = ["createdAt"]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.action}:{self.deviceId}"
