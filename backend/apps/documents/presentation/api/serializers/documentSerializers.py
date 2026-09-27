"""Documents API serializers (Phase 31)."""

from __future__ import annotations

from rest_framework import serializers


class DocumentUploadSerializer(serializers.Serializer):
    file = serializers.FileField()
    category = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    description = serializers.CharField(max_length=2000, required=False, allow_blank=True, default="")
