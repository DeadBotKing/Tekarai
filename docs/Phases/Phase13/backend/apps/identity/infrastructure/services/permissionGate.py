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
        grants = self.accessRepository.grantsOfUser(actorId, tenantId or actorId)
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
