"""§8/§10/§11 resolution services — policy, tenant rules, user preferences.

Pure orchestulation over the repository ports; channel arithmetic itself
lives in the domain rules (notificationRules.resolveChannels).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.entities.notificationPolicy import NotificationPolicy
from apps.notifications.domain.services import notificationRules
from apps.notifications.domain.valueObjects.notificationTypes import (
    CATEGORY_SECURITY,
    CHANNEL_IN_APP,
    PRIORITY_NORMAL,
)
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationPolicyRepository,
    NotificationPreferenceRepository,
)


@dataclass(frozen=True)
class PolicyResolution:
    policy: NotificationPolicy
    forcedChannels: tuple[str, ...] = ()
    deniedChannels: tuple[str, ...] = ()

    def trace(self) -> list[str]:
        traceLines: list[str] = [f"policy={self.policy.policyKey}"]
        if self.forcedChannels:
            traceLines.append(f"tenant-forced={','.join(self.forcedChannels)}")
        if self.deniedChannels:
            traceLines.append(f"tenant-denied={','.join(self.deniedChannels)}")
        return traceLines


def defaultPolicyFor(tenantId: uuid.UUID, notificationType: str, category: str) -> NotificationPolicy:
    """Safe fallback when no configured policy matches (§8): in-app only."""
    return NotificationPolicy(
        id=uuid.uuid5(uuid.NAMESPACE_URL, f"tekarai:defaultPolicy:{tenantId}:{notificationType}"),
        tenantId=tenantId,
        policyKey="default.inApp",
        notificationType=notificationType,
        category=category,
        priority=PRIORITY_NORMAL,
        channels=(CHANNEL_IN_APP,),
        templateKey="",
        description="Implicit fallback policy (in-app only).",
    )


class ResolveNotificationPolicyService(NotificationUseCase):
    """§8 — the most specific enabled policy for a type/category wins."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        policyRepository: NotificationPolicyRepository,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.policyRepository = policyRepository
        self.preferenceRepository = preferenceRepository

    def perform(self, message: Any) -> Any:  # pragma: no cover — routed via resolve()
        raise NotImplementedError

    def resolve(
        self, tenantId: uuid.UUID, notificationType: str, category: str
    ) -> PolicyResolution:
        policy = self.policyRepository.findApplicable(tenantId, notificationType, category)
        if policy is None or not policy.enabled:
            policy = defaultPolicyFor(tenantId, notificationType, category)

        forced: list[str] = []
        denied: list[str] = []
        for rule in self.preferenceRepository.listRules(tenantId):
            applies = (
                not rule.notificationType
                and not rule.category
            ) or (
                rule.notificationType
                and rule.notificationType == notificationType
            ) or (
                not rule.notificationType
                and rule.category
                and rule.category == category
            )
            if not applies:
                continue
            # §11 — a tenant may never weaken platform security delivery
            if rule.action == rule.DENIED and rule.channel == CHANNEL_IN_APP and category == CATEGORY_SECURITY:
                continue
            if rule.action == rule.FORCED:
                forced.append(rule.channel)
            elif rule.action == rule.DENIED:
                denied.append(rule.channel)
        return PolicyResolution(
            policy=policy,
            forcedChannels=tuple(dict.fromkeys(forced)),
            deniedChannels=tuple(dict.fromkeys(denied)),
        )


class ResolveNotificationPreferencesService(NotificationUseCase):
    """§10 — most specific preference wins (TYPE > CATEGORY > GLOBAL),
    §11 tenant rules override user wishes, §5 CRITICAL bypass only when
    the policy explicitly allows it for SECURITY/SYSTEM."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferenceRepository = preferenceRepository

    def perform(self, message: Any) -> Any:  # pragma: no cover — routed via resolve()
        raise NotImplementedError

    def preferenceRowsForUser(
        self, tenantId: uuid.UUID, userId: uuid.UUID
    ) -> list[tuple[str, str, str, str, bool]]:
        return [
            (preference.level, preference.category, preference.notificationType,
             preference.channel, preference.enabled)
            for preference in self.preferenceRepository.listForUser(tenantId, userId)
        ]

    def resolveChannels(
        self,
        *,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        policyResolution: PolicyResolution,
        notificationType: str,
        category: str,
        priority: str,
    ) -> tuple[tuple[str, ...], list[str]]:
        return notificationRules.resolveChannels(
            policyChannels=policyResolution.policy.channels,
            forcedChannels=policyResolution.forcedChannels,
            deniedChannels=policyResolution.deniedChannels,
            preferenceRows=self.preferenceRowsForUser(tenantId, userId),
            notificationType=notificationType,
            category=category,
            priority=priority,
            allowPreferenceBypass=policyResolution.policy.allowPreferenceBypass,
        )
