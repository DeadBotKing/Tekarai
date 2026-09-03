"""CreateTenantUseCase — the §8 eight-step template in practice.

Steps: validate → authorize (tenant.create) → business rules (code grammar +
global uniqueness BR-TEN-004) → create entity → persist (inside UoW) →
event → audit (CREATE) → DTO.
"""

from __future__ import annotations

from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import AUDIT_CREATE, UseCase
from apps.sharedKernel.domain.errors import DuplicateBusinessCodeError
from apps.tenancy.application.commands.tenantCommands import CreateTenantCommand
from apps.tenancy.application.dto.tenantDtos import TenantDto, tenantDtoFromDomain
from apps.tenancy.domain.entities.tenant import Tenant
from apps.tenancy.domain.repositories.tenantRepository import TenantRepository
from apps.tenancy.domain.valueObjects.tenantState import TenantCode


class CreateTenantUseCase(UseCase[CreateTenantCommand, TenantDto]):
    requiredAction = "tenant.create"

    def __init__(
        self,
        repository: TenantRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def validateCommand(self, command: CreateTenantCommand) -> None:
        # Step 1 — grammar first (value objects raise ValidationFailedError).
        TenantCode(command.code)

    def businessRules(self, command: CreateTenantCommand) -> None:
        # Step 3 — BR-TEN-004: Tenant.code is globally unique.
        if self.repository.existsByCode(command.code):
            raise DuplicateBusinessCodeError(
                "Tenant code already exists.",
                details={"code": command.code, "ruleId": "BR-TEN-004"},
            )

    def perform(self, command: CreateTenantCommand) -> TenantDto:
        tenant = Tenant.create(
            TenantCode(command.code),
            command.name,
            self.clock.nowUtc(),
        )
        self.repository.create(tenant)  # Step 5
        self.collectEventsFrom(tenant)  # Step 6 (dispatched post-commit)
        self.audit(  # Step 7
            AUDIT_CREATE,
            resourceType="Tenant",
            resourceId=str(tenant.id),
            tenantId=tenant.id,
            after=tenant.snapshot(),
        )
        return tenantDtoFromDomain(tenant)  # Step 8
