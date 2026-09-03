"""§9 recipient resolution — groups become individual user ids here.

The aggregate is always single-recipient; fan-out happens in this service
so delivery/read/ack state stays unambiguous (§3, §26).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.repositories.notificationRepositories import (
    RecipientDirectory,
)
from apps.sharedKernel.domain.errors import ValidationFailedError


@dataclass(frozen=True)
class ResolvedRecipient:
    userId: uuid.UUID
    externalAddress: str = ""  # §9 EXTERNAL_RECIPIENT — no platform user


class ResolveRecipientsService(NotificationUseCase):
    """§9 — USER/ROLE/group spec → concrete recipient list."""

    requiredAction = ""

    def __init__(self, *args: Any, recipientDirectory: RecipientDirectory, **kwargs: Any) -> None:
        super().__init__(*args, **kwargs)
        self.recipientDirectory = recipientDirectory

    def perform(self, message: Any) -> Any:  # pragma: no cover — routed via resolve()
        raise NotImplementedError

    # -- direct API (called by CreateNotificationService, not via execute) ----

    def resolve(self, tenantId: uuid.UUID, recipientSpec: dict[str, Any]) -> list[ResolvedRecipient]:
        recipientType = str(recipientSpec.get("type", "") or "").upper()
        if not recipientType:
            raise ValidationFailedError(
                "Recipient type is required.", fieldErrors={"type": "empty"}
            )
        rawValue = recipientSpec.get("value") or recipientSpec.get("id") or ""
        if isinstance(rawValue, (list, tuple)):
            values = [str(item) for item in rawValue]
        else:
            values = [str(rawValue)] if str(rawValue).strip() else []

        if recipientType == "EXTERNAL_RECIPIENT":
            # §9 external delivery — stable synthetic identity per address
            return [
                ResolvedRecipient(
                    userId=uuid.uuid5(uuid.NAMESPACE_URL, f"tekarai:external:{address}"),
                    externalAddress=address,
                )
                for address in values
            ]

        userIds: list[uuid.UUID] = []
        if recipientType == "USER":
            userIds = [uuid.UUID(value) for value in values if value]
        else:
            spec = {"type": recipientType, "value": values or ""}
            userIds = list(self.recipientDirectory.resolveUserIds(tenantId, spec))

        # §34 — one authoritative de-duplicated, tenant-scoped list
        seen: set[uuid.UUID] = set()
        ordered: list[ResolvedRecipient] = []
        for userId in userIds:
            if userId in seen:
                continue
            seen.add(userId)
            ordered.append(ResolvedRecipient(userId=userId))
        return ordered
