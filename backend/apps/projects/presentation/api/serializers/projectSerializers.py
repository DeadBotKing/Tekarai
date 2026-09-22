"""Project request serializers (Phase 18b)."""

from __future__ import annotations

from rest_framework import serializers


class CreateProjectSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=32)
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ownerName = serializers.CharField(required=False, allow_blank=True, default="")
    dueDate = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateProjectSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    ownerName = serializers.CharField(required=False, allow_blank=True, default="")
    dueDate = serializers.CharField(required=False, allow_blank=True, default="")
    progress = serializers.IntegerField(min_value=0, max_value=100, required=False, default=0)
    health = serializers.IntegerField(min_value=0, max_value=100, required=False, default=100)


class ChangeProjectStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=["active", "onHold", "completed", "archived"])
