"""PermissionEvaluator — domain service (§11): business logic that belongs
to no single entity.

Decision order (§44 layers 3–5, BR-PER-002/003/004):
1. an explicit deny always wins (BR-PER-003 exceptions are auditable);
2. an exact/module wildcard grant with GLOBAL scope passes any tenant;
3. a TENANT… scope grant passes only the actor's own tenant or the grant's
   narrowed ``scopeRef``;
4. otherwise — deny (fail closed).
"""

from __future__ import annotations

import uuid

from apps.identity.domain.valueObjects.accessGrant import (
    SCOPE_GLOBAL,
    SCOPE_TENANT,
    AccessGrant,
)


class PermissionEvaluator:
    def hasPermission(
        self,
        grants: list[AccessGrant],
        actorId: uuid.UUID,
        action: str,
        *,
        actorTenantId: uuid.UUID | None = None,
        targetTenantId: uuid.UUID | None = None,
        targetId: uuid.UUID | None = None,
    ) -> bool:
        del targetId  # object-level refinements arrive with later contexts
        matching = [grant for grant in grants if grant.matchesAction(action)]
        if any(grant.effect == "deny" for grant in matching):
            return False
        for grant in matching:
            if grant.effect != "allow":
                continue
            if grant.scopeType == SCOPE_GLOBAL:
                return True
            if grant.scopeType == SCOPE_TENANT:
                if grant.scopeRef:
                    if targetTenantId and uuid.UUID(grant.scopeRef) == targetTenantId:
                        return True
                elif targetTenantId is None or (actorTenantId and targetTenantId == actorTenantId):
                    return True
        return False

    def expandActionCodes(self, grants: list[AccessGrant]) -> list[str]:
        """Effective action patterns for the account screen (``/me``)."""
        return sorted({grant.actionPattern for grant in grants if grant.effect == "allow"})
