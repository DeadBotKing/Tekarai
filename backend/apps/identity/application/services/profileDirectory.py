"""Identity profile directory — public cross-context read contract.

Phase 09 notification-platform read-side integration: the notification
context resolves recipients, contact data and language preferences
through these functions only (RULE E/F — application contracts are the
public surface; infrastructure stays private).
"""

from __future__ import annotations

import uuid


def emailOf(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    row = _userRow(tenantId, userId)
    return str(row.email) if row else ""


def phoneOf(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    row = _userRow(tenantId, userId)
    return str(row.phone or "") if row else ""


def languageOf(tenantId: uuid.UUID, userId: uuid.UUID) -> str:
    """§20 language chain step 1 — the user's own choice. The profile
    field arrives with the organization phase; empty falls through."""
    row = _userRow(tenantId, userId)
    if row is None:
        return ""
    return str(getattr(row, "language", "") or "")


def userExists(tenantId: uuid.UUID, userId: uuid.UUID) -> bool:
    return _userRow(tenantId, userId) is not None


def activeUserIdsOfTenant(tenantId: uuid.UUID) -> list[uuid.UUID]:
    from apps.identity.infrastructure.models import TenantMembershipModel

    return list(
        TenantMembershipModel.objects.filter(tenantId=tenantId, status="active")
        .values_list("userId", flat=True)
    )


def userIdsOfRole(tenantId: uuid.UUID, roleNames: list[str]) -> list[uuid.UUID]:
    from apps.identity.infrastructure.models import RoleModel, UserRoleModel

    roleIds = list(
        RoleModel.objects.filter(code__in=roleNames, isActive=True).values_list(
            "id", flat=True
        )
    )
    if not roleIds:
        return []
    userMap: dict[uuid.UUID, None] = {}
    for userId, grantTenantId in UserRoleModel.objects.filter(
        roleId__in=roleIds
    ).values_list("userId", "tenantId"):
        if grantTenantId is None or grantTenantId == tenantId:
            userMap[userId] = None
    return list(userMap)


def _userRow(tenantId: uuid.UUID, userId: uuid.UUID):
    from apps.identity.infrastructure.models import UserModel

    return UserModel.objects.filter(
        tenantId=tenantId, id=userId, deletedAt__isnull=True
    ).first()
