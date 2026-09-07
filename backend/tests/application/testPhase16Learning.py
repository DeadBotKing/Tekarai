"""Phase 16 domain/application/infrastructure lifecycle tests."""

from __future__ import annotations

import uuid
from unittest import mock

from django.utils import timezone

from apps.identity.infrastructure.models import (
    PermissionModel,
    RoleModel,
    RolePermissionModel,
    UserRoleModel,
)
from apps.learning.application.commands.learningCommands import (
    ArtifactActionCommand,
    BuildDatasetCommand,
    CreateDatasetCommand,
    CreateExperienceCommand,
    CreateExperimentCommand,
    DetectDriftCommand,
    ProcessLearningJobCommand,
    RecordFeedbackCommand,
    RecordMetricsCommand,
    RunExperimentCommand,
    ValidateDatasetCommand,
)
from apps.learning.domain.entities.learningRecords import LearningDataset, LearningExperiment
from apps.learning.domain.valueObjects.learningTypes import compareMetrics, safePayload
from apps.learning.infrastructure import container
from apps.learning.infrastructure.persistence.models import (
    LearningApprovalModel,
    LearningArtifactModel,
    LearningAuditModel,
    LearningDeploymentModel,
    LearningEventModel,
    LearningExperienceModel,
    LearningJobModel,
    LearningRunModel,
    LearningSampleModel,
    LearningSnapshotModel,
    ModelVersionModel,
    PolicyVersionModel,
)
from apps.learning.infrastructure.queue.learningQueue import CeleryLearningJobQueue
from apps.sharedKernel.domain.errors import ConflictError, ValidationFailedError
from tests.application.testPhase12UseCases import Phase12Base

ACTIONS = (
    "learning.view",
    "learning.observe",
    "learning.manage",
    "learning.run",
    "learning.approve",
    "learning.deploy",
    "learning.feedback",
    "learning.monitor",
)


def grantLearning(user, tenant):
    role, _ = RoleModel.objects.get_or_create(
        code=f"learning-admin-{user.id}", defaults={"name": "Learning Admin", "scopeType": "TENANT"}
    )
    for action in ACTIONS:
        permission, _ = PermissionModel.objects.get_or_create(
            code=action, defaults={"module": "learning"}
        )
        RolePermissionModel.objects.get_or_create(
            roleId=role.id, actionPattern=action, defaults={"permissionId": permission.id}
        )
    UserRoleModel.objects.get_or_create(
        userId=user.id, roleId=role.id, scopeType="TENANT", defaults={"tenantId": tenant.id}
    )
    from apps.identity.infrastructure.services.authorizationCache import bumpVersion

    bumpVersion(user.id)


class Phase16LearningTests(Phase12Base):
    def setUp(self):
        super().setUp()
        grantLearning(self.admin, self.tenant)
        grantLearning(self.u2, self.tenant)
        self.artifactRoot = self.settings(LEARNING_ARTIFACT_ROOT="/tmp/tekarai-learning-tests")
        self.artifactRoot.enable()
        self.addCleanup(self.artifactRoot.disable)

    def createApprovedDataset(self):
        with self.context(self.tenant, self.admin):
            experience = container.createExperienceService().execute(
                CreateExperienceCommand(
                    source="tasks",
                    context={"team": "ops"},
                    input={"load": 3},
                    action="assign",
                    expectedOutcome={"duration": 10},
                    actualOutcome={"duration": 8},
                    traceId=uuid.uuid4().hex,
                    reward=0.8,
                    success=True,
                )
            )
            dataset = container.createDatasetService().execute(
                CreateDatasetCommand(
                    name=f"dataset-{uuid.uuid4().hex[:6]}", version="1.0.0", source="experiences"
                )
            )
            built = container.buildDatasetService().execute(
                BuildDatasetCommand(
                    datasetId=str(dataset["id"]),
                    samples=(
                        {
                            "input": {"load": 3},
                            "target": {"duration": 8},
                            "context": {"team": "ops"},
                            "sourceExperienceId": experience["id"],
                            "weight": 1.0,
                        },
                    ),
                )
            )
            approved = container.validateDatasetService().execute(
                ValidateDatasetCommand(str(dataset["id"]), 1)
            )
        self.assertEqual(built["sampleCount"], 1)
        self.assertEqual(approved["status"], "APPROVED")
        return approved

    def createArtifact(self, version="1.0.0", name="routing-model"):
        dataset = self.createApprovedDataset()
        with self.context(self.tenant, self.admin):
            experiment = container.createExperimentService().execute(
                CreateExperimentCommand(
                    name=f"experiment-{uuid.uuid4().hex[:6]}",
                    datasetId=str(dataset["id"]),
                    algorithm="deterministic",
                    configuration={
                        "artifactName": name,
                        "artifactVersion": version,
                        "randomSeed": 7,
                    },
                )
            )
            with mock.patch.object(container.jobQueue(), "publish", autospec=True):
                # Container returns a fresh queue, so patch the class method instead below.
                pass
            with mock.patch(
                "apps.learning.infrastructure.queue.learningQueue.CeleryLearningJobQueue.publish"
            ) as publish:
                job = container.queueExperimentService().execute(
                    RunExperimentCommand(str(experiment["id"]), f"job-{uuid.uuid4().hex}")
                )
                publish.assert_called_once()
        result = container.processJobService().execute(ProcessLearningJobCommand(jobId=job["id"]))
        return result["artifact"], experiment, job

    def testDomainTransitionsAndRegressionRules(self):
        now = timezone.now()
        dataset = LearningDataset(
            uuid.uuid4(),
            self.tenant.id,
            "d",
            "1.0.0",
            "",
            "s",
            "DRAFT",
            0,
            "",
            now,
            self.admin.id,
            {},
        )
        dataset.moveTo("BUILDING", now)
        dataset.moveTo("READY", now)
        self.assertEqual(dataset.status, "READY")
        experiment = LearningExperiment(
            uuid.uuid4(),
            self.tenant.id,
            "e",
            "",
            dataset.id,
            dataset.version,
            "algo",
            {},
            None,
            "CREATED",
            now,
            None,
            self.admin.id,
        )
        experiment.start(now)
        experiment.complete(now)
        self.assertEqual(experiment.status, "COMPLETED")
        passed, failures = compareMetrics(
            {"accuracy": 0.9, "latencyMs": 50},
            {"accuracy": 0.91, "latencyMs": 40},
            minimums={"accuracy": 0.8},
            maximumRegression={"latencyMs": 5},
        )
        self.assertFalse(passed)
        self.assertTrue(failures)

    def testExperienceImmutableTraceAndSecretRejection(self):
        command = CreateExperienceCommand(
            source="ops",
            context={},
            input={"x": 1},
            action="act",
            expectedOutcome={},
            actualOutcome={},
            traceId="stable-trace",
        )
        with self.context(self.tenant, self.admin):
            first = container.createExperienceService().execute(command)
            second = container.createExperienceService().execute(command)
            self.assertEqual(first["id"], second["id"])
            with self.assertRaises(ConflictError):
                container.createExperienceService().execute(
                    CreateExperienceCommand(
                        source="ops",
                        context={},
                        input={"x": 2},
                        action="act",
                        expectedOutcome={},
                        actualOutcome={},
                        traceId="stable-trace",
                    )
                )
        with self.assertRaises(ValidationFailedError):
            safePayload({"apiToken": "forbidden"})
        self.assertEqual(LearningExperienceModel.objects.count(), 1)

    def testDatasetRequiresSourcedSamplesAndIsTenantScoped(self):
        dataset = self.createApprovedDataset()
        self.assertEqual(LearningSampleModel.objects.count(), 1)
        self.assertTrue(dataset["datasetHash"])
        self.assertIsNone(
            container.store().getDataset(self.other.id, uuid.UUID(str(dataset["id"])))
        )

    def testAsyncRunIsIdempotentReproducibleAndVersioned(self):
        artifact, experiment, job = self.createArtifact()
        self.assertTrue(artifact["checksum"])
        self.assertEqual(LearningJobModel.objects.get(id=job["id"]).status, "COMPLETED")
        run = LearningRunModel.objects.get(experimentId=experiment["id"])
        self.assertEqual(run.randomSeed, 7)
        self.assertEqual(run.status, "COMPLETED")
        self.assertEqual(
            container.processJobService().execute(ProcessLearningJobCommand(job["id"]))["status"],
            "COMPLETED",
        )
        self.assertEqual(LearningArtifactModel.objects.count(), 1)

    def evaluateValidateApprove(self, artifact):
        with self.context(self.tenant, self.admin):
            evaluation = container.artifactLifecycleService().execute(
                ArtifactActionCommand(str(artifact["id"]), "evaluate")
            )
            validation = container.artifactLifecycleService().execute(
                ArtifactActionCommand(
                    str(artifact["id"]), "validate", policy={"minimums": {"accuracy": 0.5}}
                )
            )
            with self.assertRaises(ConflictError):
                container.artifactLifecycleService().execute(
                    ArtifactActionCommand(str(artifact["id"]), "approve", reason="self approval")
                )
        with self.context(self.tenant, self.u2):
            approval = container.artifactLifecycleService().execute(
                ArtifactActionCommand(str(artifact["id"]), "approve", reason="validated candidate")
            )
        self.assertEqual(validation["decision"], "PASSED")
        self.assertEqual(approval["decision"], "APPROVED")
        return evaluation

    def deployFully(self, artifact):
        result = None
        for stage in (5, 25, 50, 100):
            with self.context(self.tenant, self.admin):
                result = container.artifactLifecycleService().execute(
                    ArtifactActionCommand(str(artifact["id"]), "deploy", trafficPercentage=stage)
                )
                if stage < 100:
                    container.monitoringService().execute(
                        RecordMetricsCommand(
                            artifactId=str(artifact["id"]),
                            deploymentId=result["id"],
                            metrics={"accuracy": 0.9, "errorRate": 0.1},
                        )
                    )
        self.assertIsNotNone(result)
        assert result is not None
        self.assertEqual(result["status"], "ACTIVE")
        return result

    def testEvaluationApprovalCanaryAndRollbackRestoreStable(self):
        first, _exp1, _job1 = self.createArtifact("1.0.0")
        self.evaluateValidateApprove(first)
        firstDeployment = self.deployFully(first)
        second, _exp2, _job2 = self.createArtifact("1.1.0")
        self.evaluateValidateApprove(second)
        secondDeployment = self.deployFully(second)
        self.assertEqual(
            LearningDeploymentModel.objects.get(id=firstDeployment["id"]).status, "SUPERSEDED"
        )
        with self.context(self.tenant, self.admin):
            restored = container.artifactLifecycleService().execute(
                ArtifactActionCommand(
                    str(second["id"]), "rollback", reason="performance regression"
                )
            )
        self.assertEqual(restored["restoredDeploymentId"], firstDeployment["id"])
        self.assertEqual(
            LearningDeploymentModel.objects.get(id=secondDeployment["id"]).status, "ROLLED_BACK"
        )
        self.assertTrue(LearningSnapshotModel.objects.exists())
        self.assertEqual(LearningApprovalModel.objects.count(), 2)

    def testFeedbackMonitoringDriftEventsAndAudit(self):
        artifact, _experiment, _job = self.createArtifact()
        with self.context(self.tenant, self.admin):
            feedback = container.feedbackService().execute(
                RecordFeedbackCommand(
                    source="operator",
                    feedbackType="HUMAN",
                    artifactId=str(artifact["id"]),
                    humanAction="RATE",
                    score=-0.4,
                    comment="regressed",
                )
            )
            container.monitoringService().execute(
                RecordMetricsCommand(
                    artifactId=str(artifact["id"]), metrics={"accuracy": 0.6, "latencyMs": 100}
                )
            )
            drift = container.monitoringService().execute(
                DetectDriftCommand(
                    artifactId=str(artifact["id"]),
                    baselineMetrics={"accuracy": 0.9, "latencyMs": 40},
                    thresholds={"accuracy": 0.1, "latencyMs": 0.2},
                )
            )
        self.assertEqual(feedback["source"], "operator")
        self.assertTrue(drift["detected"])
        self.assertTrue(LearningEventModel.objects.filter(eventType="DriftDetected").exists())
        self.assertGreater(LearningAuditModel.objects.count(), 0)

    def testQueuePublishesOnlyAfterDatabaseCommitAndTasksAreRegistered(self):
        queue = CeleryLearningJobQueue()
        with mock.patch(
            "apps.learning.infrastructure.queue.learningJobs.processLearningJob.delay"
        ) as delay:
            with self.captureOnCommitCallbacks(execute=True):
                queue.publish("job-id")
                delay.assert_not_called()
            delay.assert_called_once_with("job-id")
        from config.celery import app

        self.assertIn("learning.processJob", app.tasks)
        self.assertIn("learning.monitorDeployments", app.tasks)

    def testValidationFailureCannotBeApprovedOrDeployed(self):
        artifact, _experiment, _job = self.createArtifact()
        with self.context(self.tenant, self.admin):
            container.artifactLifecycleService().execute(
                ArtifactActionCommand(str(artifact["id"]), "evaluate")
            )
            result = container.artifactLifecycleService().execute(
                ArtifactActionCommand(
                    str(artifact["id"]),
                    "validate",
                    policy={"minimums": {"accuracy": 1.0}, "safetyPassed": False},
                )
            )
            self.assertEqual(result["decision"], "FAILED")
            with self.assertRaises(ConflictError):
                container.artifactLifecycleService().execute(
                    ArtifactActionCommand(str(artifact["id"]), "deploy")
                )

    def testModelAndPolicyVersionRecordsAreImmutable(self):
        model, _experiment, _job = self.createArtifact("2.0.0", "versioned-model")
        self.assertTrue(ModelVersionModel.objects.filter(artifactId=model["id"]).exists())
        dataset = self.createApprovedDataset()
        with self.context(self.tenant, self.admin):
            experiment = container.createExperimentService().execute(
                CreateExperimentCommand(
                    name=f"policy-{uuid.uuid4().hex[:6]}",
                    datasetId=str(dataset["id"]),
                    algorithm="policy-builder",
                    configuration={
                        "artifactName": "routing-policy",
                        "artifactVersion": "1.0.0",
                        "artifactType": "POLICY",
                    },
                )
            )
            with mock.patch(
                "apps.learning.infrastructure.queue.learningQueue.CeleryLearningJobQueue.publish"
            ):
                job = container.queueExperimentService().execute(
                    RunExperimentCommand(str(experiment["id"]), f"job-{uuid.uuid4().hex}")
                )
        policy = container.processJobService().execute(ProcessLearningJobCommand(job["id"]))[
            "artifact"
        ]
        self.assertTrue(PolicyVersionModel.objects.filter(artifactId=policy["id"]).exists())
        self.assertEqual(LearningArtifactModel.objects.filter(name="routing-policy").count(), 1)

    def testFailedRunNeverCreatesArtifact(self):
        dataset = self.createApprovedDataset()
        with self.context(self.tenant, self.admin):
            experiment = container.createExperimentService().execute(
                CreateExperimentCommand(
                    name=f"bad-{uuid.uuid4().hex[:6]}",
                    datasetId=str(dataset["id"]),
                    algorithm="broken",
                    configuration={"artifactVersion": "1.0.0"},
                )
            )
            with mock.patch(
                "apps.learning.infrastructure.queue.learningQueue.CeleryLearningJobQueue.publish"
            ):
                job = container.queueExperimentService().execute(
                    RunExperimentCommand(str(experiment["id"]), f"job-{uuid.uuid4().hex}")
                )
        with mock.patch.object(
            container.learningEngine(), "train", side_effect=RuntimeError("boom")
        ):
            # Patch the configured class because the composition root creates fresh adapters.
            with mock.patch(
                "apps.learning.infrastructure.learning.deterministicEngine.DeterministicLearningEngine.train",
                side_effect=RuntimeError("boom"),
            ):
                with self.assertRaises(RuntimeError):
                    container.processJobService().execute(ProcessLearningJobCommand(job["id"]))
        self.assertEqual(LearningJobModel.objects.get(id=job["id"]).status, "FAILED")
        self.assertFalse(
            LearningArtifactModel.objects.filter(
                metadata__experimentId=str(experiment["id"])
            ).exists()
        )
