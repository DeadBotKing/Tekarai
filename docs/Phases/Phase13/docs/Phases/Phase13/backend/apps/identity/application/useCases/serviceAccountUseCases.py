"""Service-account use cases (Phase 07 §21, §31).

Service accounts are non-human identities (agents, integrations, workers,
AI callers — §2). They authenticate via API keys, never passwords, and can
be disabled/re-enabled (active↔disabled state machine).
"""

from __future__ import annotations

from apps.identity.application.commands.identityCommands import (
    CreateServiceAccountCommand,
    DisableServiceAccountCommand,
    EnableServiceAccountCommand,
)
from apps.identity.application.dto.identityDtos import ServiceAccountDto
from apps.identity.application.queries.identityQueries import ListServiceAccountsQuery
from apps.identity.domain.entities.serviceAccount import ServiceAccount
from apps.identity.domain.repositories.identityRepositories import (
    ServiceAccountRepository,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import (
    AUDIT_CREATE,
    AUDIT_UPDATE,
    UseCase,
)
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


class CreateServiceAccountUseCase(UseCase[CreateServiceAccountCommand, ServiceAccountDto]):
    requiredAction = "serviceaccount.create"

    def __init__(
        self,
        repository: ServiceAccountRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def validateCommand(self, command: CreateServiceAccountCommand) -> None:
        if not command.code.strip() or not command.name.strip():
            raise ValidationFailedError("Service account code and name are required.")

    def businessRules(self, command: CreateServiceAccountCommand) -> None:
        if self.repository.existsByCode(asUuid(command.tenantId), command.code.strip().lower()):
            from apps.sharedKernel.domain.errors import DuplicateIdentifierError

            raise DuplicateIdentifierError(
                "Service account code already exists in this tenant.",
                details={"ruleId": "PHASE7-UQ_ServiceAccount_code"},
            )

    def perform(self, command: CreateServiceAccountCommand) -> ServiceAccountDto:
        account = ServiceAccount.create(
            tenantId=asUuid(command.tenantId),
            code=command.code.strip().lower(),
            name=command.name.strip(),
            description=command.description.strip(),
            now=self.clock.nowUtc(),
            scopes=tuple(command.scopes),
        )
        self.repository.create(account)
        self.collectEventsFrom(account)
        self.audit(
            AUDIT_CREATE,
            resourceType="ServiceAccount",
            resourceId=str(account.id),
            tenantId=account.tenantId,
            after={"code": account.code},
        )
        return serviceAccountDto(account)


class DisableServiceAccountUseCase(UseCase[DisableServiceAccountCommand, ServiceAccountDto]):
    requiredAction = "serviceaccount.disable"

    def __init__(
        self,
        repository: ServiceAccountRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, command: DisableServiceAccountCommand) -> ServiceAccountDto:
        account = self.load(asUuid(command.accountId))
        account.transitionTo("disabled", self.clock.nowUtc())
        self.repository.update(account)
        self.collectEventsFrom(account)
        self.audit(
            AUDIT_UPDATE,
            resourceType="ServiceAccount",
            resourceId=str(account.id),
            tenantId=account.tenantId,
            after={"status": "disabled"},
        )
        return serviceAccountDto(account)

    def load(self, accountId):
        account = self.repository.getById(accountId)
        if account is None:
            raise EntityNotFoundError("ServiceAccount", str(accountId))
        return account


class EnableServiceAccountUseCase(UseCase[EnableServiceAccountCommand, ServiceAccountDto]):
    requiredAction = "serviceaccount.disable"

    def __init__(
        self,
        repository: ServiceAccountRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, command: EnableServiceAccountCommand) -> ServiceAccountDto:
        accountId = asUuid(command.accountId)
        account = self.repository.getById(accountId)
        if account is None:
            raise EntityNotFoundError("ServiceAccount", command.accountId)
        account.transitionTo("active", self.clock.nowUtc())
        self.repository.update(account)
        self.collectEventsFrom(account)
        self.audit(
            AUDIT_UPDATE,
            resourceType="ServiceAccount",
            resourceId=str(account.id),
            tenantId=account.tenantId,
            after={"status": "active"},
        )
        return serviceAccountDto(account)


class ListServiceAccountsUseCase(UseCase[ListServiceAccountsQuery, list[ServiceAccountDto]]):
    requiredAction = "serviceaccount.list"

    def __init__(
        self,
        repository: ServiceAccountRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: ListServiceAccountsQuery) -> list[ServiceAccountDto]:
        context = currentContext()
        tenantId = asUuid(query.tenantId) if query.tenantId else asUuid(context.actorTenantId)
        return [serviceAccountDto(a) for a in self.repository.list(tenantId)]


def serviceAccountDto(account: ServiceAccount) -> ServiceAccountDto:
    return ServiceAccountDto(
        id=str(account.id),
        tenantId=str(account.tenantId),
        code=account.code,
        name=account.name,
        description=account.description,
        status=str(account.status),
        scopes=list(account.scopes),
        createdAt=account.createdAt.isoformat(),
        disabledAt=account.disabledAt.isoformat() if account.disabledAt else "",
    )
