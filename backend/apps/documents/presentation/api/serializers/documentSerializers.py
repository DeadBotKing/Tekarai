"""Documents API serializers (Phase 31)."""

from __future__ import annotations

from rest_framework import serializers


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    deviceIds = serializers.ListField(child=serializers.UUIDField(), required=False, default=list, max_length=500)
    category = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    description = serializers.CharField(
        max_length=2000, required=False, allow_blank=True, default=""
    )


class DocumentUpdateSerializer(serializers.Serializer):
    category = serializers.CharField(max_length=80, required=False, allow_blank=True)
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True)
    deviceIds = serializers.ListField(child=serializers.UUIDField(), required=False, max_length=500)


class DocumentListSerializer(serializers.Serializer):
    search = serializers.CharField(required=False, allow_blank=True, default="")
    category = serializers.CharField(required=False, allow_blank=True, default="")
    deviceId = serializers.UUIDField(required=False)
    limit = serializers.IntegerField(min_value=1, max_value=200, required=False, default=50)
    offset = serializers.IntegerField(min_value=0, required=False, default=0)
