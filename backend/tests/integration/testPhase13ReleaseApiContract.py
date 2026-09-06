"""Phase 13-Z public REST, async worker, security and release contract."""

from __future__ import annotations

import uuid

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.ai.infrastructure.models import AIAgentDefinitionModel, AIJobModel
from apps.ai.management.commands.runAiWorker import buildQueueService
from apps.identity.infrastructure.models import RoleModel, UserModel, UserRoleModel
from apps.tenancy.infrastructure.models import TenantModel
from tests.support.phase6Helpers import (
    PLATFORM_ADMIN_PASSWORD,
    PLATFORM_ADMIN_USERNAME,
    seedPlatform,
)
from tests.support.phase8Helpers import ensureUser
from tests.support.phase9Helpers import sessionTokenFor

BASE = "/api/v1/ai"


class Phase13ReleaseApiBase(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenant = TenantModel.objects.get(code="platform")
        self.admin = UserModel.objects.get(username=PLATFORM_ADMIN_USERNAME)
        self.client = APIClient()
        login = self.client.post(
            "/api/v1/auth/login",
            {
                "tenantCode": "platform",
                "identifier": PLATFORM_ADMIN_USERNAME,
                "password": PLATFORM_ADMIN_PASSWORD,
            },
            format="json",
        )
        self.assertEqual(login.status_code, 200, login.content)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {login.json()['data']['accessToken']}"}

    def registerApproved(self, code: str = "RELEASE_ASSISTANT", risk: str = "LOW") -> dict:
        created = self.client.post(
            f"{BASE}/agents",
            {
                "code": code,
                "name": "Release assistant",
                "instructions": "Return a concise release answer.",
                "riskLevel": risk,
                "modelPolicy": {"provider": "DETERMINISTIC", "model": "test"},
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(created.status_code, 201, created.content)
        version = created.json()["data"]["version"]
        submitted = self.client.post(
            f"{BASE}/agents/{code}/versions/{version}/submit", {}, format="json", **self.auth
        )
        self.assertEqual(submitted.status_code, 200, submitted.content)
        approved = self.client.post(
            f"{BASE}/agents/{code}/versions/{version}/approve", {}, format="json", **self.auth
        )
        self.assertEqual(approved.status_code, 200, approved.content)
        return approved.json()["data"]


class AgentRegistryApiTests(Phase13ReleaseApiBase):
    def testAuthenticationIsMandatory(self) -> None:
        response = self.client.get(f"{BASE}/agents")
        self.assertEqual(response.status_code, 401)
        self.assertFalse(response.json()["success"])

    def testRegistryLifecycleAndReadEnvelope(self) -> None:
        approved = self.registerApproved()
        self.assertEqual(approved["status"], "APPROVED")
        listed = self.client.get(f"{BASE}/agents?status=APPROVED", **self.auth)
        self.assertEqual(listed.status_code, 200, listed.content)
        self.assertTrue(listed.json()["success"])
        self.assertEqual(listed.json()["meta"]["count"], 1)
        # Instructions are write-only at the public boundary.
        self.assertNotIn("instructions", listed.json()["data"][0])

    def testTenantIsolationHidesForeignDefinitions(self) -> None:
        AIAgentDefinitionModel.objects.create(
            tenantId=uuid.uuid4(),
            code="FOREIGN_AGENT",
            version=1,
            name="Foreign",
            instructions="never visible",
            status="APPROVED",
        )
        response = self.client.get(f"{BASE}/agents", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        self.assertFalse(any(item["code"] == "FOREIGN_AGENT" for item in response.json()["data"]))

    def testValidationEnvelopeAndUnknownAction(self) -> None:
        response = self.client.post(f"{BASE}/agents", {}, format="json", **self.auth)
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertTrue(response.json()["errors"])


class AgentRunApiTests(Phase13ReleaseApiBase):
    def testSynchronousRunUsesOfflineProviderAndPersistsSteps(self) -> None:
        self.registerApproved()
        response = self.client.post(
            f"{BASE}/agents/RELEASE_ASSISTANT/runs",
            {"input": {"task": "verify release"}, "mode": "SYNC"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201, response.content)
        body = response.json()["data"]
        self.assertTrue(body["executed"])
        self.assertEqual(body["run"]["status"], "COMPLETED")
        runId = body["run"]["runId"]
        steps = self.client.get(f"{BASE}/runs/{runId}/steps", **self.auth)
        self.assertEqual(steps.status_code, 200, steps.content)
        self.assertGreaterEqual(steps.json()["meta"]["count"], 1)

    def testAsyncRunIsIdempotentRedactedAndWorkerExecutesIt(self) -> None:
        self.registerApproved(code="ASYNC_ASSISTANT")
        payload = {
            "input": {"task": "async", "apiKey": "must-not-persist"},
            "mode": "ASYNC",
            "idempotencyKey": "release-job-1",
        }
        first = self.client.post(
            f"{BASE}/agents/ASYNC_ASSISTANT/runs", payload, format="json", **self.auth
        )
        second = self.client.post(
            f"{BASE}/agents/ASYNC_ASSISTANT/runs", payload, format="json", **self.auth
        )
        self.assertEqual(first.status_code, 202, first.content)
        self.assertEqual(first.json()["data"]["jobId"], second.json()["data"]["jobId"])
        row = AIJobModel.objects.get(id=first.json()["data"]["jobId"])
        self.assertEqual(row.payload["input"]["apiKey"], "[REDACTED]")

        report = buildQueueService().tick(tenantId=row.tenantId, limit=10)
        self.assertEqual(report.succeeded, 1)
        detail = self.client.get(f"{BASE}/jobs/{row.id}", **self.auth)
        self.assertEqual(detail.json()["data"]["status"], "SUCCEEDED")
        self.assertNotIn("payload", detail.json()["data"])
        self.assertEqual(detail.json()["data"]["resultSummary"]["runStatus"], "COMPLETED")

    def testHighRiskApprovalRequiresAnotherUserAndCanBeResumed(self) -> None:
        self.registerApproved(code="GOVERNED_ASSISTANT", risk="HIGH")
        pending = self.client.post(
            f"{BASE}/agents/GOVERNED_ASSISTANT/runs",
            {"input": {"task": "governed"}},
            format="json",
            **self.auth,
        )
        self.assertEqual(pending.status_code, 202, pending.content)
        approvalId = pending.json()["data"]["approval"]["approvalId"]

        reviewer = ensureUser(self.tenant, "phase13-reviewer")
        role = RoleModel.objects.get(code="tenantAdmin")
        UserRoleModel.objects.create(
            userId=reviewer.id, roleId=role.id, tenantId=self.tenant.id, scopeType="TENANT"
        )
        reviewerToken = sessionTokenFor(reviewer.id, self.tenant.id)
        reviewerAuth = {"HTTP_AUTHORIZATION": f"Bearer {reviewerToken}"}
        granted = self.client.post(
            f"{BASE}/approvals/{approvalId}/grant", {}, format="json", **reviewerAuth
        )
        self.assertEqual(granted.status_code, 200, granted.content)
        self.assertEqual(granted.json()["data"]["decision"], "GRANTED")

        resumed = self.client.post(
            f"{BASE}/agents/GOVERNED_ASSISTANT/runs",
            {"input": {"task": "governed"}, "approvalId": approvalId},
            format="json",
            **self.auth,
        )
        self.assertEqual(resumed.status_code, 201, resumed.content)
        self.assertEqual(resumed.json()["data"]["run"]["status"], "COMPLETED")

    def testAsyncRunRequiresIdempotencyKey(self) -> None:
        self.registerApproved(code="IDEMPOTENT_ASSISTANT")
        response = self.client.post(
            f"{BASE}/agents/IDEMPOTENT_ASSISTANT/runs",
            {"input": {}, "mode": "ASYNC"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 400)


class ReleaseReadinessApiTests(Phase13ReleaseApiBase):
    def testReadinessHasNoSecretsAndMigrationsAreApplied(self) -> None:
        response = self.client.get(f"{BASE}/release/readiness", **self.auth)
        self.assertEqual(response.status_code, 200, response.content)
        data = response.json()["data"]
        self.assertTrue(data["ready"])
        self.assertEqual(data["checks"]["pendingAiMigrations"], [])
        self.assertIn("DETERMINISTIC", data["checks"]["configuredProviders"])
        self.assertNotIn("apiKey", str(data))
