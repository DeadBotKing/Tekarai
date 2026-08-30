"""§22 scheduling + §23 expiration + cancellation."""

from __future__ import annotations

import uuid
from datetime import timedelta
from typing import Any

from apps.notifications.application.commands.notificationCommands import (
    CancelNotificationCommand,
    CancelScheduleCommand,
    CreateNotificationCommand,
    RunDueSchedulesCommand,
    ScheduleNotificationCommand,
)
from apps.notifications.application.dto.notificationDtos import (
    ScheduleDto,
    scheduleDtoFromDomain,
)
from apps.notifications.application.queries.notificationQueries import (
    ListSchedulesQuery,
)
from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.entities.notificationDigest import NotificationSchedule
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationRepository,
    NotificationScheduleRepository,
)
from apps.notifications.domain.valueObjects.notificationTypes import (
    DIGEST_DAILY,
    DIGEST_HOURLY,
    DIGEST_WEEKLY,
    SCHEDULE_CANCELLED,
    SCHEDULE_DELAYED,
    SCHEDULE_DIGEST,
    SCHEDULE_IMMEDIATE,
    SCHEDULE_RECURRING,
    SCHEDULE_SCHEDULED,
    SCHEDULE_KINDS,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    ValidationFailedError,
)

_KIND_TO_DIGEST = {"HOURLY": DIGEST_HOURLY, "DAILY": DIGEST_DAILY, "WEEKLY": DIGEST_WEEKLY}


class ScheduleNotificationService(NotificationUseCase):
    """§22 — the scheduler is backend-driven, never frontend-driven."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        scheduleRepository: NotificationScheduleRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.scheduleRepository = scheduleRepository

    def validateCommand(self, command: ScheduleNotificationCommand) -> None:
        if command.kind not in SCHEDULE_KINDS:
            raise ValidationFailedError(
                "Unknown schedule kind.", fieldErrors={"kind": command.kind}
            )
        if command.kind == SCHEDULE_RECURRING and command.recurEverySeconds <= 0:
            raise ValidationFailedError(
                "RECURRING needs recurEverySeconds > 0.",
                fieldErrors={"recurEverySeconds": "required"},
            )
        if command.kind in (SCHEDULE_SCHEDULED, SCHEDULE_IMMEDIATE) and command.scheduledAt is None:
            raise ValidationFailedError(
                f"{command.kind} needs scheduledAt.",
                fieldErrors={"scheduledAt": "required"},
            )

    def perform(self, command: ScheduleNotificationCommand) -> ScheduleDto:
        now = self.nowUtc()
        scheduledAt = command.scheduledAt
        if command.kind == SCHEDULE_DELAYED:
            scheduledAt = now + timedelta(seconds=max(0, command.delaySeconds))
        if command.kind == SCHEDULE_DIGEST:
            scheduledAt = now  # digest kind materializes on the worker tick
        schedule = NotificationSchedule(
            id=uuid.uuid4(),
            tenantId=command.tenantId,
            kind=command.kind,
            recipientSpec=dict(command.recipientSpec),
            notificationType=command.notificationType,
            category=command.category,
            priority=command.priority,
            title=command.title,
            body=command.body,
            sourceType=command.sourceType,
            sourceId=command.sourceId,
            scheduledAt=scheduledAt,
            recurEverySeconds=command.recurEverySeconds,
            expiresAt=command.expiresAt,
            payload=dict(command.payload),
            correlationId=command.correlationId,
        )
        self.scheduleRepository.create(schedule)
        self.audit(
            "CREATE",
            resourceType="NotificationSchedule",
            resourceId=str(schedule.id),
            tenantId=command.tenantId,
            after={"kind": schedule.kind, "type": schedule.notificationType},
        )
        return scheduleDtoFromDomain(schedule)


class RunDueSchedulesService(NotificationUseCase):
    """§22 — worker tick: due schedules become CreateNotification commands."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        scheduleRepository: NotificationScheduleRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.scheduleRepository = scheduleRepository

    def perform(self, command: RunDueSchedulesCommand) -> dict:
        from apps.notifications.application.services.createNotification import (
            CreateNotificationService,
        )
        from apps.notifications.infrastructure.container import container

        now = self.nowUtc()
        created, skipped = 0, 0
        createService: CreateNotificationService = container.createNotificationService()
        for schedule in self.scheduleRepository.listDue(now, limit=command.limit):
            payload = dict(schedule.payload)
            payload["scheduleId"] = str(schedule.id)
            outcome = createService.execute(
                CreateNotificationCommand(
                    tenantId=schedule.tenantId,
                    recipientSpec=schedule.recipientSpec,
                    eventType=f"schedule.{schedule.kind}",
                    eventId=f"{schedule.id}:{(schedule.lastRunAt or schedule.nextRunAt or self.nowUtc()).isoformat()}",
                    notificationType=schedule.notificationType,
                    category=schedule.category,
                    priority=schedule.priority,
                    title=schedule.title,
                    body=schedule.body,
                    sourceType=schedule.sourceType or "SCHEDULE",
                    sourceId=schedule.sourceId or str(schedule.id),
                    data=payload,
                    expiresAt=schedule.expiresAt,
                    correlationId=schedule.correlationId,
                    causationId=f"schedule:{schedule.id}",
                )
            )
            created += len(outcome.notifications)
            skipped += outcome.duplicates
            schedule.recordRun(now)
            self.scheduleRepository.update(schedule)
        return {"created": created, "duplicates": skipped}


class CancelScheduleService(NotificationUseCase):
    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        scheduleRepository: NotificationScheduleRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.scheduleRepository = scheduleRepository

    def perform(self, command: CancelScheduleCommand) -> dict:
        schedule = self.scheduleRepository.getById(command.scheduleId)
        if schedule is None:
            raise EntityNotFoundError("NotificationSchedule", str(command.scheduleId))
        if schedule.status != SCHEDULE_CANCELLED:
            schedule.cancel()
            self.scheduleRepository.update(schedule)
        return {"cancelled": True}


class ListSchedulesService(NotificationUseCase):
    requiredAction = "notification.manage"

    def __init__(
        self,
        *args: Any,
        scheduleRepository: NotificationScheduleRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.scheduleRepository = scheduleRepository

    def perform(self, query: ListSchedulesQuery) -> list[ScheduleDto]:
        return [
            scheduleDtoFromDomain(schedule)
            for schedule in self.scheduleRepository.listAll(query.tenantId)
        ]


class CancelNotificationService(NotificationUseCase):
    """§40 — cancel before delivery; idempotent; audited."""

    requiredAction = "notification.send"

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, command: CancelNotificationCommand) -> dict:
        notification = self.notificationRepository.getById(command.notificationId)
        if notification is None:
            raise EntityNotFoundError("NotificationRecord", str(command.notificationId))
        notification.cancel(self.nowUtc(), actorId=command.actorId)
        self.notificationRepository.update(notification)
        self.collectEventsFrom(notification)
        self.audit(
            "DELETE",
            resourceType="NotificationRecord",
            resourceId=str(notification.id),
            tenantId=notification.tenantId,
        )
        return {"cancelled": True, "status": notification.status}


class ExpireNotificationsService(NotificationUseCase):
    """§23 — expired notifications are never delivered; sweeper tick."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        notificationRepository: NotificationRepository,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.notificationRepository = notificationRepository

    def perform(self, command: Any) -> dict:
        now = self.nowUtc()
        expired = 0
        for notification in self.notificationRepository.listExpiredUndelivered(
            now, limit=command.limit
        ):
            if notification.expire(now):
                self.notificationRepository.update(notification)
                self.collectEventsFrom(notification)
                expired += 1
        return {"expired": expired}
