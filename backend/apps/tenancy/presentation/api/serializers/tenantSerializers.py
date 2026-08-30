"""Tenant request serializers — API-layer input validation only (§12).

Business rules never live here (§1: no serializer owns a business rule);
serializers just shape and type-check incoming JSON before it becomes a
command.
"""

from __future__ import annotations

from rest_framework import serializers


class CreateTenantSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)


class ChangeTenantStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=["active", "suspended", "closed"])
    reason = serializers.CharField(required=False, allow_blank=True, max_length=500)
