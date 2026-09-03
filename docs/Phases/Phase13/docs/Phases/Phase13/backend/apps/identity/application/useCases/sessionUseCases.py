"""Session use cases (Phase 07 §7/§10/§31) — login, MFA challenge, refresh
rotation, logout, session listing and revocation.

Login (§10) = credential check + status check + tenant resolution + rate
limit (middleware) + brute-force lock + audit + session. The issued pair is
a short-lived JWT access token plus an opaque rotating refresh token whose
SHA-256 hash is the session row's identity (ADR-022). JWT is never the sole
session mechanism — every verified access token re-checks the Session row
(§7; invariants §35.4/5).
"""

from __future__ import annotations

import hashlib
import secrets
import uuid

from apps.identity.application.commands.identityCommands import (
    AuthenticateUserCommand,
    LogoutCommand,
    RefreshSessionCommand,
    RevokeAllSessionsCommand,
    RevokeSessionCommand,
    VerifyMfaChallengeCommand,
)
from apps.identity.application.dto.identityDtos import (
    AuthTokenDto,
    SessionDto,
    userDtoFromDomain,
)
from apps.identity.application.queries.identityQueries import ListSessionsQuery
from apps.identity.domain.entities.session import Session
from apps.identity.domain.policies.resourcePolicies import POLICIES
from apps.identity.domain.repositories.identityRepositories import (
    MfaRepository,
    SecurityEventRecorder,
    SessionRepository,
    TenantMembershipRepository,
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
    TokenIssuer,
    UnitOfWork,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import (
    AUDIT_LOGIN,
    AUDIT_LOGOUT,
    UseCase,
)
from apps.sharedKernel.domain.errors import (
    AuthenticationRequiredError,
    EntityNotFoundError,
    InvalidCredentialsError,
    PermissionDeniedError,
    TenantAccessDeniedError,
    TenantSuspendedError,
    TokenExpiredError,
)
from apps.sharedKernel.domain.valueObjects import asUuid
from apps.tenancy.application.services.tenantDirectory import TenantDirectory

SESSION_TTL_MINUTES = 480  # refresh-token lifetime; access JWT is §8-short
MAX_FAILED_LOGINS = 5
LOCK_MINUTES = 15
RECOVERY_CODE_COUNT = 8


def hashToken(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def generateRefreshToken() -> str:
    return secrets.token_urlsafe(48)


class AuthenticateUserUseCase(UseCase[AuthenticateUserCommand, AuthTokenDto]):
    """Login — no permission step (§20): authentication only."""

    def __init__(
        self,
        userRepository: UserRepository,
        sessionRepository: SessionRepository,
        membershipRepository: TenantMembershipRepository,
        mfaRepository: MfaRepository,
        tenantDirectory: TenantDirectory,
        passwordHasher: PasswordHasher,
        tokenIssuer: TokenIssuer,
        secretVault: SecretVault,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.sessionRepository = sessionRepository
        self.membershipRepository = membershipRepository
        self.mfaRepository = mfaRepository
        self.tenantDirectory = tenantDirectory
        self.passwordHasher = passwordHasher
        self.tokenIssuer = tokenIssuer
        self.secretVault = secretVault
        self.securityEvents = securityEvents
        self._failure: tuple[str, str] | None = None

    def execute(self, command: AuthenticateUserCommand) -> AuthTokenDto:
        """Failed logins are counted, locked, audited and security-logged
        OUTSIDE the rolled-back transaction — the §10 counter must survive
        the business failure (§19 vs §9)."""
        self._failure = None
        try:
            return super().execute(command)
        except (InvalidCredentialsError, AuthenticationRequiredError) as exc:
            self._registerFailure(command)
            raise exc

    def _registerFailure(self, command: AuthenticateUserCommand) -> None:
        """Post-rollback: bump the failure counter, maybe lock (§10), audit."""
        tenant = self.tenantDirectory.getByCode(command.tenantCode)
        if tenant is None:
            return
        tenantId = asUuid(tenant.id)
        user = self.userRepository.getByIdentifier(tenantId, command.identifier)
        userId = user.id if user is not None else None
        locked = False
        if user is not None:
            locked = user.registerFailedLogin(
                self.clock.nowUtc(),
                maxFailedAttempts=MAX_FAILED_LOGINS,
                lockMinutes=LOCK_MINUTES,
            )
            self.userRepository.update(user)
        self.securityEvents.record(
            "LOGIN_FAILED",
            userId=userId,
            tenantId=tenantId,
            result="failure",
            reason=command.identifier[:120],
        )
        if locked:
            self.securityEvents.record(
                "ACCOUNT_LOCKED",
                userId=userId,
                tenantId=tenantId,
                reason="Too many failed logins.",
            )
        self.audit(
            AUDIT_LOGIN,
            resourceType="Session",
            resourceId="",
            tenantId=tenantId,
            after={
                "outcome": "failure",
                "identifier": command.identifier[:120],
                "locked": locked,
            },
        )

    def businessRules(self, command: AuthenticateUserCommand) -> None:
        tenant = self.tenantDirectory.getByCode(command.tenantCode)
        if tenant is None:
            raise InvalidCredentialsError("Invalid credentials.")
        if not tenant.active:
            raise TenantSuspendedError("This tenant is suspended.")

    def perform(self, command: AuthenticateUserCommand) -> AuthTokenDto:
        from apps.identity.domain.valueObjects.userState import effectiveStatusOf

        now = self.clock.nowUtc()
        tenant = self.tenantDirectory.getByCode(command.tenantCode)
        if tenant is None:  # re-checked inside the transaction
            raise InvalidCredentialsError("Invalid credentials.")
        tenantId = asUuid(tenant.id)

        user = self.userRepository.getByIdentifier(tenantId, command.identifier)
        if user is None or not self.passwordHasher.verify(command.password, user.passwordHash):
            # Failure counting happens post-rollback in _registerFailure (§10).
            raise InvalidCredentialsError("Invalid credentials.")  # no user reveal

        if user.isLockedAt(now):
            self._failure = (user.username, tenant.id)
            raise AuthenticationRequiredError("Account temporarily locked.")
        effective = effectiveStatusOf(
            str(user.status), lockedUntil=user.lockedUntil, expiresAt=user.expiresAt, now=now
        )
        if str(effective).lower() != "active":
            self._failure = (user.username, tenant.id)
            raise AuthenticationRequiredError("Account is not active.")  # §35.7

        if not self.membershipRepository.existsActive(user.id, tenantId):
            raise TenantAccessDeniedError("No active membership in this tenant.")

        user.registerSuccessfulLogin(now)
        self.userRepository.update(user)

        mfaFactor = self.mfaRepository.activeFactorOf(user.id)
        if mfaFactor is not None:
            return self._startMfaChallenge(user, tenantId, mfaFactor, command, now)
        return self._openSession(user, tenantId, command, now)

    # -- helpers --------------------------------------------------------------

    def _startMfaChallenge(self, user, tenantId: uuid.UUID, factor, command, now) -> AuthTokenDto:
        challenge = self.tokenIssuer.issueMfaChallenge(
            userId=user.id, tenantId=tenantId, sessionId=uuid.uuid4()
        )
        return AuthTokenDto(
            accessToken="",
            refreshToken="",
            expiresAt="",
            user=userDtoFromDomain(user),
            mfaRequired=True,
            mfaChallenge=challenge,
        )

    def _openSession(self, user, tenantId: uuid.UUID, command, now) -> AuthTokenDto:
        refreshToken = generateRefreshToken()
        session = Session.start(
            userId=user.id,
            tenantId=tenantId,
            refreshTokenHash=hashToken(refreshToken),
            now=now,
            ttlMinutes=SESSION_TTL_MINUTES,
            ipAddress=command.ipAddress,
            userAgent=command.userAgent,
            device=command.device,
        )
        self.sessionRepository.create(session)
        self.collectEventsFrom(session)
        accessToken, ttlSeconds = self.tokenIssuer.issueAccessToken(
            userId=user.id, tenantId=tenantId, sessionId=session.id
        )
        self.securityEvents.record(
            "LOGIN_SUCCESS", userId=user.id, tenantId=tenantId, sessionId=session.id
        )
        self.audit(
            AUDIT_LOGIN,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=tenantId,
            after={"ip": command.ipAddress, "device": command.device},
        )
        return AuthTokenDto(
            accessToken=accessToken,
            refreshToken=refreshToken,
            expiresIn=ttlSeconds,
            expiresAt=session.expiresAt.isoformat(),
            user=userDtoFromDomain(user),
        )


class VerifyMfaChallengeUseCase(UseCase[VerifyMfaChallengeCommand, AuthTokenDto]):
    """Second factor (§24): TOTP code or single-use recovery code → tokens."""

    def __init__(
        self,
        userRepository: UserRepository,
        sessionRepository: SessionRepository,
        mfaRepository: MfaRepository,
        tokenIssuer: TokenIssuer,
        secretVault: SecretVault,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.userRepository = userRepository
        self.sessionRepository = sessionRepository
        self.mfaRepository = mfaRepository
        self.tokenIssuer = tokenIssuer
        self.secretVault = secretVault
        self.securityEvents = securityEvents

    def perform(self, command: VerifyMfaChallengeCommand) -> AuthTokenDto:
        now = self.clock.nowUtc()
        claims = self.tokenIssuer.verifyMfaChallenge(command.challengeToken)
        user = self.userRepository.getById(uuid.UUID(claims["sub"]))
        if user is None or not user.isActive():
            raise AuthenticationRequiredError("Account is not active.")
        factor = self.mfaRepository.activeFactorOf(user.id)
        if factor is None:
            raise AuthenticationRequiredError("No active MFA factor.")
        code = command.code.strip().replace("-", "")
        secret = self.secretVault.reveal(factor.secretRef)
        totpOk = TotpService.verifyCode(secret, code)
        recoveryOk = False
        if not totpOk and len(code) == 10:
            recoveryOk = self.mfaRepository.consumeRecoveryCode(user.id, hashToken(code))
        if not (totpOk or recoveryOk):
            self.securityEvents.record(
                "LOGIN_FAILED",
                userId=user.id,
                tenantId=user.tenantId,
                result="failure",
                reason="mfa_code_invalid",
            )
            raise InvalidCredentialsError("Invalid MFA code.")

        refreshToken = generateRefreshToken()
        session = Session.start(
            userId=user.id,
            tenantId=user.tenantId,
            refreshTokenHash=hashToken(refreshToken),
            now=now,
            ttlMinutes=SESSION_TTL_MINUTES,
        )
        self.sessionRepository.create(session)
        self.collectEventsFrom(session)
        accessToken, ttlSeconds = self.tokenIssuer.issueAccessToken(
            userId=user.id, tenantId=user.tenantId, sessionId=session.id
        )
        self.securityEvents.record(
            "LOGIN_SUCCESS", userId=user.id, tenantId=user.tenantId, sessionId=session.id
        )
        self.audit(
            AUDIT_LOGIN,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=user.tenantId,
            after={"mfa": factor.factorType, "recoveryCode": recoveryOk},
        )
        return AuthTokenDto(
            accessToken=accessToken,
            refreshToken=refreshToken,
            expiresIn=ttlSeconds,
            expiresAt=session.expiresAt.isoformat(),
            user=userDtoFromDomain(user),
        )


class RefreshSessionUseCase(UseCase[RefreshSessionCommand, AuthTokenDto]):
    """Refresh rotation (§7/§31): new refresh hash replaces the old one on
    the SAME session row; the old refresh token becomes worthless."""

    def __init__(
        self,
        sessionRepository: SessionRepository,
        userRepository: UserRepository,
        tokenIssuer: TokenIssuer,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.sessionRepository = sessionRepository
        self.userRepository = userRepository
        self.tokenIssuer = tokenIssuer
        self.securityEvents = securityEvents

    def perform(self, command: RefreshSessionCommand) -> AuthTokenDto:
        session = self.sessionRepository.findActiveByRefreshHash(hashToken(command.refreshToken))
        if session is None:
            raise InvalidCredentialsError("Invalid refresh token.")  # §35.4
        now = self.clock.nowUtc()
        if session.isExpiredAt(now):
            raise TokenExpiredError("Session expired.")  # §35.5
        user = self.userRepository.getById(session.userId)
        if user is None or not user.isActive():
            raise AuthenticationRequiredError("Account is not active.")

        newRefreshToken = generateRefreshToken()
        session.rotateRefreshToken(hashToken(newRefreshToken), now)
        session.touch(now)
        self.sessionRepository.update(session)
        accessToken, ttlSeconds = self.tokenIssuer.issueAccessToken(
            userId=user.id, tenantId=session.tenantId, sessionId=session.id
        )
        self.audit(
            AUDIT_LOGIN,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=session.tenantId,
            after={"rotated": True},
        )
        return AuthTokenDto(
            accessToken=accessToken,
            refreshToken=newRefreshToken,
            expiresIn=ttlSeconds,
            expiresAt=session.expiresAt.isoformat(),
            user=userDtoFromDomain(user),
        )


class LogoutUseCase(UseCase[LogoutCommand, object]):
    """Revoke the session backing this refresh token (§7)."""

    def __init__(
        self,
        sessionRepository: SessionRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.sessionRepository = sessionRepository
        self.securityEvents = securityEvents

    def perform(self, command: LogoutCommand) -> object:
        session = self.sessionRepository.findActiveByRefreshHash(hashToken(command.refreshToken))
        if session is None:
            raise EntityNotFoundError("Session", "")
        session.revoke(self.clock.nowUtc())
        self.sessionRepository.update(session)
        self.collectEventsFrom(session)
        self.securityEvents.record(
            "SESSION_REVOKED",
            userId=session.userId,
            tenantId=session.tenantId,
            sessionId=session.id,
            reason="logout",
        )
        self.audit(
            AUDIT_LOGOUT,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=session.tenantId,
        )
        return {"revoked": True, "sessionId": str(session.id)}


class ListSessionsUseCase(UseCase[ListSessionsQuery, list[SessionDto]]):
    """§9 — a user can list their active sessions."""

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

    def perform(self, query: ListSessionsQuery) -> list[SessionDto]:
        context = currentContext()
        actorId = uuid.UUID(context.actorId) if context.actorId else None
        if actorId is None:
            raise AuthenticationRequiredError()
        targetUserId = asUuid(query.userId) if query.userId else actorId
        actorTenant = uuid.UUID(context.actorTenantId) if context.actorTenantId else None
        if targetUserId != actorId and not self.permissionGate.hasPermission(
            actorId, "audit.view", tenantId=actorTenant
        ):
            raise PermissionDeniedError(action="audit.view")  # §19 SessionPolicy
        sessions = self.sessionRepository.listActiveForUser(targetUserId)
        currentSessionId = context.sessionId
        return [
            SessionDto(
                id=str(s.id),
                userId=str(s.userId),
                issuedAt=s.issuedAt.isoformat(),
                lastActivityAt=(s.lastActivityAt or s.issuedAt).isoformat(),
                expiresAt=s.expiresAt.isoformat(),
                status=s.statusAt(self.clock.nowUtc()),
                ipAddress=s.ipAddress,
                userAgent=s.userAgent,
                device=s.device,
                current=str(s.id) == currentSessionId,
            )
            for s in sessions
        ]


class RevokeSessionUseCase(UseCase[RevokeSessionCommand, object]):
    """§9 — revoke one of your sessions (or another user's with audit.view)."""

    def __init__(
        self,
        sessionRepository: SessionRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.sessionRepository = sessionRepository
        self.securityEvents = securityEvents

    def perform(self, command: RevokeSessionCommand) -> object:
        context = currentContext()
        actorId = uuid.UUID(context.actorId) if context.actorId else None
        if actorId is None:
            raise AuthenticationRequiredError()
        session = self.sessionRepository.getById(asUuid(command.sessionId))
        if session is None:
            raise EntityNotFoundError("Session", command.sessionId)
        policy = POLICIES["Session"]
        request = self._request(session, actorId, command)
        if not policy.canUpdate(request, session):
            raise PermissionDeniedError(action="session.revoke")
        session.revoke(self.clock.nowUtc())
        self.sessionRepository.update(session)
        self.collectEventsFrom(session)
        self.securityEvents.record(
            "SESSION_REVOKED",
            userId=session.userId,
            tenantId=session.tenantId,
            sessionId=session.id,
            reason="revoked_by_user",
        )
        self.audit(
            AUDIT_LOGOUT,
            resourceType="Session",
            resourceId=str(session.id),
            tenantId=session.tenantId,
        )
        return {"revoked": True, "sessionId": str(session.id)}

    def _request(self, session: Session, actorId: uuid.UUID, command):
        from apps.identity.domain.policies.resourcePolicies import AccessRequest

        context = currentContext()
        return AccessRequest(
            actorId=actorId,
            tenantId=session.tenantId,
            isGlobalScope=self.permissionGate.hasPermission(
                actorId,
                "tenant.list",
                tenantId=uuid.UUID(context.actorTenantId) if context.actorTenantId else None,
            ),
            actions=frozenset({"session.revoke"}),
        )


class RevokeAllSessionsUseCase(UseCase[RevokeAllSessionsCommand, object]):
    """Logout everywhere (§9/§31) — revoke every active session of a user."""

    def __init__(
        self,
        sessionRepository: SessionRepository,
        securityEvents: SecurityEventRecorder,
        unitOfWork: UnitOfWork,
        auditRecorder: AuditRecorder,
        eventDispatcher: EventDispatcher,
        permissionGate: PermissionGate,
        clock: Clock,
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.sessionRepository = sessionRepository
        self.securityEvents = securityEvents

    def perform(self, command: RevokeAllSessionsCommand) -> object:
        context = currentContext()
        actorId = uuid.UUID(context.actorId) if context.actorId else None
        if actorId is None:
            raise AuthenticationRequiredError()
        targetUserId = asUuid(command.userId) if command.userId else actorId
        if targetUserId != actorId and not self.permissionGate.hasPermission(
            actorId,
            "audit.view",
            tenantId=uuid.UUID(context.actorTenantId) if context.actorTenantId else None,
        ):
            raise PermissionDeniedError(action="audit.view")
        count = self.sessionRepository.revokeAllForUser(targetUserId, self.clock.nowUtc())
        self.securityEvents.record(
            "SESSION_REVOKED",
            userId=targetUserId,
            result="success",
            reason=f"logout_all:{count}",
        )
        self.audit(
            AUDIT_LOGOUT,
            resourceType="Session",
            resourceId=str(targetUserId),
            after={"revokedCount": count},
        )
        return {"revoked": True, "sessionsRevoked": count}
