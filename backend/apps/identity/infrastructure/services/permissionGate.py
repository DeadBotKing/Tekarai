"""PermissionGateDjango — authorization port implementation (§17).

Loads the user's grants through the AccessRepository and delegates the
decision to the domain ``PermissionEvaluator`` (domain service §11).
Authentication already happened elsewhere (§16 separation).
"""

from __future__ import annotations

import uuid
from typing import Any

from apps.identity.domain.repositories.identityRepositories import AccessRepository
from apps.identity.domain.services.permissionEvaluator import PermissionEvaluator


class PermissionGateDjango:
    def __init__(self, accessRepository: AccessRepository | None = None) -> None:
        self.accessRepository = accessRepository or defaultAccessRepository()
        self.evaluator = PermissionEvaluator()

    def hasPermission(
        self,
        actorId: uuid.UUID,
        action: str,
        *,
        tenantId: uuid.UUID | None = None,
        targetTenantId: uuid.UUID | None = None,
        targetId: uuid.UUID | None = None,
    ) -> bool:
        from apps.tenancy.infrastructure.services.organizationWorkspace import allowsAction
        if (targetTenantId or tenantId) is not None and not allowsAction(targetTenantId or tenantId, action):
            return False
        return self.hasDelegationAuthority(actorId, action, tenantId=tenantId, targetTenantId=targetTenantId, targetId=targetId)

    def hasDelegationAuthority(self, actorId, action, *, tenantId=None, targetTenantId=None, targetId=None):
        """Internal role-delegation check only: module enablement is not a role grant.
        All scope/deny/MFA/retirement checks still apply. Never use for business access.
        """
        grants = self.accessRepository.grantsOfUser(actorId, tenantId or actorId)
        from apps.identity.infrastructure.services.administrativeAuthentication import administrativeGrants
        additions = administrativeGrants(actorId, requireFresh=True)
        from apps.identity.infrastructure.models import AdministrativeGovernanceModel
        if action in {'tenant.create','tenant.list','tenant.suspend','tenant.activate','tenant.close'}:
            if AdministrativeGovernanceModel.objects.filter(legacyAdminRetiredAt__isnull=False).exists() and not additions:
                return False
        grants = list(grants) + additions
        return self.evaluator.hasPermission(
            grants,
            actorId,
            action,
            actorTenantId=tenantId,
            targetTenantId=targetTenantId,
            targetId=targetId,
        )


def defaultAccessRepository() -> Any:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        AccessRepositoryDjango,
    )

    return AccessRepositoryDjango()
