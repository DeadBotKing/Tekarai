"""Shared tenant-scope resolution for maintenance use cases (Phase 21)."""

from __future__ import annotations

import uuid
from datetime import date

from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import TenantAccessDeniedError


def resolveTenantId(requestedTenantId: str) -> uuid.UUID:
    """Resolve the tenant to operate on, refusing anything but the caller's own.

    This used to return `uuid.UUID(requestedTenantId)` unexamined. Views feed
    it `request.data.get("tenantId")` — a value the client controls — so any
    authenticated user could plant rows in any tenant they could name, and
    tenant ids are not secret: the API returns them in every payload. Proven
    by `tests/integration/testMultiTenantIsolation.py`, which got `201` three
    different ways before this guard existed.

    A request that names the caller's own tenant is still fine; clients do
    send it, and rejecting a matching value would be a regression wearing a
    security fix as a costume.
    """

    context = currentContext()
    contextValue = context.actorTenantId or context.tenantId

    if requestedTenantId:
        requested = uuid.UUID(requestedTenantId)
        if contextValue and str(requested) != str(contextValue):
            # PermissionDeniedError takes `action`, not `details` — passing
            # the wrong kwarg turns a 403 into a 500 and hides the refusal.
            raise TenantAccessDeniedError(
                "Cross-tenant access is forbidden.",
                action="tenant.scope",
            )
        # No context at all means no HTTP request: the alert scanner, the PM
        # generator and the reminder command all iterate tenants explicitly
        # and have nobody to be compared against. Every authenticated request
        # does have a context, because authentication sets it before any use
        # case runs, so this branch is not reachable from the network.
        return requested

    if contextValue:
        return uuid.UUID(contextValue)
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
