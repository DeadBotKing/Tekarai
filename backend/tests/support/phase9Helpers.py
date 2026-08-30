"""Phase 9 test support — notification seeding shared by the new suites."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from apps.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    SessionModel,
    UserModel,
    UserRoleModel,
)
from apps.sharedKernel.application.requestContext import (
    RequestContext,
    requestScope,
)
from tests.support.phase8Helpers import ensureTenant, ensureUser

NOTIFICATION_ADMIN_ACTIONS = ("notification.send", "notification.manage")


def grantNotificationAdmin(tenant, user) -> None:
    role, _ = RoleModel.objects.get_or_create(
        code="ntf-admin",
        defaults={"name": "Notification Admin", "scopeType": "TENANT"},
    )
    for action in NOTIFICATION_ADMIN_ACTIONS:
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
    return requestScope(
        RequestContext(
            actorId=str(userId), tenantId=str(tenantId), actorTenantId=str(tenantId)
        )
    )


def sessionTokenFor(userId, tenantId) -> str:
    from apps.identity.infrastructure.services.jwtService import defaultJwtService

    sessionId = uuid.uuid4()
    SessionModel.objects.create(
        id=sessionId,
        userId=userId,
        tenantId=tenantId,
        refreshTokenHash=uuid.uuid4().hex,
        expiresAt=datetime.now(UTC) + timedelta(hours=1),
    )
    token, _ttl = defaultJwtService().issueAccessToken(
        userId=userId, tenantId=tenantId, sessionId=sessionId
    )
    return token


def apiClientWithToken(token: str):
    from rest_framework.test import APIClient

    client = APIClient()
    client.credentials(HTTP_AUTHORIZATION=f"Bearer {token}")
    return client


def notificationOf(tenant, user, *, eventId: str = "evt-1", **overrides):
    """Convenience command factory for the create service."""
    from apps.notifications.application.commands.notificationCommands import (
        CreateNotificationCommand,
    )

    defaults = dict(
        tenantId=tenant.id,
        recipientSpec={"type": "USER", "value": str(user.id)},
        eventType="test.event",
        eventId=eventId,
        notificationType="test.ping",
        category="SYSTEM",
        priority="NORMAL",
        title="سلام",
        body="متن اعلان",
    )
    defaults.update(overrides)
    return CreateNotificationCommand(**defaults)
