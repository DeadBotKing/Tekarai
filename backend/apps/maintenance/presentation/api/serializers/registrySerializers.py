"""Equipment-registry request serializers (Phase 26)."""

from __future__ import annotations

from rest_framework import serializers

from apps.maintenance.presentation.api.serializers.taxonomyFields import openVocabulary

from apps.maintenance.domain.valueObjects.maintenanceState import (
    ASSET_CRITICALITIES,
    ASSET_LEVELS,
    DEVICE_ASSIGNMENT_ROLES,
    LOCATION_KINDS,
    MAINTENANCE_DEPARTMENTS,
    PM_FREQUENCY_UNITS,
)
from apps.maintenance.domain.valueObjects.meterTypes import (
    PM_TRIGGER_TYPES,
    THRESHOLD_OPERATORS,
)

DEPARTMENT_CHOICES = list(MAINTENANCE_DEPARTMENTS)
CRITICALITY_CHOICES = list(ASSET_CRITICALITIES)
LOCATION_KIND_CHOICES = list(LOCATION_KINDS)
ASSET_LEVEL_CHOICES = list(ASSET_LEVELS)
FREQUENCY_UNIT_CHOICES = list(PM_FREQUENCY_UNITS)
ASSIGNMENT_ROLE_CHOICES = list(DEVICE_ASSIGNMENT_ROLES)
TRIGGER_TYPE_CHOICES = list(PM_TRIGGER_TYPES)
THRESHOLD_OPERATOR_CHOICES = list(THRESHOLD_OPERATORS)


class SaveLocationSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=200)
    kind = openVocabulary(LOCATION_KIND_CHOICES, default="site")
    parentId = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(required=False, allow_blank=True, default="")


class SavePersonnelSerializer(serializers.Serializer):
    personnelCode = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    fullName = serializers.CharField(max_length=200)
    specialty = openVocabulary(DEPARTMENT_CHOICES, default="general")
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
    discipline = openVocabulary(DEPARTMENT_CHOICES, default="general")
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
    # -- Meter / condition trigger (Phase 33) -------------------------------------
    # Decimals travel as strings: a JSON number is a double in every browser,
    # and a threshold is a contractual value that must not be rounded.
    triggerType = serializers.ChoiceField(
        choices=TRIGGER_TYPE_CHOICES, required=False, default="calendar"
    )
    metricType = serializers.CharField(
        max_length=48, required=False, allow_blank=True, default=""
    )
    metricInterval = serializers.CharField(required=False, allow_blank=True, default="")
    thresholdOperator = serializers.ChoiceField(
        choices=THRESHOLD_OPERATOR_CHOICES, required=False, default=">="
    )
    thresholdValue = serializers.CharField(required=False, allow_blank=True, default="")
    warningValue = serializers.CharField(required=False, allow_blank=True, default="")
    metricUnit = serializers.CharField(
        max_length=30, required=False, allow_blank=True, default=""
    )
    sensorKey = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )


class RecordPmExecutionSerializer(serializers.Serializer):
    performedOn = serializers.CharField(required=False, allow_blank=True, default="")
    performedByName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    durationMinutes = serializers.IntegerField(required=False, min_value=0, default=0)
    findings = serializers.CharField(required=False, allow_blank=True, default="")
    #: Meter value observed at execution — resets a meter-driven plan's cycle.
    meterValue = serializers.CharField(required=False, allow_blank=True, default="")


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
    role = openVocabulary(ASSIGNMENT_ROLE_CHOICES, default="technician")
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
    criticality = openVocabulary(CRITICALITY_CHOICES, default="medium")
    assetLevel = openVocabulary(ASSET_LEVEL_CHOICES, default="mainEquipment")
    costCenterCode = serializers.CharField(
        max_length=60, required=False, allow_blank=True, default=""
    )
    costCenterName = serializers.CharField(
        max_length=200, required=False, allow_blank=True, default=""
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


# =====================================================================================
# Asset hierarchy (Phase 27)
# =====================================================================================
class MoveAssetSerializer(serializers.Serializer):
    """Relocate an asset. Omitting a target leaves that side untouched; the
    explicit ``clear*`` flags are how a caller detaches instead."""

    toLocationId = serializers.CharField(required=False, allow_blank=True, default="")
    toParentDeviceId = serializers.CharField(required=False, allow_blank=True, default="")
    movedOn = serializers.CharField(required=False, allow_blank=True, default="")
    reason = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    performedBy = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    note = serializers.CharField(required=False, allow_blank=True, default="")
    updateInstalledOn = serializers.BooleanField(required=False, default=False)
    clearLocation = serializers.BooleanField(required=False, default=False)
    clearParent = serializers.BooleanField(required=False, default=False)


class RetireAssetSerializer(serializers.Serializer):
    retiredOn = serializers.CharField(required=False, allow_blank=True, default="")
    reason = serializers.CharField(
        max_length=300, required=False, allow_blank=True, default=""
    )
    retireChildren = serializers.BooleanField(required=False, default=False)


class ReinstateAssetSerializer(serializers.Serializer):
    status = serializers.CharField(required=False, allow_blank=True, default="operational")
