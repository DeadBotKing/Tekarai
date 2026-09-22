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
