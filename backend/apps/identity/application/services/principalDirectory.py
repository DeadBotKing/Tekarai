"""Identity public facade for OTHER contexts (RULE F, ADR-021 pattern).

Other bounded contexts may import exactly this module — never Identity's
domain/infrastructure/presentation. The Communication context (Phase 08)
uses it for session verification and lightweight user lookups (§17).
"""

from __future__ import annotations

import uuid


def verifySessionToken(token: str):
    """Verify a bearer access JWT → SessionPrincipal | None."""
    from apps.identity.infrastructure.services.principals import (
        SessionVerifierDjango,
    )

    try:
        return SessionVerifierDjango().verifyToken(token)
    except Exception:  # noqa: BLE001 — callers treat any failure as anonymous
        return None


def userExists(tenantId: uuid.UUID, userId: uuid.UUID) -> bool:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    return UserRepositoryDjango().getById(userId, tenantId) is not None


def usernameOf(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    user = UserRepositoryDjango().getById(userId, tenantId)
    return user.username if user else ""


def userDisplayNameOf(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    """Display name (falling back to the username), or "" when unknown.

    The Maintenance context (v0.16.0) uses this to label the account a
    workforce person is linked to, so the directory shows a person, never
    a bare UUID.
    """
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    user = UserRepositoryDjango().getById(userId, tenantId)
    return (user.displayName or user.username) if user else ""


def userIdOfUsername(tenantId: uuid.UUID, username: str) -> uuid.UUID | None:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )

    user = UserRepositoryDjango().getByUsername(tenantId, username.lstrip("@"))
    return user.id if user else None


def isTenantAdministratorForAction(tenantId: uuid.UUID, userId: uuid.UUID, actionCode: str) -> bool:
    """Explicit active admin role, in this tenant, with the action still allowed.

    This is not a username check or a general role-grant bypass. Membership,
    role assignment scope and explicit permission denies remain authoritative.
    Other contexts use this facade without importing identity's ORM.
    """
    from apps.identity.infrastructure.models import (
        RoleModel, TenantMembershipModel, UserModel, UserRoleModel,
    )
    from apps.identity.infrastructure.services.permissionGate import PermissionGateDjango

    if not UserModel.objects.filter(id=userId, status="active", deletedAt__isnull=True).exists():
        return False
    if not TenantMembershipModel.objects.filter(userId=userId, tenantId=tenantId, status="active").exists():
        return False
    roleIds = RoleModel.objects.filter(
        isActive=True, code__in=("platformAdmin", "tenantAdmin"),
    ).values_list("id", flat=True)
    assignments = UserRoleModel.objects.filter(userId=userId, roleId__in=roleIds)
    allowedRole = any(
        (row.scopeType == "GLOBAL" and not row.scopeRef)
        or (
            row.scopeType == "TENANT"
            and row.tenantId == tenantId
            and (not row.scopeRef or row.scopeRef == str(tenantId))
        )
        for row in assignments
    )
    if not allowedRole:
        return False
    return PermissionGateDjango().hasPermission(
        userId, actionCode, tenantId=tenantId, targetTenantId=tenantId,
    )
