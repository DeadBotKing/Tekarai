"""MFA use cases (Phase 07 §24, §31) — TOTP enrolment + recovery codes.

The shared secret is generated in the domain, shown to the user ONCE for
authenticator enrolment, and stored only in protected form (SecretVault —
§41 no raw secrets at rest). Recovery codes are hashed, single-use (§24)
and also shown exactly once.
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from apps.identity.application.commands.identityCommands import (
    ConfirmMfaCommand,
    DisableMfaCommand,
    SetupMfaCommand,
)
from apps.identity.application.dto.identityDtos import MfaConfirmedDto, MfaSetupDto
from apps.identity.domain.entities.mfa import MfaFactor
from apps.identity.domain.repositories.identityRepositories import (
    MfaRepository,
    SecurityEventRecorder,
    UserRepository,
)
from apps.identity.domain.services import totpService as TotpService
from apps.identity.domain.services.passwordHasher import PasswordHasher
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    SecretVault,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import (
    AUDIT_UPDATE,
    UseCase,
)
from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    EntityNotFoundError,
    InvalidCredentialsError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

RECOVERY_CODE_COUNT = 8
RECOVERY_CODE_ALPHABET = "ABCDEFGHJKLMNPQRSTUVWXYZ23456789"  # no ambiguities


def hashRecoveryCode(code: str) -> str:
    return hashlib.sha256(code.encode("utf-8")).hexdigest()


class SetupMfaUseCase(UseCase[SetupMfaCommand, MfaSetupDto]):
    """Step 1 (§24): generate secret, keep it PENDING until confirmed."""

    def __init__(
        self,
        mfaRepository: MfaRepository,
        secretVault: SecretVault,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.mfaRepository = mfaRepository
        self.secretVault = secretVault

    def perform(self, command: SetupMfaCommand) -> MfaSetupDto:
        context = currentContext()
        if not context.actorId:
            raise AuthenticationRequiredError()
        userId = uuid.UUID(context.actorId)
        existing = self.mfaRepository.activeFactorOf(userId)
        if existing is not None:
            raise InvalidCredentialsError("MFA is already enabled.")
        secret = TotpService.generateSecret()
        factor = MfaFactor.beginSetup(
            userId=userId,
            factorType=command.factorType,
            secretRef=self.secretVault.protect(secret),  # §41 — protected at rest
            now=self.clock.nowUtc(),
        )
        self.mfaRepository.save(factor)
        self.audit(
            AUDIT_UPDATE,
            resourceType="MfaFactor",
            resourceId=str(factor.id),
            after={"factorType": factor.factorType, "status": "pending"},
        )
        return MfaSetupDto(
            factorId=str(factor.id),
            factorType=factor.factorType,
            secret=secret,  # shown once — authenticator enrolment
            otpauthUrl=TotpService.otpauthUrl(secret, account=userId.hex[:12]),
        )


class ConfirmMfaUseCase(UseCase[ConfirmMfaCommand, MfaConfirmedDto]):
    """Step 2 (§24): verify a live TOTP code, then ACTIVATE + recovery codes."""

    def __init__(
        self,
        mfaRepository: MfaRepository,
        secretVault: SecretVault,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.mfaRepository = mfaRepository
        self.secretVault = secretVault
        self.securityEvents = securityEvents

    def perform(self, command: ConfirmMfaCommand) -> MfaConfirmedDto:
        context = currentContext()
        if not context.actorId:
            raise AuthenticationRequiredError()
        factor = self.mfaRepository.getById(asUuid(command.factorId))
        if factor is None or factor.userId != uuid.UUID(context.actorId):
            raise EntityNotFoundError("MfaFactor", command.factorId)
        if factor.isActive():
            raise InvalidCredentialsError("MFA is already enabled.")
        secret = self.secretVault.reveal(factor.secretRef)
        if not TotpService.verifyCode(secret, command.code.strip()):
            raise InvalidCredentialsError("Invalid TOTP code.")

        now = self.clock.nowUtc()
        factor.confirm(now)
        self.mfaRepository.save(factor)
        self.collectEventsFrom(factor)

        rawCodes = [
            "".join(secrets.choice(RECOVERY_CODE_ALPHABET) for _ in range(10))
            for _ in range(RECOVERY_CODE_COUNT)
        ]
        self.mfaRepository.saveRecoveryCodes(
            factor.userId, [hashRecoveryCode(code) for code in rawCodes]
        )
        self.securityEvents.record("MFA_ENABLED", userId=factor.userId)
        self.audit(
            AUDIT_UPDATE,
            resourceType="MfaFactor",
            resourceId=str(factor.id),
            after={"status": "active", "recoveryCodes": RECOVERY_CODE_COUNT},
        )
        return MfaConfirmedDto(factorId=str(factor.id), recoveryCodes=rawCodes)


class DisableMfaUseCase(UseCase[DisableMfaCommand, object]):
    """§24 — requires the account password; revokes recovery codes too."""

    def __init__(
        self,
        mfaRepository: MfaRepository,
        userRepository: UserRepository,
        passwordHasher: PasswordHasher,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.mfaRepository = mfaRepository
        self.userRepository = userRepository
        self.passwordHasher = passwordHasher
        self.securityEvents = securityEvents

    def perform(self, command: DisableMfaCommand) -> object:
        context = currentContext()
        if not context.actorId:
            raise AuthenticationRequiredError()
        userId = uuid.UUID(context.actorId)
        user = self.userRepository.getById(userId)
        if user is None or not self.passwordHasher.verify(command.password, user.passwordHash):
            raise InvalidCredentialsError("Invalid credentials.")
        factor = self.mfaRepository.activeFactorOf(userId)
        if factor is None:
            raise EntityNotFoundError("MfaFactor", "active")
        factor.disable(self.clock.nowUtc())
        self.mfaRepository.save(factor)
        self.mfaRepository.saveRecoveryCodes(userId, [])  # revoke codes
        self.collectEventsFrom(factor)
        self.securityEvents.record("MFA_DISABLED", userId=userId)
        self.audit(
            AUDIT_UPDATE,
            resourceType="MfaFactor",
            resourceId=str(factor.id),
            after={"status": "disabled"},
        )
        return {"disabled": True}
