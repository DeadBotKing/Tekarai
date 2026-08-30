"""bootstrapPlatform — first-run composition (Phase 06).

Creates the platform tenant, seeds the permission catalogue (§73/§74 stable
codes), the global ``platformAdmin`` role, and the platform administrator
account from environment variables — never from committed values (§75: no
real secrets in seed data). Idempotent: safe to re-run.
"""

from __future__ import annotations

import os
import uuid

from django.core.management.base import BaseCommand

from apps.identity.application.commands.identityCommands import CreateUserCommand
from apps.identity.application.services.permissionCatalog import (
    ACTIONS,
    PLATFORM_ADMIN_ROLE,
    ROLE_PRESETS,
)
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.identity.infrastructure.container import createUserUseCase
from apps.identity.infrastructure.models import RoleModel
from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
    AccessRepositoryDjango,
)
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.tenancy.application.commands.tenantCommands import CreateTenantCommand
from apps.tenancy.infrastructure.container import createTenantUseCase
from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import (
    TenantRepositoryDjango,
)

PLATFORM_TENANT_CODE = os.environ.get("PLATFORM_TENANT_CODE", "platform")


class Command(BaseCommand):
    help = "Seed the platform tenant, permission catalogue and admin account."

    def handle(self, *args, **options) -> None:  # noqa: ANN002, ANN003
        username = os.environ.get("PLATFORM_ADMIN_USERNAME", "platform-admin")
        password = os.environ.get("PLATFORM_ADMIN_PASSWORD", "")
        email = os.environ.get("PLATFORM_ADMIN_EMAIL", "platform-admin@tekarai.local")
        if not password:
            self.stderr.write("PLATFORM_ADMIN_PASSWORD environment variable is required.")
            return

        access = AccessRepositoryDjango()
        access.ensureCatalogue(ACTIONS)
        roleSeeds = {
            PLATFORM_ADMIN_ROLE: ("Platform Administrator", "GLOBAL"),
            "tenantAdmin": ("Tenant Administrator", "TENANT"),
            "member": ("Member", "TENANT"),
        }
        for roleCode, (roleName, scopeType) in roleSeeds.items():
            access.ensureRole(roleCode, roleName, ROLE_PRESETS[roleCode], scopeType)
        adminRoleId = RoleModel.objects.get(code=PLATFORM_ADMIN_ROLE).id

        repository = TenantRepositoryDjango()
        tenant = repository.getByCode(PLATFORM_TENANT_CODE)
        if tenant is None:
            useCase = createTenantUseCase()
            useCase.requiredAction = ""  # first-run seed has no actor yet (§75)
            with requestScope(RequestContext(actorId="", tenantId="")):
                tenantDto = useCase.execute(
                    CreateTenantCommand(code=PLATFORM_TENANT_CODE, name="Tekarai Platform")
                )
            tenantId = uuid.UUID(tenantDto.id)
            self.stdout.write(f"platform tenant created: {PLATFORM_TENANT_CODE}")
        else:
            tenantId = tenant.id
            self.stdout.write(f"platform tenant exists: {PLATFORM_TENANT_CODE}")

        existingUser = None
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            UserRepositoryDjango,
        )

        existingUser = UserRepositoryDjango().getByUsername(tenantId, username)
        if existingUser is None:
            try:
                validatePasswordStrength(password)
            except ValidationFailedError as exc:
                self.stderr.write(f"PLATFORM_ADMIN_PASSWORD policy failure: {exc.fieldErrors}")
                return
            userUseCase = createUserUseCase()
            userUseCase.requiredAction = ""  # first-run seed has no actor yet
            with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
                userDto = userUseCase.execute(
                    CreateUserCommand(
                        tenantId=str(tenantId),
                        username=username,
                        email=email,
                        password=password,
                        displayName="Platform Administrator",
                    )
                )
            access.grantRoleToUser(uuid.UUID(userDto.id), tenantId, adminRoleId)
            self.stdout.write(f"platform admin created: {username}")
        else:
            access.grantRoleToUser(existingUser.id, tenantId, adminRoleId)
            self.stdout.write(f"platform admin ready: {username}")
