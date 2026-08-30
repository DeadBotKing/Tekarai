"""Session use cases: AuthenticateUser (login), RefreshSession, Logout.

Authentication ≠ authorization (§16): login only proves who the caller is;
permissions are evaluated per action elsewhere. Tenant resolution goes
through the Tenancy public contract (TenantDirectory — RULE F).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from apps.identity.application.commands.identityCommands import (
    AuthenticateUserCommand,
    LogoutCommand,
    RefreshSessionCommand,
)
from apps.identity.application.dto.identityDtos import SessionTokenDto, userDtoFromDomain
from apps.identity.domain.entities.session import Session
from apps.identity.domain.repositories.identityRepositories import (
    SessionRepository,
    UserRepository,
)
from apps.identity.domain.services.passwordHasher import PasswordHasher
from apps.sharedKernel.application.ports import (
    AuditRecorder,
    Clock,
    EventDispatcher,
    PermissionGate,
    UnitOfWork,
)
from apps.sharedKernel.application.useCase import (
    AUDIT_LOGIN,
    AUDIT_LOGOUT,
    UseCase,
)
from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    EntityNotFoundError,
    InvalidCredentialsError,
    TenantSuspendedError,
    TokenExpiredError,
)
from apps.sharedKernel.domain.valueObjects import asUuid
from apps.tenancy.application.services.tenantDirectory import TenantDirectory

SESSION_TTL_MINUTES = 480


def hashToken(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generateToken() -> str:
    return secrets.token_urlsafe(32)


class AuthenticateUserUseCase(UseCase[AuthenticateUserCommand, SessionTokenDto]):
    """Login — no authorization step (§16): credentials + tenant state only."""

    def __init__(
        self,
        userRepository: UserRepository,
        sessionRepository: SessionRepository,
        tenantDirectory: TenantDirectory,
        passwordHasher: PasswordHasher,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.sessionRepository = sessionRepository
        self.tenantDirectory = tenantDirectory
        self.passwordHasher = passwordHasher
        self._failedLogin: tuple[str, str] | None = None

    def execute(self, command: AuthenticateUserCommand) -> SessionTokenDto:
        """Failed logins are audited OUTSIDE the rolled-back transaction —
        a security audit must survive the business failure (§19 vs §9)."""
        self._failedLogin = None
        try:
            return super().execute(command)
        except InvalidCredentialsError:
            if self._failedLogin is not None:
                username, tenantId = self._failedLogin
                self.audit(
                    AUDIT_LOGIN,
                    resourceType="Session",
                    resourceId="",
                    tenantId=uuid.UUID(tenantId),
                    after={"outcome": "failure", "username": username},
                )
            raise

    def businessRules(self, command: AuthenticateUserCommand) -> None:
        tenant = self.tenantDirectory.getByCode(command.tenantCode)
        if tenant is None:
            raise InvalidCredentialsError("Invalid credentials.")
        if not tenant.active:
            raise TenantSuspendedError("This tenant is suspended.")

    def perform(self, command: AuthenticateUserCommand) -> SessionTokenDto:
        tenant = self.tenantDirectory.getByCode(command.tenantCode)
        if tenant is None:  # defensive: re-checked inside the transaction
            raise InvalidCredentialsError("Invalid credentials.")
        user = self.userRepository.getByUsername(asUuid(tenant.id), command.username)
        if user is None or not self.passwordHasher.verify(command.password, user.passwordHash):
            self._failedLogin = (command.username, tenant.id)
            raise InvalidCredentialsError("Invalid credentials.")
        if not user.isActive():
            raise InvalidCredentialsError("Account is not active.")
        token = generateToken()
        session = Session.issue(
            userId=user.id,
            tenantId=user.tenantId,
            tokenHash=hashToken(token),
            now=self.clock.nowUtc(),
            ttlMinutes=SESSION_TTL_MINUTES,
        )
        self.sessionRepository.create(session)
        self.collectEventsFrom(session)
        self.audit(
            AUDIT_LOGIN,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=user.tenantId,
            after=session.snapshot(),
        )
        return SessionTokenDto(
            token=token,
            expiresAt=session.expiresAt.isoformat(),
            user=userDtoFromDomain(user),
        )


class RefreshSessionUseCase(UseCase[RefreshSessionCommand, SessionTokenDto]):
    """Token rotation (§16 refresh-token architecture, ADR-019)."""

    def __init__(
        self,
        sessionRepository: SessionRepository,
        userRepository: UserRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.sessionRepository = sessionRepository
        self.userRepository = userRepository

    def perform(self, command: RefreshSessionCommand) -> SessionTokenDto:
        session = self.findSession(command.token)
        now = self.clock.nowUtc()
        if session.isExpiredAt(now):
            raise TokenExpiredError("Session expired.")
        user = self.userRepository.getById(session.userId)
        if user is None or not user.isActive():
            raise AuthenticationRequiredError("Account is not active.")
        session.revoke(now)
        self.sessionRepository.update(session)
        token = generateToken()
        refreshed = Session.issue(
            userId=session.userId,
            tenantId=session.tenantId,
            tokenHash=hashToken(token),
            now=now,
            ttlMinutes=SESSION_TTL_MINUTES,
        )
        self.sessionRepository.create(refreshed)
        self.collectEventsFrom(refreshed)
        self.audit(
            AUDIT_LOGIN,
            resourceType="Session",
            resourceId=str(refreshed.id),
            tenantId=refreshed.tenantId,
            after={"rotatedFrom": str(session.id)},
        )
        return SessionTokenDto(
            token=token,
            expiresAt=refreshed.expiresAt.isoformat(),
            user=userDtoFromDomain(user),
        )

    def findSession(self, token: str) -> Session:
        session = self.sessionRepository.findActiveByTokenHash(hashToken(token))
        if session is None:
            raise InvalidCredentialsError("Invalid session token.")
        return session


class LogoutUseCase(UseCase[LogoutCommand, object]):
    def __init__(
        self,
        sessionRepository: SessionRepository,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.sessionRepository = sessionRepository

    def perform(self, command: LogoutCommand) -> object:
        session = self.sessionRepository.findActiveByTokenHash(hashToken(command.token))
        if session is None:
            raise EntityNotFoundError("Session", "")
        session.revoke(self.clock.nowUtc())
        self.sessionRepository.update(session)
        self.collectEventsFrom(session)
        self.audit(
            AUDIT_LOGOUT,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=session.tenantId,
        )
        return {"revoked": True, "sessionId": str(session.id)}
