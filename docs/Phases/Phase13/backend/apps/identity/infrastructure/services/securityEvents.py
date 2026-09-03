"""Security-event recorder (Phase 07 §27/§38).

Writes the §27 event vocabulary with the §38 field set (timestamp via
occurredAt, event, userId, tenantId, sessionId, ip, userAgent,
correlationId, result, reason). Never logs passwords, tokens or secrets
(§38) — the recorder only ever receives event metadata.
"""

from __future__ import annotations

import uuid

from apps.sharedKernel.application.requestContext import snapshotContext

LOGIN_SUCCESS = "LOGIN_SUCCESS"
LOGIN_FAILED = "LOGIN_FAILED"
ACCOUNT_LOCKED = "ACCOUNT_LOCKED"
PASSWORD_CHANGED = "PASSWORD_CHANGED"
PASSWORD_RESET = "PASSWORD_RESET"
MFA_ENABLED = "MFA_ENABLED"
MFA_DISABLED = "MFA_DISABLED"
SESSION_CREATED = "SESSION_CREATED"
SESSION_REVOKED = "SESSION_REVOKED"
API_KEY_CREATED = "API_KEY_CREATED"
API_KEY_REVOKED = "API_KEY_REVOKED"
ROLE_ASSIGNED = "ROLE_ASSIGNED"
ROLE_REMOVED = "ROLE_REMOVED"
PERMISSION_CHANGED = "PERMISSION_CHANGED"

ALL_EVENTS = (
    LOGIN_SUCCESS,
    LOGIN_FAILED,
    ACCOUNT_LOCKED,
    PASSWORD_CHANGED,
    PASSWORD_RESET,
    MFA_ENABLED,
    MFA_DISABLED,
    SESSION_CREATED,
    SESSION_REVOKED,
    API_KEY_CREATED,
    API_KEY_REVOKED,
    ROLE_ASSIGNED,
    ROLE_REMOVED,
    PERMISSION_CHANGED,
)


class SecurityEventRecorderDjango:
    def record(
        self,
        eventType: str,
        *,
        userId: uuid.UUID | None = None,
        tenantId: uuid.UUID | None = None,
        sessionId: uuid.UUID | None = None,
        result: str = "success",
        reason: str = "",
    ) -> None:
        from apps.identity.infrastructure.models import SecurityEventModel

        snapshot = snapshotContext()
        SecurityEventModel.objects.create(
            eventType=eventType,
            userId=userId,
            tenantId=tenantId or (uuid.UUID(snapshot.tenantId) if snapshot.tenantId else None),
            sessionId=sessionId,
            ipAddress=snapshot.ipAddress[:64],
            userAgent=snapshot.userAgent[:300],
            correlationId=snapshot.correlationId[:64],
            result=result[:10],
            reason=reason[:300],
        )
