"""Identity request serializers — input shaping only (§12/§1)."""

from __future__ import annotations

from rest_framework import serializers


class LoginSerializer(serializers.Serializer):
    tenantCode = serializers.CharField(max_length=64)
    identifier = serializers.CharField(max_length=320, help_text="username or email (§4)")
    password = serializers.CharField(max_length=200, write_only=True, trim_whitespace=False)


class RefreshSerializer(serializers.Serializer):
    refreshToken = serializers.CharField(max_length=200)


class MfaChallengeSerializer(serializers.Serializer):
    challengeToken = serializers.CharField(max_length=2048)
    code = serializers.CharField(max_length=24)


class ChangePasswordSerializer(serializers.Serializer):
    currentPassword = serializers.CharField(max_length=200, write_only=True, trim_whitespace=False)
    newPassword = serializers.CharField(max_length=200, write_only=True, trim_whitespace=False)


class PasswordResetRequestSerializer(serializers.Serializer):
    tenantCode = serializers.CharField(max_length=64)
    identifier = serializers.CharField(max_length=320)


class PasswordResetConfirmSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)
    newPassword = serializers.CharField(max_length=200, trim_whitespace=False)


class SendVerificationSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    channel = serializers.ChoiceField(choices=["email", "phone"])


class VerifyChannelSerializer(serializers.Serializer):
    token = serializers.CharField(max_length=200)


class CreateRoleSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    scopeType = serializers.ChoiceField(
        choices=["SYSTEM", "GLOBAL", "TENANT", "ORGANIZATION", "DEPARTMENT", "PROJECT", "RESOURCE"],
        required=False,
        default="TENANT",
    )
    actions = serializers.ListField(child=serializers.CharField(max_length=120), required=False)


class UpdateRoleSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160, required=False, allow_blank=True)
    actions = serializers.ListField(child=serializers.CharField(max_length=120), required=False)


class AssignRoleSerializer(serializers.Serializer):
    roleId = serializers.UUIDField()
    tenantId = serializers.UUIDField(required=False)


class ApiKeyCreateSerializer(serializers.Serializer):
    tenantId = serializers.UUIDField()
    name = serializers.CharField(max_length=120)
    ownerType = serializers.ChoiceField(
        choices=["user", "serviceAccount"], required=False, default="user"
    )
    ownerId = serializers.UUIDField(required=False)
    scopes = serializers.ListField(child=serializers.CharField(max_length=120), required=False)
    expiresAt = serializers.CharField(max_length=40, required=False, allow_blank=True)


class CreateServiceAccountSerializer(serializers.Serializer):
    tenantId = serializers.UUIDField()
    code = serializers.CharField(max_length=64)
    name = serializers.CharField(max_length=160)
    description = serializers.CharField(max_length=500, required=False, allow_blank=True)
    scopes = serializers.ListField(child=serializers.CharField(max_length=120), required=False)


class SetupMfaSerializer(serializers.Serializer):
    factorType = serializers.ChoiceField(choices=["totp"], required=False, default="totp")


class ConfirmMfaSerializer(serializers.Serializer):
    factorId = serializers.UUIDField()
    code = serializers.CharField(max_length=24)


class DisableMfaSerializer(serializers.Serializer):
    password = serializers.CharField(max_length=200, write_only=True, trim_whitespace=False)


class CreateUserSerializer(serializers.Serializer):
    phone = serializers.CharField(max_length=40)
    displayName = serializers.CharField(max_length=160)
    email = serializers.EmailField(max_length=320)
    username = serializers.CharField(max_length=64, required=False, allow_blank=True, default='')


class AssignMembershipSerializer(serializers.Serializer):
    tenantId = serializers.UUIDField()
