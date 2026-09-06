"""Input-only DRF serializers for the Phase 13-Z public API."""

from rest_framework import serializers


class AgentRegistrationSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=80)
    name = serializers.CharField(max_length=160)
    instructions = serializers.CharField(max_length=65536)
    description = serializers.CharField(required=False, allow_blank=True, default="")
    version = serializers.IntegerField(required=False, min_value=1)
    accessLevel = serializers.ChoiceField(
        choices=["ADVISORY", "READ_ONLY", "MUTATING", "AUTONOMOUS"], default="ADVISORY"
    )
    riskLevel = serializers.ChoiceField(
        choices=["LOW", "MEDIUM", "HIGH", "CRITICAL"], default="LOW"
    )
    capabilityCodes = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, default=list
    )
    toolCodes = serializers.ListField(
        child=serializers.CharField(max_length=80), required=False, default=list
    )
    outputSchema = serializers.DictField(required=False, default=dict)
    contextPolicy = serializers.DictField(required=False, default=dict)
    modelPolicy = serializers.DictField(required=False, default=dict)
    permissionPolicy = serializers.DictField(required=False, default=dict)
    executionPolicy = serializers.DictField(required=False, default=dict)
    declaredApprovalMode = serializers.ChoiceField(
        choices=["", "AUTOMATIC", "HUMAN_REQUIRED", "DUAL_CONTROL"],
        required=False,
        allow_blank=True,
        default="",
    )
    metadata = serializers.DictField(required=False, default=dict)


class AgentVersionSerializer(serializers.Serializer):
    overrides = serializers.DictField(required=False, default=dict)


class AgentActionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class AgentRunSerializer(serializers.Serializer):
    input = serializers.DictField(required=False, default=dict)
    version = serializers.IntegerField(required=False, allow_null=True, min_value=1)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    approvalId = serializers.UUIDField(required=False, allow_null=True)
    mode = serializers.ChoiceField(choices=["SYNC", "ASYNC"], default="SYNC")
    idempotencyKey = serializers.CharField(
        required=False, allow_blank=True, max_length=200, default=""
    )
    priority = serializers.IntegerField(required=False, min_value=0, max_value=9, default=5)


class ApprovalDecisionSerializer(serializers.Serializer):
    reason = serializers.CharField(required=False, allow_blank=True, default="")


class RetentionSerializer(serializers.Serializer):
    retentionDays = serializers.IntegerField(required=False, min_value=1)
