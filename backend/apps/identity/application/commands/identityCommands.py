"""Identity commands (Phase 06 §5 + Phase 07 §31 use-case inventory)."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class CreateUserCommand(Command):
    tenantId: str
    username: str
    email: str
    password: str
    displayName: str = ""


@dataclass(frozen=True)
class AssignUserToTenantCommand(Command):
    userId: str
    targetTenantId: str


@dataclass(frozen=True)
class AuthenticateUserCommand(Command):
    tenantCode: str
    identifier: str  # username OR email (§4)
    password: str
    ipAddress: str = ""
    userAgent: str = ""
    device: str = ""


@dataclass(frozen=True)
class VerifyMfaChallengeCommand(Command):
    challengeToken: str
    code: str


@dataclass(frozen=True)
class RefreshSessionCommand(Command):
    refreshToken: str


@dataclass(frozen=True)
class LogoutCommand(Command):
    refreshToken: str


@dataclass(frozen=True)
class ChangeUserStatusCommand(Command):
    userId: str
    target: str


@dataclass(frozen=True)
class ChangePasswordCommand(Command):
    currentPassword: str
    newPassword: str
    userId: str = ""  # self when empty (§23)


@dataclass(frozen=True)
class RequestPasswordResetCommand(Command):
    tenantCode: str
    identifier: str


@dataclass(frozen=True)
class ConfirmPasswordResetCommand(Command):
    token: str
    newPassword: str


@dataclass(frozen=True)
class VerifyEmailCommand(Command):
    token: str


@dataclass(frozen=True)
class VerifyPhoneCommand(Command):
    token: str


@dataclass(frozen=True)
class SendVerificationCommand(Command):
    userId: str
    channel: str  # email | phone (§26)


@dataclass(frozen=True)
class CreateRoleCommand(Command):
    code: str
    name: str
    scopeType: str = "TENANT"
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class UpdateRoleCommand(Command):
    roleId: str
    name: str = ""
    actions: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DeleteRoleCommand(Command):
    roleId: str


@dataclass(frozen=True)
class AssignRoleCommand(Command):
    userId: str
    roleId: str
    tenantId: str = ""


@dataclass(frozen=True)
class RemoveRoleCommand(Command):
    userId: str
    roleId: str


@dataclass(frozen=True)
class CreateApiKeyCommand(Command):
    tenantId: str
    name: str
    ownerType: str = "user"  # user | serviceAccount (§21)
    ownerId: str = ""
    scopes: list[str] = field(default_factory=list)
    expiresAt: str = ""


@dataclass(frozen=True)
class RevokeApiKeyCommand(Command):
    apiKeyId: str


@dataclass(frozen=True)
class CreateServiceAccountCommand(Command):
    tenantId: str
    code: str
    name: str
    description: str = ""
    scopes: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class DisableServiceAccountCommand(Command):
    accountId: str


@dataclass(frozen=True)
class EnableServiceAccountCommand(Command):
    accountId: str


@dataclass(frozen=True)
class SetupMfaCommand(Command):
    factorType: str = "totp"


@dataclass(frozen=True)
class ConfirmMfaCommand(Command):
    factorId: str
    code: str


@dataclass(frozen=True)
class DisableMfaCommand(Command):
    password: str


@dataclass(frozen=True)
class RevokeSessionCommand(Command):
    sessionId: str
    userId: str = ""  # target user for admin revocation; self when empty


@dataclass(frozen=True)
class RevokeAllSessionsCommand(Command):
    userId: str = ""  # logout-everywhere; self when empty
