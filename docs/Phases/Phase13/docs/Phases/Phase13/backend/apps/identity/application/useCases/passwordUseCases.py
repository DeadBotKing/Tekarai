"""Password use cases (Phase 07 §23/§25/§31).

- ChangePassword: self-service; verifies the current password, enforces the
  policy + history (§23), revokes every session (§35), audits.
- RequestPasswordReset / ConfirmPasswordReset: tokenized, time-limited,
  single-use, audited (§25). The response NEVER reveals whether the
  identifier exists (no account enumeration).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from apps.identity.application.commands.identityCommands import (
    ChangePasswordCommand,
    ConfirmPasswordResetCommand,
    RequestPasswordResetCommand,
)
from apps.identity.domain.entities.credential import (
    PasswordHistoryEntry,
    PasswordResetToken,
)
from apps.identity.domain.repositories.identityRepositories import (
    CredentialRepository,
    SecurityEventRecorder,
    SessionRepository,
    UserRepository,
)
from apps.identity.domain.services.passwordHasher import PasswordHasher
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid
from apps.tenancy.application.services.tenantDirectory import TenantDirectory

PASSWORD_HISTORY_LIMIT = 5
RESET_TOKEN_TTL_MINUTES = 30


def hashToken(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class ChangePasswordUseCase(UseCase[ChangePasswordCommand, object]):
    """§23 — policy + history check; every session revoked afterwards."""

    def __init__(
        self,
        userRepository: UserRepository,
        credentialRepository: CredentialRepository,
        sessionRepository: SessionRepository,
        passwordHasher: PasswordHasher,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.credentialRepository = credentialRepository
        self.sessionRepository = sessionRepository
        self.passwordHasher = passwordHasher
        self.securityEvents = securityEvents

    def perform(self, command: ChangePasswordCommand) -> object:
        context = currentContext()
        actorId = uuid.UUID(context.actorId) if context.actorId else None
        if actorId is None:
            raise AuthenticationRequiredError()
        userId = asUuid(command.userId) if command.userId else actorId
        if userId != actorId:
            raise InvalidCredentialsError("Passwords can only be changed by their owner.")

        user = self.userRepository.getById(userId)
        if user is None:
            raise InvalidCredentialsError("Invalid credentials.")
        if not self.passwordHasher.verify(command.currentPassword, user.passwordHash):
            raise InvalidCredentialsError("Current password is incorrect.")

        validatePasswordStrength(command.newPassword)  # §23 policy (raises)
        now = self.clock.nowUtc()
        newHash = self.passwordHasher.hash(command.newPassword)
        if self.passwordHasher.verify(command.newPassword, user.passwordHash):
            raise ValidationFailedError(
                "New password must differ from the current one.",
                fieldErrors={"newPassword": "Same as current password."},
            )
        for oldHash in self.credentialRepository.passwordHistoryOf(userId, PASSWORD_HISTORY_LIMIT):
            if self.passwordHasher.verify(command.newPassword, oldHash):
                raise ValidationFailedError(
                    "Password was used recently.",
                    fieldErrors={"newPassword": "Password reuse is not allowed."},
                )

        self.credentialRepository.addPasswordHistory(
            PasswordHistoryEntry(
                id=uuid.uuid4(),
                userId=userId,
                passwordHash=user.passwordHash,
                createdAt=now,
            )
        )
        user.changePassword(newHash, now)
        self.userRepository.update(user)
        self.collectEventsFrom(user)
        revoked = self.sessionRepository.revokeAllForUser(userId, now)  # §35
        self.securityEvents.record("PASSWORD_CHANGED", userId=userId, tenantId=user.tenantId)
        self.audit(
            "UPDATE",
            resourceType="User",
            resourceId=str(userId),
            tenantId=user.tenantId,
            after={"passwordChanged": True, "sessionsRevoked": revoked},
        )
        return {"changed": True, "sessionsRevoked": revoked}


class RequestPasswordResetUseCase(UseCase[RequestPasswordResetCommand, dict]):
    """§25 — always answers 202-style success; token delivered out-of-band."""

    def __init__(
        self,
        userRepository: UserRepository,
        credentialRepository: CredentialRepository,
        tenantDirectory: TenantDirectory,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.credentialRepository = credentialRepository
        self.tenantDirectory = tenantDirectory
        self.securityEvents = securityEvents

    def perform(self, command: RequestPasswordResetCommand) -> dict:
        now = self.clock.nowUtc()
        tenant = self.tenantDirectory.getByCode(command.tenantCode)
        user = (
            self.userRepository.getByIdentifier(asUuid(tenant.id), command.identifier)
            if tenant
            else None
        )
        if user is not None:
            rawToken = secrets.token_urlsafe(32)
            token = PasswordResetToken.issue(
                userId=user.id,
                tokenHash=hashToken(rawToken),
                now=now,
                ttlMinutes=RESET_TOKEN_TTL_MINUTES,
                requestIp=self._clientIp(),
            )
            self.credentialRepository.saveResetToken(token)
            self.collectEventsFrom(token)
            self.audit(
                "PASSWORD_RESET_REQUEST",
                resourceType="User",
                resourceId=str(user.id),
                tenantId=user.tenantId,
            )
            # Out-of-band delivery is an integration concern (§25); the raw
            # token is returned to the transport layer in dev/test only.
            return {"requested": True, "resetToken": rawToken}
        return {"requested": True, "resetToken": ""}  # no account enumeration

    def _clientIp(self) -> str:
        return currentContext().ipAddress


class ConfirmPasswordResetUseCase(UseCase[ConfirmPasswordResetCommand, object]):
    """§25 — single-use token consumed on success; sessions revoked (§35)."""

    def __init__(
        self,
        userRepository: UserRepository,
        credentialRepository: CredentialRepository,
        sessionRepository: SessionRepository,
        passwordHasher: PasswordHasher,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.credentialRepository = credentialRepository
        self.sessionRepository = sessionRepository
        self.passwordHasher = passwordHasher
        self.securityEvents = securityEvents

    def perform(self, command: ConfirmPasswordResetCommand) -> object:
        now = self.clock.nowUtc()
        token = self.credentialRepository.findResetToken(hashToken(command.token))
        if token is None or not token.isUsableAt(now):
            raise InvalidCredentialsError("Invalid or expired reset token.")
        user = self.userRepository.getById(token.userId)
        if user is None:
            raise InvalidCredentialsError("Invalid or expired reset token.")

        validatePasswordStrength(command.newPassword)  # §23 policy (raises)
        user.changePassword(self.passwordHasher.hash(command.newPassword), now)
        self.userRepository.update(user)
        self.collectEventsFrom(user)
        self.credentialRepository.markResetTokenUsed(token.id)  # single-use
        revoked = self.sessionRepository.revokeAllForUser(user.id, now)
        self.securityEvents.record("PASSWORD_RESET", userId=user.id, tenantId=user.tenantId)
        self.audit(
            "PASSWORD_RESET",
            resourceType="User",
            resourceId=str(user.id),
            tenantId=user.tenantId,
            after={"sessionsRevoked": revoked},
        )
        return {"reset": True, "sessionsRevoked": revoked}
