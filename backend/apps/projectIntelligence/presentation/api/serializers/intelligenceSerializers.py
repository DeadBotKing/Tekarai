"""Strict Phase 17 request validation."""

from rest_framework import serializers


class WorkspaceSerializer(serializers.Serializer):
    workspace = serializers.CharField(max_length=1000, default=".")


class AnalyzeSerializer(WorkspaceSerializer):
    idempotencyKey = serializers.CharField(max_length=120, required=False, default="")
    priority = serializers.IntegerField(min_value=0, max_value=9, default=5)


class ContextSerializer(serializers.Serializer):
    task = serializers.CharField(max_length=2000)
    tokenBudget = serializers.IntegerField(min_value=256, max_value=100000, default=4000)


class CompareSerializer(serializers.Serializer):
    fromSnapshotId = serializers.UUIDField()
    toSnapshotId = serializers.UUIDField(required=False, allow_null=True)
