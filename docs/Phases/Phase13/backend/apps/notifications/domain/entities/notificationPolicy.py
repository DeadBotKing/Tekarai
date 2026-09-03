"""Notification policy aggregate (Phase 09 §8, §21, §27)."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.notifications.domain.valueObjects.notificationTypes import (
    DELIVERY_CHANNELS,
    NOTIFICATION_PRIORITIES,
)
from apps.sharedKernel.domain.entities import AggregateRoot
from apps.sharedKernel.domain.errors import ValidationFailedError


class NotificationPolicy(AggregateRoot):
    """§8 — configuration-driven behaviour per event/notification type."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        policyKey: str,
        *,
        notificationType: str = "",
        category: str = "",
        enabled: bool = True,
        priority: str = "NORMAL",
        channels: tuple[str, ...] = ("IN_APP",),
        templateKey: str = "",
        maxAttempts: int = 3,
        cooldownSeconds: int = 60,
        digestible: bool = False,
        escalation: list[dict[str, Any]] | None = None,
        allowPreferenceBypass: bool = False,
        description: str = "",
    ) -> None:
        super().__init__(id)
        if not policyKey.strip():
            raise ValidationFailedError(
                "Policy key is required.", fieldErrors={"policyKey": "empty"}
            )
        if priority not in NOTIFICATION_PRIORITIES:
            raise ValidationFailedError(
                "Unknown priority.", fieldErrors={"priority": priority}
            )
        unknown = [c for c in channels if c not in DELIVERY_CHANNELS]
        if unknown:
            raise ValidationFailedError(
                "Unknown channel in policy.", fieldErrors={"channels": str(unknown)}
            )
        if not channels and enabled:
            raise ValidationFailedError(
                "An enabled policy needs at least one channel.",
                fieldErrors={"channels": "empty"},
            )
        self.tenantId = tenantId
        self.policyKey = policyKey
        self.notificationType = notificationType
        self.category = category
        self.enabled = enabled
        self.priority = priority
        self.channels = tuple(channels)
        self.templateKey = templateKey
        self.maxAttempts = maxAttempts
        self.cooldownSeconds = cooldownSeconds
        self.digestible = digestible
        self.escalation = escalation or []  # §27 [{afterSeconds, recipientSpec}]
        self.allowPreferenceBypass = allowPreferenceBypass
        self.description = description

    # -- §27 escalation -----------------------------------------------------------

    def escalationFor(self, elapsedSeconds: int) -> list[dict[str, Any]]:
        stages = []
        for stage in sorted(self.escalation, key=lambda s: int(s.get("afterSeconds", 0))):
            if elapsedSeconds >= int(stage.get("afterSeconds", 0)):
                stages.append(stage)
        return stages

    def appliesTo(self, notificationType: str, category: str) -> bool:
        if self.notificationType and self.notificationType == notificationType:
            return True
        if not self.notificationType and self.category and self.category == category:
            return True
        return False


class NotificationPolicyChannel:
    """§36 — per-policy channel rows (provider overrides)."""

    def __init__(
        self,
        id: uuid.UUID,
        policyId: uuid.UUID,
        channel: str,
        *,
        enabled: bool = True,
        providerOverride: str = "",
    ) -> None:
        self.id = id
        self.policyId = policyId
        self.channel = channel
        self.enabled = enabled
        self.providerOverride = providerOverride
