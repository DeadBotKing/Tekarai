"""Maintenance persistence models (Phase 21)."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.db import models


def maintenanceAttachmentPath(instance, filename: str) -> str:  # noqa: ANN001
    """Opaque, tenant-partitioned storage key; never trust the client filename."""
    extension = Path(filename).suffix.lower()[:12]
    return (
        f"maintenance/{instance.tenantId}/{instance.targetType}/"
        f"{instance.targetId}/{uuid.uuid4().hex}{extension}"
    )


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

    # -- Phase 26 asset registry (nameplate) -------------------------------------
    # All optional so every pre-existing row stays valid without a data backfill.
    manufacturer = models.CharField(max_length=200, blank=True, default="")
    modelNumber = models.CharField(max_length=200, blank=True, default="")
    serialNumber = models.CharField(max_length=200, blank=True, default="")
    assetType = models.CharField(max_length=160, blank=True, default="")
    manufactureYear = models.CharField(max_length=10, blank=True, default="")
    capacity = models.CharField(max_length=160, blank=True, default="")
    powerRating = models.CharField(max_length=160, blank=True, default="")
    electricalSpec = models.CharField(max_length=300, blank=True, default="")
    criticality = models.CharField(max_length=10, default="medium", db_index=True)
    # Self-reference: a line owns machines, a machine owns its motor/gearbox.
    parentDeviceId = models.UUIDField(null=True, blank=True, db_index=True)
    locationId = models.UUIDField(null=True, blank=True, db_index=True)
    locationPath = models.CharField(max_length=800, blank=True, default="")
    operatorUnit = models.CharField(max_length=160, blank=True, default="")
    purchasedOn = models.DateField(null=True, blank=True)
    installedOn = models.DateField(null=True, blank=True)
    commissionedOn = models.DateField(null=True, blank=True)
    warrantyUntil = models.DateField(null=True, blank=True)
    supplier = models.CharField(max_length=200, blank=True, default="")
    purchaseCost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    runningHours = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    notes = models.TextField(blank=True, default="")

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

    # -- Phase 26 failure / downtime / cost capture -------------------------------
    # Recorded when the order is closed; these columns are what turn the report
    # page from a chart into evidence (MTTR, downtime, repeat failures, cost).
    failureType = models.CharField(max_length=24, blank=True, default="", db_index=True)
    failedComponent = models.CharField(max_length=200, blank=True, default="")
    failureSymptom = models.CharField(max_length=300, blank=True, default="")
    rootCause = models.TextField(blank=True, default="")
    actionTaken = models.TextField(blank=True, default="")
    repeatFailure = models.BooleanField(default=False)
    failureReportedAt = models.DateTimeField(null=True, blank=True)
    repairStartedAt = models.DateTimeField(null=True, blank=True)
    repairFinishedAt = models.DateTimeField(null=True, blank=True)
    returnedToServiceAt = models.DateTimeField(null=True, blank=True)
    downtimeMinutes = models.IntegerField(default=0)
    labourHours = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    labourCost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    partsCost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    pmPlanId = models.UUIDField(null=True, blank=True, db_index=True)

    class Meta:
        db_table = "WorkOrder"
        ordering = ["-createdAt"]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.status}:{self.title}"


class MaintenanceAttachmentModel(models.Model):
    """File metadata; bytes are stored under MEDIA_ROOT using an opaque key."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    targetType = models.CharField(max_length=20, db_index=True)
    targetId = models.UUIDField(db_index=True)
    category = models.CharField(max_length=20, default="other")
    originalName = models.CharField(max_length=255)
    mimeType = models.CharField(max_length=120)
    sizeBytes = models.PositiveBigIntegerField()
    file = models.FileField(upload_to=maintenanceAttachmentPath, max_length=500)
    uploadedAt = models.DateTimeField(auto_now_add=True, db_index=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenanceAttachment"
        ordering = ["-uploadedAt"]
        indexes = [models.Index(fields=["tenantId", "targetType", "targetId"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(targetType__in=("device", "workOrder")),
                name="ck_maintenance_attachment_target",
            ),
            models.CheckConstraint(
                condition=models.Q(category__in=("failurePhoto", "manual", "invoice", "other")),
                name="ck_maintenance_attachment_category",
            ),
        ]


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


# =====================================================================================
# Phase 26 — Equipment registry (equipment master data) and maintenance analytics.
#
# The registry turns "device" into a real asset record: a hierarchical location
# tree, an independent personnel directory, PM plans per discipline, a bill of
# materials linking shared spare parts to many devices, and per-device
# assignments. Every consumable fact (a repair, a PM execution, a part issue) is
# stored as its own dated row so the reporting layer can count, average and
# drill down instead of trusting a hand-maintained total.
# =====================================================================================


class MaintenanceLocationModel(models.Model):
    """One node of the location tree — site, building, floor, hall, line, room.

    Self-referencing via ``parentId`` so depth is never capped at three levels;
    ``path`` caches the materialised ancestor chain ("سایت / ساختمان / اتاق")
    purely for display and search.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    parentId = models.UUIDField(null=True, blank=True, db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=20, default="site")
    path = models.CharField(max_length=800, blank=True, default="")
    note = models.TextField(blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenanceLocation"
        ordering = ["path", "name"]
        indexes = [models.Index(fields=["tenantId", "parentId"])]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_location_tenant_code",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=("site", "building", "floor", "hall", "line", "room", "area")
                ),
                name="ck_maintenance_location_kind",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.kind}:{self.name}"


class MaintenancePersonnelModel(models.Model):
    """Maintenance workforce directory — independent of any single device."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    personnelCode = models.CharField(max_length=60)
    fullName = models.CharField(max_length=200)
    specialty = models.CharField(max_length=24, default="general", db_index=True)
    unit = models.CharField(max_length=160, blank=True, default="")
    phone = models.CharField(max_length=40, blank=True, default="")
    shift = models.CharField(max_length=60, blank=True, default="")
    skills = models.TextField(blank=True, default="")
    certifications = models.TextField(blank=True, default="")
    active = models.BooleanField(default=True)
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenancePersonnel"
        ordering = ["fullName"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "personnelCode"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_personnel_tenant_code",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.personnelCode}:{self.fullName}"


class DeviceSpecificationModel(models.Model):
    """User-defined technical spec (label → value) for one device.

    Free-form on purpose: a compressor and a PLC do not share a fixed form, so
    the registry stores named rows instead of a rigid column per attribute.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    label = models.CharField(max_length=160)
    value = models.CharField(max_length=500, blank=True, default="")
    unit = models.CharField(max_length=40, blank=True, default="")
    sortOrder = models.IntegerField(default=0)
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "DeviceSpecification"
        ordering = ["sortOrder", "label"]
        indexes = [models.Index(fields=["tenantId", "deviceId"])]


class PmPlanModel(models.Model):
    """A recurring preventive-maintenance plan owned by one discipline.

    A *plan* is the rule ("تعویض روغن هر ۳ ماه"); each actual execution is a
    separate ``PmExecutionModel`` row. Keeping them apart is what makes PM
    compliance and overdue reporting trustworthy.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    title = models.CharField(max_length=300)
    discipline = models.CharField(max_length=24, default="general", db_index=True)
    description = models.TextField(blank=True, default="")
    checklist = models.TextField(blank=True, default="")
    frequencyEvery = models.IntegerField(default=1)
    frequencyUnit = models.CharField(max_length=20, default="month")
    estimatedMinutes = models.IntegerField(default=0)
    responsibleName = models.CharField(max_length=160, blank=True, default="")
    lastExecutedOn = models.DateField(null=True, blank=True)
    active = models.BooleanField(default=True)
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "PmPlan"
        ordering = ["discipline", "title"]
        indexes = [models.Index(fields=["tenantId", "deviceId", "discipline"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(frequencyEvery__gt=0),
                name="ck_pm_plan_frequency_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(
                    frequencyUnit__in=("day", "week", "month", "runningHour")
                ),
                name="ck_pm_plan_frequency_unit",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.discipline}:{self.title}"


class PmExecutionModel(models.Model):
    """One completed run of a PM plan — the historical fact behind compliance."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    planId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    discipline = models.CharField(max_length=24, default="general", db_index=True)
    performedOn = models.DateField(db_index=True)
    dueOn = models.DateField(null=True, blank=True)
    onTime = models.BooleanField(default=True)
    performedByName = models.CharField(max_length=160, blank=True, default="")
    durationMinutes = models.IntegerField(default=0)
    findings = models.TextField(blank=True, default="")
    workOrderId = models.UUIDField(null=True, blank=True, db_index=True)
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "PmExecution"
        ordering = ["-performedOn"]
        indexes = [models.Index(fields=["tenantId", "deviceId", "performedOn"])]


class DeviceBomModel(models.Model):
    """Bill-of-materials link: which shared spare part fits which device.

    Many-to-many on purpose — one bearing serves many machines, so the part
    itself lives once in ``SparePart`` and is *referenced* here.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    position = models.CharField(max_length=160, blank=True, default="")
    standardQuantity = models.DecimalField(max_digits=14, decimal_places=3, default=1)
    note = models.CharField(max_length=500, blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "DeviceBom"
        ordering = ["position"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "deviceId", "partId"],
                name="uq_device_bom_device_part",
            ),
            models.CheckConstraint(
                condition=models.Q(standardQuantity__gt=0),
                name="ck_device_bom_quantity_positive",
            ),
        ]


class DeviceAssignmentModel(models.Model):
    """Who is attached to a device, in which role, over which period.

    Dated rows (``fromDate`` / ``toDate``) keep the history intact when an
    operator or a responsible engineer changes.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    personnelId = models.UUIDField(null=True, blank=True, db_index=True)
    personnelName = models.CharField(max_length=200, blank=True, default="")
    role = models.CharField(max_length=20, default="technician")
    unit = models.CharField(max_length=160, blank=True, default="")
    fromDate = models.DateField(null=True, blank=True)
    toDate = models.DateField(null=True, blank=True)
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "DeviceAssignment"
        ordering = ["role", "personnelName"]
        indexes = [models.Index(fields=["tenantId", "deviceId", "role"])]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    role__in=("operator", "responsible", "technician", "deputy")
                ),
                name="ck_device_assignment_role",
            )
        ]
