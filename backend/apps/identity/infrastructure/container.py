"""Identity composition root (§34)."""

from __future__ import annotations

from apps.identity.application.useCases.assignUserToTenant import AssignUserToTenantUseCase
from apps.identity.application.useCases.createUser import CreateUserUseCase
from apps.identity.application.useCases.sessionUseCases import (
    AuthenticateUserUseCase,
    LogoutUseCase,
    RefreshSessionUseCase,
)
from apps.identity.application.useCases.userQueryUseCases import (
    GetCurrentAccountUseCase,
    GetUserUseCase,
    ListUsersUseCase,
)
from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
    AccessRepositoryDjango,
    SessionRepositoryDjango,
    TenantMembershipRepositoryDjango,
    UserRepositoryDjango,
)
from apps.identity.infrastructure.services.passwordHasherImpl import PasswordHasherDjango
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider
from apps.tenancy.application.services.tenantDirectory import defaultTenantDirectory


def kernelPorts() -> dict:
    return {
        "unitOfWork": sharedKernelProvider("unitOfWork")(),
        "auditRecorder": sharedKernelProvider("auditRecorder")(),
        "eventDispatcher": sharedKernelProvider("eventDispatcher")(),
        "permissionGate": sharedKernelProvider("permissionGate")(),
        "clock": sharedKernelProvider("clock")(),
    }


def createUserUseCase() -> CreateUserUseCase:
    return CreateUserUseCase(
        repository=UserRepositoryDjango(),
        passwordHasher=PasswordHasherDjango(),
        **kernelPorts(),
    )


def assignUserToTenantUseCase() -> AssignUserToTenantUseCase:
    return AssignUserToTenantUseCase(
        userRepository=UserRepositoryDjango(),
        membershipRepository=TenantMembershipRepositoryDjango(),
        **kernelPorts(),
    )


def authenticateUserUseCase() -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(
        userRepository=UserRepositoryDjango(),
        sessionRepository=SessionRepositoryDjango(),
        tenantDirectory=defaultTenantDirectory(),
        passwordHasher=PasswordHasherDjango(),
        **kernelPorts(),
    )


def refreshSessionUseCase() -> RefreshSessionUseCase:
    return RefreshSessionUseCase(
        sessionRepository=SessionRepositoryDjango(),
        userRepository=UserRepositoryDjango(),
        **kernelPorts(),
    )


def logoutUseCase() -> LogoutUseCase:
    return LogoutUseCase(
        sessionRepository=SessionRepositoryDjango(),
        **kernelPorts(),
    )


def getUserUseCase() -> GetUserUseCase:
    return GetUserUseCase(repository=UserRepositoryDjango(), **kernelPorts())


def listUsersUseCase() -> ListUsersUseCase:
    return ListUsersUseCase(repository=UserRepositoryDjango(), **kernelPorts())


def getCurrentAccountUseCase() -> GetCurrentAccountUseCase:
    return GetCurrentAccountUseCase(
        repository=UserRepositoryDjango(),
        accessRepository=AccessRepositoryDjango(),
        **kernelPorts(),
    )
