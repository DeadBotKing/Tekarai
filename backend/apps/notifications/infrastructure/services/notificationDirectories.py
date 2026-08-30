"""Cross-context directories for the notification context (§9/§12/§13).

- ``IdentityRecipientDirectory``: recipient specs → user ids
- ``IdentityContactDirectory``: email/phone/language lookups

Both read OTHER contexts through their APPLICATION contracts only
(RULE E/F); the notification domain stays independent of all of it.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.notifications.domain.repositories.notificationRepositories import (
    RecipientDirectory,
    UserContactDirectory,
)

logger = logging.getLogger(__name__)


class IdentityRecipientDirectory(RecipientDirectory):
    """§9 — resolves USER / ROLE / group specs to concrete user ids.

    Group structures whose bounded contexts are not opened yet resolve to
    an empty list (logged) — the engine supports them; the org data
    arrives with future phases.
    """

    def resolveUserIds(
        self, tenantId: uuid.UUID, recipientSpec: dict[str, Any]
    ) -> list[uuid.UUID]:
        recipientType = str(recipientSpec.get("type", "") or "").upper()
        raw = recipientSpec.get("value")
        values = (
            [str(item) for item in raw]
            if isinstance(raw, (list, tuple))
            else [str(raw or "")]
        )

        if recipientType == "USER":
            return [self._asUuid(value) for value in values if self._asUuid(value)]

        if recipientType == "ROLE":
            return self._usersOfRole(tenantId, values)

        if recipientType == "TENANT_ADMIN":
            return self._usersOfRole(tenantId, ["tenantAdmin", "platformAdmin"])

        if recipientType in ("TENANT", "ORGANIZATION"):
            from apps.identity.application.services import profileDirectory

            return profileDirectory.activeUserIdsOfTenant(tenantId)

        if recipientType == "CONVERSATION":
            return self._viaCommunication("conversationMemberIds", values)
        if recipientType == "MEETING":
            return self._viaCommunication("meetingInviteeIds", values)
        if recipientType == "CALL":
            return self._viaCommunication("callParticipantIds", values)
        if recipientType == "CHANNEL":
            return self._viaCommunicationChannel(tenantId, values)

        # Remaining group units (team/org-unit/project-work) arrive with
        # their own phases — resolution is ready, the data is not.
        logger.info(
            "Group recipient type resolves empty until its context opens",
            extra={"recipientType": recipientType},
        )
        return []

    # -- helpers ---------------------------------------------------------------

    @staticmethod
    def _asUuid(value: str) -> uuid.UUID | None:
        try:
            return uuid.UUID(str(value))
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _usersOfRole(tenantId: uuid.UUID, roleNames: list[str]) -> list[uuid.UUID]:
        from apps.identity.application.services import profileDirectory

        return profileDirectory.userIdsOfRole(tenantId, roleNames)

    def _viaCommunication(self, functionName: str, values: list[str]) -> list[uuid.UUID]:
        from apps.communication.application.services import participantDirectory

        ids = [self._asUuid(value) for value in values]
        ids = [parsed for parsed in ids if parsed]
        if not ids:
            return []
        return list(getattr(participantDirectory, functionName)(ids))

    def _viaCommunicationChannel(
        self, tenantId: uuid.UUID, values: list[str]
    ) -> list[uuid.UUID]:
        from apps.communication.application.services import participantDirectory

        ids = [self._asUuid(value) for value in values]
        ids = [parsed for parsed in ids if parsed]
        if not ids:
            return []
        return participantDirectory.channelMemberIds(tenantId, ids)


class IdentityContactDirectory(UserContactDirectory):
    """§12 contact data + §20 language resolution input."""

    def emailOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str:
        from apps.identity.application.services import profileDirectory

        return profileDirectory.emailOf(tenantId, userId)

    def phoneOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str:
        from apps.identity.application.services import profileDirectory

        return profileDirectory.phoneOf(tenantId, userId)

    def languageOf(self, tenantId: uuid.UUID, userId: uuid.UUID) -> str:
        from apps.identity.application.services import profileDirectory

        return profileDirectory.languageOf(tenantId, userId)

    def exists(self, tenantId: uuid.UUID, userId: uuid.UUID) -> bool:
        from apps.identity.application.services import profileDirectory

        return profileDirectory.userExists(tenantId, userId)
