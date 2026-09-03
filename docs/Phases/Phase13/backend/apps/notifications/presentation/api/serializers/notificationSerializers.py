"""Notification API serializers (Phase 09 §40)."""

from __future__ import annotations

from rest_framework import serializers


class CreateNotificationSerializer(serializers.Serializer):
    """§40 admin/system send surface (services normally arrive via §30)."""

    recipientType = serializers.CharField(max_length=32)
    recipientValue = serializers.JSONField(required=False, default=list)
    notificationType = serializers.CharField(max_length=120)
    category = serializers.CharField(max_length=32)
    priority = serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"], default="NORMAL"
    )
    title = serializers.CharField(max_length=300)
    body = serializers.CharField(required=False, default="", allow_blank=True)
    sourceType = serializers.CharField(max_length=64, required=False, allow_blank=True, default="")
    sourceId = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    templateKey = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    actionUrl = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    ackRequired = serializers.BooleanField(default=False)
    channels = serializers.ListField(
        child=serializers.CharField(), required=False, default=list
    )
    data = serializers.DictField(required=False, default=dict)
    eventId = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    expiresAt = serializers.DateTimeField(required=False, allow_null=True, default=None)


class ScheduleNotificationSerializer(serializers.Serializer):
    kind = serializers.ChoiceField(
        choices=["IMMEDIATE", "SCHEDULED", "RECURRING", "DELAYED", "DIGEST"]
    )
    recipientType = serializers.CharField(max_length=32)
    recipientValue = serializers.JSONField(required=False, default=list)
    notificationType = serializers.CharField(max_length=120)
    category = serializers.CharField(max_length=32)
    priority = serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"], default="NORMAL"
    )
    title = serializers.CharField(max_length=300)
    body = serializers.CharField(required=False, default="", allow_blank=True)
    scheduledAt = serializers.DateTimeField(required=False, allow_null=True, default=None)
    recurEverySeconds = serializers.IntegerField(default=0, min_value=0)
    delaySeconds = serializers.IntegerField(default=0, min_value=0)
    payload = serializers.DictField(required=False, default=dict)


class PreferenceInSerializer(serializers.Serializer):
    level = serializers.ChoiceField(choices=["GLOBAL", "CATEGORY", "TYPE"])
    channel = serializers.CharField(max_length=16)
    category = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    notificationType = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    enabled = serializers.BooleanField(default=True)
    quietHoursStart = serializers.CharField(
        max_length=8, required=False, allow_blank=True, default=""
    )
    quietHoursEnd = serializers.CharField(
        max_length=8, required=False, allow_blank=True, default=""
    )


class UpdatePreferencesSerializer(serializers.Serializer):
    preferences = PreferenceInSerializer(many=True)


class RegisterDeviceSerializer(serializers.Serializer):
    platform = serializers.ChoiceField(choices=["IOS", "ANDROID", "WEB", "DESKTOP", "OTHER"])
    deviceIdentifier = serializers.CharField(max_length=190)
    pushToken = serializers.CharField(max_length=512)
    provider = serializers.CharField(max_length=48, required=False, default="FCM")


class SaveTemplateSerializer(serializers.Serializer):
    templateKey = serializers.CharField(max_length=120)
    language = serializers.CharField(max_length=16)
    channel = serializers.CharField(max_length=16)
    title = serializers.CharField(max_length=300)
    subject = serializers.CharField(max_length=300, required=False, allow_blank=True, default="")
    body = serializers.CharField(required=False, allow_blank=True, default="")


class SavePolicySerializer(serializers.Serializer):
    policyKey = serializers.CharField(max_length=120)
    matchType = serializers.ChoiceField(choices=["TYPE", "CATEGORY"])
    matchValue = serializers.CharField(max_length=120)
    channels = serializers.ListField(child=serializers.CharField(), default=list)
    priority = serializers.ChoiceField(
        choices=["LOW", "NORMAL", "HIGH", "URGENT", "CRITICAL"], default="NORMAL"
    )
    templateKey = serializers.CharField(max_length=120, required=False, allow_blank=True, default="")
    maxRetries = serializers.IntegerField(default=3, min_value=1, max_value=10)
    cooldownSeconds = serializers.IntegerField(default=60, min_value=0)
    digestKind = serializers.ChoiceField(
        choices=["", "HOURLY", "DAILY", "WEEKLY"], required=False, allow_blank=True, default=""
    )
    allowPreferenceBypass = serializers.BooleanField(default=False)
    escalationStages = serializers.ListField(
        child=serializers.DictField(), required=False, default=list
    )


class SaveTenantRuleSerializer(serializers.Serializer):
    effect = serializers.ChoiceField(choices=["FORCED", "DENIED"])
    channel = serializers.CharField(max_length=16)
    category = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    notificationType = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
