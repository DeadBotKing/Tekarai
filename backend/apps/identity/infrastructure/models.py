"""Identity persistence models (Phase 05 dictionary — Identity context).

Column names follow ``FieldCatalog.md`` (camelCase §3). ``tenantId`` is a
plain UUID — no cross-context FK to the Tenancy table: bounded contexts
stay decoupled at the storage edge (Phase 03 boundaries; composite-FK
enforcement strategy documented in ConstraintCatalog §3).
"""

from __future__ import annotations

import uuid

from django.db import models


class UserModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    username = models.CharField(max_length=64)
    email = models.CharField(max_length=320)
    passwordHash = models.CharField(max_length=255)
    displayName = models.CharField(max_length=160, blank=True, default="")
    status = models.CharField(max_length=20, default="active")
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
    tokenHash = models.CharField(max_length=64, unique=True)
    issuedAt = models.DateTimeField(auto_now_add=True)
    expiresAt = models.DateTimeField(db_index=True)
    lastUsedAt = models.DateTimeField(null=True, blank=True)
    revokedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "Session"
        indexes = [models.Index(fields=["userId", "expiresAt"], name="IX_Session_u_exp")]


class TenantMembershipModel(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    userId = models.UUIDField(db_index=True)
    tenantId = models.UUIDField(db_index=True)
    joinedAt = models.DateTimeField(auto_now_add=True)
    leftAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "TenantMembership"
        indexes = [models.Index(fields=["userId", "tenantId"], name="IX_TM_user_tenant")]


class PermissionModel(models.Model):
    """Reference data (§73/§74): stable action codes — never renamed."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    code = models.CharField(max_length=64, unique=True)
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
        constraints = [models.UniqueConstraint(fields=["code"], name="UQ_Role_code")]


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
