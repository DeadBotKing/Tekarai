"""Identity request serializers — input shaping only (§12/§1)."""

from __future__ import annotations

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    tenantCode = serializers.CharField(max_length=64)
    username = serializers.CharField(max_length=64)
    password = serializers.CharField(max_length=200, write_only=True)


class RefreshSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class CreateUserSerializer(serializers.Serializer):
    username = serializers.CharField(max_length=64)
    email = serializers.EmailField(max_length=320)
    password = serializers.CharField(max_length=200, write_only=True, min_length=12)
    displayName = serializers.CharField(max_length=160, required=False, allow_blank=True)


class AssignMembershipSerializer(serializers.Serializer):
    tenantId = serializers.UUIDField()
