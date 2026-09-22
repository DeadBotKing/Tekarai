"""Shared tenant-scope resolution for maintenance use cases (Phase 21)."""

from __future__ import annotations

import uuid
from datetime import date

from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import TenantAccessDeniedError


def resolveTenantId(requestedTenantId: str) -> uuid.UUID:
    if requestedTenantId:
        return uuid.UUID(requestedTenantId)
    context = currentContext()
    if context.actorTenantId:
        return uuid.UUID(context.actorTenantId)
    if context.tenantId:
        return uuid.UUID(context.tenantId)
    raise TenantAccessDeniedError("Tenant scope could not be resolved.")


def parseDateOrToday(value: str, today: date) -> date:
    if not value:
        return today
    try:
        return date.fromisoformat(value)
    except ValueError:
        return today


def parseDateOrNone(value: str) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None
