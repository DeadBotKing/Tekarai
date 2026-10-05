"""Maintenance persistence models (Phase 21)."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.db import models

from apps.maintenance.domain.exceptions.meterErrors import MeterReadingImmutableError


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
    criticality = models.CharField(max_length=24, default="medium", db_index=True)
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

    # -- Phase 27 asset hierarchy ------------------------------------------------
    # Where this record sits in تجهیز اصلی ← زیرتجهیز ← قطعه. Defaulted rather
    # than nullable so every pre-existing row reads as a main asset, which is
    # what it was before the level existed.
    assetLevel = models.CharField(max_length=20, default="mainEquipment", db_index=True)
    # Which budget carries this asset's repairs. Code and name are stored
    # together so a report does not have to resolve a foreign context.
    costCenterCode = models.CharField(max_length=60, blank=True, default="")
    costCenterName = models.CharField(max_length=200, blank=True, default="")
    # End of service. `status = retired` says it is out; this says when and why.
    retiredOn = models.DateField(null=True, blank=True)
    retirementReason = models.CharField(max_length=300, blank=True, default="")

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
    # Latest purchase/replacement price per ``unit`` — the consumption rows
    # snapshot this value so historical costs never drift with price updates.
    unitCost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
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
            models.CheckConstraint(
                condition=models.Q(unitCost__gte=0),
                name="ck_spare_part_unit_cost_nonnegative",
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
    # Price snapshot taken from ``SparePart.unitCost`` at consumption time.
    unitCost = models.DecimalField(max_digits=16, decimal_places=2, default=0)
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


class WorkOrderLabourEntryModel(models.Model):
    """One logged chunk of technician work on a work order (time & cost).

    Rows are kept individually (not summed into a single counter) so the cost
    report can answer «کی، چقدر، با چه نرخی» and deleting a mistaken entry
    only removes its own share from the roll-up on ``WorkOrderModel``.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    workOrderId = models.UUIDField(db_index=True)
    technicianName = models.CharField(max_length=160)
    hours = models.DecimalField(max_digits=10, decimal_places=2)
    hourlyRate = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    workedAt = models.DateTimeField(db_index=True)
    note = models.CharField(max_length=500, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "WorkOrderLabourEntry"
        ordering = ["-workedAt"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(hours__gt=0),
                name="ck_labour_entry_hours_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(hourlyRate__gte=0),
                name="ck_labour_entry_rate_nonnegative",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.technicianName}:{self.hours}h@{self.workOrderId}"


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


class AssetMovementModel(models.Model):
    """Append-only record of every time a device changed its installed place.

    The device row carries only *where it is now*. Without this ledger the
    previous location is lost on the next move, and questions the plant
    actually asks — "which line was this motor on last year?", "how often has
    this pump been shuffled?" — have no answer. Both ends of the move are
    denormalised (id plus the display path) so history stays readable even
    after a location is renamed or removed.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    fromLocationId = models.UUIDField(null=True, blank=True)
    fromLocationPath = models.CharField(max_length=800, blank=True, default="")
    toLocationId = models.UUIDField(null=True, blank=True)
    toLocationPath = models.CharField(max_length=800, blank=True, default="")
    fromParentDeviceId = models.UUIDField(null=True, blank=True)
    toParentDeviceId = models.UUIDField(null=True, blank=True)
    movedOn = models.DateField(db_index=True)
    reason = models.CharField(max_length=300, blank=True, default="")
    performedBy = models.CharField(max_length=160, blank=True, default="")
    note = models.TextField(blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "AssetMovement"
        ordering = ["-movedOn", "-createdAt"]
        indexes = [models.Index(fields=["tenantId", "deviceId", "-movedOn"])]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"move:{self.deviceId}:{self.movedOn}"


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
    kind = models.CharField(max_length=24, default="site")
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
            # Phase 26.1: the kind is an open vocabulary — the UI offers the
            # canonical catalogue and lets a plant add its own word («سوله»),
            # so the database only guarantees that a kind was given at all.
            models.CheckConstraint(
                condition=~models.Q(kind=""),
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

    # -- Meter / condition trigger ------------------------------------------------
    # These columns were added to the database by migration 0012 but were never
    # declared here, so every INSERT omitted them and the NOT NULL column
    # ``triggerType`` rejected it — creating any PM plan returned HTTP 500.
    # Declaring them restores plan creation *and* activates the meter triggers
    # the migration was written for.
    triggerType = models.CharField(default="calendar", db_index=True, max_length=20)
    metricType = models.CharField(blank=True, default="", max_length=40)
    metricInterval = models.DecimalField(decimal_places=3, default=0, max_digits=14)
    thresholdOperator = models.CharField(default=">=", max_length=4)
    thresholdValue = models.DecimalField(decimal_places=3, default=0, max_digits=18)
    warningValue = models.DecimalField(decimal_places=3, default=0, max_digits=18)
    metricUnit = models.CharField(blank=True, default="", max_length=30)
    sensorKey = models.CharField(blank=True, default="", max_length=120)
    lastMetricValue = models.DecimalField(blank=True, null=True, decimal_places=3, max_digits=18)
    # The meter value at the last execution — the baseline a meter trigger
    # counts its next interval from.
    lastExecutedMeterValue = models.DecimalField(
        blank=True, null=True, decimal_places=3, max_digits=18
    )

    class Meta:
        db_table = "PmPlan"
        ordering = ["discipline", "title"]
        indexes = [
            models.Index(fields=["tenantId", "deviceId", "discipline"]),
            models.Index(
                fields=["tenantId", "triggerType", "active"],
                name="ix_pm_plan_tenant_trigger",
            ),
        ]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(frequencyEvery__gt=0),
                name="ck_pm_plan_frequency_positive",
            ),
            models.CheckConstraint(
                condition=models.Q(frequencyUnit__in=("day", "week", "month", "runningHour")),
                name="ck_pm_plan_frequency_unit",
            ),
            models.CheckConstraint(
                condition=models.Q(triggerType__in=("calendar", "meter", "condition")),
                name="ck_pm_plan_trigger_type",
            ),
            models.CheckConstraint(
                condition=models.Q(thresholdOperator__in=(">=", "<=", ">", "<")),
                name="ck_pm_plan_threshold_operator",
            ),
            # A meter trigger without a positive interval can never fire; a
            # database that allows one guarantees a silently inert plan.
            models.CheckConstraint(
                condition=~models.Q(triggerType="meter") | models.Q(metricInterval__gt=0),
                name="ck_pm_plan_meter_interval",
            ),
            # Both meter-driven trigger types need to know which meter to read.
            models.CheckConstraint(
                condition=models.Q(triggerType="calendar") | ~models.Q(metricType=""),
                name="ck_pm_plan_metric_type_required",
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
    # Meter value at execution time — resets a meter-driven plan's cycle the
    # way ``performedOn`` resets a calendar plan's.
    meterValue = models.DecimalField(blank=True, null=True, decimal_places=3, max_digits=18)
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
    role = models.CharField(max_length=24, default="technician")
    unit = models.CharField(max_length=160, blank=True, default="")
    fromDate = models.DateField(null=True, blank=True)
    toDate = models.DateField(null=True, blank=True)
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "DeviceAssignment"
        ordering = ["role", "personnelName"]
        indexes = [models.Index(fields=["tenantId", "deviceId", "role"])]
        constraints = [
            # Phase 26.1: open vocabulary — see the location kind above.
            models.CheckConstraint(
                condition=~models.Q(role=""),
                name="ck_device_assignment_role",
            )
        ]


class PartReservationModel(models.Model):
    """رزرو قطعه روی درخواست کار — قابل هم‌گام‌سازی بین همه‌ی اعضای تیم."""

    # شناسه‌ی رشته‌ای: سمت فرانت با پیشوند rsv- ساخته می‌شود تا حالت آفلاین
    # (localStorage) و حالت آنلاین (پایگاه‌داده) از همین هویت استفاده کنند.
    id = models.CharField(max_length=64, primary_key=True)
    tenantId = models.UUIDField(db_index=True)
    workOrderId = models.UUIDField(db_index=True)
    partCode = models.CharField(max_length=60, db_index=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    status = models.CharField(
        max_length=16, default="active", db_index=True
    )  # active/consumed/released
    reservedByName = models.CharField(max_length=160, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    closedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "PartReservation"
        ordering = ["-createdAt"]


class InspectionTemplateModel(models.Model):
    """قالب چک‌لیست بازرسی — تیمی و مشترک بین تکنسین‌ها."""

    id = models.CharField(max_length=64, primary_key=True)
    tenantId = models.UUIDField(db_index=True)
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    deviceCode = models.CharField(max_length=60, blank=True, default="")
    checks = models.JSONField(default=list)
    isCommitted = models.BooleanField(default=False)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "InspectionTemplate"
        ordering = ["name"]


class InspectionRecordModel(models.Model):
    """سابقه‌ی اجرای چک‌لیست روی یک درخواست کار."""

    id = models.CharField(max_length=64, primary_key=True)
    tenantId = models.UUIDField(db_index=True)
    templateId = models.CharField(max_length=64, db_index=True)
    workOrderId = models.UUIDField(db_index=True, null=True, blank=True)
    deviceId = models.UUIDField(db_index=True)
    passedChecks = models.JSONField(default=list)
    failedChecks = models.JSONField(default=list)
    performedByName = models.CharField(max_length=160, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "InspectionRecord"
        ordering = ["-createdAt"]


class PartTransactionModel(models.Model):
    """دفتر تراکنش انبار — ردی نامتغیر برای هر ورود/خروج/برگشت/تعدیل."""

    TRANSACTION_TYPES = (
        ("RECEIPT", "رسید"),
        ("ISSUE", "حواله"),
        ("RETURN", "برگشت"),
        ("ADJUSTMENT", "تعدیل"),
    )

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    partCode = models.CharField(max_length=60)
    partName = models.CharField(max_length=200)
    unit = models.CharField(max_length=30, default="عدد")
    transactionType = models.CharField(max_length=12, choices=TRANSACTION_TYPES)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    balanceAfter = models.DecimalField(max_digits=14, decimal_places=3)
    note = models.CharField(max_length=500, blank=True, default="")
    reference = models.CharField(max_length=120, blank=True, default="")
    actorId = models.UUIDField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)

    class Meta:
        db_table = "PartTransaction"
        ordering = ["-createdAt"]
        constraints = [
            models.CheckConstraint(
                condition=~models.Q(quantity=0),
                name="ck_part_transaction_nonzero_quantity",
            ),
            models.CheckConstraint(
                condition=models.Q(balanceAfter__gte=0),
                name="ck_part_transaction_nonnegative_balance",
            ),
        ]


# =====================================================================================
# Meter readings — ثبت قرائت دستی و سنسوری
# =====================================================================================
class MeterPointModel(models.Model):
    """A measurable channel on one device (hour meter, kWh, temperature …)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=48)
    name = models.CharField(max_length=200)
    unit = models.CharField(max_length=30, blank=True, default="")
    kind = models.CharField(max_length=12, default="gauge", db_index=True)
    # Gateway binding (PLC tag / OPC-UA node / MQTT topic). Unique per tenant
    # when present, so one pushed sample can never match two meter points.
    sensorKey = models.CharField(max_length=120, blank=True, default="", db_index=True)
    minimumValue = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    maximumValue = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    rolloverMaximum = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    maximumStepPerHour = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    drivesRunningHours = models.BooleanField(default=False)
    active = models.BooleanField(default=True, db_index=True)
    # Denormalised current state, refreshed on append.
    lastValue = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    lastReadingAt = models.DateTimeField(null=True, blank=True)
    lastCaptureMode = models.CharField(max_length=10, blank=True, default="")
    readingCount = models.IntegerField(default=0)
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MeterPoint"
        ordering = ["code"]
        indexes = [
            models.Index(fields=["tenantId", "deviceId", "active"], name="ix_mpoint_tenant_dev"),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "deviceId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_meter_point_device_code",
            ),
            # One sensor key resolves to exactly one point, tenant-wide.
            models.UniqueConstraint(
                fields=["tenantId", "sensorKey"],
                condition=models.Q(deletedAt__isnull=True) & ~models.Q(sensorKey=""),
                name="uq_meter_point_sensor_key",
            ),
            models.CheckConstraint(
                condition=models.Q(kind__in=("cumulative", "gauge")),
                name="ck_meter_point_kind",
            ),
            models.CheckConstraint(
                condition=models.Q(minimumValue__isnull=True)
                | models.Q(maximumValue__isnull=True)
                | models.Q(minimumValue__lte=models.F("maximumValue")),
                name="ck_meter_point_range",
            ),
            models.CheckConstraint(
                condition=models.Q(rolloverMaximum__isnull=True) | models.Q(rolloverMaximum__gt=0),
                name="ck_meter_point_rollover_positive",
            ),
            # Only a counter can roll over; a thermometer that "wraps" is a
            # configuration mistake that would silently fabricate consumption.
            models.CheckConstraint(
                condition=models.Q(rolloverMaximum__isnull=True) | models.Q(kind="cumulative"),
                name="ck_meter_point_rollover_cumulative_only",
            ),
            # Running hours accumulate; a gauge can never be their source.
            models.CheckConstraint(
                condition=models.Q(drivesRunningHours=False) | models.Q(kind="cumulative"),
                name="ck_meter_point_hours_cumulative_only",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.code}:{self.name}"


class MeterReadingQuerySet(models.QuerySet):
    """Block accidental bulk mutation of the append-only reading stream."""

    def update(self, **kwargs) -> int:  # noqa: ANN003 — Django QuerySet contract
        raise MeterReadingImmutableError("Meter readings cannot be updated.")

    def delete(self) -> tuple[int, dict[str, int]]:
        raise MeterReadingImmutableError("Meter readings cannot be deleted.")

    def markSuperseded(self, readingId: uuid.UUID, correctionId: uuid.UUID) -> int:
        """The one sanctioned write to an existing row.

        Linking a mistake to its correction is bookkeeping about the row, not
        a change to the observation it records, so it is allowed — but only
        through this named method, and only on a row not already superseded.
        """
        rows = super().filter(id=readingId, supersededByReadingId__isnull=True)
        # Call Django's implementation directly: self.update() is the guard
        # above, and going through it here would block the one write we allow.
        return models.QuerySet.update(rows, supersededByReadingId=correctionId)


class MeterReadingModel(models.Model):
    """One observed meter value — immutable once written."""

    objects = MeterReadingQuerySet.as_manager()

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    deviceId = models.UUIDField(db_index=True)
    meterPoint = models.ForeignKey(
        MeterPointModel,
        on_delete=models.PROTECT,
        related_name="readings",
        db_column="meterPointId",
    )
    value = models.DecimalField(max_digits=18, decimal_places=4)
    delta = models.DecimalField(max_digits=18, decimal_places=4, null=True, blank=True)
    capturedAt = models.DateTimeField(db_index=True)
    captureMode = models.CharField(max_length=10, default="manual", db_index=True)
    quality = models.CharField(max_length=10, default="good", db_index=True)
    rolloverApplied = models.BooleanField(default=False)
    note = models.CharField(max_length=500, blank=True, default="")
    sensorKey = models.CharField(max_length=120, blank=True, default="")
    sourceRef = models.CharField(max_length=160, blank=True, default="")
    # Idempotency token from the gateway; unique per tenant when present so a
    # retried batch cannot double-count a counter.
    ingestionKey = models.CharField(max_length=128, null=True, blank=True)
    recordedById = models.UUIDField(null=True, blank=True)
    recordedByName = models.CharField(max_length=160, blank=True, default="")
    correctsReadingId = models.UUIDField(null=True, blank=True, db_index=True)
    supersededByReadingId = models.UUIDField(null=True, blank=True)
    correlationId = models.CharField(max_length=64, blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)

    class Meta:
        db_table = "MeterReading"
        ordering = ["-capturedAt", "-createdAt"]
        indexes = [
            models.Index(
                fields=["tenantId", "meterPoint", "capturedAt"],
                name="ix_mr_tenant_point_time",
            ),
            models.Index(
                fields=["tenantId", "deviceId", "capturedAt"],
                name="ix_mr_tenant_device_time",
            ),
            models.Index(
                fields=["tenantId", "captureMode", "capturedAt"],
                name="ix_mr_tenant_mode_time",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "ingestionKey"],
                condition=models.Q(ingestionKey__isnull=False),
                name="uq_meter_reading_ingestion_key",
            ),
            models.CheckConstraint(
                condition=models.Q(captureMode__in=("manual", "sensor")),
                name="ck_meter_reading_capture_mode",
            ),
            models.CheckConstraint(
                condition=models.Q(quality__in=("good", "suspect", "estimated", "bad")),
                name="ck_meter_reading_quality",
            ),
            # A reading cannot supersede itself — that would create a cycle
            # that makes the correction chain unresolvable.
            models.CheckConstraint(
                condition=~models.Q(supersededByReadingId=models.F("id")),
                name="ck_meter_reading_no_self_supersede",
            ),
            models.CheckConstraint(
                condition=~models.Q(correctsReadingId=models.F("id")),
                name="ck_meter_reading_no_self_correction",
            ),
        ]

    def save(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        """Allow the insert, and afterwards only the supersede bookkeeping."""
        if not self._state.adding:
            allowed = kwargs.get("update_fields") or ()
            if set(allowed) - {"supersededByReadingId"}:
                raise MeterReadingImmutableError("Meter readings cannot be updated.")
            if not allowed:
                raise MeterReadingImmutableError("Meter readings cannot be updated.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs) -> None:  # noqa: ANN002, ANN003
        raise MeterReadingImmutableError(
            "Meter readings cannot be deleted; append a correction instead."
        )


# =====================================================================================
# Field operations — work timers and offline sync (کار میدانی: تایمر و همگام‌سازی)
# =====================================================================================
class WorkTimerModel(models.Model):
    """A technician's running stopwatch on one work order.

    The row exists from «شروع کار» until «پایان کار». Stopping it mints a
    :class:`WorkOrderLabourEntryModel` from the measured span, so the cost
    report keeps a single source of truth (labour entries) while the timer
    table keeps the evidence of *when* the span was actually observed.

    ``startedAt`` is always the moment the technician pressed start — even if
    the press happened offline and reached the server hours later.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    workOrderId = models.UUIDField(db_index=True)
    technicianName = models.CharField(max_length=160)
    technicianUserId = models.UUIDField(null=True, blank=True, db_index=True)
    startedAt = models.DateTimeField(db_index=True)
    endedAt = models.DateTimeField(null=True, blank=True, db_index=True)
    pausedSeconds = models.IntegerField(default=0)
    hourlyRate = models.DecimalField(max_digits=16, decimal_places=2, default=0)
    startNote = models.CharField(max_length=500, blank=True, default="")
    endNote = models.CharField(max_length=500, blank=True, default="")
    labourEntryId = models.UUIDField(null=True, blank=True, db_index=True)
    capturedOffline = models.BooleanField(default=False)
    startedVia = models.CharField(max_length=12, default="online")
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "WorkTimer"
        ordering = ["-startedAt"]
        indexes = [
            models.Index(
                fields=["tenantId", "workOrderId", "startedAt"],
                name="ix_wt_tenant_order_start",
            ),
            models.Index(
                fields=["tenantId", "technicianName", "startedAt"],
                name="ix_wt_tenant_tech_start",
            ),
        ]
        constraints = [
            # One running stopwatch per technician per order. The filtered
            # condition is mandatory: SQL Server treats NULLs as equal in a
            # plain unique index, which would forbid a second *finished* span.
            models.UniqueConstraint(
                fields=["tenantId", "workOrderId", "technicianName"],
                condition=models.Q(endedAt__isnull=True),
                name="uq_work_timer_one_running_per_tech",
            ),
            models.CheckConstraint(
                condition=models.Q(endedAt__isnull=True)
                | models.Q(endedAt__gte=models.F("startedAt")),
                name="ck_work_timer_end_after_start",
            ),
            models.CheckConstraint(
                condition=models.Q(pausedSeconds__gte=0),
                name="ck_work_timer_paused_nonnegative",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.technicianName}@{self.workOrderId}:{self.startedAt:%Y-%m-%dT%H:%M}"


class OfflineSyncOperationModel(models.Model):
    """Durable idempotency ledger for operations captured offline.

    A phone that lost the network keeps its writes in a local queue and
    replays them later — possibly twice, possibly days later, possibly after
    a server restart. The shared-kernel ``IdempotencyMixin`` cannot carry that
    load: it is cache-backed (LocMem in development) and evaporates on
    restart. This table is the durable equivalent, keyed by the
    client-generated ``clientRequestId``.

    A replayed operation returns its *stored* outcome instead of executing
    again, so a double-sync can never create two labour entries or consume a
    spare part twice.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    clientRequestId = models.CharField(max_length=80)
    kind = models.CharField(max_length=40, db_index=True)
    status = models.CharField(max_length=12, default="applied", db_index=True)
    resultId = models.CharField(max_length=64, blank=True, default="")
    resultPayload = models.JSONField(default=dict, blank=True)
    errorCode = models.CharField(max_length=60, blank=True, default="")
    errorMessage = models.CharField(max_length=500, blank=True, default="")
    actorName = models.CharField(max_length=160, blank=True, default="")
    capturedAt = models.DateTimeField(null=True, blank=True)
    receivedAt = models.DateTimeField(db_index=True)
    deviceLabel = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "OfflineSyncOperation"
        ordering = ["-receivedAt"]
        indexes = [
            models.Index(
                fields=["tenantId", "kind", "receivedAt"],
                name="ix_sync_tenant_kind_time",
            ),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "clientRequestId"],
                name="uq_sync_operation_client_request",
            ),
            models.CheckConstraint(
                condition=models.Q(status__in=("applied", "failed", "rejected", "conflict")),
                name="ck_sync_operation_status",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.kind}:{self.clientRequestId}:{self.status}"


# =================================================================================
# Phase 28 — work calendar, holidays, shifts
# =================================================================================


class WorkCalendarModel(models.Model):
    """A site's working pattern: which days it opens and in which timezone.

    Scoped to a location rather than a tenant so a group with plants in
    different provinces — or different countries — can run different weekends,
    holidays and clocks under one account. A calendar with ``locationId`` null
    and ``isDefault`` true is the tenant-wide fallback used by every site that
    has not been given its own.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    #: The site this calendar governs. Null = tenant-wide default.
    locationId = models.UUIDField(null=True, blank=True, db_index=True)
    #: IANA name, not an offset: offsets change twice a year, names do not.
    timezone = models.CharField(max_length=64, default="Asia/Tehran")
    #: CSV of python weekday numbers (Mon 0 … Sun 6). Default is جمعه only.
    weekendDays = models.CharField(max_length=32, default="4")
    #: What to do with a PM landing on a closed day.
    rollPolicy = models.CharField(max_length=16, default="forward")
    isDefault = models.BooleanField(default=False)
    active = models.BooleanField(default=True)
    note = models.CharField(max_length=400, blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenanceWorkCalendar"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_calendar_tenant_code",
            ),
            # One calendar per site. Without this a location could end up with
            # two calendars and the resolver would have to guess which wins.
            models.UniqueConstraint(
                fields=["tenantId", "locationId"],
                condition=models.Q(deletedAt__isnull=True, locationId__isnull=False),
                name="uq_maintenance_calendar_tenant_location",
            ),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.code}:{self.name}"


class CalendarHolidayModel(models.Model):
    """One non-working date on a calendar.

    Stored as a concrete Gregorian date because that is what arithmetic needs.
    ``recursAnnually`` marks the fixed-Jalali holidays (نوروز, ۲۲ بهمن) whose
    Gregorian date drifts a day either way: the Jalali month/day is kept
    alongside so a later year can be generated without re-deriving it.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    calendarId = models.UUIDField(db_index=True)
    onDate = models.DateField(db_index=True)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, default="official")
    recursAnnually = models.BooleanField(default=False)
    #: Jalali month/day for recurring holidays; 0 when not applicable.
    jalaliMonth = models.PositiveSmallIntegerField(default=0)
    jalaliDay = models.PositiveSmallIntegerField(default=0)
    createdAt = models.DateTimeField(db_index=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenanceCalendarHoliday"
        ordering = ["onDate"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "calendarId", "onDate"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_holiday_calendar_date",
            )
        ]
        indexes = [models.Index(fields=["tenantId", "calendarId", "onDate"])]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.onDate}:{self.name}"


class WorkShiftModel(models.Model):
    """A staffed window on a calendar — the unit scheduling actually buys.

    ``headcount`` is the planned crew size. Real assignments live in
    ``ShiftAssignmentModel``; capacity prefers the assignments when they exist
    and falls back to this figure so a plant can plan before it rosters.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    calendarId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    kind = models.CharField(max_length=16, default="general")
    startTime = models.TimeField()
    endTime = models.TimeField()
    #: CSV of weekday numbers; empty = every day the calendar is open.
    weekdays = models.CharField(max_length=32, blank=True, default="")
    headcount = models.PositiveSmallIntegerField(default=0)
    active = models.BooleanField(default=True)
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenanceWorkShift"
        ordering = ["startTime"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "calendarId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_shift_calendar_code",
            )
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.code}:{self.startTime}-{self.endTime}"


class ShiftAssignmentModel(models.Model):
    """Which technician works which shift, over which period.

    Dated rather than a plain link so the roster has history: capacity for a
    date in the past is computed from who was actually on that shift then, not
    from today's roster.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    shiftId = models.UUIDField(db_index=True)
    personnelId = models.UUIDField(db_index=True)
    fromDate = models.DateField(db_index=True)
    #: Null = open-ended, still on this shift.
    toDate = models.DateField(null=True, blank=True)
    createdAt = models.DateTimeField(db_index=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenanceShiftAssignment"
        ordering = ["-fromDate"]
        indexes = [
            models.Index(fields=["tenantId", "shiftId", "fromDate"]),
            models.Index(fields=["tenantId", "personnelId"]),
        ]

    def __str__(self) -> str:  # pragma: no cover — debug helper
        return f"{self.personnelId}@{self.shiftId}"


class PerformanceReviewCycleModel(models.Model):
    """One appraisal round (دورهٔ ارزیابی) — Phase 29.

    A cycle is the unit everything else hangs off: scores belong to a cycle,
    results are computed per cycle, and a rater's standing is learned across
    cycles. Keeping the weights on the cycle rather than in global settings
    means a past review can always be recomputed under the rules it was
    actually judged by, instead of silently changing when somebody retunes
    the weights next year.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=200)
    fromDate = models.DateField()
    toDate = models.DateField()
    status = models.CharField(max_length=16, default="draft", db_index=True)
    #: Share of the final mark taken from measured work rather than opinion.
    systemWeightPercent = models.PositiveSmallIntegerField(default=30)
    #: JSON object of role -> relative weight; empty means use the defaults.
    roleWeights = models.TextField(blank=True, default="")
    note = models.CharField(max_length=400, blank=True, default="")
    createdAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenancePerformanceCycle"
        ordering = ["-fromDate", "name"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "code"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_perfcycle_tenant_code",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.code} — {self.name}"


class PerformanceRaterScoreModel(models.Model):
    """One manager's mark for one person in one cycle.

    The unique constraint is the honesty mechanism: a role gets exactly one
    score per person per cycle. Without it the same manager could submit
    twice and double their own weight.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    cycleId = models.UUIDField(db_index=True)
    personnelId = models.UUIDField(db_index=True)
    raterRole = models.CharField(max_length=32, db_index=True)
    #: Who submitted it, for the audit trail — a role is not a person.
    raterUserId = models.UUIDField(null=True, blank=True)
    raterName = models.CharField(max_length=200, blank=True, default="")
    score = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    note = models.CharField(max_length=600, blank=True, default="")
    submittedAt = models.DateTimeField(db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenancePerformanceRaterScore"
        ordering = ["raterRole"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "cycleId", "personnelId", "raterRole"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_perfscore_cycle_person_role",
            ),
        ]
        indexes = [
            models.Index(
                fields=["tenantId", "cycleId", "personnelId"],
                name="ix_perfscore_cycle_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.raterRole}: {self.score}"


class PerformanceResultModel(models.Model):
    """The computed outcome for one person in one cycle.

    Stored rather than recomputed on every read for one reason: once a cycle
    is closed the number has been shown to the person it describes, and it
    must not drift afterwards because a work order was backdated or a weight
    was retuned. ``breakdown`` keeps the full per-rater audit trail as JSON so
    "why is my score this?" stays answerable years later.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    cycleId = models.UUIDField(db_index=True)
    personnelId = models.UUIDField(db_index=True)
    finalScore = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    humanScore = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    systemScore = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    consensus = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    spread = models.DecimalField(max_digits=6, decimal_places=2, default=0)
    raterCount = models.PositiveSmallIntegerField(default=0)
    dampedCount = models.PositiveSmallIntegerField(default=0)
    systemWeightPercent = models.PositiveSmallIntegerField(default=30)
    #: JSON: per-rater weights, damping and the reason for each.
    breakdown = models.TextField(blank=True, default="")
    computedAt = models.DateTimeField(db_index=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "MaintenancePerformanceResult"
        ordering = ["-finalScore"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "cycleId", "personnelId"],
                condition=models.Q(deletedAt__isnull=True),
                name="uq_maintenance_perfresult_cycle_person",
            ),
        ]

    def __str__(self) -> str:
        return f"{self.personnelId}: {self.finalScore}"
