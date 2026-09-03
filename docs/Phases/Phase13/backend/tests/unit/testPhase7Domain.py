"""Phase 7 unit tests — domain layer (state machines, TOTP, policies, JWT)."""

from __future__ import annotations

import time
import uuid
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from apps.identity.domain.entities.apiKey import ApiKey
from apps.identity.domain.entities.mfa import MfaFactor
from apps.identity.domain.entities.serviceAccount import ServiceAccount
from apps.identity.domain.entities.session import Session
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.entities.user import User
from apps.identity.domain.policies.resourcePolicies import POLICIES, AccessRequest
from apps.identity.domain.services import totpService
from apps.identity.domain.valueObjects.userState import (
    LOCKABLE_STATUSES,
    effectiveStatusOf,
    validatePasswordStrength,
)
from apps.sharedKernel.domain.errors import (
    InvalidStateTransitionError,
    ValidationFailedError,
)

NOW = datetime(2026, 1, 1, tzinfo=UTC)


class UserStateMachineTests(SimpleTestCase):
    def build(self, status: str = "invited") -> User:
        user = User.register(uuid.uuid4(), "sara", "s@a.com", "h", "S", NOW, status=status)
        user.pullEvents()
        return user

    def testInvitedCanGoPendingActiveSuspendedDisabled(self) -> None:
        for target in ("pendingActivation", "active", "suspended", "disabled"):
            self.build().transitionTo(target, NOW)  # all legal from INVITED

    def testPendingActivationCannotSuspend(self) -> None:
        user = self.build("pendingActivation")
        with self.assertRaises(InvalidStateTransitionError):
            user.transitionTo("suspended", NOW)

    def testSuspendedReactivatesOrDisables(self) -> None:
        user = self.build("suspended")
        user.transitionTo("active", NOW)
        user.transitionTo("suspended", NOW)
        user.transitionTo("disabled", NOW)

    def testDisabledIsTerminal(self) -> None:
        user = self.build("disabled")
        with self.assertRaises(InvalidStateTransitionError):
            user.transitionTo("active", NOW)

    def testActivationEventEmitted(self) -> None:
        user = self.build()
        user.transitionTo("active", NOW)
        self.assertEqual(user.pullEvents()[-1].name, "userActivated")

    def testLockOverlayAndRecovery(self) -> None:
        user = self.build("active")
        locked = user.registerFailedLogin(NOW, maxFailedAttempts=3, lockMinutes=15)
        self.assertFalse(locked)
        locked = user.registerFailedLogin(NOW, maxFailedAttempts=3, lockMinutes=15)
        self.assertFalse(locked)
        locked = user.registerFailedLogin(NOW, maxFailedAttempts=3, lockMinutes=15)
        self.assertTrue(locked, "third failure trips the lock (§10)")
        self.assertEqual(
            effectiveStatusOf("active", lockedUntil=user.lockedUntil, now=NOW),
            "locked",
        )
        self.assertEqual(
            effectiveStatusOf(
                "active", lockedUntil=user.lockedUntil, now=NOW + timedelta(minutes=16)
            ),
            "active",
            "lock expires by itself (§3 temporal overlay)",
        )
        events = [e.name for e in user.pullEvents()]
        self.assertIn("accountLocked", events)
        self.assertIn("active", LOCKABLE_STATUSES)

    def testExpiryOverlay(self) -> None:
        expires = NOW - timedelta(days=1)
        self.assertEqual(effectiveStatusOf("active", expiresAt=expires, now=NOW), "expired")

    def testPasswordPolicyConfigurable(self) -> None:
        with self.assertRaises(ValidationFailedError):
            validatePasswordStrength("short!")
        with self.assertRaises(ValidationFailedError):
            validatePasswordStrength("onlyletters123")
        self.assertEqual(
            validatePasswordStrength("abc", minLength=3, requireComplexity=False), "abc"
        )


class MembershipStateMachineTests(SimpleTestCase):
    def testSuspendReactivateRemove(self) -> None:
        membership = TenantMembership.establish(uuid.uuid4(), uuid.uuid4(), NOW)
        self.assertTrue(membership.isActive())
        membership.suspend(NOW)
        self.assertTrue(membership.isSuspended())
        membership.reactivate(NOW)
        self.assertTrue(membership.isActive())
        membership.remove(NOW)
        self.assertFalse(membership.isActive())
        with self.assertRaises(InvalidStateTransitionError):
            membership.reactivate(NOW)  # REMOVED is terminal


class ServiceAccountStateMachineTests(SimpleTestCase):
    def testActiveDisabledBothWays(self) -> None:
        account = ServiceAccount.create(
            uuid.uuid4(), "worker-1", "Worker", "", NOW, scopes=("jobs.run",)
        )
        self.assertTrue(account.isActive())
        account.transitionTo("disabled", NOW)
        self.assertFalse(account.isActive())
        account.transitionTo("active", NOW)
        self.assertTrue(account.isActive())


class ApiKeyEntityTests(SimpleTestCase):
    def testIssuePrefixAndValidity(self) -> None:
        key = ApiKey.issue(uuid.uuid4(), "ci-key", "h" * 64, "tek_abc", "user", uuid.uuid4(), NOW)
        self.assertTrue(key.isValidAt(NOW))
        self.assertEqual([e.name for e in key.pullEvents()], ["apiKeyCreated"])

    def testRevokedAndExpiredInvalid(self) -> None:
        key = ApiKey.issue(uuid.uuid4(), "k", "h" * 64, "tek_abc", "user", uuid.uuid4(), NOW)
        key.revoke(NOW)
        self.assertFalse(key.isValidAt(NOW))
        expired = ApiKey.issue(
            uuid.uuid4(),
            "k2",
            "h" * 64,
            "tek_abd",
            "user",
            uuid.uuid4(),
            NOW,
            expiresAt=NOW + timedelta(minutes=1),
        )
        self.assertFalse(expired.isValidAt(NOW + timedelta(minutes=2)))


class SessionEntityTests(SimpleTestCase):
    def testRotateRefreshTokenReplacesHash(self) -> None:
        session = Session.start(uuid.uuid4(), uuid.uuid4(), "old", NOW, 30)
        session.rotateRefreshToken("new", NOW)
        self.assertEqual(session.refreshTokenHash, "new")
        self.assertTrue(session.isValidAt(NOW))

    def testStatusAtReflectsRevocationAndExpiry(self) -> None:
        session = Session.start(uuid.uuid4(), uuid.uuid4(), "h", NOW, 30)
        self.assertEqual(session.statusAt(NOW), "active")
        session.revoke(NOW)
        self.assertEqual(session.statusAt(NOW), "revoked")
        self.assertEqual(session.statusAt(NOW + timedelta(hours=1)), "revoked")


class TotpServiceTests(SimpleTestCase):
    def testCurrentCodeVerifiesWithDrift(self) -> None:
        secret = totpService.generateSecret()
        code = totpService.currentCode(secret)
        self.assertTrue(totpService.verifyCode(secret, code))
        past = totpService.currentCode(secret, at=int(time.time()) - 30)
        self.assertTrue(totpService.verifyCode(secret, past), "±1 step drift allowed (§24)")
        self.assertFalse(totpService.verifyCode(secret, "000000"))
        self.assertFalse(totpService.verifyCode(secret, "not-a-code"))

    def testOtpauthUrlShape(self) -> None:
        url = totpService.otpauthUrl("SECRET", account="sara")
        self.assertTrue(url.startswith("otpauth://totp/Tekarai:sara?secret=SECRET"))


class MfaFactorTests(SimpleTestCase):
    def testPendingToActiveToDisabled(self) -> None:
        factor = MfaFactor.beginSetup(uuid.uuid4(), "totp", "ref", NOW)
        self.assertFalse(factor.isActive())
        factor.confirm(NOW)
        self.assertTrue(factor.isActive())
        factor.disable(NOW)
        self.assertFalse(factor.isActive())


class ResourcePolicyTests(SimpleTestCase):
    def actor(
        self,
        *,
        actorId: uuid.UUID | None = None,
        isGlobalScope: bool = False,
        actions: frozenset[str] = frozenset({"user.update"}),
    ) -> AccessRequest:
        return AccessRequest(
            actorId=actorId or uuid.uuid4(),
            tenantId=uuid.uuid4(),
            isGlobalScope=isGlobalScope,
            actions=actions,
        )

    def testSelfViewAllowedPeerNeedsTenantMatch(self) -> None:
        policy = POLICIES["User"]
        me = User.register(uuid.uuid4(), "me", "m@a.com", "h", "M", NOW, status="active")
        self.assertTrue(policy.canView(self.actor(actorId=me.id), me))
        otherTenant = User.register(uuid.uuid4(), "peer", "p@a.com", "h", "P", NOW, status="active")
        self.assertFalse(policy.canView(self.actor(), otherTenant))
        self.assertTrue(
            policy.canView(self.actor(isGlobalScope=True), otherTenant),
            "GLOBAL scope crosses tenants (§19)",
        )

    def testNeverDisableYourself(self) -> None:
        policy = POLICIES["User"]
        me = User.register(uuid.uuid4(), "me", "m@a.com", "h", "M", NOW, status="active")
        request = self.actor(actorId=me.id, actions=frozenset({"user.suspend"}))
        self.assertFalse(policy.canDisable(request, me), "§19 never yourself")

    def testSessionPolicyOwnOnly(self) -> None:
        policy = POLICIES["Session"]
        session = Session.start(uuid.uuid4(), uuid.uuid4(), "h", NOW, 30)
        stranger = self.actor(actorId=uuid.uuid4())
        self.assertFalse(policy.canUpdate(stranger, session))
        owner = self.actor(actorId=session.userId)
        self.assertTrue(policy.canUpdate(owner, session))
        auditor = self.actor(actorId=uuid.uuid4(), actions=frozenset({"audit.view"}))
        self.assertTrue(policy.canView(auditor, session))


class JwtServiceTests(SimpleTestCase):
    """§8 claim set + §7 verification rules (ADR-022 in-house HS256)."""

    def testRoundTripAndMinimalClaims(self) -> None:
        from apps.identity.infrastructure.services.jwtService import JwtService

        service = JwtService(
            signingKey="unit-test-key",
            issuer="tekarai",
            audience="tekarai-api",
            accessTtlMinutes=15,
        )
        userId, tenantId, sessionId = uuid.uuid4(), uuid.uuid4(), uuid.uuid4()
        token, ttl = service.issueAccessToken(userId=userId, tenantId=tenantId, sessionId=sessionId)
        self.assertEqual(ttl, 900)
        claims = service.verifyAccessToken(token)
        self.assertEqual(claims["sub"], str(userId))
        self.assertEqual(claims["tenantId"], str(tenantId))
        self.assertEqual(claims["sessionId"], str(sessionId))
        self.assertEqual(claims["iss"], "tekarai")
        self.assertEqual(claims["typ"], "access")
        self.assertNotIn("permissions", claims, "§8 — no bulk permissions in token")

    def testTamperedSignatureRejected(self) -> None:
        from apps.identity.infrastructure.services.jwtService import JwtService

        service = JwtService(signingKey="k1", issuer="i", audience="a", accessTtlMinutes=5)
        token, _ = service.issueAccessToken(
            userId=uuid.uuid4(), tenantId=uuid.uuid4(), sessionId=uuid.uuid4()
        )
        header, payload, signature = token.split(".")
        tampered = f"{header}.{payload}.{'0' * len(signature)}"
        from apps.sharedKernel.domain.errors import AuthenticationRequiredError

        with self.assertRaises(AuthenticationRequiredError):
            service.verifyAccessToken(tampered)

    def testExpiredTokenRejected(self) -> None:
        from apps.identity.infrastructure.services.jwtService import JwtService

        service = JwtService(signingKey="k1", issuer="i", audience="a", accessTtlMinutes=-1)
        token, _ = service.issueAccessToken(
            userId=uuid.uuid4(), tenantId=uuid.uuid4(), sessionId=uuid.uuid4()
        )
        from apps.sharedKernel.domain.errors import TokenExpiredError

        with self.assertRaises(TokenExpiredError):
            service.verifyAccessToken(token)

    def testWrongAudienceRejected(self) -> None:
        from apps.identity.infrastructure.services.jwtService import JwtService

        issuer = JwtService(signingKey="k", issuer="i", audience="a1", accessTtlMinutes=5)
        token, _ = issuer.issueAccessToken(
            userId=uuid.uuid4(), tenantId=uuid.uuid4(), sessionId=uuid.uuid4()
        )
        stranger = JwtService(signingKey="k", issuer="i", audience="a2", accessTtlMinutes=5)
        from apps.sharedKernel.domain.errors import AuthenticationRequiredError

        with self.assertRaises(AuthenticationRequiredError):
            stranger.verifyAccessToken(token)

    def testChallengeTypeNotAcceptedAsAccess(self) -> None:
        from apps.identity.infrastructure.services.jwtService import JwtService

        service = JwtService(signingKey="k", issuer="i", audience="a", accessTtlMinutes=5)
        challenge = service.issueMfaChallenge(
            userId=uuid.uuid4(), tenantId=uuid.uuid4(), sessionId=uuid.uuid4()
        )
        from apps.sharedKernel.domain.errors import AuthenticationRequiredError

        with self.assertRaises(AuthenticationRequiredError):
            service.verifyAccessToken(challenge)
