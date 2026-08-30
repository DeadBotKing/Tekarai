"""Notification queries (Phase 09 §40/§42)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass


@dataclass(frozen=True)
class ListNotificationsQuery:
    tenantId: uuid.UUID
    recipientId: uuid.UUID
    unreadOnly: bool = False
    category: str = ""
    priority: str = ""
    beforeId: uuid.UUID | None = None
    limit: int = 50
    includeArchived: bool = False


@dataclass(frozen=True)
class GetNotificationQuery:
    notificationId: uuid.UUID
    recipientId: uuid.UUID


@dataclass(frozen=True)
class UnreadCountQuery:
    tenantId: uuid.UUID
    recipientId: uuid.UUID


@dataclass(frozen=True)
class GetPreferencesQuery:
    tenantId: uuid.UUID
    userId: uuid.UUID


@dataclass(frozen=True)
class ListDevicesQuery:
    tenantId: uuid.UUID
    userId: uuid.UUID
    activeOnly: bool = False


@dataclass(frozen=True)
class ListTemplatesQuery:
    tenantId: uuid.UUID


@dataclass(frozen=True)
class ListTemplateVersionsQuery:
    tenantId: uuid.UUID
    templateKey: str
    language: str
    channel: str


@dataclass(frozen=True)
class ListPoliciesQuery:
    tenantId: uuid.UUID


@dataclass(frozen=True)
class ListTenantRulesQuery:
    tenantId: uuid.UUID


@dataclass(frozen=True)
class ListSchedulesQuery:
    tenantId: uuid.UUID
