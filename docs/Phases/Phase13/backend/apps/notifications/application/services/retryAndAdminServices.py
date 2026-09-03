"""§24 retry service + §8/§18/§19 admin services (policies/templates)."""

from __future__ import annotations

import uuid
from typing import Any

from apps.notifications.application.commands.notificationCommands import (
    DeactivateTemplateCommand,
    DeletePolicyCommand,
    RetryDueDeliveriesCommand,
    SavePolicyCommand,
    SaveTemplateCommand,
)
from apps.notifications.application.dto.notificationDtos import (
    PolicyDto,
    TemplateDto,
    policyDtoFromDomain,
    templateDtoFromDomain,
)
from apps.notifications.application.queries.notificationQueries import (
    ListPoliciesQuery,
    ListTemplateVersionsQuery,
    ListTemplatesQuery,
)
from apps.notifications.application.services.notificationSupport import (
    NotificationChannelRegistry,
    NotificationUseCase,
)
from apps.notifications.domain.entities.notificationPolicy import NotificationPolicy
from apps.notifications.domain.entities.notificationTemplate import NotificationTemplate
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationDeliveryRepository,
    NotificationPolicyRepository,
    NotificationRepository,
    NotificationTemplateRepository,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    DELIVERY_CHANNELS,
    DELIVERY_DELIVERED,
    DELIVERY_PERMANENTLY_FAILED,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    ValidationFailedError,
)


class RetryNotificationDeliveryService(NotificationUseCase):
    """§24 — only RETRY_SCHEDULED rows whose backoff elapsed are retried;
    PERMANENTLY_FAILED rows are never touched again."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        deliveryRepository: NotificationDeliveryRepository,
        channelRegistry: NotificationChannelRegistry,
        renderService: Any,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository
        self.deliveryRepository = deliveryRepository
        self.channelRegistry = channelRegistry
        self.renderService = renderService

    def perform(self, command: RetryDueDeliveriesCommand) -> dict:
        from apps.notifications.infrastructure.metrics.notificationMetrics import (
            notificationMetrics,
        )

        now = self.nowUtc()
        retried, recovered, dead = 0, 0, 0
        pendingRows = self.deliveryRepository.listPendingRetry(now, limit=command.limit)
        for delivery in pendingRows:
            if not delivery.retryIsDue(now):
                continue
            notification = self.notificationRepository.getById(delivery.notificationId)
            if notification is None or not notification.isDispatchable():
                continue  # aggregate already terminal — leave the row
            retried += 1
            notificationMetrics().increment("retryAttempts")
            adapter = self.channelRegistry.channelFor(delivery.channel)
            rendered = self.renderService.render(
                tenantId=notification.tenantId,
                recipientId=notification.recipientId,
                templateKey=str(notification.payload.get("templateKey", "") or ""),
                channel=delivery.channel,
                fallbackTitle=notification.title,
                fallbackBody=notification.body,
                data={**notification.payload, "title": notification.title,
                      "body": notification.body},
            )
            if adapter is None:
                outcome = None
            else:
                try:
                    outcome = adapter.deliver(
                        tenantId=notification.tenantId,
                        notification=notification,
                        renderedTitle=rendered.title,
                        renderedSubject=rendered.subject,
                        renderedBody=rendered.body,
                    )
                except Exception:  # noqa: BLE001 — §47 isolation
                    outcome = None
            delivery.attemptCount += 1
            if outcome is not None and outcome.ok:
                delivery.markDelivered(now)
                recovered += 1
                notificationMetrics().increment(f"channelUsage.{delivery.channel}")
            else:
                errorCode = outcome.errorCode if outcome is not None else "PROVIDER_ERROR"
                errorMessage = (
                    outcome.errorMessage if outcome is not None else "adapter unavailable"
                )
                stillRetrying = delivery.markFailed(
                    now, errorCode=errorCode, errorMessage=errorMessage
                )
                if not stillRetrying:
                    dead += 1
            self.deliveryRepository.update(delivery)

            # §47 re-evaluate aggregate outcome from the full channel set
            siblings = self.deliveryRepository.getForNotification(notification.id)
            delivered = sum(1 for row in siblings if row.status == DELIVERY_DELIVERED)
            failed = sum(
                1 for row in siblings if row.status == DELIVERY_PERMANENTLY_FAILED
            )
            if delivered or failed:
                notification.applyDeliveryOutcome(
                    deliveredChannels=delivered, failedChannels=failed, now=now
                )
                self.notificationRepository.update(notification)
                self.collectEventsFrom(notification)
        return {"retried": retried, "recovered": recovered, "exhausted": dead}


class SaveTemplateService(NotificationUseCase):
    """§18/§19 — saving an existing (key, language, channel) creates the
    next version and deactivates the previous active row."""

    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        templateRepository: NotificationTemplateRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.templateRepository = templateRepository

    def perform(self, command: SaveTemplateCommand) -> TemplateDto:
        versions = self.templateRepository.listVersions(
            command.tenantId, command.templateKey, command.language, command.channel
        )
        if versions:
            previous = versions[0]
            template = previous.nextVersion(
                title=command.titleTemplate,
                subject=command.subjectTemplate,
                body=command.bodyTemplate,
            )
            template.createdBy = command.actorId
            self.templateRepository.deactivate(previous.id)
        else:
            template = NotificationTemplate(
                id=uuid.uuid4(),
                tenantId=command.tenantId,
                templateKey=command.templateKey,
                language=command.language,
                channel=command.channel,
                version=1,
                title=command.titleTemplate,
                subject=command.subjectTemplate,
                body=command.bodyTemplate,
                createdBy=command.actorId,
            )
        self.templateRepository.create(template)
        self.audit(
            "CREATE",
            resourceType="NotificationTemplate",
            resourceId=str(template.id),
            tenantId=command.tenantId,
            after={"templateKey": template.templateKey, "version": template.version},
        )
        return templateDtoFromDomain(template)


class DeactivateTemplateService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        templateRepository: NotificationTemplateRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.templateRepository = templateRepository

    def perform(self, command: DeactivateTemplateCommand) -> dict:
        self.templateRepository.deactivate(command.templateId)
        return {"deactivated": True}


class ListTemplatesService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        templateRepository: NotificationTemplateRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.templateRepository = templateRepository

    def perform(self, query: ListTemplatesQuery | ListTemplateVersionsQuery) -> list[TemplateDto]:
        if isinstance(query, ListTemplateVersionsQuery):
            versions = self.templateRepository.listVersions(
                query.tenantId, query.templateKey, query.language, query.channel
            )
            return [templateDtoFromDomain(template) for template in versions]
        return [
            templateDtoFromDomain(template)
            for template in self.templateRepository.listAll(query.tenantId)
        ]


class SavePolicyService(NotificationUseCase):
    """§8 — policies are configuration, never code."""

    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        policyRepository: NotificationPolicyRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.policyRepository = policyRepository

    def validateCommand(self, command: SavePolicyCommand) -> None:
        unknown = [c for c in command.channels if c not in DELIVERY_CHANNELS]
        if unknown:
            raise ValidationFailedError(
                "Unknown channel in policy.", fieldErrors={"channels": str(unknown)}
            )
        if not command.matchValue:
            raise ValidationFailedError(
                "matchValue (notificationType or category) is required.",
                fieldErrors={"matchValue": "empty"},
            )

    def perform(self, command: SavePolicyCommand) -> PolicyDto:
        existing = self.policyRepository.findByKey(command.tenantId, command.policyKey)
        notificationType = (
            command.matchValue if command.matchType == "TYPE" else ""
        )
        category = command.matchValue if command.matchType == "CATEGORY" else ""
        policy = NotificationPolicy(
            id=existing.id if existing is not None else uuid.uuid4(),
            tenantId=command.tenantId,
            policyKey=command.policyKey,
            notificationType=notificationType,
            category=category,
            priority=command.priority,
            channels=tuple(command.channels) or ("IN_APP",),
            templateKey=command.templateKey,
            maxAttempts=command.maxRetries,
            cooldownSeconds=command.cooldownSeconds,
            digestible=bool(command.digestKind),
            escalation=[dict(stage) for stage in command.escalationStages],
            allowPreferenceBypass=command.allowPreferenceBypass,
            description="managed via admin API",
        )
        if existing is not None:
            self.policyRepository.update(policy)
        else:
            self.policyRepository.create(policy)
        self.audit(
            "UPDATE",
            resourceType="NotificationPolicy",
            resourceId=str(policy.id),
            tenantId=command.tenantId,
            after={"policyKey": policy.policyKey},
        )
        return policyDtoFromDomain(policy)


class DeletePolicyService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        policyRepository: NotificationPolicyRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.policyRepository = policyRepository

    def perform(self, command: DeletePolicyCommand) -> dict:
        if not self.policyRepository.delete(command.policyId):
            raise EntityNotFoundError("NotificationPolicy", str(command.policyId))
        return {"deleted": True}


class ListPoliciesService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        policyRepository: NotificationPolicyRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.policyRepository = policyRepository

    def perform(self, query: ListPoliciesQuery) -> list[PolicyDto]:
        return [
            policyDtoFromDomain(policy)
            for policy in self.policyRepository.listAll(query.tenantId)
        ]
