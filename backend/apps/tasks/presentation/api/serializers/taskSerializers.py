"""Task request serializers (Phase 18b)."""

from __future__ import annotations

from rest_framework import serializers


class CreateTaskSerializer(serializers.Serializer):
    projectId = serializers.CharField(required=False, allow_blank=True, default="")
    title = serializers.CharField(max_length=300)
    priority = serializers.ChoiceField(choices=["low", "normal", "high", "critical"], default="normal")
    assigneeName = serializers.CharField(required=False, allow_blank=True, default="")
    dueDate = serializers.CharField(required=False, allow_blank=True, default="")
    estimate = serializers.CharField(required=False, allow_blank=True, default="")


class UpdateTaskSerializer(serializers.Serializer):
    title = serializers.CharField(max_length=300)
    priority = serializers.ChoiceField(choices=["low", "normal", "high", "critical"], default="normal")
    assigneeName = serializers.CharField(required=False, allow_blank=True, default="")
    dueDate = serializers.CharField(required=False, allow_blank=True, default="")
    estimate = serializers.CharField(required=False, allow_blank=True, default="")


class ChangeTaskStatusSerializer(serializers.Serializer):
    target = serializers.ChoiceField(choices=["backlog", "todo", "inProgress", "review", "done"])
