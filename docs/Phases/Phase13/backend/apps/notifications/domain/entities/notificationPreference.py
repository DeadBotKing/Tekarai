"""User preference + tenant rule entities (Phase 09 §10/§11)."""

from __future__ import annotations

import uuid

from apps.notifications.domain.valueObjects.notificationTypes import (
    DELIVERY_CHANNELS,
    PREFERENCE_LEVELS,
    PREF_LEVEL_CATEGORY,
    PREF_LEVEL_GLOBAL,
    PREF_LEVEL_TYPE,
)
from apps.sharedKernel.domain.entities import AggregateRoot
from apps.sharedKernel.domain.errors import ValidationFailedError


class NotificationPreference(AggregateRoot):
    """§10 — one row per (user, level, scope, channel); the most specific
    applicable preference wins (resolution lives in the rules service)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        level: str,
        channel: str,
        *,
        category: str = "",
        notificationType: str = "",
        enabled: bool = True,
        quietHoursStart: str = "",
        quietHoursEnd: str = "",
    ) -> None:
        super().__init__(id)
        if level not in PREFERENCE_LEVELS:
            raise ValidationFailedError(
                "Unknown preference level.", fieldErrors={"level": level}
            )
        if channel not in DELIVERY_CHANNELS:
            raise ValidationFailedError(
                "Unknown channel.", fieldErrors={"channel": channel}
            )
        if level == PREF_LEVEL_TYPE and not notificationType:
            raise ValidationFailedError(
                "TYPE-level preference requires notificationType.",
                fieldErrors={"notificationType": "empty"},
            )
        if level == PREF_LEVEL_CATEGORY and not category:
            raise ValidationFailedError(
                "CATEGORY-level preference requires category.",
                fieldErrors={"category": "empty"},
            )
        if level == PREF_LEVEL_GLOBAL and (category or notificationType):
            raise ValidationFailedError(
                "GLOBAL preference must not be scoped.",
                fieldErrors={"category": "must be empty"},
            )
        self.tenantId = tenantId
        self.userId = userId
        self.level = level
        self.category = category
        self.notificationType = notificationType
        self.channel = channel
        self.enabled = enabled
        self.quietHoursStart = quietHoursStart
        self.quietHoursEnd = quietHoursEnd

    def scopeKey(self) -> tuple[str, str, str, str]:
        return (self.level, self.category, self.notificationType, self.channel)

    def setEnabled(self, enabled: bool) -> None:
        self.enabled = enabled


class NotificationPreferenceRule(AggregateRoot):
    """§11 — tenant-level organizational rules.

    ``forced`` channels override user preferences (e.g. security alerts);
    ``denied`` channels are removed regardless of user wishes (e.g. SMS off).
    Tenant rules may never weaken mandatory platform security rules — the
    rules service refuses rules that deny forced platform channels.
    """

    FORCED = "FORCED"
    DENIED = "DENIED"
    ACTIONS = (FORCED, DENIED)

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        channel: str,
        action: str,
        *,
        category: str = "",
        notificationType: str = "",
        description: str = "",
    ) -> None:
        super().__init__(id)
        if action not in self.ACTIONS:
            raise ValidationFailedError(
                "Unknown rule action.", fieldErrors={"action": action}
            )
        self.tenantId = tenantId
        self.category = category
        self.notificationType = notificationType
        self.channel = channel
        self.action = action
        self.description = description
