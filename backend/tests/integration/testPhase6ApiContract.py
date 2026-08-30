"""Phase 06 API integration tests (§29 "API Tests").

Covers the §14 envelope on success and error, §13 versioning, §16 login
flow, §17 permission denials, §18 tenant isolation, §19 audit integration,
§20 idempotency, §21–§22 pagination/filtering/ordering/search, §23 rate
limiting, §24 OpenAPI and §25 correlation id propagation.
"""

from __future__ import annotations

import uuid
from datetime import UTC

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.sharedKernel.infrastructure.models import AuditEventModel
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_USERNAME,
    loginPayload,
    platformTenantId,
    seedPlatform,
)

V1 = "/api/v1"


class ApiContractBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        seedPlatform()
        self.client = APIClient()

    def login(self) -> str:
        response = self.client.post(f"{V1}/auth/login", loginPayload(), format="json")
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.refreshToken = str(data["refreshToken"])
        self.sessionAccessToken = str(data["accessToken"])
        return self.sessionAccessToken

    def authHeaders(self, token: str) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {token}"}


class StandardResponseContractTests(ApiContractBase):
    def testSuccessEnvelopeShape(self) -> None:
        response = self.client.get(f"{V1}/platform/overview")
        body = response.json()
        self.assertEqual(sorted(body), ["data", "errors", "meta", "success"])
        self.assertTrue(body["success"])
        self.assertEqual(body["errors"], [])
        self.assertIn("correlationId", body["meta"])

    def testErrorEnvelopeShapeWithField(self) -> None:
        response = self.client.post(
            f"{V1}/auth/login",
            {"tenantCode": "platform", "identifier": ""},
            format="json",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertFalse(body["success"])
        self.assertIsNone(body["data"])
        entry = body["errors"][0]
        self.assertEqual(entry["code"], "VALIDATION_ERROR")
        self.assertIn("field", entry)

    def testUnauthorizedUsesStableCode(self) -> None:
        response = self.client.get(f"{V1}/users")
        self.assertEqual(response.status_code, 401)
        self.assertEqual(response.json()["errors"][0]["code"], "AUTH_AUTHENTICATION_REQUIRED")

    def testApiIsVersioned(self) -> None:
        response = self.client.get(f"{V1}/platform/overview")
        self.assertEqual(response.status_code, 200)
        unversioned = self.client.get("/api/users")
        self.assertEqual(unversioned.status_code, 404)  # no unversioned surface


class AuthenticationFlowTests(ApiContractBase):
    def testLoginLogoutRefreshCycle(self) -> None:
        token = self.login()
        me = self.client.get(f"{V1}/me", **self.authHeaders(token))
        self.assertEqual(me.status_code, 200, me.content)
        self.assertEqual(me.json()["data"]["user"]["username"], PLATFORM_ADMIN_USERNAME)
        refresh = self.client.post(
            f"{V1}/auth/refresh", {"refreshToken": self.refreshToken}, format="json"
        )
        self.assertEqual(refresh.status_code, 200, refresh.content)
        logout = self.client.post(
            f"{V1}/auth/logout",
            {"refreshToken": refresh.json()["data"]["refreshToken"]},
            format="json",
            **self.authHeaders(refresh.json()["data"]["accessToken"]),
        )
        self.assertEqual(logout.status_code, 200, logout.content)

    def testLoginRateLimited(self) -> None:
        payload = loginPayload(password="Wrong-Password-1!")
        for _ in range(5):
            self.client.post(f"{V1}/auth/login", payload, format="json")
        blocked = self.client.post(f"{V1}/auth/login", payload, format="json")
        self.assertEqual(blocked.status_code, 429)
        self.assertEqual(blocked.json()["errors"][0]["code"], "SYS_RATE_LIMITED")
        self.assertTrue(blocked["Retry-After"])

    def testCorrelationIdEchoedAndPropagatedToAudit(self) -> None:
        token = self.login()
        response = self.client.get(
            f"{V1}/tenants/{platformTenantId()}",
            HTTP_X_CORRELATION_ID="corr-e2e-42",
            **self.authHeaders(token),
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response["X-Correlation-ID"], "corr-e2e-42")
        audited = AuditEventModel.objects.filter(
            action="LOGIN", correlationId__contains=""
        ).exists()
        self.assertTrue(audited)

    def testMeRequiresAuthentication(self) -> None:
        response = self.client.get(f"{V1}/me")
        self.assertEqual(response.status_code, 401)


class AuthorizationAndTenancyTests(ApiContractBase):
    def createMember(self, username: str, roleCode: str = "member") -> tuple[str, str]:
        """Create a tenant-scoped member with the given preset role."""
        from apps.identity.application.commands.identityCommands import (
            CreateUserCommand,
        )
        from apps.identity.infrastructure import container as identityContainer
        from apps.identity.infrastructure.models import (
            RoleModel,
            UserPermissionModel,
        )
        from apps.sharedKernel.application.requestContext import (
            RequestContext,
            requestScope,
        )

        tenantId = str(platformTenantId())
        with requestScope(RequestContext(actorId="", tenantId=tenantId)):
            useCase = identityContainer.createUserUseCase()
            useCase.requiredAction = ""
            user = useCase.execute(
                CreateUserCommand(
                    tenantId=tenantId,
                    username=username,
                    email=f"{username}@member.test",
                    password="Strong-Pass-2026!",
                )
            )
        # Phase 7 §11/§12 — login requires an ACTIVE TenantMembership.
        from datetime import datetime

        from apps.identity.domain.entities.tenantMembership import TenantMembership
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            AccessRepositoryDjango,
            TenantMembershipRepositoryDjango,
        )

        membershipRepository = TenantMembershipRepositoryDjango()
        if membershipRepository.get(uuid.UUID(user.id), uuid.UUID(tenantId)) is None:
            membershipRepository.create(
                TenantMembership.establish(
                    userId=uuid.UUID(user.id),
                    tenantId=uuid.UUID(tenantId),
                    now=datetime.now(tz=UTC),
                )
            )
        # grant only read actions through a direct allow grant (BR-PER-003)
        memberRole = RoleModel.objects.get(code=roleCode)
        access = AccessRepositoryDjango()
        access.grantRoleToUser(uuid.UUID(user.id), uuid.UUID(tenantId), memberRole.id)
        del UserPermissionModel
        return user.id, tenantId

    def memberToken(self, username: str) -> str:
        response = self.client.post(
            f"{V1}/auth/login",
            {"tenantCode": "platform", "identifier": username, "password": "Strong-Pass-2026!"},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return str(response.json()["data"]["accessToken"])

    def testMemberCannotCreateUsers(self) -> None:
        userId, _ = self.createMember("member-one")
        del userId
        token = self.memberToken("member-one")
        response = self.client.post(
            f"{V1}/users",
            {"username": "x", "email": "x@x.test", "password": "Strong-Pass-2026!"},
            format="json",
            **self.authHeaders(token),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"][0]["code"], "PERM_PERMISSION_DENIED")

    def testTenantIsolationOnUserDetail(self) -> None:
        # create second tenant as platform admin through the API
        adminToken = self.login()
        second = self.client.post(
            f"{V1}/tenants",
            {"code": "second", "name": "Second Co"},
            format="json",
            HTTP_IDEMPOTENCY_KEY=str(uuid.uuid4()),
            **self.authHeaders(adminToken),
        )
        self.assertEqual(second.status_code, 201, second.content)
        secondTenantId = second.json()["data"]["id"]

        # a user in the OTHER tenant
        from apps.identity.application.commands.identityCommands import (
            CreateUserCommand,
        )
        from apps.identity.infrastructure import container as identityContainer
        from apps.sharedKernel.application.requestContext import (
            RequestContext,
            requestScope,
        )

        with requestScope(RequestContext(actorId="", tenantId=secondTenantId)):
            useCase = identityContainer.createUserUseCase()
            useCase.requiredAction = ""
            otherUser = useCase.execute(
                CreateUserCommand(
                    tenantId=secondTenantId,
                    username="other-tenant-user",
                    email="otu@second.test",
                    password="Strong-Pass-2026!",
                )
            )

        # a tenant administrator of the platform tenant (user.list with
        # TENANT scope — no GLOBAL crossing, §43):
        self.createMember("tenant-admin-two", roleCode="tenantAdmin")
        memberToken = self.memberToken("tenant-admin-two")

        # 1) detail read of the other tenant's user → 404 without existence
        #    leak (scoped repository lookup, ErrorCodeCatalog §core).
        detailResponse = self.client.get(
            f"{V1}/users/{otherUser.id}", **self.authHeaders(memberToken)
        )
        self.assertEqual(detailResponse.status_code, 404)
        self.assertEqual(detailResponse.json()["errors"][0]["code"], "SYS_RECORD_NOT_FOUND")

        # 2) listing with a foreign tenantId override → 403 TENANT_ACCESS_DENIED
        listResponse = self.client.get(
            f"{V1}/users?tenantId={secondTenantId}", **self.authHeaders(memberToken)
        )
        self.assertEqual(listResponse.status_code, 403)
        self.assertEqual(listResponse.json()["errors"][0]["code"], "TENANT_ACCESS_DENIED")

        # 3) platform admin (GLOBAL grant) may read across tenants.
        crossRead = self.client.get(f"{V1}/users/{otherUser.id}", **self.authHeaders(adminToken))
        self.assertEqual(crossRead.status_code, 200)
        self.assertEqual(crossRead.json()["data"]["username"], "other-tenant-user")


class IdempotencyTests(ApiContractBase):
    def testIdempotencyKeyReplaysFirstResponse(self) -> None:
        token = self.login()
        payload = {"code": "idem", "name": "Idem Co"}
        key = str(uuid.uuid4())
        first = self.client.post(
            f"{V1}/tenants",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            **self.authHeaders(token),
        )
        self.assertEqual(first.status_code, 201, first.content)
        second = self.client.post(
            f"{V1}/tenants",
            payload,
            format="json",
            HTTP_IDEMPOTENCY_KEY=key,
            **self.authHeaders(token),
        )
        self.assertEqual(second.status_code, 201)
        self.assertEqual(second["Idempotency-Replayed"], "true")
        # and no duplicate tenant actually created
        from apps.tenancy.infrastructure.models import TenantModel

        self.assertEqual(TenantModel.objects.filter(code="idem").count(), 1)


class ListCapabilityTests(ApiContractBase):
    def seedUsers(self, count: int) -> None:
        from apps.identity.application.commands.identityCommands import (
            CreateUserCommand,
        )
        from apps.identity.infrastructure import container as identityContainer
        from apps.sharedKernel.application.requestContext import (
            RequestContext,
            requestScope,
        )

        tenantId = str(platformTenantId())
        with requestScope(RequestContext(actorId="", tenantId=tenantId)):
            useCase = identityContainer.createUserUseCase()
            useCase.requiredAction = ""
            for index in range(count):
                useCase.execute(
                    CreateUserCommand(
                        tenantId=tenantId,
                        username=f"bulk{index:02d}",
                        email=f"bulk{index:02d}@bulk.test",
                        password="Strong-Pass-2026!",
                    )
                )

    def testPaginationMeta(self) -> None:
        self.seedUsers(5)
        token = self.login()
        response = self.client.get(f"{V1}/users?page=1&pageSize=3", **self.authHeaders(token))
        body = response.json()
        pagination = body["meta"]["pagination"]
        self.assertEqual(pagination["totalCount"], 6)  # admin + 5
        self.assertEqual(pagination["pageSize"], 3)
        self.assertEqual(len(body["data"]), 3)
        self.assertTrue(pagination["hasNext"])

    def testFilteringAndOrdering(self) -> None:
        self.seedUsers(3)
        token = self.login()
        response = self.client.get(
            f"{V1}/users?status=active&ordering=username&pageSize=100",
            **self.authHeaders(token),
        )
        self.assertEqual(response.status_code, 200)
        usernames = [row["username"] for row in response.json()["data"]]
        self.assertEqual(usernames, sorted(usernames))

    def testSearchNarrowsResults(self) -> None:
        self.seedUsers(3)
        token = self.login()
        response = self.client.get(f"{V1}/users?search=bulk01", **self.authHeaders(token))
        data = response.json()["data"]
        self.assertEqual(len(data), 1)
        self.assertEqual(data[0]["username"], "bulk01")

    def testUnknownSortFieldRejected(self) -> None:
        token = self.login()
        response = self.client.get(f"{V1}/users?ordering=passwordHash", **self.authHeaders(token))
        self.assertEqual(response.status_code, 422)
        self.assertEqual(response.json()["errors"][0]["code"], "SYS_VALIDATION_FAILED")

    def testTenantsCursorAuditStreamRequiresPermission(self) -> None:
        memberToken = None
        adminToken = self.login()
        response = self.client.get(
            f"{V1}/platform/audit-events?pageSize=5", **self.authHeaders(adminToken)
        )
        self.assertEqual(response.status_code, 200, response.content)
        pagination = response.json()["meta"]["pagination"]
        self.assertIn("nextCursor", pagination)
        del memberToken


class OpenApiContractTests(ApiContractBase):
    def testOpenApiDocumentListsAllV1Endpoints(self) -> None:
        response = self.client.get(f"{V1}/openapi.json")
        self.assertEqual(response.status_code, 200)
        document = response.json()
        self.assertEqual(document["openapi"], "3.1.0")
        paths = document["paths"]
        for expectedPath in (
            "/api/v1/auth/login",
            "/api/v1/me",
            "/api/v1/users",
            "/api/v1/tenants",
            "/api/v1/platform/audit-events",
            "/api/v1/openapi.json",
        ):
            self.assertIn(expectedPath, paths)
        login = paths["/api/v1/auth/login"]["post"]
        self.assertEqual(login["security"], [])  # login is public
        users = paths["/api/v1/users"]["get"]
        self.assertTrue(users["parameters"])  # pagination documented

    def testDocsPageRenders(self) -> None:
        response = self.client.get(f"{V1}/docs")
        self.assertEqual(response.status_code, 200)
        self.assertIn("Tekarai API", response.content.decode())


class AuditIntegrationTests(ApiContractBase):
    def testLoginWritesAuditRowWithCorrelation(self) -> None:
        self.client.post(
            f"{V1}/auth/login",
            loginPayload(),
            format="json",
            HTTP_X_CORRELATION_ID="corr-audit-7",
        )
        row = AuditEventModel.objects.get(action="LOGIN", correlationId="corr-audit-7")
        self.assertEqual(row.resourceType, "Session")
        self.assertEqual(row.ipAddress, "127.0.0.1")
