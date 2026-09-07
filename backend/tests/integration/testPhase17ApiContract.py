"""Phase 17 authentication, authorization, tenancy and complete API contract tests."""

from __future__ import annotations

import tempfile
import uuid
from pathlib import Path
from unittest import mock

from apps.projectIntelligence.application.commands.intelligenceCommands import (
    ProcessIntelligenceJobCommand,
)
from apps.projectIntelligence.infrastructure import container
from tests.application.testPhase17ProjectIntelligence import grantIntelligence
from tests.integration.testPhase12ApiContract import Phase12ApiBase
from tests.support.phase8Helpers import ensureTenant, ensureUser
from tests.support.phase9Helpers import sessionTokenFor


class Phase17ApiContractTests(Phase12ApiBase):
    def setUp(self):
        super().setUp()
        grantIntelligence(self.admin, self.tenant)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        (root / "project").mkdir()
        (root / "project" / "main.py").write_text("import os\nprint('ok')\n")
        (root / "project" / "README.md").write_text("# Demo\n")
        override = self.settings(
            PROJECT_INTELLIGENCE_WORKSPACE_ROOT=root,
            PROJECT_INTELLIGENCE_ARTIFACT_ROOT=root / "artifacts",
            PROJECT_INTELLIGENCE_MAX_FILES=1000,
            PROJECT_INTELLIGENCE_MAX_FILE_BYTES=100000,
            PROJECT_INTELLIGENCE_CACHE_TTL_SECONDS=3600,
        )
        override.enable()
        self.addCleanup(override.disable)
        self.projectId = uuid.uuid4()
        self.base = f"/api/v1/projects/{self.projectId}/intelligence"

    def testAllProjectIntelligenceEndpointsRequireAuthentication(self):
        for method, path in (
            ("get", "/"),
            ("post", "/snapshot/"),
            ("post", "/analyze/"),
            ("post", "/reanalyze/"),
            ("get", "/state/"),
            ("get", "/architecture/"),
            ("get", "/dependencies/"),
            ("get", "/insights/"),
            ("get", "/recommendations/"),
            ("get", "/context/"),
            ("post", "/context/build/"),
            ("get", "/resume/"),
            ("get", "/changes/"),
            ("post", "/compare/"),
        ):
            response = getattr(self.client, method)(self.base + path, {}, format="json")
            self.assertEqual(response.status_code, 401, (path, response.content))

    def testSnapshotWorkspaceBoundaryAndReadContract(self):
        escaped = self.client.post(
            self.base + "/snapshot/", {"workspace": "../"}, format="json", **self.auth()
        )
        self.assertEqual(escaped.status_code, 422, escaped.content)
        created = self.client.post(
            self.base + "/snapshot/", {"workspace": "project"}, format="json", **self.auth()
        )
        self.assertEqual(created.status_code, 201, created.content)
        state = self.client.get(self.base + "/state/", **self.auth())
        self.assertEqual(state.status_code, 200, state.content)
        self.assertEqual(state.json()["data"]["status"], "READY")

    def testAsyncAnalysisAllReadEndpointsContextAndCompare(self):
        with (
            mock.patch(
                "apps.projectIntelligence.infrastructure.queue.intelligenceQueue.CeleryIntelligenceJobQueue.publish"
            ) as publish,
            self.captureOnCommitCallbacks(execute=True),
        ):
            queued = self.client.post(
                self.base + "/analyze/",
                {"workspace": "project", "idempotencyKey": "api-analysis"},
                format="json",
                **self.auth(),
            )
        self.assertEqual(queued.status_code, 202, queued.content)
        publish.assert_called_once()
        jobId = uuid.UUID(queued.json()["data"]["id"])
        container.processJobService().execute(ProcessIntelligenceJobCommand(jobId))
        job = self.client.get(f"/api/v1/project-intelligence/jobs/{jobId}/", **self.auth())
        self.assertEqual(job.status_code, 200, job.content)
        self.assertEqual(job.json()["data"]["status"], "COMPLETED")
        for path in (
            "/",
            "/state/",
            "/architecture/",
            "/dependencies/",
            "/insights/",
            "/recommendations/",
            "/resume/",
            "/changes/",
        ):
            response = self.client.get(self.base + path, **self.auth())
            self.assertEqual(response.status_code, 200, (path, response.content))
        context = self.client.post(
            self.base + "/context/build/",
            {"task": "update main output", "tokenBudget": 512},
            format="json",
            **self.auth(),
        )
        self.assertEqual(context.status_code, 201, context.content)
        self.assertEqual(
            context.json()["data"]["knowledgeId"],
            self.client.get(self.base + "/", **self.auth()).json()["data"]["knowledge"]["id"],
        )
        snapshots = self.client.get(self.base + "/", **self.auth()).json()["data"]
        first = snapshots["state"]["snapshotId"]
        compared = self.client.post(
            self.base + "/compare/", {"fromSnapshotId": first}, format="json", **self.auth()
        )
        self.assertEqual(compared.status_code, 200, compared.content)
        self.assertEqual(compared.json()["data"]["modified"], [])

    def testOrdinaryUserCannotAnalyzeOrBuildContext(self):
        token = sessionTokenFor(self.u1.id, self.tenant.id)
        auth = {"HTTP_AUTHORIZATION": f"Bearer {token}"}
        for path, payload in (
            ("/snapshot/", {"workspace": "project"}),
            ("/analyze/", {"workspace": "project"}),
            ("/context/build/", {"task": "x", "tokenBudget": 256}),
        ):
            response = self.client.post(self.base + path, payload, format="json", **auth)
            self.assertEqual(response.status_code, 403, response.content)

    def testTenantIsolationHidesAnotherTenantProject(self):
        container.pipeline().run(self.tenant.id, self.admin.id, self.projectId, "project")
        other = ensureTenant("phase17-other")
        alien = ensureUser(other, "phase17-alien")
        grantIntelligence(alien, other)
        token = sessionTokenFor(alien.id, other.id)
        response = self.client.get(self.base + "/state/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertIsNone(response.json()["data"])
