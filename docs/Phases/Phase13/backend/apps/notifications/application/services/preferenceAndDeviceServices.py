"""§10/§11 preference + tenant-rule services and §15 device registry."""

from __future__ import annotations

import uuid
from typing import Any

from apps.notifications.application.commands.notificationCommands import (
    DeleteTenantRuleCommand,
    RegisterDeviceCommand,
    RevokeDeviceCommand,
    SaveTenantRuleCommand,
    UpdatePreferencesCommand,
)
from apps.notifications.application.dto.notificationDtos import (
    DeviceDto,
    PreferenceDto,
    TenantRuleDto,
    deviceDtoFromDomain,
    preferenceDtoFromDomain,
    tenantRuleDtoFromDomain,
)
from apps.notifications.application.queries.notificationQueries import (
    GetPreferencesQuery,
    ListDevicesQuery,
    ListTenantRulesQuery,
)
from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.entities.notificationDevice import NotificationDevice
from apps.notifications.domain.entities.notificationPreference import (
    NotificationPreference,
    NotificationPreferenceRule,
)
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationDeviceRepository,
    NotificationPreferenceRepository,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    CATEGORY_SECURITY,
    CHANNEL_IN_APP,
    DELIVERY_CHANNELS,
    PREF_LEVEL_CATEGORY,
    PREF_LEVEL_GLOBAL,
    PREF_LEVEL_TYPE,
)
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    EntityNotFoundError,
    ValidationFailedError,
)


class UpdatePreferencesService(NotificationUseCase):
    """§10 — replace the user's own preference set (validated per level)."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferenceRepository = preferenceRepository

    def validateCommand(self, command: UpdatePreferencesCommand) -> None:
        seen: set[tuple[str, str, str, str]] = set()
        for row in command.preferences:
            channel = str(row.get("channel", "") or "")
            level = str(row.get("level", "") or "").upper()
            if channel not in DELIVERY_CHANNELS:
                raise ValidationFailedError(
                    "Unknown channel.", fieldErrors={"channel": channel}
                )
            key = (
                level,
                str(row.get("category", "") or ""),
                str(row.get("notificationType", "") or ""),
                channel,
            )
            if key in seen:
                raise ValidationFailedError(
                    "Duplicate preference scope.", fieldErrors={"preferences": str(key)}
                )
            seen.add(key)

    def perform(self, command: UpdatePreferencesCommand) -> list[PreferenceDto]:
        rows: list[NotificationPreference] = []
        for row in command.preferences:
            rows.append(
                NotificationPreference(
                    id=uuid.uuid4(),
                    tenantId=command.tenantId,
                    userId=command.userId,
                    level=str(row.get("level", "") or "").upper(),
                    channel=str(row.get("channel", "") or ""),
                    category=str(row.get("category", "") or ""),
                    notificationType=str(row.get("notificationType", "") or ""),
                    enabled=bool(row.get("enabled", True)),
                    quietHoursStart=str(row.get("quietHoursStart", "") or ""),
                    quietHoursEnd=str(row.get("quietHoursEnd", "") or ""),
                )
            )
        self.preferenceRepository.replaceForUser(command.userId, rows)
        self.audit(
            "UPDATE",
            resourceType="NotificationPreferences",
            resourceId=str(command.userId),
            tenantId=command.tenantId,
            after={"count": len(rows)},
        )
        return self.listFor(command.tenantId, command.userId)

    def listFor(self, tenantId: uuid.UUID, userId: uuid.UUID) -> list[PreferenceDto]:
        return [
            preferenceDtoFromDomain(preference)
            for preference in self.preferenceRepository.listForUser(tenantId, userId)
        ]


class GetPreferencesService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferenceRepository = preferenceRepository

    def perform(self, query: GetPreferencesQuery) -> dict:
        rows = [
            preferenceDtoFromDomain(preference)
            for preference in self.preferenceRepository.listForUser(
                query.tenantId, query.userId
            )
        ]
        return {
            "preferences": rows,
            "levels": [PREF_LEVEL_GLOBAL, PREF_LEVEL_CATEGORY, PREF_LEVEL_TYPE],
            "channels": list(DELIVERY_CHANNELS),
        }


class SaveTenantRuleService(NotificationUseCase):
    """§11 — tenant org rules; FORCED for security delivery can't be denied."""

    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferenceRepository = preferenceRepository

    def perform(self, command: SaveTenantRuleCommand) -> TenantRuleDto:
        rule = NotificationPreferenceRule(
            id=uuid.uuid4(),
            tenantId=command.tenantId,
            channel=command.channel,
            action=command.effect,
            category=command.category,
            notificationType=command.notificationType,
            description=f"tenant rule {command.effect}",
        )
        self.guardPlatformSecurity(command)
        self.preferenceRepository.saveRule(rule)
        self.audit(
            "PERMISSION_CHANGE",
            resourceType="NotificationTenantRule",
            resourceId=str(rule.id),
            tenantId=command.tenantId,
            after={"channel": rule.channel, "action": rule.action},
        )
        return tenantRuleDtoFromDomain(rule)

    @staticmethod
    def guardPlatformSecurity(command: SaveTenantRuleCommand) -> None:
        """§11 — tenant rules may never weaken platform security delivery."""
        if (
            command.effect == NotificationPreferenceRule.DENIED
            and command.channel == CHANNEL_IN_APP
            and (not command.category or command.category == CATEGORY_SECURITY)
        ):
            raise BusinessRuleViolationError(
                "Tenant rules cannot disable in-app security delivery.",
                ruleId="BR-NTF-011",
            )


class DeleteTenantRuleService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferenceRepository = preferenceRepository

    def perform(self, command: DeleteTenantRuleCommand) -> dict:
        if not self.preferenceRepository.deleteRule(command.ruleId):
            raise EntityNotFoundError("NotificationTenantRule", str(command.ruleId))
        return {"deleted": True}


class ListTenantRulesService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        preferenceRepository: NotificationPreferenceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.preferenceRepository = preferenceRepository

    def perform(self, query: ListTenantRulesQuery) -> list[TenantRuleDto]:
        return [
            tenantRuleDtoFromDomain(rule)
            for rule in self.preferenceRepository.listRules(query.tenantId)
        ]


class RegisterNotificationDeviceService(NotificationUseCase):
    """§15 — many devices per user; idempotent per deviceIdentifier."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        deviceRepository: NotificationDeviceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.deviceRepository = deviceRepository

    def perform(self, command: RegisterDeviceCommand) -> DeviceDto:
        now = self.nowUtc()
        existing = self.deviceRepository.findByIdentifier(
            command.tenantId, command.userId, command.deviceIdentifier
        )
        if existing is not None:
            existing.pushToken = command.pushToken  # token rotation §15
            existing.provider = command.provider
            if existing.revokedAt is not None:
                existing.reactivate(now, command.pushToken)
            else:
                existing.touch(now)
            self.deviceRepository.update(existing)
            return deviceDtoFromDomain(existing)
        device = NotificationDevice(
            id=uuid.uuid4(),
            tenantId=command.tenantId,
            userId=command.userId,
            platform=command.platform,
            deviceIdentifier=command.deviceIdentifier,
            pushToken=command.pushToken,
            provider=command.provider,
            createdAt=now,
        )
        device.touch(now)
        self.deviceRepository.create(device)
        self.audit(
            "CREATE",
            resourceType="NotificationDevice",
            resourceId=str(device.id),
            tenantId=command.tenantId,
            after={"platform": device.platform},
        )
        return deviceDtoFromDomain(device)


class RevokeNotificationDeviceService(NotificationUseCase):
    """§49 — a revoked device stops receiving push immediately."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        deviceRepository: NotificationDeviceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.deviceRepository = deviceRepository

    def perform(self, command: RevokeDeviceCommand) -> dict:
        device = self.deviceRepository.getById(command.deviceId)
        if device is None or device.userId != command.userId:
            raise EntityNotFoundError("NotificationDevice", str(command.deviceId))
        device.revoke(self.nowUtc())
        self.deviceRepository.update(device)
        self.audit(
            "DELETE",
            resourceType="NotificationDevice",
            resourceId=str(device.id),
            tenantId=device.tenantId,
        )
        return {"revoked": True}


class ListDevicesService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        deviceRepository: NotificationDeviceRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.deviceRepository = deviceRepository

    def perform(self, query: ListDevicesQuery) -> list[DeviceDto]:
        return [
            deviceDtoFromDomain(device)
            for device in self.deviceRepository.listForUser(
                query.tenantId, query.userId, activeOnly=query.activeOnly
            )
        ]
