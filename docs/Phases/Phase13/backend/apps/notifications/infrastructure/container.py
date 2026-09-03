"""Notification composition root (Phase 09 §38 services)."""

from __future__ import annotations

from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


def kernelPorts() -> dict:
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


# -- singletons ----------------------------------------------------------------------

_realtimeSingleton = None


def realtime():
    global _realtimeSingleton
    if _realtimeSingleton is None:
        from apps.notifications.infrastructure.realtime.notificationRealtime import (
            ChannelsNotificationBroadcaster,
        )

        _realtimeSingleton = ChannelsNotificationBroadcaster()
    return _realtimeSingleton


def notificationPorts() -> dict:
    ports = kernelPorts()
    ports["realtime"] = realtime()
    return ports


def recipientDirectory():
    from apps.notifications.infrastructure.services.notificationDirectories import (
        IdentityRecipientDirectory,
    )

    return IdentityRecipientDirectory()


def userContacts():
    from apps.notifications.infrastructure.services.notificationDirectories import (
        IdentityContactDirectory,
    )

    return IdentityContactDirectory()


def deviceRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationDeviceRepositoryDjango,
    )

    return NotificationDeviceRepositoryDjango()


def channelRegistry():
    from apps.notifications.infrastructure.channels.deliveryChannels import (
        ChannelRegistry,
    )

    return ChannelRegistry(contactSource=userContacts(), deviceSource=deviceRepository())


def jobQueue():
    from django.conf import settings

    from apps.sharedKernel.infrastructure.wiring import importFromDottedPath

    dotted = getattr(
        settings,
        "NOTIFICATION_QUEUE_IMPL",
        "apps.notifications.infrastructure.queue.notificationQueue.InlineNotificationQueue",
    )
    return importFromDottedPath(dotted)()


# -- repositories --------------------------------------------------------------------


def notificationRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationRepositoryDjango,
    )

    return NotificationRepositoryDjango()


def deliveryRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationDeliveryRepositoryDjango,
    )

    return NotificationDeliveryRepositoryDjango()


def preferenceRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationPreferenceRepositoryDjango,
    )

    return NotificationPreferenceRepositoryDjango()


def templateRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationTemplateRepositoryDjango,
    )

    return NotificationTemplateRepositoryDjango()


def policyRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationPolicyRepositoryDjango,
    )

    return NotificationPolicyRepositoryDjango()


def digestRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationDigestRepositoryDjango,
    )

    return NotificationDigestRepositoryDjango()


def scheduleRepository():
    from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
        NotificationScheduleRepositoryDjango,
    )

    return NotificationScheduleRepositoryDjango()


# -- §38 application services -----------------------------------------------------------


class NotificationContainer:
    """Lazy factory per service (fresh instances, shared singletons inside)."""

    # -- repository accessors (also used by management/tests/metrics view) --

    def notificationRepository(self):
        return notificationRepository()

    def deliveryRepository(self):
        return deliveryRepository()

    def deviceRepository(self):
        return deviceRepository()

    def digestRepository(self):
        return digestRepository()

    def scheduleRepository(self):
        return scheduleRepository()

    def preferenceRepository(self):
        return preferenceRepository()

    def templateRepository(self):
        return templateRepository()

    def policyRepository(self):
        return policyRepository()

    def channelRegistry(self):
        return channelRegistry()

    def jobQueue(self):
        return jobQueue()

    def realtime(self):
        return realtime()

    def createNotificationService(self):
        from apps.notifications.application.services.createNotification import (
            CreateNotificationService,
        )

        return CreateNotificationService(
            **notificationPorts(),
            notificationRepository=notificationRepository(),
            digestRepository=digestRepository(),
            resolveRecipients=self.resolveRecipientsService(),
            resolvePolicy=self.resolvePolicyService(),
            renderService=self.renderService(),
            jobQueue=jobQueue(),
        )

    def resolveRecipientsService(self):
        from apps.notifications.application.services.resolveRecipients import (
            ResolveRecipientsService,
        )

        return ResolveRecipientsService(
            **notificationPorts(), recipientDirectory=recipientDirectory()
        )

    def resolvePolicyService(self):
        from apps.notifications.application.services.resolvePolicyAndPreferences import (
            ResolveNotificationPolicyService,
        )

        return ResolveNotificationPolicyService(
            **notificationPorts(),
            policyRepository=policyRepository(),
            preferenceRepository=preferenceRepository(),
        )

    def resolvePreferencesService(self):
        from apps.notifications.application.services.resolvePolicyAndPreferences import (
            ResolveNotificationPreferencesService,
        )

        return ResolveNotificationPreferencesService(
            **notificationPorts(), preferenceRepository=preferenceRepository()
        )

    def renderService(self):
        from apps.notifications.application.services.renderNotificationContent import (
            RenderNotificationService,
        )

        return RenderNotificationService(
            **notificationPorts(),
            templateRepository=templateRepository(),
            userContacts=userContacts(),
        )

    def dispatchService(self):
        from apps.notifications.application.services.dispatchNotification import (
            DispatchNotificationService,
        )

        return DispatchNotificationService(
            **notificationPorts(),
            notificationRepository=notificationRepository(),
            deliveryRepository=deliveryRepository(),
            resolvePolicy=self.resolvePolicyService(),
            resolvePreferences=self.resolvePreferencesService(),
            renderService=self.renderService(),
            channelRegistry=channelRegistry(),
            userContacts=userContacts(),
        )

    def retryService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            RetryNotificationDeliveryService,
        )

        return RetryNotificationDeliveryService(
            **notificationPorts(),
            notificationRepository=notificationRepository(),
            deliveryRepository=deliveryRepository(),
            channelRegistry=channelRegistry(),
            renderService=self.renderService(),
        )

    def createDigestService(self):
        from apps.notifications.application.services.digestServices import (
            CreateDigestService,
        )

        return CreateDigestService(
            **notificationPorts(), digestRepository=digestRepository()
        )

    def sendDigestService(self):
        from apps.notifications.application.services.digestServices import (
            SendDigestService,
        )

        return SendDigestService(
            **notificationPorts(),
            digestRepository=digestRepository(),
            notificationRepository=notificationRepository(),
        )

    def scheduleNotificationService(self):
        from apps.notifications.application.services.scheduleAndExpiryServices import (
            ScheduleNotificationService,
        )

        return ScheduleNotificationService(
            **notificationPorts(), scheduleRepository=scheduleRepository()
        )

    def runDueSchedulesService(self):
        from apps.notifications.application.services.scheduleAndExpiryServices import (
            RunDueSchedulesService,
        )

        return RunDueSchedulesService(
            **notificationPorts(), scheduleRepository=scheduleRepository()
        )

    def cancelScheduleService(self):
        from apps.notifications.application.services.scheduleAndExpiryServices import (
            CancelScheduleService,
        )

        return CancelScheduleService(
            **notificationPorts(), scheduleRepository=scheduleRepository()
        )

    def listSchedulesService(self):
        from apps.notifications.application.services.scheduleAndExpiryServices import (
            ListSchedulesService,
        )

        return ListSchedulesService(
            **notificationPorts(), scheduleRepository=scheduleRepository()
        )

    def cancelNotificationService(self):
        from apps.notifications.application.services.scheduleAndExpiryServices import (
            CancelNotificationService,
        )

        return CancelNotificationService(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def expireNotificationsService(self):
        from apps.notifications.application.services.scheduleAndExpiryServices import (
            ExpireNotificationsService,
        )

        return ExpireNotificationsService(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def markNotificationReadService(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            MarkNotificationReadService,
        )

        return MarkNotificationReadService(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def markNotificationUnreadService(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            MarkNotificationUnreadService,
        )

        return MarkNotificationUnreadService(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def acknowledgeNotificationService(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            AcknowledgeNotificationService,
        )

        return AcknowledgeNotificationService(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def archiveNotificationService(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            ArchiveNotificationService,
        )

        return ArchiveNotificationService(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def listNotificationsUseCase(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            ListNotificationsUseCase,
        )

        return ListNotificationsUseCase(
            **notificationPorts(),
            notificationRepository=notificationRepository(),
            deliveryRepository=deliveryRepository(),
        )

    def getNotificationUseCase(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            GetNotificationUseCase,
        )

        return GetNotificationUseCase(
            **notificationPorts(),
            notificationRepository=notificationRepository(),
            deliveryRepository=deliveryRepository(),
        )

    def unreadCountUseCase(self):
        from apps.notifications.application.services.notificationReceiptServices import (
            UnreadCountUseCase,
        )

        return UnreadCountUseCase(
            **notificationPorts(), notificationRepository=notificationRepository()
        )

    def updatePreferencesService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            UpdatePreferencesService,
        )

        return UpdatePreferencesService(
            **notificationPorts(), preferenceRepository=preferenceRepository()
        )

    def getPreferencesService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            GetPreferencesService,
        )

        return GetPreferencesService(
            **notificationPorts(), preferenceRepository=preferenceRepository()
        )

    def saveTenantRuleService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            SaveTenantRuleService,
        )

        return SaveTenantRuleService(
            **notificationPorts(), preferenceRepository=preferenceRepository()
        )

    def deleteTenantRuleService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            DeleteTenantRuleService,
        )

        return DeleteTenantRuleService(
            **notificationPorts(), preferenceRepository=preferenceRepository()
        )

    def listTenantRulesService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            ListTenantRulesService,
        )

        return ListTenantRulesService(
            **notificationPorts(), preferenceRepository=preferenceRepository()
        )

    def registerDeviceService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            RegisterNotificationDeviceService,
        )

        return RegisterNotificationDeviceService(
            **notificationPorts(), deviceRepository=deviceRepository()
        )

    def revokeDeviceService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            RevokeNotificationDeviceService,
        )

        return RevokeNotificationDeviceService(
            **notificationPorts(), deviceRepository=deviceRepository()
        )

    def listDevicesService(self):
        from apps.notifications.application.services.preferenceAndDeviceServices import (
            ListDevicesService,
        )

        return ListDevicesService(
            **notificationPorts(), deviceRepository=deviceRepository()
        )

    def saveTemplateService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            SaveTemplateService,
        )

        return SaveTemplateService(
            **notificationPorts(), templateRepository=templateRepository()
        )

    def deactivateTemplateService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            DeactivateTemplateService,
        )

        return DeactivateTemplateService(
            **notificationPorts(), templateRepository=templateRepository()
        )

    def listTemplatesService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            ListTemplatesService,
        )

        return ListTemplatesService(
            **notificationPorts(), templateRepository=templateRepository()
        )

    def savePolicyService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            SavePolicyService,
        )

        return SavePolicyService(
            **notificationPorts(), policyRepository=policyRepository()
        )

    def deletePolicyService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            DeletePolicyService,
        )

        return DeletePolicyService(
            **notificationPorts(), policyRepository=policyRepository()
        )

    def listPoliciesService(self):
        from apps.notifications.application.services.retryAndAdminServices import (
            ListPoliciesService,
        )

        return ListPoliciesService(
            **notificationPorts(), policyRepository=policyRepository()
        )


container = NotificationContainer()


# ---------------------------------------------------------------------------
# Phase 12 — multi-recipient broadcast model (docs/Phases/Phase12.md).
# Standalone factories so the Phase 09 container class stays untouched.
# ---------------------------------------------------------------------------


def broadcastRepository():
    from apps.notifications.infrastructure.repositories.phase12RepositoriesImpl import (
        BroadcastNotificationRepositoryDjango,
    )

    return BroadcastNotificationRepositoryDjango()


def recipientDeliveryRepository():
    from apps.notifications.infrastructure.repositories.phase12RepositoriesImpl import (
        RecipientDeliveryRepositoryDjango,
    )

    return RecipientDeliveryRepositoryDjango()


def notificationRuleRepository():
    from apps.notifications.infrastructure.repositories.phase12RepositoriesImpl import (
        NotificationRuleRepositoryDjango,
    )

    return NotificationRuleRepositoryDjango()


def inboundEventRepository():
    from apps.notifications.infrastructure.repositories.phase12RepositoriesImpl import (
        InboundEventRepositoryDjango,
    )

    return InboundEventRepositoryDjango()


def createBroadcastService():
    from apps.notifications.application.services.phase12Services import (
        CreateBroadcastService,
    )

    return CreateBroadcastService(
        broadcastRepository=broadcastRepository(), **notificationPorts()
    )


def recipientStateService():
    from apps.notifications.application.services.phase12Services import (
        RecipientStateService,
    )

    return RecipientStateService(
        broadcastRepository=broadcastRepository(), **notificationPorts()
    )


def broadcastQueryService():
    from apps.notifications.application.services.phase12Services import (
        BroadcastQueryService,
    )

    return BroadcastQueryService(
        broadcastRepository=broadcastRepository(), **notificationPorts()
    )


def deliveryDispatchService():
    from apps.notifications.application.services.phase12Services import (
        DeliveryDispatchService,
    )

    return DeliveryDispatchService(
        broadcastRepository=broadcastRepository(),
        deliveryRepository=recipientDeliveryRepository(),
        **notificationPorts(),
    )


def deliveryRetryService():
    from apps.notifications.application.services.phase12Services import (
        DeliveryRetryService,
    )

    return DeliveryRetryService(
        deliveryRepository=recipientDeliveryRepository(), **notificationPorts()
    )


def deliveryQueryService():
    from apps.notifications.application.services.phase12Services import (
        DeliveryQueryService,
    )

    return DeliveryQueryService(
        deliveryRepository=recipientDeliveryRepository(), **notificationPorts()
    )


def ruleDefinitionService():
    from apps.notifications.application.services.phase12Services import (
        RuleDefinitionService,
    )

    return RuleDefinitionService(
        ruleRepository=notificationRuleRepository(), **notificationPorts()
    )


def eventIntakeService():
    from apps.notifications.application.services.phase12Services import (
        EventIntakeService,
    )

    return EventIntakeService(
        inboundEventRepository=inboundEventRepository(),
        ruleRepository=notificationRuleRepository(),
        broadcastRepository=broadcastRepository(),
        dispatchService=deliveryDispatchService(),
        **notificationPorts(),
    )
