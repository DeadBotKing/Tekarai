"""§18–§20 template rendering + language resolution service."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any

from apps.notifications.application.services.notificationSupport import (
    NotificationUseCase,
)
from apps.notifications.domain.repositories.notificationRepositories import (
    NotificationTemplateRepository,
    UserContactDirectory,
)
from apps.notifications.domain.services.notificationRules import resolveLanguage
from apps.notifications.domain.valueObjects.notificationTypes import (
    PLATFORM_DEFAULT_LANGUAGE,
)


@dataclass(frozen=True)
class RenderedContent:
    title: str
    subject: str
    body: str
    language: str
    templateKey: str
    templateVersion: int
    usedTemplate: bool

    def trace(self) -> list[str]:
        if not self.usedTemplate:
            return ["render=fallback(title/body)"]
        return [f"render={self.templateKey}@v{self.templateVersion}:{self.language}"]


class RenderNotificationService(NotificationUseCase):
    """§20 — USER → ORG policy → TENANT → PLATFORM language chain, then
    §18 safe {token} substitution (templates never execute code)."""

    requiredAction = ""

    def __init__(
        self,
        *args: Any,
        templateRepository: NotificationTemplateRepository,
        userContacts: UserContactDirectory,
        tenantDefaultLanguage: str = PLATFORM_DEFAULT_LANGUAGE,
        **kwargs: Any,
    ) -> None:
        super().__init__(*args, **kwargs)
        self.templateRepository = templateRepository
        self.userContacts = userContacts
        self.tenantDefaultLanguage = tenantDefaultLanguage

    def perform(self, message: Any) -> Any:  # pragma: no cover — routed via render()
        raise NotImplementedError

    def resolveLanguageFor(
        self, tenantId: uuid.UUID, userId: uuid.UUID | None
    ) -> str:
        userLanguage = ""
        if userId is not None:
            userLanguage = self.userContacts.languageOf(tenantId, userId)
        return resolveLanguage(
            userLanguage=userLanguage,
            tenantDefault=self.tenantDefaultLanguage,
        )

    def render(
        self,
        *,
        tenantId: uuid.UUID,
        recipientId: uuid.UUID | None,
        templateKey: str,
        channel: str,
        fallbackTitle: str,
        fallbackBody: str,
        data: dict[str, Any],
    ) -> RenderedContent:
        language = self.resolveLanguageFor(tenantId, recipientId)
        if templateKey:
            for candidate in self._languageCandidates(language):
                template = self.templateRepository.findActive(
                    tenantId, templateKey, candidate, channel
                )
                if template is not None:
                    title, subject, body = template.render(data)
                    return RenderedContent(
                        title=title,
                        subject=subject,
                        body=body,
                        language=candidate,
                        templateKey=template.templateKey,
                        templateVersion=template.version,
                        usedTemplate=True,
                    )
        return RenderedContent(
            title=fallbackTitle,
            subject=fallbackTitle,
            body=fallbackBody,
            language=language,
            templateKey="",
            templateVersion=0,
            usedTemplate=False,
        )

    def _languageCandidates(self, language: str) -> tuple[str, ...]:
        """Exact → tenant default → platform default (§20 four-step chain;
        the organization-policy step feeds tenantDefault from config)."""
        candidates = [language]
        if self.tenantDefaultLanguage and self.tenantDefaultLanguage not in candidates:
            candidates.append(self.tenantDefaultLanguage)
        if PLATFORM_DEFAULT_LANGUAGE not in candidates:
            candidates.append(PLATFORM_DEFAULT_LANGUAGE)
        return tuple(candidates)


#: kept for documentation clarity — org-policy language arrives as config
TENANT_DEFAULT_LANGUAGE_PLACEHOLDER = PLATFORM_DEFAULT_LANGUAGE
