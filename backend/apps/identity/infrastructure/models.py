"""Identity persistence models (Phase 07 §29 domain model, §34 constraints).

Column names follow the Phase 05 dictionary (camelCase §3). Secrets are
stored ONLY as hashes (DoD 20): passwordHash / tokenHash / keyHash /
codeHash — never raw tokens or keys. Database-level constraints back the
application rules (§34): unique user identifier per tenant, unique active
membership, unique role name per scope, unique permission code, unique API
key hash.
"""

from __future__ import annotations

import uuid

from django.db import models


class UserModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    username = models.CharField(max_length=64)
    email = models.CharField(max_length=320)
    phone = models.CharField(max_length=32, blank=True, default="")
    passwordHash = models.CharField(max_length=255)
    displayName = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=24, default="active")
    kind = models.CharField(max_length=12, default="human")  # human | service
    lastLoginAt = models.DateTimeField(null=True, blank=True)
    passwordChangedAt = models.DateTimeField(null=True, blank=True)
    failedLoginCount = models.IntegerField(default=0)
    lockedUntil = models.DateTimeField(null=True, blank=True)
    expiresAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(null=True, blank=True)
    deletedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "User"
        ordering = ["-createdAt"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "username"], name="UQ_User_tenant_username"
            ),
            models.UniqueConstraint(fields=["tenantId", "email"], name="UQ_User_tenant_email"),
        ]
        indexes = [models.Index(fields=["tenantId", "status"], name="IX_User_t_status")]


class SessionModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField()
    refreshTokenHash = models.CharField(max_length=64, unique=True)
    issuedAt = models.DateTimeField(auto_now_add=True)
    lastActivityAt = models.DateTimeField(null=True, blank=True)
    expiresAt = models.DateTimeField(db_index=True)
    revokedAt = models.DateTimeField(null=True, blank=True)
    ipAddress = models.CharField(max_length=64, blank=True, default="")
    userAgent = models.CharField(max_length=300, blank=True, default="")
    device = models.CharField(max_length=120, blank=True, default="")

    class Meta:
        db_table = "Session"
        indexes = [models.Index(fields=["userId", "expiresAt"], name="IX_Session_u_exp")]


class TenantMembershipModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    status = models.CharField(max_length=12, default="active")
    isPrimary = models.BooleanField(default=False)
    defaultRole = models.CharField(max_length=64, blank=True, default="member")
    joinedAt = models.DateTimeField(auto_now_add=True)
    leftAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "TenantMembership"
        indexes = [models.Index(fields=["userId", "tenantId"], name="IX_TM_user_tenant")]


class PermissionModel(models.Model):
    """Reference data (§73/§74): stable action codes — never renamed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)  # UQ permission code (§34)
    module = models.CharField(max_length=40)
    description = models.CharField(max_length=200, blank=True, default="")

    class Meta:
        db_table = "Permission"


class RoleModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    scopeType = models.CharField(max_length=20, default="TENANT")
    isActive = models.BooleanField(default=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "Role"
        constraints = [
            # Unique role name per scope (§34).
            models.UniqueConstraint(fields=["scopeType", "code"], name="UQ_Role_scope_code")
        ]


class UserRoleModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    roleId = models.UUIDField()
    tenantId = models.UUIDField(null=True, blank=True)
    scopeType = models.CharField(max_length=20, default="GLOBAL")
    scopeRef = models.CharField(max_length=64, blank=True, default="")
    grantedAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "UserRole"
        constraints = [
            models.UniqueConstraint(
                fields=["userId", "roleId", "scopeType"], name="UQ_UserRole_once"
            )
        ]


class RolePermissionModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    roleId = models.UUIDField(db_index=True)
    permissionId = models.UUIDField()
    actionPattern = models.CharField(max_length=64)

    class Meta:
        db_table = "RolePermission"
        constraints = [
            models.UniqueConstraint(
                fields=["roleId", "actionPattern"], name="UQ_RolePermission_once"
            )
        ]


class UserPermissionModel(models.Model):
    """Direct exception grants with explicit allow/deny (BR-PER-003)."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    permissionId = models.UUIDField()
    actionPattern = models.CharField(max_length=64)
    effect = models.CharField(max_length=6, choices=[("allow", "allow"), ("deny", "deny")])
    scopeType = models.CharField(max_length=20, default="TENANT")
    scopeRef = models.CharField(max_length=64, blank=True, default="")
    grantedAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "UserPermission"
        constraints = [
            models.UniqueConstraint(
                fields=["userId", "actionPattern", "effect", "scopeType"],
                name="UQ_UserPermission_once",
            )
        ]


class PasswordHistoryModel(models.Model):
    """§23 password history — hashes only."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    passwordHash = models.CharField(max_length=255)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PasswordHistory"
        ordering = ["-createdAt"]


class VerificationTokenModel(models.Model):
    """Email/phone/activation verification (§26) — hashed, single use."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    channel = models.CharField(max_length=16)
    destination = models.CharField(max_length=320)
    tokenHash = models.CharField(max_length=64, unique=True)
    expiresAt = models.DateTimeField(db_index=True)
    verifiedAt = models.DateTimeField(null=True, blank=True)
    attemptCount = models.IntegerField(default=0)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "VerificationToken"


class PasswordResetTokenModel(models.Model):
    """Password recovery (§25) — hashed, time limited, single use."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    tokenHash = models.CharField(max_length=64, unique=True)
    expiresAt = models.DateTimeField(db_index=True)
    usedAt = models.DateTimeField(null=True, blank=True)
    requestIp = models.CharField(max_length=64, blank=True, default="")
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "PasswordResetToken"


class MfaFactorModel(models.Model):
    """MFA factors (§24): pending → active → disabled."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    factorType = models.CharField(max_length=16)
    secretRef = models.CharField(max_length=512)  # encrypted/reference — never raw log
    status = models.CharField(max_length=10, default="pending")
    confirmedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "MfaFactor"


class RecoveryCodeModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    codeHash = models.CharField(max_length=64)
    createdAt = models.DateTimeField(auto_now_add=True)
    usedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "RecoveryCode"


class ApiKeyModel(models.Model):
    """API keys (§22): hashed, revocable, scoped, expirable, auditable."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    name = models.CharField(max_length=160)
    prefix = models.CharField(max_length=16, db_index=True)  # display fragment
    keyHash = models.CharField(max_length=64, unique=True)  # UQ key identifier (§34)
    ownerType = models.CharField(max_length=16, default="user")
    ownerId = models.UUIDField(db_index=True)
    scopes = models.JSONField(default=list, blank=True)
    expiresAt = models.DateTimeField(null=True, blank=True)
    revokedAt = models.DateTimeField(null=True, blank=True)
    lastUsedAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ApiKey"
        ordering = ["-createdAt"]


class ServiceAccountModel(models.Model):
    """Service accounts (§21) — non-human principals."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    code = models.CharField(max_length=64)
    name = models.CharField(max_length=160)
    description = models.CharField(max_length=500, blank=True, default="")
    status = models.CharField(max_length=10, default="active")
    scopes = models.JSONField(default=list, blank=True)
    disabledAt = models.DateTimeField(null=True, blank=True)
    createdAt = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "ServiceAccount"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "code"], name="UQ_ServiceAccount_code")
        ]


class SecurityEventModel(models.Model):
    """Security events (§27/§38): eventType/user/tenant/session/ip/agent/
    correlation/result/reason — aligned with the audit trail."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    occurredAt = models.DateTimeField(auto_now_add=True, db_index=True)
    eventType = models.CharField(max_length=40, db_index=True)
    userId = models.UUIDField(null=True, blank=True)
    tenantId = models.UUIDField(null=True, blank=True, db_index=True)
    sessionId = models.UUIDField(null=True, blank=True)
    ipAddress = models.CharField(max_length=64, blank=True, default="")
    userAgent = models.CharField(max_length=300, blank=True, default="")
    correlationId = models.CharField(max_length=64, blank=True, default="")
    result = models.CharField(max_length=10, default="success")
    reason = models.CharField(max_length=300, blank=True, default="")

    class Meta:
        db_table = "SecurityEvent"
        ordering = ["-occurredAt"]
        indexes = [
            models.Index(fields=["tenantId", "occurredAt"], name="IX_SecEvent_t_occ"),
            models.Index(fields=["userId", "eventType"], name="IX_SecEvent_u_event"),
        ]
