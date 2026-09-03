"""Phase 7 application tests — use cases (§31) over the real ORM."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.test import TestCase

from apps.identity.application.commands.identityCommands import (
    AssignRoleCommand,
    AuthenticateUserCommand,
    ChangePasswordCommand,
    ConfirmMfaCommand,
    ConfirmPasswordResetCommand,
    CreateApiKeyCommand,
    CreateRoleCommand,
    CreateServiceAccountCommand,
    DeleteRoleCommand,
    DisableServiceAccountCommand,
    RequestPasswordResetCommand,
    RevokeApiKeyCommand,
    RevokeSessionCommand,
    SetupMfaCommand,
    VerifyMfaChallengeCommand,
)
from apps.identity.application.queries.identityQueries import (
    ListApiKeysQuery,
    ListServiceAccountsQuery,
    ListSessionsQuery,
)
from apps.identity.domain.services import totpService
from apps.identity.infrastructure import container as identityContainer
from apps.identity.infrastructure.models import (
    ApiKeyModel,
    SecurityEventModel,
    SessionModel,
)
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import (
    DuplicateIdentifierError,
    InvalidCredentialsError,
    ValidationFailedError,
)
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_PASSWORD,
    platformTenantId,
    seedPlatform,
)


def asAdmin(tenantId: str) -> RequestContext:
    from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
        UserRepositoryDjango,
    )
    from tests.support.phase6Helpers import PLATFORM_ADMIN_USERNAME

    admin = UserRepositoryDjango().getByUsername(platformTenantId(), PLATFORM_ADMIN_USERNAME)
    return RequestContext(
        actorId=str(admin.id) if admin else "",
        tenantId=tenantId,
        actorTenantId=tenantId,
    )


class AuthenticateFlowTests(TestCase):
    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = str(platformTenantId())

    def login(self, identifier: str = "platform-admin", password: str = PLATFORM_ADMIN_PASSWORD):
        return identityContainer.authenticateUserUseCase().execute(
            AuthenticateUserCommand("platform", identifier, password)
        )

    def testLoginWithUsernameAndEmail(self) -> None:
        byName = self.login("platform-admin")
        byEmail = self.login("platform-admin@tekarai.local")
        self.assertTrue(byName.accessToken and byEmail.accessToken)

    def testFiveBadPasswordsLockAccountAndAudit(self) -> None:
        for _ in range(5):
            with self.assertRaises(InvalidCredentialsError):
                self.login(password="Wrong-Password-1!")
        self.assertTrue(
            SecurityEventModel.objects.filter(eventType="ACCOUNT_LOCKED").exists(),
            "ACCOUNT_LOCKED security event must be recorded (§27)",
        )
        locked = SecurityEventModel.objects.filter(eventType="LOGIN_FAILED").count()
        self.assertGreaterEqual(locked, 5)
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            UserRepositoryDjango,
        )
        from tests.support.phase6Helpers import PLATFORM_ADMIN_USERNAME

        user = UserRepositoryDjango().getByUsername(platformTenantId(), PLATFORM_ADMIN_USERNAME)
        assert user is not None
        self.assertIsNotNone(user.lockedUntil, "brute-force lock is set (§10)")
        from apps.sharedKernel.domain.errors import AuthenticationRequiredError

        with self.assertRaises((InvalidCredentialsError, AuthenticationRequiredError)):
            self.login()  # even the RIGHT password is denied while locked

    def testMfaChallengeFlowIssuesTokens(self) -> None:

        with requestScope(asAdmin(self.tenantId)):
            setup = identityContainer.setupMfaUseCase().execute(SetupMfaCommand())
            code = totpService.currentCode(setup.secret)
            confirmed = identityContainer.confirmMfaUseCase().execute(
                ConfirmMfaCommand(factorId=setup.factorId, code=code)
            )
            self.assertEqual(len(confirmed.recoveryCodes), 8)

        dto = self.login()
        self.assertTrue(dto.mfaRequired)
        self.assertFalse(dto.accessToken)
        challenge = identityContainer.verifyMfaChallengeUseCase()
        with requestScope(RequestContext()):
            tokens = challenge.execute(
                VerifyMfaChallengeCommand(
                    challengeToken=dto.mfaChallenge,
                    code=totpService.currentCode(setup.secret),
                )
            )
        self.assertTrue(tokens.accessToken and tokens.refreshToken)
        # recovery code path (single-use, hashed)
        second = identityContainer.verifyMfaChallengeUseCase()
        with requestScope(RequestContext()):
            recovery = second.execute(
                VerifyMfaChallengeCommand(
                    challengeToken=dto.mfaChallenge,
                    code=confirmed.recoveryCodes[0],
                )
            )
        self.assertTrue(recovery.accessToken)

    def testSessionsListedAndRevokedByOwner(self) -> None:
        self.login()
        self.login()  # two concurrent sessions
        with requestScope(asAdmin(self.tenantId)):
            sessions = identityContainer.listSessionsUseCase().execute(ListSessionsQuery())
        self.assertEqual(len(sessions), 2)
        target = [s for s in sessions if not s.current][0]
        with requestScope(asAdmin(self.tenantId)):
            identityContainer.revokeSessionUseCase().execute(
                RevokeSessionCommand(sessionId=target.id)
            )
        with requestScope(asAdmin(self.tenantId)):
            remaining = identityContainer.listSessionsUseCase().execute(ListSessionsQuery())
        self.assertEqual(len(remaining), 1)


class PasswordPolicyTests(TestCase):
    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = str(platformTenantId())

    def testChangePasswordRejectsReuseAndWrongCurrent(self) -> None:
        with requestScope(asAdmin(self.tenantId)):
            with self.assertRaises(InvalidCredentialsError):
                identityContainer.changePasswordUseCase().execute(
                    ChangePasswordCommand(
                        currentPassword="Not-The-Password-1!",
                        newPassword="Fresh-Secret-9!",
                    )
                )
            with self.assertRaises(ValidationFailedError):
                identityContainer.changePasswordUseCase().execute(
                    ChangePasswordCommand(
                        currentPassword=PLATFORM_ADMIN_PASSWORD,
                        newPassword=PLATFORM_ADMIN_PASSWORD,  # reuse
                    )
                )

    def testChangePasswordRevokesSessions(self) -> None:
        identityContainer.authenticateUserUseCase().execute(
            AuthenticateUserCommand("platform", "platform-admin", PLATFORM_ADMIN_PASSWORD)
        )
        self.assertTrue(SessionModel.objects.filter(revokedAt__isnull=True).exists())
        with requestScope(asAdmin(self.tenantId)):
            identityContainer.changePasswordUseCase().execute(
                ChangePasswordCommand(
                    currentPassword=PLATFORM_ADMIN_PASSWORD,
                    newPassword="Fresh-Secret-9!",
                )
            )
        self.assertFalse(
            SessionModel.objects.filter(revokedAt__isnull=True).exists(),
            "§35 — password change kills every session",
        )
        # old password no longer works; new one does
        with self.assertRaises(InvalidCredentialsError):
            identityContainer.authenticateUserUseCase().execute(
                AuthenticateUserCommand("platform", "platform-admin", PLATFORM_ADMIN_PASSWORD)
            )
        fresh = identityContainer.authenticateUserUseCase().execute(
            AuthenticateUserCommand("platform", "platform-admin", "Fresh-Secret-9!")
        )
        self.assertTrue(fresh.accessToken)

    def testResetTokenSingleUse(self) -> None:
        request = identityContainer.requestPasswordResetUseCase()
        with requestScope(RequestContext()):
            result = request.execute(
                RequestPasswordResetCommand(tenantCode="platform", identifier="platform-admin")
            )
        assert result["resetToken"]
        confirm = identityContainer.confirmPasswordResetUseCase()
        with requestScope(RequestContext()):
            confirm.execute(
                ConfirmPasswordResetCommand(
                    token=result["resetToken"], newPassword="Rotated-Pass-7!"
                )
            )
            with self.assertRaises(InvalidCredentialsError):
                confirm.execute(
                    ConfirmPasswordResetCommand(
                        token=result["resetToken"], newPassword="Rotated-Pass-8!"
                    )
                )

    def testResetRequestDoesNotRevealUnknownAccounts(self) -> None:
        request = identityContainer.requestPasswordResetUseCase()
        with requestScope(RequestContext()):
            result = request.execute(
                RequestPasswordResetCommand(tenantCode="platform", identifier="ghost@nowhere.test")
            )
        self.assertTrue(result["requested"])
        self.assertEqual(result["resetToken"], "")

    def testUnknownIdentifierUniformFailure(self) -> None:
        with self.assertRaises(InvalidCredentialsError):
            identityContainer.authenticateUserUseCase().execute(
                AuthenticateUserCommand("platform", "ghost-user", "Whatever-9!")
            )


def nowUtcHelper():

    return datetime.now(tz=UTC)


class RbacAdminTests(TestCase):
    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = str(platformTenantId())

    def testRoleCrudAndAssignment(self) -> None:
        with requestScope(asAdmin(self.tenantId)):
            role = identityContainer.createRoleUseCase().execute(
                CreateRoleCommand(
                    code="auditor",
                    name="Auditor",
                    scopeType="TENANT",
                    actions=["audit.view"],
                )
            )
            with self.assertRaises(DuplicateIdentifierError):
                identityContainer.createRoleUseCase().execute(
                    CreateRoleCommand("auditor", "Auditor 2", "TENANT", ["audit.view"])
                )
            from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
                UserRepositoryDjango,
            )
            from tests.support.phase6Helpers import PLATFORM_ADMIN_USERNAME

            admin = UserRepositoryDjango().getByUsername(
                platformTenantId(), PLATFORM_ADMIN_USERNAME
            )
            assert admin is not None
            identityContainer.assignRoleUseCase().execute(
                AssignRoleCommand(userId=str(admin.id), roleId=role.id)
            )
            from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

            gate = sharedKernelProvider("permissionGate")()
            # fresh member WITHOUT the admin presets (isolation §35.9)
            from apps.identity.application.commands.identityCommands import (
                CreateUserCommand,
                RemoveRoleCommand,
            )

            member = identityContainer.createUserUseCase().execute(
                CreateUserCommand(
                    tenantId=self.tenantId,
                    username="rbac-probe",
                    email="rbac-probe@member.test",
                    password="Strong-Pass-2026!",
                )
            )
            from apps.identity.domain.entities.tenantMembership import TenantMembership
            from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
                TenantMembershipRepositoryDjango,
            )

            TenantMembershipRepositoryDjango().create(
                TenantMembership.establish(uuid.UUID(member.id), platformTenantId(), nowUtcHelper())
            )
            denied = gate.hasPermission(
                uuid.UUID(member.id), "audit.view", tenantId=platformTenantId()
            )
            self.assertFalse(denied, "no grants before assignment")
            identityContainer.assignRoleUseCase().execute(
                AssignRoleCommand(userId=member.id, roleId=role.id)
            )
            granted = gate.hasPermission(
                uuid.UUID(member.id), "audit.view", tenantId=platformTenantId()
            )
            self.assertTrue(granted, "role grant effective immediately")
            identityContainer.removeRoleUseCase().execute(
                RemoveRoleCommand(userId=member.id, roleId=role.id)
            )
            revoked = gate.hasPermission(
                uuid.UUID(member.id), "audit.view", tenantId=platformTenantId()
            )
            self.assertFalse(revoked, "§35.9 — revocation effective immediately")

    def testDeleteAssignedRoleBlocked(self) -> None:
        from apps.identity.infrastructure.models import RoleModel
        from apps.sharedKernel.domain.errors import ConflictError

        with requestScope(asAdmin(self.tenantId)):
            role = identityContainer.createRoleUseCase().execute(
                CreateRoleCommand(code="temp-role", name="Temp", actions=["user.view"])
            )
            from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
                UserRepositoryDjango,
            )
            from tests.support.phase6Helpers import PLATFORM_ADMIN_USERNAME

            admin = UserRepositoryDjango().getByUsername(
                platformTenantId(), PLATFORM_ADMIN_USERNAME
            )
            assert admin is not None
            identityContainer.assignRoleUseCase().execute(
                AssignRoleCommand(userId=str(admin.id), roleId=role.id)
            )
            with self.assertRaises(ConflictError):
                identityContainer.deleteRoleUseCase().execute(DeleteRoleCommand(roleId=role.id))
            RoleModel.objects.filter(code="temp-role").exists()


class ApiKeyUseCaseTests(TestCase):
    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = str(platformTenantId())

    def testCreateVerifyRevoke(self) -> None:
        with requestScope(asAdmin(self.tenantId)):
            created = identityContainer.createApiKeyUseCase().execute(
                CreateApiKeyCommand(tenantId=self.tenantId, name="ci", scopes=["jobs.run"])
            )
        self.assertTrue(created.rawKey.startswith("tek_"))
        row = ApiKeyModel.objects.get(id=uuid.UUID(created.apiKey.id))
        self.assertNotEqual(row.keyHash, created.rawKey, "only the hash is stored")

        from apps.identity.infrastructure.services.principals import ApiKeyVerifierDjango

        principal = ApiKeyVerifierDjango().verifyApiKey(created.rawKey)
        self.assertEqual(str(principal.userId), created.apiKey.ownerId)

        with requestScope(asAdmin(self.tenantId)):
            identityContainer.revokeApiKeyUseCase().execute(
                RevokeApiKeyCommand(apiKeyId=created.apiKey.id)
            )
        from apps.sharedKernel.domain.errors import AuthenticationRequiredError

        with self.assertRaises(AuthenticationRequiredError):
            ApiKeyVerifierDjango().verifyApiKey(created.rawKey)  # §35.6

    def testListNeverReturnsRawKey(self) -> None:
        with requestScope(asAdmin(self.tenantId)):
            created = identityContainer.createApiKeyUseCase().execute(
                CreateApiKeyCommand(tenantId=self.tenantId, name="ci2")
            )
            keys = identityContainer.listApiKeysUseCase().execute(ListApiKeysQuery())
        self.assertTrue(all(k.id != created.rawKey for k in keys))
        self.assertFalse(any("tek_" in str(k.prefix) and len(str(k.prefix)) > 8 for k in keys))


class ServiceAccountUseCaseTests(TestCase):
    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = str(platformTenantId())

    def testCreateDisableEnable(self) -> None:
        with requestScope(asAdmin(self.tenantId)):
            account = identityContainer.createServiceAccountUseCase().execute(
                CreateServiceAccountCommand(
                    tenantId=self.tenantId,
                    code="agent-42",
                    name="Deploy Agent",
                    description="CI runner",
                )
            )
            self.assertEqual(account.status, "active")
            with self.assertRaises(DuplicateIdentifierError):
                identityContainer.createServiceAccountUseCase().execute(
                    CreateServiceAccountCommand(self.tenantId, "agent-42", "Duplicate", "")
                )
            disabled = identityContainer.disableServiceAccountUseCase().execute(
                DisableServiceAccountCommand(accountId=account.id)
            )
            self.assertEqual(disabled.status, "disabled")
            accounts = identityContainer.listServiceAccountsUseCase().execute(
                ListServiceAccountsQuery()
            )
        self.assertEqual(len(accounts), 1)

    def testDisabledServiceAccountApiKeyRejected(self) -> None:
        from apps.identity.infrastructure.services.principals import ApiKeyVerifierDjango
        from apps.sharedKernel.domain.errors import AuthenticationRequiredError

        with requestScope(asAdmin(self.tenantId)):
            account = identityContainer.createServiceAccountUseCase().execute(
                CreateServiceAccountCommand(self.tenantId, "bot", "Bot", "")
            )
            key = identityContainer.createApiKeyUseCase().execute(
                CreateApiKeyCommand(
                    tenantId=self.tenantId,
                    name="bot-key",
                    ownerType="serviceAccount",
                    ownerId=account.id,
                )
            )
            ApiKeyVerifierDjango().verifyApiKey(key.rawKey)  # works while active
            identityContainer.disableServiceAccountUseCase().execute(
                DisableServiceAccountCommand(accountId=account.id)
            )
        with self.assertRaises(AuthenticationRequiredError):
            ApiKeyVerifierDjango().verifyApiKey(key.rawKey)


class AuthorizationCacheTests(TestCase):
    """§28 — grants are cached and invalidated on mutation."""

    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = str(platformTenantId())

    def testCacheBumpInvalidatesGrants(self) -> None:
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            AccessRepositoryDjango,
        )
        from apps.identity.infrastructure.services import authorizationCache

        access = AccessRepositoryDjango()
        with requestScope(asAdmin(self.tenantId)):
            from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
                UserRepositoryDjango,
            )
            from tests.support.phase6Helpers import PLATFORM_ADMIN_USERNAME

            admin = UserRepositoryDjango().getByUsername(
                platformTenantId(), PLATFORM_ADMIN_USERNAME
            )
            assert admin is not None
            userId, tenantId = admin.id, platformTenantId()
            grants1 = access.grantsOfUser(userId, tenantId)
            cached = authorizationCache.readGrants(userId, tenantId)
            self.assertIsNotNone(cached, "grants cached after first read")
            authorizationCache.bumpVersion(userId)
            self.assertIsNone(
                authorizationCache.readGrants(userId, tenantId),
                "version bump kills the cache entry",
            )
            grants2 = access.grantsOfUser(userId, tenantId)
            self.assertEqual(len(grants1), len(grants2))
