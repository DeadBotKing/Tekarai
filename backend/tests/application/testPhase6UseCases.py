"""Phase 06 application tests (§29 "Application Tests" + "Authorization
Tests" + "Multi-Tenant Isolation Tests").

Runs the real use cases against the hermetic test database through the
Django repository implementations (§29 "Repository Tests" in the same run:
every repository method is exercised by the flows).
"""

from __future__ import annotations

import uuid

from django.test import TestCase

from apps.identity.application.commands.identityCommands import (
    AssignUserToTenantCommand,
    AuthenticateUserCommand,
    CreateUserCommand,
    LogoutCommand,
    RefreshSessionCommand,
)
from apps.identity.application.dto.identityDtos import UserDto
from apps.identity.application.queries.identityQueries import (
    GetCurrentAccountQuery,
    GetUserQuery,
    ListUsersQuery,
)
from apps.identity.infrastructure import container as identityContainer
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import (
    DuplicateActiveMembershipError,
    DuplicateIdentifierError,
    EntityNotFoundError,
    InvalidCredentialsError,
    PermissionDeniedError,
)
from apps.sharedKernel.infrastructure.models import AuditEventModel
from apps.tenancy.application.commands.tenantCommands import CreateTenantCommand
from apps.tenancy.infrastructure import container as tenancyContainer
from tests.support.phase6Helpers import platformTenantId, seedPlatform

ADMIN_PASSWORD = "Platform-Admin-2026!"


def asPlatformAdmin(actorTenantId: str) -> RequestContext:
    from apps.identity.infrastructure.models import UserModel

    admin = UserModel.objects.get(username="platform-admin")
    return RequestContext(
        correlationId="corr-test-0001",
        requestId="req-test-0001",
        actorId=str(admin.id),
        actorTenantId=actorTenantId,
        tenantId=actorTenantId,
        ipAddress="127.0.0.1",
        userAgent="pytest-agent",
    )


class TenantUseCaseTests(TestCase):
    def testCreateTenantHappyPathAuditsAndReturnsDto(self) -> None:
        seedPlatform()
        tenantId = str(platformTenantId())
        with requestScope(asPlatformAdmin(tenantId)):
            dto = tenancyContainer.createTenantUseCase().execute(
                CreateTenantCommand(code="acme", name="ACME Industries")
            )
        self.assertEqual(dto.code, "acme")
        self.assertEqual(dto.status, "active")
        audit = AuditEventModel.objects.filter(resourceType="Tenant", resourceId=dto.id).get()
        self.assertEqual(audit.action, "CREATE")
        self.assertEqual(audit.correlationId, "corr-test-0001")

    def testDuplicateTenantCodeRejected(self) -> None:
        seedPlatform()
        tenantId = str(platformTenantId())
        with requestScope(asPlatformAdmin(tenantId)):
            tenancyContainer.createTenantUseCase().execute(
                CreateTenantCommand(code="acme", name="ACME")
            )
            from apps.sharedKernel.domain.errors import DuplicateBusinessCodeError

            with self.assertRaises(DuplicateBusinessCodeError):
                tenancyContainer.createTenantUseCase().execute(
                    CreateTenantCommand(code="acme", name="ACME 2")
                )

    def testUnauthorizedActorCannotCreateTenant(self) -> None:
        seedPlatform()
        stranger = RequestContext(actorId=str(uuid.uuid4()), tenantId="")
        with requestScope(stranger):
            with self.assertRaises(PermissionDeniedError):
                tenancyContainer.createTenantUseCase().execute(
                    CreateTenantCommand(code="rogue", name="Rogue")
                )


class UserUseCaseTests(TestCase):
    def createUser(self, tenantId: str, username: str = "sara") -> UserDto:
        return identityContainer.createUserUseCase().execute(
            CreateUserCommand(
                tenantId=tenantId,
                username=username,
                email=f"{username}@acme.test",
                password="Strong-Pass-2026!",
                displayName=username.title(),
            )
        )

    def testCreateUserAndDuplicateUsername(self) -> None:
        seedPlatform()
        tenantId = str(platformTenantId())
        with requestScope(asPlatformAdmin(tenantId)):
            dto = self.createUser(tenantId)
            self.assertEqual(dto.username, "sara")
            with self.assertRaises(DuplicateIdentifierError):
                self.createUser(tenantId)

    def testAssignMembershipOnce(self) -> None:
        seedPlatform()
        tenantId = str(platformTenantId())
        with requestScope(asPlatformAdmin(tenantId)):
            user = self.createUser(tenantId)
            with requestScope(asPlatformAdmin(tenantId)):
                otherTenant = tenancyContainer.createTenantUseCase().execute(
                    CreateTenantCommand(code="branch", name="Branch")
                )
            identityContainer.assignUserToTenantUseCase().execute(
                AssignUserToTenantCommand(userId=user.id, targetTenantId=otherTenant.id)
            )
            with self.assertRaises(DuplicateActiveMembershipError):
                identityContainer.assignUserToTenantUseCase().execute(
                    AssignUserToTenantCommand(userId=user.id, targetTenantId=otherTenant.id)
                )

    def testListUsersIsTenantScoped(self) -> None:
        seedPlatform()
        tenantId = str(platformTenantId())
        with requestScope(asPlatformAdmin(tenantId)):
            self.createUser(tenantId, "sara")
            self.createUser(tenantId, "dara")
            other = tenancyContainer.createTenantUseCase().execute(
                CreateTenantCommand(code="other", name="Other")
            )
            identityContainer.createUserUseCase().execute(
                CreateUserCommand(
                    tenantId=other.id,
                    username="only-other",
                    email="o@other.test",
                    password="Strong-Pass-2026!",
                )
            )
        # platform admin (GLOBAL) sees all three tenants' users when scoped
        with requestScope(asPlatformAdmin(tenantId)):
            page = identityContainer.listUsersUseCase().execute(
                ListUsersQuery(tenantId=str(other.id))
            )
        self.assertEqual(page.totalCount, 1)
        self.assertEqual(page.items[0].username, "only-other")


class SessionUseCaseTests(TestCase):
    def testLoginIssuesTokenAndAudits(self) -> None:
        seedPlatform()
        dto = identityContainer.authenticateUserUseCase().execute(
            AuthenticateUserCommand(
                tenantCode="platform",
                username="platform-admin",
                password=ADMIN_PASSWORD,
            )
        )
        self.assertTrue(dto.token)
        assert dto.user is not None
        self.assertEqual(dto.user.username, "platform-admin")
        audit = AuditEventModel.objects.filter(action="LOGIN").latest("occurredAt")
        self.assertEqual(audit.resourceType, "Session")

    def testFailedLoginAuditedOutsideTransaction(self) -> None:
        seedPlatform()
        with self.assertRaises(InvalidCredentialsError):
            identityContainer.authenticateUserUseCase().execute(
                AuthenticateUserCommand(
                    tenantCode="platform",
                    username="platform-admin",
                    password="Wrong-Password-1!",
                )
            )
        failure = AuditEventModel.objects.filter(action="LOGIN", afterState__outcome="failure")
        self.assertTrue(failure.exists(), "failed login must be audited")

    def testRefreshRotatesAndLogoutRevokes(self) -> None:
        seedPlatform()
        login = identityContainer.authenticateUserUseCase().execute(
            AuthenticateUserCommand("platform", "platform-admin", ADMIN_PASSWORD)
        )
        refreshed = identityContainer.refreshSessionUseCase().execute(
            RefreshSessionCommand(token=login.token)
        )
        self.assertNotEqual(refreshed.token, login.token)
        identityContainer.logoutUseCase().execute(LogoutCommand(token=refreshed.token))
        with self.assertRaises(InvalidCredentialsError):
            identityContainer.refreshSessionUseCase().execute(
                RefreshSessionCommand(token=refreshed.token)
            )


class TenantIsolationTests(TestCase):
    def testCrossTenantUserReadDeniedWithoutGlobalGrant(self) -> None:
        seedPlatform()
        platformId = str(platformTenantId())
        with requestScope(asPlatformAdmin(platformId)):
            admin = identityContainer.listUsersUseCase().execute(
                ListUsersQuery(tenantId=platformId)
            )
            other = tenancyContainer.createTenantUseCase().execute(
                CreateTenantCommand(code="isolated", name="Isolated")
            )
            outsider = identityContainer.createUserUseCase().execute(
                CreateUserCommand(
                    tenantId=other.id,
                    username="outsider",
                    email="o@isolated.test",
                    password="Strong-Pass-2026!",
                )
            )
        # A tenant-scoped member (no GLOBAL grant) may not read another
        # tenant's user: simulate by calling the evaluator directly.
        from apps.identity.domain.services.permissionEvaluator import (
            PermissionEvaluator,
        )
        from apps.identity.domain.valueObjects.accessGrant import AccessGrant

        evaluator = PermissionEvaluator()
        tenantScoped = [AccessGrant("user.view", "TENANT")]
        self.assertFalse(
            evaluator.hasPermission(
                tenantScoped,
                uuid.UUID(admin.items[0].id),
                "user.view",
                actorTenantId=uuid.UUID(platformId),
                targetTenantId=uuid.UUID(outsider.tenantId),
            )
        )
        # And the repository itself never returns other-tenant rows:
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            UserRepositoryDjango,
        )

        repository = UserRepositoryDjango()
        self.assertIsNone(
            repository.getById(uuid.UUID(outsider.id), tenantId=uuid.UUID(platformId))
        )
        self.assertIsNotNone(
            repository.getById(uuid.UUID(outsider.id), tenantId=uuid.UUID(outsider.tenantId))
        )

    def testGetUserUnknownIdRaisesNotFound(self) -> None:
        seedPlatform()
        with requestScope(asPlatformAdmin(str(platformTenantId()))):
            with self.assertRaises(EntityNotFoundError):
                identityContainer.getUserUseCase().execute(GetUserQuery(userId=str(uuid.uuid4())))


class AccountQueryTests(TestCase):
    def testCurrentAccountReturnsPermissions(self) -> None:
        seedPlatform()
        platformId = str(platformTenantId())
        with requestScope(asPlatformAdmin(platformId)):
            account = identityContainer.getCurrentAccountUseCase().execute(GetCurrentAccountQuery())
        self.assertIn("tenant.create", account.permissions)
        self.assertIn("audit.view", account.permissions)
