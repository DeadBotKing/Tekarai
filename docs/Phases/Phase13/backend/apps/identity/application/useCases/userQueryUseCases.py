"""User read use cases: GetUser, ListUsers, GetCurrentAccount (/me).

Tenant isolation is enforced here and in the repositories — list queries
always carry a tenant id (§10), and cross-tenant reads require a GLOBAL
grant (BR-TEN-001).
"""

from __future__ import annotations

from apps.identity.application.dto.identityDtos import (
    AccountDto,
    UserDto,
    UserPageDto,
    userDtoFromDomain,
)
from apps.identity.application.queries.identityQueries import (
    GetCurrentAccountQuery,
    GetUserQuery,
    ListUsersQuery,
)
from apps.identity.domain.repositories.identityRepositories import (
    AccessRepository,
    UserFilters,
    UserRepository,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import EntityNotFoundError, TenantAccessDeniedError
from apps.sharedKernel.domain.valueObjects import asUuid


class GetUserUseCase(UseCase[GetUserQuery, UserDto]):
    requiredAction = "user.view"

    def __init__(
        self,
        repository: UserRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: GetUserQuery) -> UserDto:
        userId = asUuid(query.userId)
        context = currentContext()
        actorTenantId = asUuid(context.actorTenantId) if context.actorTenantId else None
        user = self.repository.getById(userId, tenantId=actorTenantId)
        if user is None:
            # Scoped lookup missed: either absent or another tenant's.
            # Crossing tenants requires a GLOBAL grant (§44 layer six);
            # without it the answer stays 404 — never leak existence (§61).
            candidate = self.repository.getById(userId)
            if candidate is None or not context.actorId:
                raise EntityNotFoundError("User", query.userId)
            allowed = self.permissionGate.hasPermission(
                asUuid(context.actorId),
                "user.view",
                tenantId=actorTenantId,
                targetTenantId=candidate.tenantId,
            )
            if not allowed:
                raise EntityNotFoundError("User", query.userId)
            user = candidate
        return userDtoFromDomain(user)


class ListUsersUseCase(UseCase[ListUsersQuery, UserPageDto]):
    requiredAction = "user.list"

    def __init__(
        self,
        repository: UserRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository

    def perform(self, query: ListUsersQuery) -> UserPageDto:
        context = currentContext()
        actorTenantId = asUuid(context.actorTenantId)
        # Scope resolution: GLOBAL grants may list another tenant (§43);
        # everyone else is pinned to their own tenant (BR-TEN-001).
        assert context.actorId is not None
        canCrossTenants = self.permissionGate.hasPermission(
            asUuid(context.actorId),
            "tenant.list",
            tenantId=actorTenantId,
        )
        requestedTenantId = asUuid(query.tenantId) if query.tenantId else actorTenantId
        if requestedTenantId != actorTenantId and not canCrossTenants:
            raise TenantAccessDeniedError()
        pageSize = min(100, max(1, query.pageSize))
        page = self.repository.list(
            UserFilters(
                tenantId=requestedTenantId,
                status=query.status,
                search=query.search,
                ordering=query.ordering,
                page=max(1, query.page),
                pageSize=pageSize,
            )
        )
        return UserPageDto(
            items=[userDtoFromDomain(user) for user in page.items],
            totalCount=page.totalCount,
            page=max(1, query.page),
            pageSize=pageSize,
        )


class GetCurrentAccountUseCase(UseCase[GetCurrentAccountQuery, AccountDto]):
    """``/me`` — authenticated identity + effective permissions (§42)."""

    def __init__(
        self,
        repository: UserRepository,
        accessRepository: AccessRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.repository = repository
        self.accessRepository = accessRepository

    def perform(self, query: GetCurrentAccountQuery) -> AccountDto:
        context = currentContext()
        if not context.actorId:
            raise EntityNotFoundError("User", "")
        userId = asUuid(context.actorId)
        user = self.repository.getById(userId)
        if user is None:
            raise EntityNotFoundError("User", str(userId))
        grants = self.accessRepository.grantsOfUser(userId, user.tenantId)
        from apps.identity.domain.services.permissionEvaluator import PermissionEvaluator

        evaluator = PermissionEvaluator()
        return AccountDto(
            user=userDtoFromDomain(user),
            permissions=evaluator.expandActionCodes(grants),
        )
