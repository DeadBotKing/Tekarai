"""Input serializers — team sync (reservations & inspection templates)."""

from __future__ import annotations

from rest_framework import serializers


class SaveReservationSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=64)
    orderId = serializers.CharField(max_length=64)
    partCode = serializers.CharField(max_length=60)
    quantity = serializers.CharField(max_length=24, default="0")
    status = serializers.CharField(max_length=16, default="active", required=False)
    reservedByName = serializers.CharField(max_length=160, default="", required=False)


class CloseReservationSerializer(serializers.Serializer):
    status = serializers.ChoiceField(choices=("consumed", "released"))


class SaveInspectionTemplateSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=200)
    description = serializers.CharField(default="", required=False)
    deviceCode = serializers.CharField(max_length=60, default="", required=False)
    checks = serializers.ListField(
        child=serializers.CharField(max_length=200), default=list, required=False
    )


class SaveInspectionRecordSerializer(serializers.Serializer):
    id = serializers.CharField(max_length=64)
    templateId = serializers.CharField(max_length=64)
    workOrderId = serializers.CharField(max_length=64)
    deviceId = serializers.CharField(max_length=64)
    passedChecks = serializers.ListField(
        child=serializers.CharField(max_length=200), default=list, required=False
    )
    failedChecks = serializers.ListField(
        child=serializers.CharField(max_length=200), default=list, required=False
    )
    performedByName = serializers.CharField(max_length=160, default="", required=False)
