"""Maintenance request serializers (Phase 21)."""

from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers

from apps.maintenance.presentation.api.serializers.taxonomyFields import openVocabulary

from apps.maintenance.domain.valueObjects.maintenanceState import MAINTENANCE_DEPARTMENTS

DEVICE_STATUS_CHOICES = ["operational", "underMaintenance", "outOfService", "retired"]
WORK_ORDER_TYPE_CHOICES = ["corrective", "preventive", "inspection"]
WORK_ORDER_STATUS_CHOICES = [
    "submitted",
    "routed",
    "assigned",
    "inProgress",
    "onHold",
    "pendingApproval",
    "completed",
    "cancelled",
]
PRIORITY_CHOICES = ["low", "normal", "high", "critical"]
# Derived from the domain catalogue so the seven maintenance disciplines
# (general, electrical, mechanical, facilities, instrumentation, hydraulic,
# pneumatic) never drift between the domain and the API contract.
DEPARTMENT_CHOICES = list(MAINTENANCE_DEPARTMENTS)


# -- Device -----------------------------------------------------------------------
class RegisterDeviceSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60)
    name = serializers.CharField(max_length=200)
    location = serializers.CharField(required=False, allow_blank=True, default="")
    department = openVocabulary(DEPARTMENT_CHOICES, default="general")
    pmIntervalDays = serializers.IntegerField(required=False, min_value=0, default=0)


class UpdateDeviceSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    location = serializers.CharField(required=False, allow_blank=True, default="")
    department = openVocabulary(DEPARTMENT_CHOICES, default="general")
    pmIntervalDays = serializers.IntegerField(required=False, min_value=0, default=0)


class ChangeDeviceStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=DEVICE_STATUS_CHOICES)


class RecordDevicePmSerializer(serializers.Serializer):
    performedOn = serializers.CharField(required=False, allow_blank=True, default="")


# -- Maintenance attachments -------------------------------------------------------
class MaintenanceAttachmentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    category = serializers.ChoiceField(
        choices=("failurePhoto", "manual", "invoice", "other"), default="other"
    )


# -- Spare-parts inventory ---------------------------------------------------------
class CreateSparePartSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60)
    name = serializers.CharField(max_length=200)
    unit = serializers.CharField(max_length=30, required=False, default="عدد")
    quantityOnHand = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0"))
    minimumStock = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0"), required=False, default=0
    )


class UpdateSparePartSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    unit = serializers.CharField(max_length=30, required=False, default="عدد")
    quantityOnHand = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0"))
    minimumStock = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0"), required=False, default=0
    )


class ConsumeSparePartSerializer(serializers.Serializer):
    partId = serializers.UUIDField()
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")


# -- Work order -------------------------------------------------------------------
class SubmitWorkOrderSerializer(serializers.Serializer):
    deviceId = serializers.CharField()
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    orderType = serializers.ChoiceField(choices=WORK_ORDER_TYPE_CHOICES, default="corrective")
    priority = serializers.ChoiceField(choices=PRIORITY_CHOICES, default="normal")
    department = openVocabulary(DEPARTMENT_CHOICES, default="", allowBlank=True)
    requestedByName = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateWorkOrderSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.ChoiceField(choices=PRIORITY_CHOICES, default="normal")


class RouteWorkOrderSerializer(serializers.Serializer):
    department = openVocabulary(DEPARTMENT_CHOICES)


class AssignWorkOrderSerializer(serializers.Serializer):
    # When ``auto`` is true the technician name is optional — the server picks
    # the least-loaded technician of the order's department.
    assignedToName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    auto = serializers.BooleanField(required=False, default=False)


class ChangeWorkOrderStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=WORK_ORDER_STATUS_CHOICES)
    resolutionNote = serializers.CharField(required=False, allow_blank=True, default="")


class ApproveWorkOrderSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class RejectWorkOrderSerializer(serializers.Serializer):
    note = serializers.CharField(required=False, allow_blank=True, default="")


class DeviceReportQuerySerializer(serializers.Serializer):
    """Optional inclusive date bounds (YYYY-MM-DD) and export format.

    The export selector is named ``export`` (not ``format``) on purpose:
    DRF reserves the ``format`` query param for content negotiation and would
    404 on an unknown value before the view ever runs.
    """

    fromDate = serializers.DateField(required=False, allow_null=True, default=None)
    toDate = serializers.DateField(required=False, allow_null=True, default=None)
    export = serializers.ChoiceField(
        choices=("json", "csv", "xlsx"), required=False, default="json"
    )
