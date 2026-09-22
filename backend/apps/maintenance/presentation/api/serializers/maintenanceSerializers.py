"""Maintenance request serializers (Phase 21)."""

from __future__ import annotations

from rest_framework import serializers

DEVICE_STATUS_CHOICES = ["operational", "underMaintenance", "outOfService", "retired"]
WORK_ORDER_TYPE_CHOICES = ["corrective", "preventive", "inspection"]
WORK_ORDER_STATUS_CHOICES = [
    "submitted",
    "routed",
    "assigned",
    "inProgress",
    "onHold",
    "completed",
    "cancelled",
]
PRIORITY_CHOICES = ["low", "normal", "high", "critical"]
DEPARTMENT_CHOICES = [
    "general",
    "electrical",
    "mechanical",
    "facilities",
    "instrumentation",
]


# -- Device -----------------------------------------------------------------------
class RegisterDeviceSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60)
    name = serializers.CharField(max_length=200)
    location = serializers.CharField(required=False, allow_blank=True, default="")
    department = serializers.ChoiceField(choices=DEPARTMENT_CHOICES, default="general")
    pmIntervalDays = serializers.IntegerField(required=False, min_value=0, default=0)


class UpdateDeviceSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    location = serializers.CharField(required=False, allow_blank=True, default="")
    department = serializers.ChoiceField(choices=DEPARTMENT_CHOICES, default="general")
    pmIntervalDays = serializers.IntegerField(required=False, min_value=0, default=0)


class ChangeDeviceStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=DEVICE_STATUS_CHOICES)


class RecordDevicePmSerializer(serializers.Serializer):
    performedOn = serializers.CharField(required=False, allow_blank=True, default="")


# -- Work order -------------------------------------------------------------------
class SubmitWorkOrderSerializer(serializers.Serializer):
    deviceId = serializers.CharField()
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    orderType = serializers.ChoiceField(choices=WORK_ORDER_TYPE_CHOICES, default="corrective")
    priority = serializers.ChoiceField(choices=PRIORITY_CHOICES, default="normal")
    department = serializers.ChoiceField(
        choices=DEPARTMENT_CHOICES, required=False, allow_blank=True, default=""
    )
    requestedByName = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateWorkOrderSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    priority = serializers.ChoiceField(choices=PRIORITY_CHOICES, default="normal")


class RouteWorkOrderSerializer(serializers.Serializer):
    department = serializers.ChoiceField(choices=DEPARTMENT_CHOICES)


class AssignWorkOrderSerializer(serializers.Serializer):
    assignedToName = serializers.CharField(max_length=160)


class ChangeWorkOrderStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=WORK_ORDER_STATUS_CHOICES)
    resolutionNote = serializers.CharField(required=False, allow_blank=True, default="")
