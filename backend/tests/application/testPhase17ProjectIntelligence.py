"""Phase 17 domain, analyzer, pipeline, integrity and failure-path tests."""

from __future__ import annotations

import os
import tempfile
import uuid
from pathlib import Path

from apps.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)
from apps.projectIntelligence.application.commands.intelligenceCommands import (
    BuildContextCommand,
    ProcessIntelligenceJobCommand,
)
from apps.projectIntelligence.domain.entities.intelligenceRecords import (
    ProjectDecision,
    ProjectInsight,
    ProjectRecommendation,
    ProjectState,
)
from apps.projectIntelligence.domain.services.intelligenceEngines import (
    ChangeDetector,
)
from apps.projectIntelligence.infrastructure import container
from apps.projectIntelligence.infrastructure.agentContextProvider import (
    ProjectIntelligenceAgentContextProvider,
)
from apps.projectIntelligence.infrastructure.analyzers.builtinAnalyzers import (
    ArchitectureAnalyzer,
    DependencyAnalyzer,
    FrameworkAnalyzer,
    LanguageAnalyzer,
)
from apps.projectIntelligence.infrastructure.filesystem.secureWorkspace import SecureWorkspaceReader
from apps.projectIntelligence.infrastructure.persistence.models import (
    IntelligenceAuditModel,
    IntelligenceEventModel,
    ProjectAnalysisResultModel,
    ProjectContextPackageModel,
    ProjectDecisionModel,
    ProjectInsightModel,
    ProjectKnowledgeEdgeModel,
    ProjectKnowledgeModel,
    ProjectKnowledgeNodeModel,
    ProjectRecommendationModel,
    ProjectSnapshotModel,
)
from apps.sharedKernel.application.requestContext import RequestContext, requestScope
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError
from tests.application.testPhase12UseCases import Phase12Base


def ctx(tenantId, userId):
    return requestScope(
        RequestContext(actorId=str(userId), tenantId=str(tenantId), actorTenantId=str(tenantId))
    )


ACTIONS = (
    "projectIntelligence.view",
    "projectIntelligence.manage",
    "projectIntelligence.analyze",
    "projectIntelligence.context",
)


def grantIntelligence(user, tenant):
    role, _ = RoleModel.objects.get_or_create(
        code=f"pi-admin-{user.id}",
        defaults={"name": "Project Intelligence Admin", "scopeType": "TENANT"},
    )
    for action in ACTIONS:
        permission, _ = PermissionModel.objects.get_or_create(
            code=action, defaults={"module": "projectIntelligence"}
        )
        RolePermissionModel.objects.get_or_create(
            roleId=role.id, actionPattern=action, defaults={"permissionId": permission.id}
        )
    UserRoleModel.objects.get_or_create(
        userId=user.id, roleId=role.id, scopeType="TENANT", defaults={"tenantId": tenant.id}
    )
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion

    bumpVersion(user.id)


class Phase17ProjectIntelligenceTests(Phase12Base):
    def setUp(self):
        super().setUp()
        grantIntelligence(self.admin, self.tenant)
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.workspace = root / "demo"
        self.workspace.mkdir()
        (self.workspace / "app").mkdir()
        (self.workspace / "tests").mkdir()
        (self.workspace / "docs").mkdir()
        (self.workspace / "app" / "service.py").write_text(
            "import django\nfrom app import domain\n\ndef run():\n    return 1\n"
        )
        (self.workspace / "app" / "domain.py").write_text("VALUE = 1\n")
        (self.workspace / "tests" / "test_service.py").write_text("from app.service import run\n")
        (self.workspace / "docs" / "architecture.md").write_text("# Architecture\nLayered design\n")
        (self.workspace / "pyproject.toml").write_text('[project]\ndependencies=["django"]\n')
        self.override = self.settings(
            PROJECT_INTELLIGENCE_WORKSPACE_ROOT=root,
            PROJECT_INTELLIGENCE_ARTIFACT_ROOT=root / "artifacts",
            PROJECT_INTELLIGENCE_MAX_FILES=1000,
            PROJECT_INTELLIGENCE_MAX_FILE_BYTES=100000,
            PROJECT_INTELLIGENCE_CACHE_TTL_SECONDS=3600,
        )
        self.override.enable()
        self.addCleanup(self.override.disable)
        self.projectId = uuid.uuid4()

    def testDomainInvariantsVersioningAndEvidence(self):
        now = container.kernel()["clock"].nowUtc()
        state = ProjectState(uuid.uuid4(), self.tenant.id, self.projectId, "INITIALIZING", now)
        state.moveTo("SCANNING", now)
        with self.assertRaises(ConflictError):
            state.moveTo("READY", now)
        with self.assertRaises(ValidationFailedError):
            ProjectInsight(
                uuid.uuid4(),
                self.tenant.id,
                self.projectId,
                uuid.uuid4(),
                "X",
                "bad",
                "HIGH",
                0.9,
                [],
                "test",
                "impact",
                now,
            )
        with self.assertRaises(ValidationFailedError):
            ProjectRecommendation(
                uuid.uuid4(),
                self.tenant.id,
                self.projectId,
                uuid.uuid4(),
                1,
                "p",
                "r",
                "why",
                [],
                "benefit",
                "risk",
                "HIGH",
                now,
            )
        with self.assertRaises(ValidationFailedError):
            ProjectDecision(
                uuid.uuid4(),
                self.tenant.id,
                self.projectId,
                uuid.uuid4(),
                1,
                "ACCEPT",
                [],
                "why",
                now,
            )

    def testWorkspaceBoundarySymlinksBinaryAndGeneratedFiles(self):
        outside = Path(self.temp.name) / "outside.txt"
        outside.write_text("secret")
        try:
            os.symlink(outside, self.workspace / "escape.txt")
        except OSError:
            pass
        (self.workspace / "binary.bin").write_bytes(b"\0\1")
        (self.workspace / "bundle.min.js").write_text("x")
        (self.workspace / "signing.pem").write_text("-----BEGIN PRIVATE KEY-----\nsecret")
        reader = SecureWorkspaceReader(Path(self.temp.name))
        files = reader.scan("demo")
        by = {x["path"]: x for x in files}
        self.assertNotIn("escape.txt", by)
        self.assertTrue(by["binary.bin"]["binary"])
        self.assertTrue(by["bundle.min.js"]["generated"])
        self.assertTrue(by["signing.pem"]["secretNamed"])
        self.assertEqual(by["signing.pem"]["content"], "")
        for unsafe in ("../", "/etc", "C:\\Windows"):
            with self.assertRaises(ValidationFailedError):
                reader.scan(unsafe)

    def testSnapshotIsImmutableReproducibleAndStoredWithIntegrity(self):
        actor = self.admin.id
        snapshot, _ = container.pipeline().createSnapshot(
            self.tenant.id, actor, self.projectId, "demo"
        )
        self.assertEqual(ProjectSnapshotModel.objects.count(), 1)
        persisted = ProjectSnapshotModel.objects.get()
        persisted.workspace = "tampered"
        with self.assertRaises(ValueError):
            persisted.save()
        self.assertTrue(
            container.storage().verify(snapshot["artifactUri"], snapshot["snapshotHash"])
        )
        again, _ = container.pipeline().createSnapshot(
            self.tenant.id, actor, self.projectId, "demo"
        )
        self.assertTrue(again["unchanged"])
        self.assertEqual(ProjectSnapshotModel.objects.count(), 1)
        analyzed = container.pipeline().run(self.tenant.id, actor, self.projectId, "demo")
        self.assertEqual(analyzed["analysis"]["status"], "COMPLETED")

    def testLanguageFrameworkDependencyAndArchitectureAnalyzers(self):
        files = SecureWorkspaceReader(Path(self.temp.name)).scan("demo")
        snapshot = {"files": files, "gitState": {}, "createdAt": "fixed"}
        language = LanguageAnalyzer().analyze(snapshot)
        framework = FrameworkAnalyzer().analyze(snapshot)
        dependency = DependencyAnalyzer().analyze(snapshot)
        architecture = ArchitectureAnalyzer().analyze(snapshot)
        self.assertEqual(language["findings"][0]["language"], "Python")
        self.assertIn("Django", [x["framework"] for x in framework["findings"]])
        self.assertGreater(dependency["metrics"]["dependencyCount"], 0)
        self.assertIn("architectureViolations", architecture["metrics"])
        self.assertTrue(
            all(x["resultHash"] for x in (language, framework, dependency, architecture))
        )

    def testCompletePipelineBuildsEveryEvidenceLayer(self):
        result = container.pipeline().run(self.tenant.id, self.admin.id, self.projectId, "demo")
        self.assertEqual(result["analysis"]["status"], "COMPLETED")
        self.assertEqual(ProjectAnalysisResultModel.objects.count(), 9)
        self.assertEqual(ProjectKnowledgeModel.objects.count(), 1)
        self.assertGreater(ProjectKnowledgeNodeModel.objects.count(), 1)
        self.assertGreater(ProjectKnowledgeEdgeModel.objects.count(), 1)
        self.assertEqual(
            ProjectInsightModel.objects.count(), ProjectRecommendationModel.objects.count()
        )
        self.assertEqual(
            ProjectRecommendationModel.objects.count(), ProjectDecisionModel.objects.count()
        )
        self.assertTrue(IntelligenceAuditModel.objects.exists())
        self.assertTrue(IntelligenceEventModel.objects.exists())

    def testAnalyzerFailureIsIsolatedAndRecorded(self):
        class Broken:
            name = "broken"
            version = "1.0.0"

            def analyze(self, snapshot):
                raise RuntimeError("isolated")

        pipeline = container.pipeline()
        pipeline.analyzers = (*pipeline.analyzers, Broken())
        result = pipeline.run(self.tenant.id, self.admin.id, self.projectId, "demo")
        self.assertEqual(result["analysis"]["status"], "PARTIAL")
        failed = ProjectAnalysisResultModel.objects.get(analyzerName="broken")
        self.assertEqual(failed.status, "FAILED")
        self.assertEqual(failed.errors[0]["type"], "RuntimeError")
        self.assertNotIn("isolated", failed.errors[0]["message"])

    def testIncrementalChangeDetectionAndAnalysis(self):
        first = container.pipeline().run(self.tenant.id, self.admin.id, self.projectId, "demo")
        (self.workspace / "app" / "service.py").write_text("def run():\n return 2\n")
        second = container.pipeline().run(
            self.tenant.id, self.admin.id, self.projectId, "demo", True
        )
        self.assertTrue(second["analysis"]["incremental"])
        self.assertIn("app/service.py", second["analysis"]["affectedFiles"])
        comparison = ChangeDetector().compare(first["snapshot"], second["snapshot"])
        self.assertEqual(comparison["modified"], ["app/service.py"])
        documentation = ProjectAnalysisResultModel.objects.filter(
            analysisId=second["analysis"]["id"], analyzerName="documentation"
        ).get()
        self.assertTrue(documentation.metadata["cacheHit"])

    def testContextBudgetExcludesSecretsAndIsVersionLinked(self):
        (self.workspace / "api-token.txt").write_text("do not expose")
        container.pipeline().run(self.tenant.id, self.admin.id, self.projectId, "demo")
        with ctx(self.tenant.id, self.admin.id):
            result = container.contextService().execute(
                BuildContextCommand(str(self.projectId), "change service run", 256)
            )
        self.assertEqual(result["tokenBudget"], 256)
        self.assertNotIn("api-token.txt", result["includedFiles"])
        self.assertTrue(result["snapshotId"])
        self.assertTrue(result["knowledgeId"])
        self.assertEqual(ProjectContextPackageModel.objects.count(), 1)

    def testAgentIntegrationProvidesTenantBoundVersionedContext(self):
        container.pipeline().run(self.tenant.id, self.admin.id, self.projectId, "demo")
        with ctx(self.tenant.id, self.admin.id):
            container.contextService().execute(
                BuildContextCommand(str(self.projectId), "inspect service", 512)
            )
        source = ProjectIntelligenceAgentContextProvider().latest(self.tenant.id, self.projectId)
        self.assertEqual(source.sourceDomain, "projectIntelligence")
        self.assertEqual(source.tenantId, self.tenant.id)
        self.assertTrue(source.metadata["contextHash"])

    def testQueueIdempotencyAndWorkerCompletion(self):
        store = container.store()
        job = store.createJob(
            self.tenant.id,
            self.projectId,
            self.admin.id,
            {
                "jobType": "ANALYZE",
                "idempotencyKey": "stable-key",
                "metadata": {"workspace": "demo"},
            },
        )
        again = store.createJob(
            self.tenant.id,
            self.projectId,
            self.admin.id,
            {
                "jobType": "ANALYZE",
                "idempotencyKey": "stable-key",
                "metadata": {"workspace": "demo"},
            },
        )
        self.assertEqual(job["id"], again["id"])
        done = container.processJobService().execute(
            ProcessIntelligenceJobCommand(uuid.UUID(job["id"]))
        )
        self.assertEqual(done["status"], "COMPLETED")
        self.assertEqual(
            container.processJobService().execute(
                ProcessIntelligenceJobCommand(uuid.UUID(job["id"]))
            ),
            {"status": "SKIPPED"},
        )
        transient = store.createJob(
            self.tenant.id,
            self.projectId,
            self.admin.id,
            {"jobType": "ANALYZE", "idempotencyKey": "retry-key", "metadata": {}},
        )
        store.claimJob(uuid.UUID(transient["id"]), container.kernel()["clock"].nowUtc())
        retried = store.retryJob(uuid.UUID(transient["id"]), "OSError")
        self.assertEqual(retried["status"], "QUEUED")
        self.assertEqual(retried["retryCount"], 1)
