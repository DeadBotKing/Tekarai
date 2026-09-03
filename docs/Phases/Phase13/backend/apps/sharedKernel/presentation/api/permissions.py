"""Action-based API permissions (Phase 06 §17, BR-PER-001/004).

``actionPermission("user.create")`` returns a DRF permission class that asks
the ``PermissionGate`` port (implemented by Identity with the domain
PermissionEvaluator). Access = permission ∧ role ∧ scope ∧ tenant boundary —
never ``is_staff``/``is_superuser``. Object-level checks (§44 layer six)
happen inside use cases via ``targetTenantId``.
"""

from __future__ import annotations

import uuid

from rest_framework.permissions import BasePermission

from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import TenantAccessDeniedError
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


class IsAuthenticated(BasePermission):
    """Any valid session (authentication only — no action requirement)."""

    message = "Authentication required."

    def has_permission(self, request, view) -> bool:  # noqa: ANN001 — DRF contract
        return bool(currentContext().actorId)


def actionPermission(action: str) -> type[BasePermission]:
    """Build a permission class requiring one action-based code (§42)."""

    class ActionPermission(BasePermission):
        message = "Permission denied."

        def has_permission(self, request, view) -> bool:  # noqa: ANN001
            context = currentContext()
            if not context.actorId:
                return False
            gate = sharedKernelProvider("permissionGate")()
            return gate.hasPermission(
                uuid.UUID(context.actorId),
                action,
                tenantId=uuid.UUID(context.actorTenantId) if context.actorTenantId else None,
            )

    ActionPermission.__name__ = f"ActionPermission[{action}]"
    ActionPermission.requiredAction = action
    return ActionPermission


def requireSameTenant(targetTenantId: uuid.UUID | str) -> None:
    """Tenant boundary guard for object-level access (BR-TEN-001)."""
    context = currentContext()
    if not context.actorTenantId or str(targetTenantId) != context.actorTenantId:
        raise TenantAccessDeniedError()
