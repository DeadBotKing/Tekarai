"""Email/phone verification use cases (Phase 07 §26, §31).

Verification is SEPARATE from password reset (§26): channel-scoped
single-use tokens with limited attempts. Token generation is admin/self
triggered (SendVerification); the raw token goes out-of-band.
"""

from __future__ import annotations

import hashlib
import secrets

from apps.identity.application.commands.identityCommands import (
    SendVerificationCommand,
    VerifyEmailCommand,
    VerifyPhoneCommand,
)
from apps.identity.domain.entities.credential import VerificationToken
from apps.identity.domain.repositories.identityRepositories import (
    CredentialRepository,
    UserRepository,
)
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import UseCase
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    InvalidCredentialsError,
)
from apps.sharedKernel.domain.valueObjects import asUuid

VERIFICATION_TTL_MINUTES = 60
MAX_TOKEN_ATTEMPTS = 5


def hashToken(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class SendVerificationUseCase(UseCase[SendVerificationCommand, object]):
    """Issue a channel verification token (§26)."""

    def __init__(
        self,
        userRepository: UserRepository,
        credentialRepository: CredentialRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.credentialRepository = credentialRepository

    def perform(self, command: SendVerificationCommand) -> object:
        user = self.userRepository.getById(asUuid(command.userId))
        if user is None:
            raise EntityNotFoundError("User", command.userId)
        destination = user.email if command.channel == "email" else (user.phone or "")
        rawToken = secrets.token_urlsafe(24)
        token = VerificationToken.issue(
            userId=user.id,
            channel=command.channel,
            destination=destination,
            tokenHash=hashToken(rawToken),
            now=self.clock.nowUtc(),
            ttlMinutes=VERIFICATION_TTL_MINUTES,
        )
        self.credentialRepository.saveVerificationToken(token)
        self.collectEventsFrom(token)
        self.audit(
            "VERIFICATION_SENT",
            resourceType="User",
            resourceId=str(user.id),
            tenantId=user.tenantId,
            after={"channel": command.channel},
        )
        # Raw token leaves the system out-of-band; returned for dev/test only.
        return {"sent": True, "channel": command.channel, "token": rawToken}


class VerifyChannelUseCase(UseCase[VerifyEmailCommand | VerifyPhoneCommand, object]):
    """Consume a verification token: single-use, TTL, attempt-capped (§26)."""

    def __init__(
        self,
        userRepository: UserRepository,
        credentialRepository: CredentialRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.credentialRepository = credentialRepository

    def perform(self, command: VerifyEmailCommand | VerifyPhoneCommand) -> object:
        channel = "email" if isinstance(command, VerifyEmailCommand) else "phone"
        now = self.clock.nowUtc()
        token = self.credentialRepository.findVerificationToken(hashToken(command.token))
        if token is None or token.channel != channel:
            raise InvalidCredentialsError("Invalid verification token.")
        if token.isUsed():
            raise InvalidCredentialsError("Verification token already used.")
        if token.isExpiredAt(now):
            raise InvalidCredentialsError("Verification token expired.")
        if token.attemptCount >= MAX_TOKEN_ATTEMPTS:
            raise InvalidCredentialsError("Too many attempts.")
        self.credentialRepository.registerVerificationAttempt(token.id)
        user = self.userRepository.getById(token.userId)
        if user is None:
            raise InvalidCredentialsError("Invalid verification token.")
        # Possession of the raw token IS the proof; consume it (single-use).
        token.markVerified(now)
        self.credentialRepository.markVerificationTokenVerified(token.id)
        self.audit(
            "VERIFIED",
            resourceType="User",
            resourceId=str(user.id),
            tenantId=user.tenantId,
            after={"channel": channel},
        )
        return {"verified": True, "channel": channel}
