"""Identity composition root (Phase 06 §34 + Phase 07 §31 use cases)."""

from __future__ import annotations

from apps.identity.application.useCases.apiKeyUseCases import (
    CreateApiKeyUseCase,
    ListApiKeysUseCase,
    RevokeApiKeyUseCase,
)
from apps.identity.application.useCases.assignUserToTenant import AssignUserToTenantUseCase
from apps.identity.application.useCases.createUser import CreateUserUseCase
from apps.identity.application.useCases.mfaUseCases import (
    ConfirmMfaUseCase,
    DisableMfaUseCase,
    SetupMfaUseCase,
)
from apps.identity.application.useCases.passwordUseCases import (
    ChangePasswordUseCase,
    ConfirmPasswordResetUseCase,
    RequestPasswordResetUseCase,
)
from apps.identity.application.useCases.roleUseCases import (
    AssignRoleUseCase,
    CreateRoleUseCase,
    DeleteRoleUseCase,
    ListRolesUseCase,
    RemoveRoleUseCase,
    UpdateRoleUseCase,
)
from apps.identity.application.useCases.serviceAccountUseCases import (
    CreateServiceAccountUseCase,
    DisableServiceAccountUseCase,
    EnableServiceAccountUseCase,
    ListServiceAccountsUseCase,
)
from apps.identity.application.useCases.sessionUseCases import (
    AuthenticateUserUseCase,
    ListSessionsUseCase,
    LogoutUseCase,
    RefreshSessionUseCase,
    RevokeAllSessionsUseCase,
    RevokeSessionUseCase,
    VerifyMfaChallengeUseCase,
)
from apps.identity.application.useCases.userLifecycleUseCases import ChangeUserStatusUseCase
from apps.identity.application.useCases.userQueryUseCases import (
    GetCurrentAccountUseCase,
    GetUserUseCase,
    ListUsersUseCase,
)
from apps.identity.application.useCases.verificationUseCases import (
    SendVerificationUseCase,
    VerifyChannelUseCase,
)
from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
    AccessRepositoryDjango,
    ApiKeyRepositoryDjango,
    CredentialRepositoryDjango,
    MfaRepositoryDjango,
    RoleRepositoryDjango,
    ServiceAccountRepositoryDjango,
    SessionRepositoryDjango,
    TenantMembershipRepositoryDjango,
    UserRepositoryDjango,
)
from apps.identity.infrastructure.services.passwordHasherImpl import PasswordHasherDjango
from apps.identity.infrastructure.services.securityEvents import SecurityEventRecorderDjango
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


def _tokenIssuer():
    return sharedKernelProvider("tokenIssuer")()


def _secretVault():
    return sharedKernelProvider("secretVault")()


def _securityEvents() -> SecurityEventRecorderDjango:
    return SecurityEventRecorderDjango()


# -- users ---------------------------------------------------------------------


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


def changeUserStatusUseCase() -> ChangeUserStatusUseCase:
    return ChangeUserStatusUseCase(repository=UserRepositoryDjango(), **kernelPorts())


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


# -- authentication & sessions (§7/§10) ------------------------------------------


def authenticateUserUseCase() -> AuthenticateUserUseCase:
    return AuthenticateUserUseCase(
        userRepository=UserRepositoryDjango(),
        sessionRepository=SessionRepositoryDjango(),
        membershipRepository=TenantMembershipRepositoryDjango(),
        mfaRepository=MfaRepositoryDjango(),
        tenantDirectory=defaultTenantDirectory(),
        passwordHasher=PasswordHasherDjango(),
        tokenIssuer=_tokenIssuer(),
        secretVault=_secretVault(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def verifyMfaChallengeUseCase() -> VerifyMfaChallengeUseCase:
    return VerifyMfaChallengeUseCase(
        userRepository=UserRepositoryDjango(),
        sessionRepository=SessionRepositoryDjango(),
        mfaRepository=MfaRepositoryDjango(),
        tokenIssuer=_tokenIssuer(),
        secretVault=_secretVault(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def refreshSessionUseCase() -> RefreshSessionUseCase:
    return RefreshSessionUseCase(
        sessionRepository=SessionRepositoryDjango(),
        userRepository=UserRepositoryDjango(),
        tokenIssuer=_tokenIssuer(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def logoutUseCase() -> LogoutUseCase:
    return LogoutUseCase(
        sessionRepository=SessionRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def listSessionsUseCase() -> ListSessionsUseCase:
    return ListSessionsUseCase(sessionRepository=SessionRepositoryDjango(), **kernelPorts())


def revokeSessionUseCase() -> RevokeSessionUseCase:
    return RevokeSessionUseCase(
        sessionRepository=SessionRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def revokeAllSessionsUseCase() -> RevokeAllSessionsUseCase:
    return RevokeAllSessionsUseCase(
        sessionRepository=SessionRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


# -- passwords & verification (§23/§25/§26) --------------------------------------


def changePasswordUseCase() -> ChangePasswordUseCase:
    return ChangePasswordUseCase(
        userRepository=UserRepositoryDjango(),
        credentialRepository=CredentialRepositoryDjango(),
        sessionRepository=SessionRepositoryDjango(),
        passwordHasher=PasswordHasherDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def requestPasswordResetUseCase() -> RequestPasswordResetUseCase:
    return RequestPasswordResetUseCase(
        userRepository=UserRepositoryDjango(),
        credentialRepository=CredentialRepositoryDjango(),
        tenantDirectory=defaultTenantDirectory(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def confirmPasswordResetUseCase() -> ConfirmPasswordResetUseCase:
    return ConfirmPasswordResetUseCase(
        userRepository=UserRepositoryDjango(),
        credentialRepository=CredentialRepositoryDjango(),
        sessionRepository=SessionRepositoryDjango(),
        passwordHasher=PasswordHasherDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def sendVerificationUseCase() -> SendVerificationUseCase:
    return SendVerificationUseCase(
        userRepository=UserRepositoryDjango(),
        credentialRepository=CredentialRepositoryDjango(),
        **kernelPorts(),
    )


def verifyChannelUseCase() -> VerifyChannelUseCase:
    return VerifyChannelUseCase(
        userRepository=UserRepositoryDjango(),
        credentialRepository=CredentialRepositoryDjango(),
        **kernelPorts(),
    )


# -- RBAC (§14–§17/§28) -----------------------------------------------------------


def createRoleUseCase() -> CreateRoleUseCase:
    return CreateRoleUseCase(
        roleRepository=RoleRepositoryDjango(),
        accessRepository=AccessRepositoryDjango(),
        **kernelPorts(),
    )


def updateRoleUseCase() -> UpdateRoleUseCase:
    return UpdateRoleUseCase(
        roleRepository=RoleRepositoryDjango(),
        accessRepository=AccessRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def deleteRoleUseCase() -> DeleteRoleUseCase:
    return DeleteRoleUseCase(roleRepository=RoleRepositoryDjango(), **kernelPorts())


def assignRoleUseCase() -> AssignRoleUseCase:
    return AssignRoleUseCase(
        roleRepository=RoleRepositoryDjango(),
        accessRepository=AccessRepositoryDjango(),
        userRepository=UserRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def removeRoleUseCase() -> RemoveRoleUseCase:
    return RemoveRoleUseCase(
        roleRepository=RoleRepositoryDjango(),
        accessRepository=AccessRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def listRolesUseCase() -> ListRolesUseCase:
    return ListRolesUseCase(roleRepository=RoleRepositoryDjango(), **kernelPorts())


# -- API keys (§22) -----------------------------------------------------------------


def createApiKeyUseCase() -> CreateApiKeyUseCase:
    return CreateApiKeyUseCase(
        apiKeyRepository=ApiKeyRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def revokeApiKeyUseCase() -> RevokeApiKeyUseCase:
    return RevokeApiKeyUseCase(
        apiKeyRepository=ApiKeyRepositoryDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def listApiKeysUseCase() -> ListApiKeysUseCase:
    return ListApiKeysUseCase(apiKeyRepository=ApiKeyRepositoryDjango(), **kernelPorts())


# -- service accounts (§21) ----------------------------------------------------------


def createServiceAccountUseCase() -> CreateServiceAccountUseCase:
    return CreateServiceAccountUseCase(repository=ServiceAccountRepositoryDjango(), **kernelPorts())


def disableServiceAccountUseCase() -> DisableServiceAccountUseCase:
    return DisableServiceAccountUseCase(
        repository=ServiceAccountRepositoryDjango(), **kernelPorts()
    )


def enableServiceAccountUseCase() -> EnableServiceAccountUseCase:
    return EnableServiceAccountUseCase(repository=ServiceAccountRepositoryDjango(), **kernelPorts())


def listServiceAccountsUseCase() -> ListServiceAccountsUseCase:
    return ListServiceAccountsUseCase(repository=ServiceAccountRepositoryDjango(), **kernelPorts())


# -- MFA (§24) ------------------------------------------------------------------------


def setupMfaUseCase() -> SetupMfaUseCase:
    return SetupMfaUseCase(
        mfaRepository=MfaRepositoryDjango(),
        secretVault=_secretVault(),
        **kernelPorts(),
    )


def confirmMfaUseCase() -> ConfirmMfaUseCase:
    return ConfirmMfaUseCase(
        mfaRepository=MfaRepositoryDjango(),
        secretVault=_secretVault(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )


def disableMfaUseCase() -> DisableMfaUseCase:
    return DisableMfaUseCase(
        mfaRepository=MfaRepositoryDjango(),
        userRepository=UserRepositoryDjango(),
        passwordHasher=PasswordHasherDjango(),
        securityEvents=_securityEvents(),
        **kernelPorts(),
    )
