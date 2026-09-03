"""Tenant read use cases (§6): GetTenant, ListTenants.

Queries never mutate; authorization still applies (§44) — ``tenant.list``
is platform-scope; members read their own tenant through GetTenant with a
tenant-boundary check.
"""

from __future__ import annotations

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
from apps.tenancy.application.dto.tenantDtos import TenantPageDto, tenantDtoFromDomain
from apps.tenancy.application.queries.tenantQueries import (
    GetTenantQuery,
    ListTenantsQuery,
)
from apps.tenancy.domain.repositories.tenantRepository import (
    TenantFilters,
    TenantRepository,
)


class GetTenantUseCase(UseCase[GetTenantQuery, object]):
    requiredAction = "tenant.view"

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

    def perform(self, query: GetTenantQuery) -> object:
        tenantId = asUuid(query.tenantId)
        tenant = self.repository.getById(tenantId)
        if tenant is None:
            raise EntityNotFoundError("Tenant", query.tenantId)
        # Object-level tenant boundary (§44 layer six): members see their own
        # tenant; GLOBAL scope (platform admin) sees any.
        context = currentContext()
        if context.actorTenantId and str(tenantId) != context.actorTenantId:
            actorTenant = self.repository.getById(asUuid(context.actorTenantId))
            allowed = self.permissionGate.hasPermission(
                asUuid(context.actorId),
                "tenant.list",
                tenantId=asUuid(context.actorTenantId),
            )
            if not allowed or actorTenant is None:
                raise TenantAccessDeniedError()
        return tenantDtoFromDomain(tenant)


class ListTenantsUseCase(UseCase[ListTenantsQuery, TenantPageDto]):
    requiredAction = "tenant.list"  # platform-scope action

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

    def perform(self, query: ListTenantsQuery) -> TenantPageDto:
        page = self.repository.list(
            TenantFilters(
                status=query.status,
                search=query.search,
                ordering=query.ordering,
                page=max(1, query.page),
                pageSize=min(100, max(1, query.pageSize)),
            )
        )
        return TenantPageDto(
            items=[tenantDtoFromDomain(tenant) for tenant in page.items],
            totalCount=page.totalCount,
            page=max(1, query.page),
            pageSize=min(100, max(1, query.pageSize)),
        )
