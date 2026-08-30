"""Phase 09 seed — default templates (fa-IR/en-US) + policies.

Idempotent: existing rows keep their versions; new templates land as
version 1, re-running after edits creates the NEXT version (§19).
"""

from __future__ import annotations

import uuid

from django.core.management.base import BaseCommand

from apps.notifications.domain.valueObjects.notificationTypes import (
    CATEGORY_AI,
    CATEGORY_COMMUNICATION,
    CATEGORY_DOCUMENT,
    CATEGORY_MEETING,
    CATEGORY_SECURITY,
    CATEGORY_SYSTEM,
    CHANNEL_BROWSER,
    CHANNEL_DESKTOP,
    CHANNEL_EMAIL,
    CHANNEL_IN_APP,
    CHANNEL_PUSH,
    PRIORITY_HIGH,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
)

#: (templateKey, channel, en title/subject/body, fa title/subject/body)
TEMPLATES: list[tuple[str, str, tuple[str, str, str], tuple[str, str, str]]] = [
    (
        "meeting.invitation",
        CHANNEL_IN_APP,
        ("Meeting invitation: {title}", "", "You are invited to «{title}»."),
        ("دعوت به جلسه: {title}", "", "شما به جلسه «{title}» دعوت شده‌اید."),
    ),
    (
        "meeting.started",
        CHANNEL_IN_APP,
        ("Meeting started", "", "«{title}» has started."),
        ("جلسه شروع شد", "", "جلسه «{title}» شروع شده است."),
    ),
    (
        "meeting.cancelled",
        CHANNEL_IN_APP,
        ("Meeting cancelled", "", "«{title}» was cancelled."),
        ("جلسه لغو شد", "", "جلسه «{title}» لغو شد."),
    ),
    (
        "call.incoming",
        CHANNEL_IN_APP,
        ("Incoming call", "", "You have an incoming call."),
        ("تماس ورودی", "", "یک تماس ورودی دارید."),
    ),
    (
        "message.received",
        CHANNEL_IN_APP,
        ("New message", "", "{title}"),
        ("پیام جدید", "", "{title}"),
    ),
    (
        "letter.created",
        CHANNEL_IN_APP,
        ("Official letter created", "", "Letter «{title}» awaits processing."),
        ("نامه رسمی ثبت شد", "", "نامه «{title}» در انتظار پردازش است."),
    ),
    (
        "recording.started",
        CHANNEL_IN_APP,
        ("Recording started", "", "This meeting is being recorded."),
        ("ضبط شروع شد", "", "این جلسه در حال ضبط است."),
    ),
    (
        "ai.summary",
        CHANNEL_IN_APP,
        ("AI summary ready", "", "A new AI summary was generated."),
        ("خلاصه هوش مصنوعی آماده است", "", "خلاصه جدیدی توسط هوش مصنوعی تولید شد."),
    ),
    (
        "digest.summary",
        CHANNEL_IN_APP,
        ("You have new notifications", "", "{itemCount} notifications were grouped."),
        ("اعلان‌های جدید دارید", "", "{itemCount} اعلان گروه‌بندی شد."),
    ),
    (
        "security.alert",
        CHANNEL_EMAIL,
        (
            "Security alert",
            "Security alert on your Tekarai account",
            "A security event occurred: {title}",
        ),
        (
            "هشدار امنیتی",
            "هشدار امنیتی در حساب تک‌ارایی شما",
            "یک رویداد امنیتی رخ داد: {title}",
        ),
    ),
]

#: (policyKey, matchType, matchValue, priority, channels, digestible, bypass)
POLICIES: list[tuple[str, str, str, str, tuple[str, ...], bool, bool, int]] = [
    (
        "meeting.invitations",
        "TYPE",
        "meeting.invitation",
        PRIORITY_HIGH,
        (CHANNEL_IN_APP, CHANNEL_PUSH, CHANNEL_EMAIL),
        False,
        False,
        120,
    ),
    (
        "meeting.lifecycle",
        "CATEGORY",
        CATEGORY_MEETING,
        PRIORITY_NORMAL,
        (CHANNEL_IN_APP, CHANNEL_PUSH),
        False,
        False,
        60,
    ),
    (
        "communication.messages",
        "CATEGORY",
        CATEGORY_COMMUNICATION,
        PRIORITY_LOW,
        (CHANNEL_IN_APP,),
        True,
        False,
        60,
    ),
    (
        "documents.letters",
        "CATEGORY",
        CATEGORY_DOCUMENT,
        PRIORITY_NORMAL,
        (CHANNEL_IN_APP, CHANNEL_EMAIL),
        False,
        False,
        60,
    ),
    (
        "ai.generated",
        "CATEGORY",
        CATEGORY_AI,
        PRIORITY_LOW,
        (CHANNEL_IN_APP,),
        True,
        False,
        300,
    ),
    (
        "security.critical",
        "CATEGORY",
        CATEGORY_SECURITY,
        "CRITICAL",
        (CHANNEL_IN_APP, CHANNEL_EMAIL, CHANNEL_PUSH),
        False,
        True,  # §5 explicit bypass for SECURITY only
        0,
    ),
    (
        "system.base",
        "CATEGORY",
        CATEGORY_SYSTEM,
        PRIORITY_NORMAL,
        (CHANNEL_IN_APP, CHANNEL_BROWSER, CHANNEL_DESKTOP),
        False,
        False,
        60,
    ),
]


class Command(BaseCommand):
    help = "Seed notification templates (fa-IR/en-US) and default policies (§18–§20, §8)."

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument("--tenant", default="", help="Tenant id (default: all tenants).")

    def handle(self, *args, **options) -> None:  # noqa: ANN002/ANN003 — Django contract
        from apps.tenancy.infrastructure.models import TenantModel

        if options["tenant"]:
            tenants = TenantModel.objects.filter(id=options["tenant"])
        else:
            tenants = TenantModel.objects.all()
        createdTemplates = updatedTemplates = createdPolicies = 0
        for tenant in tenants:
            tenantId = tenant.id
            for templateKey, channel, english, persian in TEMPLATES:
                for language, content in (("en-US", english), ("fa-IR", persian)):
                    outcome = self._saveTemplate(
                        tenantId, templateKey, language, channel, content
                    )
                    if outcome == "created":
                        createdTemplates += 1
                    elif outcome == "updated":
                        updatedTemplates += 1
            for (
                policyKey,
                matchType,
                matchValue,
                priority,
                channels,
                digestible,
                bypass,
                cooldown,
            ) in POLICIES:
                if self._savePolicy(
                    tenantId,
                    policyKey,
                    matchType,
                    matchValue,
                    priority,
                    channels,
                    digestible,
                    bypass,
                    cooldown,
                ):
                    createdPolicies += 1
        self.stdout.write(
            self.style.SUCCESS(
                f"Notification seed: +{createdTemplates} templates "
                f"({updatedTemplates} re-versioned), +{createdPolicies} new policies "
                f"across {tenants.count()} tenants."
            )
        )

    @staticmethod
    def _saveTemplate(tenantId, templateKey, language, channel, content) -> str:
        from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
            NotificationTemplateRepositoryDjango,
        )
        from apps.notifications.domain.entities.notificationTemplate import (
            NotificationTemplate,
        )

        repository = NotificationTemplateRepositoryDjango()
        existing = repository.findActive(tenantId, templateKey, language, channel)
        title, subject, body = content
        if existing is not None:
            sameContent = (
                existing.title == title
                and existing.subject == subject
                and existing.body == body
            )
            if sameContent:
                return "unchanged"
            template = existing.nextVersion(title=title, subject=subject, body=body)
            repository.deactivate(existing.id)
        else:
            template = NotificationTemplate(
                id=uuid.uuid4(),
                tenantId=tenantId,
                templateKey=templateKey,
                language=language,
                channel=channel,
                version=1,
                title=title,
                subject=subject,
                body=body,
            )
        repository.create(template)
        return "created" if template.version == 1 else "updated"

    @staticmethod
    def _savePolicy(
        tenantId,
        policyKey,
        matchType,
        matchValue,
        priority,
        channels,
        digestible,
        bypass,
        cooldown,
    ) -> bool:
        from apps.notifications.infrastructure.repositories.notificationRepositoriesImpl import (
            NotificationPolicyRepositoryDjango,
        )
        from apps.notifications.domain.entities.notificationPolicy import (
            NotificationPolicy,
        )

        repository = NotificationPolicyRepositoryDjango()
        existing = repository.findByKey(tenantId, policyKey)
        if existing is not None:
            return False
        repository.create(
            NotificationPolicy(
                id=uuid.uuid4(),
                tenantId=tenantId,
                policyKey=policyKey,
                notificationType=matchValue if matchType == "TYPE" else "",
                category=matchValue if matchType == "CATEGORY" else "",
                priority=priority,
                channels=channels,
                templateKey=policyKey,
                maxAttempts=3,
                cooldownSeconds=cooldown,
                digestible=digestible,
                allowPreferenceBypass=bypass,
                description="Phase 09 seed policy",
            )
        )
        return True
