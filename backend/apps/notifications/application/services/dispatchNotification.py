"""§32/§38 DispatchNotificationService — the notification worker core.

The eleven canonical steps (§32):
 1. receive notification job        → ``execute`` / ``dispatchOne``
 2. validate notification state     → dispatchable + not expired (§23)
 3. resolve recipient               → §9 (verify the user still exists)
 4. resolve preferences             → §10/§11
 5. resolve policy                  → §8
 6. select channels                 → policy ∩ tenant rules − prefs (§5)
 7. render templates                → §18/§20 language chain
 8. execute delivery                → channel adapters, isolated per §47
 9. persist result                  → delivery rows + aggregate outcome
10. schedule retry if necessary     → §24 backoff, never for permanent
11. emit delivery event             → domain event + metrics + WS (§41/§44)
"""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any

from apps.notifications.application.services.notificationSupport import (
    NotificationChannelRegistry,
    NotificationUseCase,
)
from apps.notifications.application.services.renderNotificationContent import (
    RenderNotificationService,
)
from apps.notifications.application.services.resolvePolicyAndPreferences import (
    ResolveNotificationPolicyService,
    ResolveNotificationPreferencesService,
)
from apps.notifications.domain.entities.notificationDelivery import (
    NotificationDelivery,
)
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationDeliveryRepository,
    NotificationRepository,
    UserContactDirectory,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    CHANNEL_IN_APP,
    DELIVERY_DELIVERED,
    DELIVERY_PENDING,
    DELIVERY_PERMANENTLY_FAILED,
    DELIVERY_RETRY_SCHEDULED,
    PRIORITY_RANK,
)

logger = logging.getLogger(__name__)


@dataclass
class DispatchOutcome:
    notificationId: str
    status: str = "SKIPPED"
    channels: list[dict[str, str]] = field(default_factory=list)
    trace: list[str] = field(default_factory=list)

    def note(self, line: str) -> None:
        self.trace.append(line)


class DispatchNotificationService(NotificationUseCase):
    """Executes one notification end-to-end; idempotent by design."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        deliveryRepository: NotificationDeliveryRepository,
        resolvePolicy: ResolveNotificationPolicyService,
        resolvePreferences: ResolveNotificationPreferencesService,
        renderService: RenderNotificationService,
        channelRegistry: NotificationChannelRegistry,
        userContacts: UserContactDirectory,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository
        self.deliveryRepository = deliveryRepository
        self.resolvePolicy = resolvePolicy
        self.resolvePreferences = resolvePreferences
        self.renderService = renderService
        self.channelRegistry = channelRegistry
        self.userContacts = userContacts

    # -- step 1: receive job ------------------------------------------------------

    def perform(self, message: Any) -> Any:
        raise NotImplementedError("use dispatchOne/dispatchPending")

    def dispatchPending(self, tenantId: Any = None, *, limit: int = 100) -> list[DispatchOutcome]:
        outcomes: list[DispatchOutcome] = []
        for notification in self.notificationRepository.listDispatchable(tenantId, limit=limit):
            outcomes.append(self.dispatchOne(notification.id))
        return outcomes

    def dispatchOne(self, notificationId: Any) -> DispatchOutcome:
        startedAt = time.monotonic()
        notification = self._load(notificationId)  # step 1
        outcome = DispatchOutcome(notificationId=str(notificationId))
        if notification is None:
            outcome.note("step2=missing")
            return outcome

        # step 2 — validate state (§23 expiry re-check)
        now = self.nowUtc()
        if notification.expiresAt is not None and notification.expiresAt <= now:
            if notification.expire(now):
                self.notificationRepository.update(notification)
                self.collectEventsFrom(notification)
            outcome.status = notification.status
            outcome.note("step2=expired")
            self._emit(outcome, startedAt)
            return outcome
        if not notification.isDispatchable():
            outcome.status = notification.status
            outcome.note(f"step2={notification.status}")
            self._emit(outcome, startedAt)
            return outcome
        if self._allChannelsParked(notification):
            # every delivery is terminal or waiting on backoff — nothing to do
            outcome.status = notification.status
            outcome.note("step2=parked-in-retry")
            self._emit(outcome, startedAt)
            return outcome
        notification.startProcessing(now)

        # step 3 — resolve recipient
        externalAddress = str(notification.payload.get("externalAddress", "") or "")
        if not externalAddress and not self.userContacts.exists(
            notification.tenantId, notification.recipientId
        ):
            notification.cancel(now)
            self.notificationRepository.update(notification)
            self.collectEventsFrom(notification)
            outcome.status = notification.status
            outcome.note("step3=recipient-gone")
            self._emit(outcome, startedAt)
            return outcome
        outcome.note("step3=recipient-ok")

        # steps 4/5 — preferences + policy
        policyResolution = self.resolvePolicy.resolve(
            notification.tenantId, notification.notificationType, notification.category
        )
        outcome.note("step5=policy:" + policyResolution.policy.policyKey)

        # step 6 — select channels
        requested = notification.payload.get("channelsOverride")
        if requested:
            channels = tuple(requested)
            outcome.note(f"step6=rate-limit-override:{','.join(channels)}")
        else:
            channels, traceLines = self.resolvePreferences.resolveChannels(
                tenantId=notification.tenantId,
                userId=notification.recipientId,
                policyResolution=policyResolution,
                notificationType=notification.notificationType,
                category=notification.category,
                priority=notification.priority,
            )
            outcome.trace.extend(traceLines)
            outcome.note("step6=channels:" + (",".join(channels) or "none"))

        existingDeliveries = {
            delivery.channel: delivery
            for delivery in self.deliveryRepository.getForNotification(notification.id)
        }
        if not channels:
            delivery = self._deliveryRow(notification, CHANNEL_IN_APP, existingDeliveries)
            delivery.skip(now, "no channel selected")
            self._save(delivery)
            notification.applyDeliveryOutcome(deliveredChannels=0, failedChannels=0, now=now)
            self._finalize(notification, outcome, startedAt)
            return outcome

        deliveredCount = 0
        failedCount = 0
        for channel in channels:
            delivery = self._deliveryRow(notification, channel, existingDeliveries)
            if delivery.status == DELIVERY_DELIVERED:
                deliveredCount += 1  # already done (idempotent re-run)
                outcome.channels.append({"channel": channel, "status": "DELIVERED"})
                continue

            # step 7 — render (§20 language chain, §18 safe substitution)
            rendered = self.renderService.render(
                tenantId=notification.tenantId,
                recipientId=notification.recipientId,
                templateKey=(
                    policyResolution.policy.templateKey
                    or str(notification.payload.get("templateKey", "") or "")
                ),
                channel=channel,
                fallbackTitle=notification.title,
                fallbackBody=notification.body,
                data={
                    **notification.payload,
                    "title": notification.title,
                    "body": notification.body,
                    "notificationType": notification.notificationType,
                },
            )
            outcome.trace.extend(rendered.trace())

            # step 8 — execute delivery (§47 isolated per channel)
            adapter = self.channelRegistry.channelFor(channel)
            if adapter is None:
                delivery.skip(now, f"channel adapter unavailable: {channel}")
                self._save(delivery)
                outcome.channels.append({"channel": channel, "status": "SKIPPED"})
                continue
            try:
                result = adapter.deliver(
                    tenantId=notification.tenantId,
                    notification=notification,
                    renderedTitle=rendered.title,
                    renderedSubject=rendered.subject,
                    renderedBody=rendered.body,
                )
            except Exception as exc:  # noqa: BLE001 — §47 failure isolation
                logger.exception(
                    "Channel adapter crashed",
                    extra={"notificationId": str(notification.id), "channel": channel},
                )
                from apps.notifications.domain.repositories.notificationRepositories import (
                    DeliveryResult,
                )

                result = DeliveryResult(ok=False, errorCode="PROVIDER_ERROR",
                                        errorMessage=str(exc)[:200])

            # steps 9/10 — persist result + retry classification (§24);
            # markFailed itself decides PERMANENTLY_FAILED vs RETRY_SCHEDULED
            delivery.attemptCount += 1
            if result.ok:
                delivery.markDelivered(now)
                deliveredCount += 1
                outcome.channels.append({"channel": channel, "status": "DELIVERED"})
            else:
                retried = delivery.markFailed(
                    now, errorCode=result.errorCode, errorMessage=result.errorMessage
                )
                failedCount += 1
                outcome.channels.append(
                    {
                        "channel": channel,
                        "status": (
                            DELIVERY_RETRY_SCHEDULED
                            if retried
                            else DELIVERY_PERMANENTLY_FAILED
                        ),
                    }
                )
            self._save(delivery)

        # §47 — RETRY_SCHEDULED rows are still in flight: only PERMANENTLY_FAILED
        # channels count as failures for the aggregate outcome.
        siblings = self.deliveryRepository.getForNotification(notification.id)
        hardFailed = sum(
            1 for row in siblings if row.status == DELIVERY_PERMANENTLY_FAILED
        )
        if deliveredCount or hardFailed:
            notification.applyDeliveryOutcome(
                deliveredChannels=deliveredCount, failedChannels=hardFailed, now=now
            )

        # §27 — policy-driven escalation on total failure
        if (
            notification.status == "FAILED"
            and policyResolution.policy.escalation
        ):
            self._scheduleEscalation(notification, policyResolution.policy.escalation, now)
            outcome.note("step10=escalation-scheduled")

        self._finalize(notification, outcome, startedAt)
        return outcome

    # -- helpers -------------------------------------------------------------

    def _allChannelsParked(self, notification: Any) -> bool:
        """PROCESSING rows whose channels are all DELIVERED/SKIPPED/terminal/
        RETRY_SCHEDULED must not be re-executed by the dispatch tick (the
        retry service owns RETRY_SCHEDULED rows)."""
        from apps.notifications.domain.valueObjects.notificationTypes import (
            DELIVERY_SKIPPED,
        )

        deliveries = self.deliveryRepository.getForNotification(notification.id)
        if not deliveries:
            return False
        parked = (DELIVERY_DELIVERED, DELIVERY_SKIPPED,
                  DELIVERY_PERMANENTLY_FAILED, DELIVERY_RETRY_SCHEDULED)
        return all(row.status in parked for row in deliveries)

    def _load(self, notificationId: Any):
        notification = self.notificationRepository.getById(notificationId)
        if notification is None:
            return None
        return notification

    def _deliveryRow(
        self,
        notification: Any,
        channel: str,
        existing: dict[str, NotificationDelivery],
    ) -> NotificationDelivery:
        delivery = existing.get(channel)
        if delivery is not None:
            return delivery
        from apps.sharedKernel.domain.entities import newId

        delivery = NotificationDelivery(
            id=newId(),
            tenantId=notification.tenantId,
            notificationId=notification.id,
            channel=channel,
            provider=self._providerFor(channel),
            status=DELIVERY_PENDING,
            maxAttempts=self._maxAttempts(notification),
        )
        self.deliveryRepository.create(delivery)
        return delivery

    def _providerFor(self, channel: str) -> str:
        adapter = self.channelRegistry.channelFor(channel)
        return getattr(adapter, "providerName", channel.lower())

    def _maxAttempts(self, notification: Any) -> int:
        policy = self.resolvePolicy.resolve(
            notification.tenantId, notification.notificationType, notification.category
        ).policy
        return max(1, int(policy.maxAttempts))

    def _save(self, delivery: NotificationDelivery) -> None:
        self.deliveryRepository.update(delivery)

    def _finalize(
        self, notification: Any, outcome: DispatchOutcome, startedAt: float
    ) -> None:
        self.notificationRepository.update(notification)
        self.collectEventsFrom(notification)
        outcome.status = notification.status
        self._emit(outcome, startedAt)
        if notification.status == "FAILED":
            self.noteFailed()
        else:
            self.noteDelivered()
        # §41 — realtime optimization for the recipient's own screen
        # (the broadcaster adds the {"type": "notification.event"} envelope)
        self.pushToUser(
            notification.recipientId,
            {
                "name": "notificationDelivered",
                "notificationId": str(notification.id),
                "status": notification.status,
                "category": notification.category,
                "priority": notification.priority,
            },
        )

    def _emit(self, outcome: DispatchOutcome, startedAt: float) -> None:
        """§45 structured log — ids and statuses only, never content."""
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        notificationMetrics().observeDeliveryLatency(time.monotonic() - startedAt)
        for entry in outcome.channels:
            notificationMetrics().increment(f"channelUsage.{entry['channel']}")
            if entry["status"] in ("FAILED", "PERMANENTLY_FAILED"):
                notificationMetrics().increment("providerFailures")
        logger.info(
            "Notification dispatched",
            extra={
                "notificationId": outcome.notificationId,
                "status": outcome.status,
                "channels": outcome.channels,
                "deliveryLatencyMs": round((time.monotonic() - startedAt) * 1000, 3),
            },
        )

    def _scheduleEscalation(
        self, notification: Any, stages: list[dict[str, Any]], now: Any
    ) -> None:
        from apps.notifications.application.commands.notificationCommands import (
            ScheduleNotificationCommand,
        )
        from apps.notifications.infrastructure.container import container

        stage = sorted(stages, key=lambda item: int(item.get("afterSeconds", 0)))[0]
        command = ScheduleNotificationCommand(
            tenantId=notification.tenantId,
            kind="DELAYED",
            recipientSpec=dict(stage.get("recipientSpec", {"type": "TENANT_ADMIN"})),
            notificationType=f"{notification.notificationType}.escalated",
            category=notification.category,
            priority=self._escalatedPriority(notification.priority),
            title=notification.title,
            body=notification.body,
            sourceType=notification.sourceType,
            sourceId=notification.sourceId,
            scheduledAt=now,
            delaySeconds=int(stage.get("afterSeconds", 0)),
            payload={
                "escalationOf": str(notification.id),
                "correlationId": notification.correlationId,
            },
            correlationId=notification.correlationId,
            causationId=f"notificationFailed:{notification.id}",
        )
        container.scheduleNotificationService().execute(command)

    @staticmethod
    def _escalatedPriority(priority: str) -> str:
        rank = PRIORITY_RANK.get(priority, 1)
        for name, value in sorted(PRIORITY_RANK.items(), key=lambda item: -item[1]):
            if value == rank + 1:
                return name
        return priority
