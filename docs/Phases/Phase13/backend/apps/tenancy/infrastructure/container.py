"""Tenancy composition root (Phase 06 §34).

Presentation asks the container for ready-made use cases; the container is
the ONLY place allowed to assemble repositories with shared-kernel ports.
"""

from __future__ import annotations

from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider
from apps.tenancy.application.useCases.changeTenantStatus import ChangeTenantStatusUseCase
from apps.tenancy.application.useCases.createTenant import CreateTenantUseCase
from apps.tenancy.application.useCases.tenantQueries import (
    GetTenantUseCase,
    ListTenantsUseCase,
)
from apps.tenancy.infrastructure.repositories.tenantRepositoryImpl import (
    TenantRepositoryDjango,
)


def tenantRepository() -> TenantRepositoryDjango:
    return TenantRepositoryDjango()


def createTenantUseCase() -> CreateTenantUseCase:
    return CreateTenantUseCase(
        repository=tenantRepository(),
        unitOfWork=sharedKernelProvider("unitOfWork")(),
        auditRecorder=sharedKernelProvider("auditRecorder")(),
        eventDispatcher=sharedKernelProvider("eventDispatcher")(),
        permissionGate=sharedKernelProvider("permissionGate")(),
        clock=sharedKernelProvider("clock")(),
    )


def getTenantUseCase() -> GetTenantUseCase:
    return GetTenantUseCase(
        repository=tenantRepository(),
        unitOfWork=sharedKernelProvider("unitOfWork")(),
        auditRecorder=sharedKernelProvider("auditRecorder")(),
        eventDispatcher=sharedKernelProvider("eventDispatcher")(),
        permissionGate=sharedKernelProvider("permissionGate")(),
        clock=sharedKernelProvider("clock")(),
    )


def listTenantsUseCase() -> ListTenantsUseCase:
    return ListTenantsUseCase(
        repository=tenantRepository(),
        unitOfWork=sharedKernelProvider("unitOfWork")(),
        auditRecorder=sharedKernelProvider("auditRecorder")(),
        eventDispatcher=sharedKernelProvider("eventDispatcher")(),
        permissionGate=sharedKernelProvider("permissionGate")(),
        clock=sharedKernelProvider("clock")(),
    )


def changeTenantStatusUseCase() -> ChangeTenantStatusUseCase:
    return ChangeTenantStatusUseCase(
        repository=tenantRepository(),
        unitOfWork=sharedKernelProvider("unitOfWork")(),
        auditRecorder=sharedKernelProvider("auditRecorder")(),
        eventDispatcher=sharedKernelProvider("eventDispatcher")(),
        permissionGate=sharedKernelProvider("permissionGate")(),
        clock=sharedKernelProvider("clock")(),
    )
