"""Suspend/reactivate tenant use cases — state-machine transitions
(StateMachineCatalog · Tenant: active ⇄ suspended → closed)."""

from __future__ import annotations

from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError
from apps.sharedKernel.domain.valueObjects import asUuid
from apps.tenancy.application.commands.tenantCommands import ChangeTenantStatusCommand
from apps.tenancy.application.dto.tenantDtos import TenantDto, tenantDtoFromDomain
from apps.tenancy.domain.repositories.tenantRepository import TenantRepository

ACTION_BY_TARGET = {
    "suspended": "tenant.suspend",
    "active": "tenant.activate",
    "closed": "tenant.close",
}


class ChangeTenantStatusUseCase(UseCase[ChangeTenantStatusCommand, TenantDto]):
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

    def validateCommand(self, command: ChangeTenantStatusCommand) -> None:
        if command.target not in ACTION_BY_TARGET:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unsupported tenant status target.",
                fieldErrors={"target": command.target},
            )
        # Action depends on the target state — set before authorization runs.
        self.requiredAction = ACTION_BY_TARGET[command.target]

    def perform(self, command: ChangeTenantStatusCommand) -> TenantDto:
        tenantId = asUuid(command.tenantId)
        tenant = self.repository.getById(tenantId)
        if tenant is None:
            raise EntityNotFoundError("Tenant", command.tenantId)
        before = tenant.snapshot()
        actorId = asUuid(currentActorId()) if currentActorId() else None
        tenant.transitionTo(command.target, self.clock.nowUtc(), actorId=actorId)
        self.repository.update(tenant)
        self.collectEventsFrom(tenant)
        self.audit(
            AUDIT_UPDATE,
            resourceType="Tenant",
            resourceId=str(tenant.id),
            tenantId=tenant.id,
            before=before,
            after=tenant.snapshot(),
        )
        return tenantDtoFromDomain(tenant)


def currentActorId() -> str:
    from apps.sharedKernel.application.requestContext import currentContext

    return currentContext().actorId
