"""Resource authorization policies (Phase 07 §18–§19).

Authorization is two-step (§18): (1) permission check — done by the
permission gate; (2) resource policy check — done HERE, in the domain.
Policies answer canView/canCreate/canUpdate/canDelete/canApprove for a
concrete resource instance. Policies are never written inside views (§19) —
an architecture test enforces that.

``AccessRequest`` is the domain-side context object (§13 abstraction): it
carries actor, tenant and grant summary without any HTTP shape.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from typing import Any, Protocol

from apps.sharedKernel.domain.valueObjects import ActionCode


@dataclass(frozen=True)
class AccessRequest:
    """Who wants what, where (tenant-context abstraction, §13)."""

    actorId: uuid.UUID
    tenantId: uuid.UUID
    isGlobalScope: bool
    actions: frozenset[str] = field(default_factory=frozenset)

    def hasAction(self, action: str) -> bool:
        ActionCode(action)  # grammar guard (BR-PER-001)
        return action in self.actions


class ResourcePolicy(Protocol):
    """Policy contract (§19): per-resource access decisions."""

    def canView(self, request: AccessRequest, resource: Any) -> bool: ...

    def canUpdate(self, request: AccessRequest, resource: Any) -> bool: ...

    def canDelete(self, request: AccessRequest, resource: Any) -> bool: ...

    def canDisable(self, request: AccessRequest, resource: Any) -> bool: ...


class UserAccountPolicy:
    """User-resource policy (§18): permission alone is not enough.

    Rules (tenant boundary + object level):
    - same-tenant actors with user.update may update peers;
    - nobody may disable or demote themselves via policy path;
    - GLOBAL (system) scope may cross tenants;
    - a tenant actor may never touch a platform user of another tenant.
    """

    def canView(self, request: AccessRequest, resource: Any) -> bool:
        target = _userOf(resource)
        if request.actorId == target.id:
            return True
        return request.isGlobalScope or target.tenantId == request.tenantId

    def canUpdate(self, request: AccessRequest, resource: Any) -> bool:
        target = _userOf(resource)
        if request.actorId == target.id:
            return True  # self-service profile updates are policy-allowed
        if not request.hasAction("user.update"):
            return False
        return request.isGlobalScope or target.tenantId == request.tenantId

    def canDelete(self, request: AccessRequest, resource: Any) -> bool:
        target = _userOf(resource)
        if request.actorId == target.id:
            return False  # never yourself
        if not request.hasAction("user.suspend"):
            return False
        return request.isGlobalScope or target.tenantId == request.tenantId

    def canDisable(self, request: AccessRequest, resource: Any) -> bool:
        return self.canDelete(request, resource)


class SessionPolicy:
    """Sessions are the user's own resource (§9): list/revoke own sessions
    with authentication only; other users' sessions need ``audit.view``."""

    def canView(self, request: AccessRequest, resource: Any) -> bool:
        session = _sessionOf(resource)
        return session.userId == request.actorId or request.hasAction("audit.view")

    def canDisable(self, request: AccessRequest, resource: Any) -> bool:
        return self.canView(request, resource)

    def canUpdate(self, request: AccessRequest, resource: Any) -> bool:
        session = _sessionOf(resource)
        return session.userId == request.actorId

    def canDelete(self, request: AccessRequest, resource: Any) -> bool:
        return self.canUpdate(request, resource)


class ApiKeyPolicy:
    """API keys belong to their owner inside the tenant (§22)."""

    def canView(self, request: AccessRequest, resource: Any) -> bool:
        key = _apiKeyOf(resource)
        sameTenant = key.tenantId == request.tenantId
        own = key.ownerId == request.actorId
        return (
            (sameTenant and own)
            or (sameTenant and request.hasAction("apiKey.view"))
            or request.isGlobalScope
        )

    def canUpdate(self, request: AccessRequest, resource: Any) -> bool:
        return self.canView(request, resource)

    def canDelete(self, request: AccessRequest, resource: Any) -> bool:
        key = _apiKeyOf(resource)
        if key.tenantId != request.tenantId and not request.isGlobalScope:
            return False
        return key.ownerId == request.actorId or request.hasAction("apiKey.revoke")

    def canDisable(self, request: AccessRequest, resource: Any) -> bool:
        return self.canDelete(request, resource)


def _userOf(resource: Any) -> Any:
    from apps.identity.domain.entities.user import User

    assert isinstance(resource, User)
    return resource


def _sessionOf(resource: Any) -> Any:
    from apps.identity.domain.entities.session import Session

    assert isinstance(resource, Session)
    return resource


def _apiKeyOf(resource: Any) -> Any:
    from apps.identity.domain.entities.apiKey import ApiKey

    assert isinstance(resource, ApiKey)
    return resource


#: Policy registry (§19) — resources gain policies as contexts arrive.
POLICIES: dict[str, ResourcePolicy] = {
    "User": UserAccountPolicy(),
    "Session": SessionPolicy(),
    "ApiKey": ApiKeyPolicy(),
}


def policyFor(resourceType: str) -> ResourcePolicy:
    return POLICIES[resourceType]
