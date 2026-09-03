"""Phase 7 integration tests — §37 security matrix over HTTP, plus the §32
endpoint contract, JWT/refresh lifecycle and API-key authentication."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.identity.infrastructure.models import (
    ApiKeyModel,
    SessionModel,
    UserModel,
)
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_PASSWORD,
    PLATFORM_ADMIN_USERNAME,
    loginPayload,
    platformTenantId,
    seedPlatform,
)

V1 = "/api/v1"


class Phase7ApiBase(TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        seedPlatform()
        self.client = APIClient()

    # -- helpers --------------------------------------------------------------

    def adminUserId(self) -> str:
        user = UserModel.objects.get(username=PLATFORM_ADMIN_USERNAME)
        return str(user.id)

    def login(self, identifier: str = PLATFORM_ADMIN_USERNAME) -> dict:
        response = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "identifier": identifier,
                "password": PLATFORM_ADMIN_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertIn("accessToken", data)
        self.assertIn("refreshToken", data)
        return data

    def auth(self, accessToken: str) -> dict[str, str]:
        return {"HTTP_AUTHORIZATION": f"Bearer {accessToken}"}

    def createMember(self, username: str, roleCode: str = "member") -> str:
        """Fresh tenant user + ACTIVE membership + preset role → userId."""
        from apps.identity.application.commands.identityCommands import CreateUserCommand
        from apps.identity.domain.entities.tenantMembership import TenantMembership
        from apps.identity.infrastructure import container as identityContainer
        from apps.identity.infrastructure.models import RoleModel
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            AccessRepositoryDjango,
            TenantMembershipRepositoryDjango,
        )
        from apps.sharedKernel.application.requestContext import (
            RequestContext,
            requestScope,
        )

        tenantId = platformTenantId()
        with requestScope(RequestContext(actorId="", tenantId=str(tenantId))):
            useCase = identityContainer.createUserUseCase()
            useCase.requiredAction = ""
            user = useCase.execute(
                CreateUserCommand(
                    tenantId=str(tenantId),
                    username=username,
                    email=f"{username}@member.test",
                    password="Strong-Pass-2026!",
                )
            )
        membershipRepository = TenantMembershipRepositoryDjango()
        if membershipRepository.get(uuid.UUID(user.id), tenantId) is None:
            membershipRepository.create(
                TenantMembership.establish(
                    userId=uuid.UUID(user.id),
                    tenantId=tenantId,
                    now=datetime.now(tz=UTC),
                )
            )
        role = RoleModel.objects.get(code=roleCode)
        AccessRepositoryDjango().grantRoleToUser(uuid.UUID(user.id), tenantId, role.id)
        return user.id

    def memberLogin(
        self, username: str, password: str = "Strong-Pass-2026!", tenantCode: str = "platform"
    ) -> dict:
        response = self.client.post(
            f"{V1}/auth/login",
            {"tenantCode": tenantCode, "identifier": username, "password": password},
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]


class SecurityMatrixTests(Phase7ApiBase):
    """§37 — the ten scenarios, end to end."""

    def testS1SameTenantAllowed(self) -> None:
        admin = self.login()
        response = self.client.get(f"{V1}/users", **self.auth(admin["accessToken"]))
        self.assertEqual(response.status_code, 200, response.content)

    def testS2CrossTenantDenied(self) -> None:
        from apps.sharedKernel.application.requestContext import (
            RequestContext,
            requestScope,
        )
        from apps.tenancy.application.commands.tenantCommands import (
            CreateTenantCommand,
        )
        from apps.tenancy.infrastructure import container as tenancyContainer

        admin = self.login()
        # tenant A = platform; tenant B = branch
        with requestScope(
            RequestContext(actorId=self.adminUserId(), tenantId=str(platformTenantId()))
        ):
            tenantB = tenancyContainer.createTenantUseCase().execute(
                CreateTenantCommand(code="branch-b", name="Branch B")
            )
        self.createMember("tenant-admin-a", roleCode="tenantAdmin")

        # a tenant-B user (tenantAdmin scope B) tries to list tenant A users
        from apps.identity.application.commands.identityCommands import (
            CreateUserCommand,
        )
        from apps.identity.domain.entities.tenantMembership import TenantMembership
        from apps.identity.infrastructure import container as identityContainer
        from apps.identity.infrastructure.models import RoleModel
        from apps.identity.infrastructure.repositories.identityRepositoriesImpl import (
            AccessRepositoryDjango,
            TenantMembershipRepositoryDjango,
        )

        with requestScope(RequestContext(actorId="", tenantId=tenantB.id)):
            useCase = identityContainer.createUserUseCase()
            useCase.requiredAction = ""
            userB = useCase.execute(
                CreateUserCommand(
                    tenantId=tenantB.id,
                    username="admin-b",
                    email="admin-b@b.test",
                    password="Strong-Pass-2026!",
                )
            )
        TenantMembershipRepositoryDjango().create(
            TenantMembership.establish(
                uuid.UUID(userB.id),
                uuid.UUID(tenantB.id),
                datetime.now(tz=UTC),
            )
        )
        AccessRepositoryDjango().grantRoleToUser(
            uuid.UUID(userB.id),
            uuid.UUID(tenantB.id),
            RoleModel.objects.get(code="tenantAdmin").id,
        )

        tokens = self.memberLogin("admin-b", tenantCode="branch-b")
        response = self.client.get(
            f"{V1}/users",
            {"tenantId": str(platformTenantId())},
            **self.auth(tokens["accessToken"]),
        )
        self.assertEqual(response.status_code, 403, f"A→B must be denied: {response.content}")
        self.assertIn(
            response.json()["errors"][0]["code"],
            ("PERM_PERMISSION_DENIED", "TENANT_ACCESS_DENIED"),
        )
        del admin

    def testS3NoPermissionDenied(self) -> None:
        self.createMember("plain-member")
        tokens = self.memberLogin("plain-member")
        response = self.client.post(
            f"{V1}/users",
            {"username": "x", "email": "x@x.test", "password": "Strong-Pass-2026!"},
            format="json",
            **self.auth(tokens["accessToken"]),
        )
        self.assertEqual(response.status_code, 403)
        self.assertEqual(response.json()["errors"][0]["code"], "PERM_PERMISSION_DENIED")

    def testS4RevokedRoleDeniedImmediately(self) -> None:
        userId = self.createMember("revoked-role-user", roleCode="tenantAdmin")
        tokens = self.memberLogin("revoked-role-user")
        ok = self.client.get(f"{V1}/users", **self.auth(tokens["accessToken"]))
        self.assertEqual(ok.status_code, 200, ok.content)

        self.login()
        from apps.identity.infrastructure.models import RoleModel, UserRoleModel

        roleId = RoleModel.objects.get(code="tenantAdmin").id
        UserRoleModel.objects.filter(userId=uuid.UUID(userId), roleId=roleId).delete()
        from apps.identity.infrastructure.services.authorizationCache import bumpVersion

        bumpVersion(uuid.UUID(userId))  # §28 invalidation
        denied = self.client.get(f"{V1}/users", **self.auth(tokens["accessToken"]))
        self.assertEqual(denied.status_code, 403, denied.content)
        self.assertEqual(denied.json()["errors"][0]["code"], "PERM_PERMISSION_DENIED")

    def testS5DisabledUserCannotLogin(self) -> None:
        userId = self.createMember("to-be-disabled")
        UserModel.objects.filter(id=uuid.UUID(userId)).update(status="disabled")
        response = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "identifier": "to-be-disabled",
                "password": "Strong-Pass-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 401, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "AUTH_AUTHENTICATION_REQUIRED")

    def testS6RevokedSessionInvalidImmediately(self) -> None:
        admin = self.login()
        refresh = self.client.post(
            f"{V1}/auth/refresh",
            {"refreshToken": admin["refreshToken"]},
            format="json",
        ).json()["data"]
        # revoke the session (logout everywhere from the same session)
        response = self.client.post(
            f"{V1}/me/sessions/revoke-all",
            {},
            format="json",
            **self.auth(refresh["accessToken"]),
        )
        self.assertEqual(response.status_code, 200, response.content)
        denied = self.client.get(f"{V1}/me", **self.auth(refresh["accessToken"]))
        self.assertEqual(denied.status_code, 401, denied.content)
        self.assertEqual(denied.json()["errors"][0]["code"], "AUTH_AUTHENTICATION_REQUIRED")

    def testS7ExpiredSessionTokenDenied(self) -> None:
        admin = self.login()
        session = SessionModel.objects.latest("issuedAt")
        SessionModel.objects.filter(id=session.id).update(
            expiresAt=datetime.now(tz=UTC) - timedelta(minutes=1)
        )
        denied = self.client.get(f"{V1}/me", **self.auth(admin["accessToken"]))
        self.assertEqual(denied.status_code, 401)

    def testS8ApiKeyExpiredDenied(self) -> None:
        admin = self.login()
        created = self.client.post(
            f"{V1}/api-keys",
            {
                "tenantId": str(platformTenantId()),
                "name": "short-lived",
                "expiresAt": (datetime.now(tz=UTC) - timedelta(minutes=1)).isoformat(),
            },
            format="json",
            **self.auth(admin["accessToken"]),
        )
        self.assertEqual(created.status_code, 200, created.content)
        rawKey = created.json()["data"]["rawKey"]
        response = self.client.get(f"{V1}/me", HTTP_X_API_KEY=rawKey)
        self.assertEqual(response.status_code, 401, response.content)

    def testS9SuspendedMembershipInactive(self) -> None:
        userId = self.createMember("suspended-member")
        from apps.identity.infrastructure.models import TenantMembershipModel

        TenantMembershipModel.objects.filter(
            userId=uuid.UUID(userId), tenantId=platformTenantId()
        ).update(status="suspended")
        response = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "identifier": "suspended-member",
                "password": "Strong-Pass-2026!",
            },
            format="json",
        )
        self.assertEqual(response.status_code, 403, response.content)
        self.assertEqual(response.json()["errors"][0]["code"], "TENANT_ACCESS_DENIED")

    def testS10RevokedApiKeyDenied(self) -> None:
        admin = self.login()
        created = self.client.post(
            f"{V1}/api-keys",
            {"tenantId": str(platformTenantId()), "name": "to-revoke"},
            format="json",
            **self.auth(admin["accessToken"]),
        )
        data = created.json()["data"]
        revoked = self.client.delete(
            f"{V1}/api-keys/{data['apiKey']['id']}",
            **self.auth(admin["accessToken"]),
        )
        self.assertEqual(revoked.status_code, 200, revoked.content)
        response = self.client.get(f"{V1}/me", HTTP_X_API_KEY=data["rawKey"])
        self.assertEqual(response.status_code, 401, response.content)


class TokenLifecycleTests(Phase7ApiBase):
    def testAccessJwtShortLivedAndRefreshRotates(self) -> None:
        pair = self.login()
        self.assertLessEqual(pair["expiresIn"], 15 * 60, "§8 short-lived access")

        # access token works
        ok = self.client.get(f"{V1}/me", **self.auth(pair["accessToken"]))
        self.assertEqual(ok.status_code, 200)

        # refresh rotation: old refresh token becomes worthless
        refreshed = self.client.post(
            f"{V1}/auth/refresh", {"refreshToken": pair["refreshToken"]}, format="json"
        )
        self.assertEqual(refreshed.status_code, 200, refreshed.content)
        tokens2 = refreshed.json()["data"]
        self.assertNotEqual(tokens2["refreshToken"], pair["refreshToken"])
        self.assertNotEqual(tokens2["accessToken"], pair["accessToken"])

        replay = self.client.post(
            f"{V1}/auth/refresh", {"refreshToken": pair["refreshToken"]}, format="json"
        )
        self.assertEqual(replay.status_code, 401, replay.content)

    def testTamperedAccessTokenRejected(self) -> None:
        pair = self.login()
        tampered = pair["accessToken"][:-3] + "aaa"
        denied = self.client.get(f"{V1}/me", **self.auth(tampered))
        self.assertEqual(denied.status_code, 401)

    def testUnknownRefreshTokenRejected(self) -> None:
        response = self.client.post(
            f"{V1}/auth/refresh", {"refreshToken": "not-a-real-token"}, format="json"
        )
        self.assertEqual(response.status_code, 401)


class ApiSurfaceTests(Phase7ApiBase):
    def testApiKeyAuthenticationWorks(self) -> None:
        admin = self.login()
        created = self.client.post(
            f"{V1}/api-keys",
            {"tenantId": str(platformTenantId()), "name": "ci-key"},
            format="json",
            **self.auth(admin["accessToken"]),
        )
        rawKey = created.json()["data"]["rawKey"]
        self.assertTrue(rawKey.startswith("tek_"))
        row = ApiKeyModel.objects.get(name="ci-key")
        self.assertNotEqual(row.keyHash, rawKey, "§22 — hash only")
        response = self.client.get(f"{V1}/me", HTTP_X_API_KEY=rawKey)
        self.assertEqual(response.status_code, 200, response.content)

    def testRawKeyShownOnlyOnce(self) -> None:
        admin = self.login()
        created = self.client.post(
            f"{V1}/api-keys",
            {"tenantId": str(platformTenantId()), "name": "once-key"},
            format="json",
            **self.auth(admin["accessToken"]),
        ).json()["data"]
        listing = self.client.get(f"{V1}/api-keys", **self.auth(admin["accessToken"])).json()[
            "data"
        ]
        self.assertEqual(len(listing), 1)
        self.assertNotIn("rawKey", listing[0])
        self.assertNotIn(created["rawKey"], str(listing))

    def testPasswordChangeEndpointRevokesSessions(self) -> None:
        pair = self.login()
        changed = self.client.post(
            f"{V1}/auth/password/change",
            {
                "currentPassword": PLATFORM_ADMIN_PASSWORD,
                "newPassword": "Rotated-Secret-8!",
            },
            format="json",
            **self.auth(pair["accessToken"]),
        )
        self.assertEqual(changed.status_code, 200, changed.content)
        dead = self.client.get(f"{V1}/me", **self.auth(pair["accessToken"]))
        self.assertEqual(dead.status_code, 401, "sessions revoked on change")

    def testPasswordResetEndpoints(self) -> None:
        request = self.client.post(
            f"{V1}/auth/password/reset/request",
            {"tenantCode": "platform", "identifier": PLATFORM_ADMIN_USERNAME},
            format="json",
        )
        self.assertEqual(request.status_code, 200, request.content)
        token = request.json()["data"]["resetToken"]
        self.assertTrue(token)

        weak = self.client.post(
            f"{V1}/auth/password/reset/confirm",
            {"token": token, "newPassword": "short"},
            format="json",
        )
        self.assertEqual(weak.status_code, 422, weak.content)  # §23 policy

        confirmed = self.client.post(
            f"{V1}/auth/password/reset/confirm",
            {"token": token, "newPassword": "Rotated-Secret-8!"},
            format="json",
        )
        self.assertEqual(confirmed.status_code, 200, confirmed.content)

        replay = self.client.post(
            f"{V1}/auth/password/reset/confirm",
            {"token": token, "newPassword": "Another-Secret-9!"},
            format="json",
        )
        self.assertEqual(replay.status_code, 401, "single-use token (§25)")

        relogin = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "identifier": PLATFORM_ADMIN_USERNAME,
                "password": "Rotated-Secret-8!",
            },
            format="json",
        )
        self.assertEqual(relogin.status_code, 200, relogin.content)

    def testResetRequestForUnknownAccountIsOpaque(self) -> None:
        response = self.client.post(
            f"{V1}/auth/password/reset/request",
            {"tenantCode": "platform", "identifier": "ghost@nowhere.test"},
            format="json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertFalse(response.json()["data"]["resetToken"])

    def testRolesEndpointsRequirePermission(self) -> None:
        admin = self.login()
        created = self.client.post(
            f"{V1}/roles",
            {"code": "auditor", "name": "Auditor", "actions": ["audit.view"]},
            format="json",
            **self.auth(admin["accessToken"]),
        )
        self.assertEqual(created.status_code, 200, created.content)

        self.createMember("no-role-admin")
        member = self.memberLogin("no-role-admin")
        denied = self.client.post(
            f"{V1}/roles",
            {"code": "hacker", "name": "H", "actions": ["user.view"]},
            format="json",
            **self.auth(member["accessToken"]),
        )
        self.assertEqual(denied.status_code, 403)

    def testSessionsSelfServiceEndpoints(self) -> None:
        self.login()  # session 1
        pair = self.login()  # session 2 (current)
        listed = self.client.get(f"{V1}/me/sessions", **self.auth(pair["accessToken"])).json()[
            "data"
        ]
        self.assertEqual(len(listed), 2)
        current = [s for s in listed if s["current"]]
        self.assertEqual(len(current), 1, "§9 — current session marked")
        other = [s for s in listed if not s["current"]][0]
        revoked = self.client.delete(
            f"{V1}/me/sessions/{other['id']}", **self.auth(pair["accessToken"])
        )
        self.assertEqual(revoked.status_code, 200, revoked.content)
        after = self.client.get(f"{V1}/me/sessions", **self.auth(pair["accessToken"])).json()[
            "data"
        ]
        self.assertEqual(len(after), 1)

    def testMfaEndpointFlow(self) -> None:
        pair = self.login()
        setup = self.client.post(
            f"{V1}/me/mfa/setup", {}, format="json", **self.auth(pair["accessToken"])
        ).json()["data"]
        self.assertIn("otpauth://", setup["otpauthUrl"])

        from apps.identity.domain.services import totpService

        code = totpService.currentCode(setup["secret"])
        confirmed = self.client.post(
            f"{V1}/me/mfa/confirm",
            {"factorId": setup["factorId"], "code": code},
            format="json",
            **self.auth(pair["accessToken"]),
        ).json()["data"]
        self.assertEqual(len(confirmed["recoveryCodes"]), 8)

        # next login demands the second factor
        challenge = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "identifier": PLATFORM_ADMIN_USERNAME,
                "password": PLATFORM_ADMIN_PASSWORD,
            },
            format="json",
        ).json()["data"]
        self.assertTrue(challenge["mfaRequired"])
        self.assertFalse(challenge["accessToken"])

        tokens = self.client.post(
            f"{V1}/auth/mfa/challenge",
            {"challengeToken": challenge["mfaChallenge"], "code": code},
            format="json",
        ).json()["data"]
        self.assertTrue(tokens["accessToken"])

    def testServiceAccountEndpoints(self) -> None:
        admin = self.login()
        created = self.client.post(
            f"{V1}/service-accounts",
            {
                "tenantId": str(platformTenantId()),
                "code": "agent-7",
                "name": "Deploy Agent",
            },
            format="json",
            **self.auth(admin["accessToken"]),
        )
        self.assertEqual(created.status_code, 200, created.content)
        accountId = created.json()["data"]["id"]
        disabled = self.client.post(
            f"{V1}/service-accounts/{accountId}",
            {"action": "disable"},
            format="json",
            **self.auth(admin["accessToken"]),
        )
        self.assertEqual(disabled.status_code, 200, disabled.content)
        self.assertEqual(disabled.json()["data"]["status"], "disabled")

    def testVerificationEndpoints(self) -> None:
        admin = self.login()
        sent = self.client.post(
            f"{V1}/auth/verification/send",
            {"userId": self.adminUserId(), "channel": "email"},
            format="json",
            **self.auth(admin["accessToken"]),
        )
        self.assertEqual(sent.status_code, 200, sent.content)
        token = sent.json()["data"]["token"]
        verified = self.client.post(f"{V1}/auth/verify-email", {"token": token}, format="json")
        self.assertEqual(verified.status_code, 200, verified.content)
        replay = self.client.post(f"{V1}/auth/verify-email", {"token": token}, format="json")
        self.assertEqual(replay.status_code, 401, "single-use (§26)")


class LoginIdentifierTests(Phase7ApiBase):
    def testLoginByEmail(self) -> None:
        response = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "identifier": "platform-admin@tekarai.local",
                "password": PLATFORM_ADMIN_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertTrue(response.json()["data"]["accessToken"])

    def testOldUsernameFieldRejectedWithValidation(self) -> None:
        response = self.client.post(
            f"{V1}/auth/login", loginPayload() | {"identifier": None}, format="json"
        )
        self.assertIn(response.status_code, (400, 200))
        del response
        legacy = self.client.post(
            f"{V1}/auth/login",
            {
                "tenantCode": "platform",
                "username": PLATFORM_ADMIN_USERNAME,
                "password": PLATFORM_ADMIN_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(legacy.status_code, 400, "legacy field no longer accepted")
