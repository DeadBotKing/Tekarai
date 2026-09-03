"""Templates with safe rendering + versioning (Phase 09 §18/§19/§20)."""

from __future__ import annotations

import re
import uuid
from datetime import datetime

from apps.sharedKernel.domain.entities import AggregateRoot
from apps.sharedKernel.domain.errors import ValidationFailedError

_PLACEHOLDER = re.compile(r"\{([a-zA-Z][a-zA-Z0-9_]*)\}")


class NotificationTemplate(AggregateRoot):
    """§18 — one (key, language, channel, version). Rendering is pure token
    substitution: templates can never execute code (§18 closing rule)."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        templateKey: str,
        language: str,
        channel: str,
        version: int,
        *,
        title: str,
        subject: str = "",
        body: str = "",
        isActive: bool = True,
        createdAt: datetime | None = None,
        createdBy: uuid.UUID | None = None,
    ) -> None:
        super().__init__(id)
        if not templateKey.strip():
            raise ValidationFailedError(
                "Template key is required.", fieldErrors={"templateKey": "empty"}
            )
        if version < 1:
            raise ValidationFailedError(
                "Template version starts at 1.", fieldErrors={"version": str(version)}
            )
        if not title.strip():
            raise ValidationFailedError(
                "Template title is required.", fieldErrors={"title": "empty"}
            )
        self.tenantId = tenantId
        self.templateKey = templateKey
        self.language = language
        self.channel = channel
        self.version = version
        self.title = title
        self.subject = subject
        self.body = body
        self.isActive = isActive
        self.createdAt = createdAt or datetime.now()
        self.createdBy = createdBy

    # -- §18 safe rendering ----------------------------------------------------

    def placeholders(self) -> tuple[str, ...]:
        tokens: dict[str, None] = {}
        for text in (self.title, self.subject, self.body):
            for match in _PLACEHOLDER.finditer(text or ""):
                tokens[match.group(1)] = None
        return tuple(tokens)

    def render(self, data: dict[str, object]) -> tuple[str, str, str]:
        """Returns (title, subject, body) with {token} substitution only."""

        def substitute(text: str) -> str:
            def replace(match: re.Match[str]) -> str:
                key = match.group(1)
                value = data.get(key)
                return "" if value is None else str(value)

            return _PLACEHOLDER.sub(replace, text or "")

        return substitute(self.title), substitute(self.subject), substitute(self.body)

    # -- §19 versioning ----------------------------------------------------------

    def nextVersion(self, *, title: str, subject: str, body: str) -> "NotificationTemplate":
        return NotificationTemplate(
            id=uuid.uuid4(),
            tenantId=self.tenantId,
            templateKey=self.templateKey,
            language=self.language,
            channel=self.channel,
            version=self.version + 1,
            title=title,
            subject=subject,
            body=body,
            isActive=True,
            createdBy=None,
        )
