"""Equipment-registry request serializers (Phase 26)."""

from __future__ import annotations

from rest_framework import serializers

from apps.maintenance.domain.valueObjects.maintenanceState import (
    ASSET_CRITICALITIES,
    DEVICE_ASSIGNMENT_ROLES,
    LOCATION_KINDS,
    MAINTENANCE_DEPARTMENTS,
    PM_FREQUENCY_UNITS,
)

DEPARTMENT_CHOICES = list(MAINTENANCE_DEPARTMENTS)
CRITICALITY_CHOICES = list(ASSET_CRITICALITIES)
LOCATION_KIND_CHOICES = list(LOCATION_KINDS)
FREQUENCY_UNIT_CHOICES = list(PM_FREQUENCY_UNITS)
ASSIGNMENT_ROLE_CHOICES = list(DEVICE_ASSIGNMENT_ROLES)


class SaveLocationSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=200)
    kind = serializers.ChoiceField(choices=LOCATION_KIND_CHOICES, default="site")
    parentId = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class SavePersonnelSerializer(serializers.Serializer):
    personnelCode = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    fullName = serializers.CharField(max_length=200)
    specialty = serializers.ChoiceField(choices=DEPARTMENT_CHOICES, default="general")
    unit = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    shift = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    skills = serializers.ListField(
        child=serializers.CharField(max_length=160), required=False, default=list
    )
    certifications = serializers.ListField(
        child=serializers.CharField(max_length=160), required=False, default=list
    )
    active = serializers.BooleanField(required=False, default=True)


class SpecificationRowSerializer(serializers.Serializer):
    label = serializers.CharField(max_length=160)
    value = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    unit = serializers.CharField(max_length=40, required=False, allow_blank=True, default="")
    sortOrder = serializers.IntegerField(required=False, default=0)


class SaveSpecificationsSerializer(serializers.Serializer):
    rows = SpecificationRowSerializer(many=True)


class SavePmPlanSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    discipline = serializers.ChoiceField(choices=DEPARTMENT_CHOICES, default="general")
    description = serializers.CharField(required=False, allow_blank=True, default="")
    checklist = serializers.ListField(
        child=serializers.CharField(max_length=300), required=False, default=list
    )
    frequencyEvery = serializers.IntegerField(required=False, min_value=1, default=1)
    frequencyUnit = serializers.ChoiceField(choices=FREQUENCY_UNIT_CHOICES, default="month")
    estimatedMinutes = serializers.IntegerField(required=False, min_value=0, default=0)
    responsibleName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    active = serializers.BooleanField(required=False, default=True)


class RecordPmExecutionSerializer(serializers.Serializer):
    performedOn = serializers.CharField(required=False, allow_blank=True, default="")
    performedByName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    durationMinutes = serializers.IntegerField(required=False, min_value=0, default=0)
    findings = serializers.CharField(required=False, allow_blank=True, default="")


class SaveBomItemSerializer(serializers.Serializer):
    partId = serializers.CharField()
    position = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    standardQuantity = serializers.CharField(required=False, default="1")
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


class AssignmentRowSerializer(serializers.Serializer):
    personnelId = serializers.CharField(required=False, allow_blank=True, default="")
    personnelName = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    role = serializers.ChoiceField(choices=ASSIGNMENT_ROLE_CHOICES, default="technician")
    unit = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    fromDate = serializers.CharField(required=False, allow_blank=True, default="")
    toDate = serializers.CharField(required=False, allow_blank=True, default="")


class SaveAssignmentsSerializer(serializers.Serializer):
    rows = AssignmentRowSerializer(many=True)


class UpdateDeviceNameplateSerializer(serializers.Serializer):
    """Optional registry attributes of a device; every field may be omitted."""

    manufacturer = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    modelNumber = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    serialNumber = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    assetType = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    manufactureYear = serializers.CharField(
        max_length=10, required=False, allow_blank=True, default=""
    )
    capacity = serializers.CharField(max_length=160, required=False, allow_blank=True, default="")
    powerRating = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    electricalSpec = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    criticality = serializers.ChoiceField(
        choices=CRITICALITY_CHOICES, required=False, default="medium"
    )
    parentDeviceId = serializers.CharField(required=False, allow_blank=True, default="")
    locationId = serializers.CharField(required=False, allow_blank=True, default="")
    operatorUnit = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    supplier = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    purchasedOn = serializers.CharField(required=False, allow_blank=True, default="")
    installedOn = serializers.CharField(required=False, allow_blank=True, default="")
    commissionedOn = serializers.CharField(required=False, allow_blank=True, default="")
    warrantyUntil = serializers.CharField(required=False, allow_blank=True, default="")
    purchaseCost = serializers.CharField(required=False, allow_blank=True, default="0")
    runningHours = serializers.CharField(required=False, allow_blank=True, default="0")
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class CloseWorkOrderDetailsSerializer(serializers.Serializer):
    """Failure, downtime and cost facts captured when a repair is closed."""

    failureType = serializers.CharField(
        max_length=24, required=False, allow_blank=True, default=""
    )
    failedComponent = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
    )
    failureSymptom = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    rootCause = serializers.CharField(required=False, allow_blank=True, default="")
    actionTaken = serializers.CharField(required=False, allow_blank=True, default="")
    repeatFailure = serializers.BooleanField(required=False, default=False)
    failureReportedAt = serializers.CharField(required=False, allow_blank=True, default="")
    repairStartedAt = serializers.CharField(required=False, allow_blank=True, default="")
    repairFinishedAt = serializers.CharField(required=False, allow_blank=True, default="")
    returnedToServiceAt = serializers.CharField(required=False, allow_blank=True, default="")
    downtimeMinutes = serializers.IntegerField(required=False, min_value=0, default=0)
    labourHours = serializers.CharField(required=False, allow_blank=True, default="0")
    labourCost = serializers.CharField(required=False, allow_blank=True, default="0")
    partsCost = serializers.CharField(required=False, allow_blank=True, default="0")
