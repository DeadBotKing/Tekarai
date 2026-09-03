"""Phase 8 test support — communication seeding shared by the new suites."""

from __future__ import annotations

import uuid

from apps.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserModel,
    UserRoleModel,
)
from apps.sharedKernel.application.requestContext import (
    RequestContext,
    requestScope,
)
from apps.tenancy.infrastructure.models import TenantModel

COMM_ADMIN_ACTIONS = (
    "letter.create",
    "letter.approve",
    "letter.sign",
    "letter.dispatch",
    "meeting.manage",
    "recording.manage",
    "conversation.create",
    "conversation.moderate",
)


def ensureTenant(name: str) -> TenantModel:
    import uuid as _uuid

    code = name.replace("_", "-")[:40]
    tenant, _ = TenantModel.objects.get_or_create(
        code=code, defaults={"name": name, "id": _uuid.uuid4()}
    )
    return tenant


def ensureUser(tenant: TenantModel, username: str) -> UserModel:
    user, _ = UserModel.objects.get_or_create(
        tenantId=tenant.id,
        username=username,
        defaults={
            "email": f"{username}@tekarai.test",
            "passwordHash": "!",
            "displayName": username,
        },
    )
    return user


def grantCommAdmin(tenant: TenantModel, user: UserModel) -> None:
    role, _ = RoleModel.objects.get_or_create(
        code="comm-admin", defaults={"name": "Communication Admin", "scopeType": "TENANT"}
    )
    for action in COMM_ADMIN_ACTIONS:
        permission, _ = PermissionModel.objects.get_or_create(
            code=action, defaults={"module": action.split(".")[0]}
        )
        RolePermissionModel.objects.get_or_create(
            roleId=role.id, actionPattern=action, defaults={"permissionId": permission.id}
        )
    UserRoleModel.objects.get_or_create(
        userId=user.id,
        roleId=role.id,
        scopeType="TENANT",
        defaults={"tenantId": tenant.id},
    )
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion

    bumpVersion(user.id)


def asUser(tenantId: uuid.UUID, userId: uuid.UUID):
    """Context manager binding the request context to one user (§17)."""
    return requestScope(
        RequestContext(actorId=str(userId), tenantId=str(tenantId), actorTenantId=str(tenantId))
    )
