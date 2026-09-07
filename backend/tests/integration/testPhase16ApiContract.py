"""Phase 16 authentication, authorization, CRUD and lifecycle API tests."""

from __future__ import annotations

import uuid
from unittest import mock

from apps.learning.application.commands.learningCommands import ProcessLearningJobCommand
from apps.learning.infrastructure import container
from tests.application.testPhase16Learning import grantLearning
from tests.integration.testPhase12ApiContract import Phase12ApiBase
from tests.support.phase8Helpers import ensureTenant, ensureUser
from tests.support.phase9Helpers import sessionTokenFor

BASE = "/api/v1/learning"


class Phase16ApiContractTests(Phase12ApiBase):
    def setUp(self):
        super().setUp()
        grantLearning(self.admin, self.tenant)

    def createDatasetPipeline(self):
        experience = self.client.post(
            f"{BASE}/experiences/",
            {
                "source": "api",
                "context": {},
                "input": {"x": 1},
                "action": "predict",
                "expectedOutcome": {"y": 1},
                "actualOutcome": {"y": 1},
                "traceId": uuid.uuid4().hex,
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(experience.status_code, 201, experience.content)
        dataset = self.client.post(
            f"{BASE}/datasets/",
            {"name": f"api-data-{uuid.uuid4().hex[:5]}", "version": "1.0.0", "source": "api"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(dataset.status_code, 201, dataset.content)
        datasetId = dataset.json()["data"]["id"]
        built = self.client.post(
            f"{BASE}/datasets/{datasetId}/build/",
            {
                "samples": [
                    {
                        "input": {"x": 1},
                        "target": {"y": 1},
                        "sourceExperienceId": experience.json()["data"]["id"],
                    }
                ]
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(built.status_code, 200, built.content)
        validated = self.client.post(
            f"{BASE}/datasets/{datasetId}/validate/",
            {"minimumSamples": 1},
            format="json",
            **self.auth(),
        )
        self.assertEqual(validated.status_code, 200, validated.content)
        return datasetId

    def testAllEndpointsRequireAuthentication(self):
        for method, path in (
            ("get", "experiences/"),
            ("get", "datasets/"),
            ("get", "experiments/"),
            ("get", "artifacts/"),
            ("get", "deployments/"),
            ("get", "metrics/"),
            ("post", "feedback/"),
        ):
            response = getattr(self.client, method)(f"{BASE}/{path}", {}, format="json")
            self.assertEqual(response.status_code, 401, (path, response.content))

    def testDatasetExperimentAsyncJobAndArtifactContract(self):
        datasetId = self.createDatasetPipeline()
        experiment = self.client.post(
            f"{BASE}/experiments/",
            {
                "name": f"api-exp-{uuid.uuid4().hex[:5]}",
                "datasetId": datasetId,
                "algorithm": "deterministic",
                "configuration": {
                    "artifactName": f"api-model-{uuid.uuid4().hex[:5]}",
                    "artifactVersion": "1.0.0",
                },
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(experiment.status_code, 201, experiment.content)
        experimentId = experiment.json()["data"]["id"]
        with mock.patch(
            "apps.learning.infrastructure.queue.learningQueue.CeleryLearningJobQueue.publish"
        ) as publish:
            queued = self.client.post(
                f"{BASE}/experiments/{experimentId}/run/",
                {"idempotencyKey": f"api-job-{uuid.uuid4().hex}"},
                format="json",
                **self.auth(),
            )
        self.assertEqual(queued.status_code, 202, queued.content)
        publish.assert_called_once()
        jobId = queued.json()["data"]["id"]
        result = container.processJobService().execute(ProcessLearningJobCommand(jobId))
        job = self.client.get(f"{BASE}/jobs/{jobId}/", **self.auth())
        self.assertEqual(job.status_code, 200, job.content)
        self.assertEqual(job.json()["data"]["status"], "COMPLETED")
        artifactId = result["artifact"]["id"]
        detail = self.client.get(f"{BASE}/artifacts/{artifactId}/", **self.auth())
        self.assertEqual(detail.status_code, 200, detail.content)
        evaluated = self.client.post(
            f"{BASE}/artifacts/{artifactId}/evaluate/", {}, format="json", **self.auth()
        )
        self.assertEqual(evaluated.status_code, 200, evaluated.content)
        validated = self.client.post(
            f"{BASE}/artifacts/{artifactId}/validate/",
            {"policy": {"minimums": {"accuracy": 0.5}}},
            format="json",
            **self.auth(),
        )
        self.assertEqual(validated.status_code, 200, validated.content)

    def testOrdinaryUserCannotManageLearning(self):
        token = sessionTokenFor(self.u1.id, self.tenant.id)
        response = self.client.post(
            f"{BASE}/datasets/",
            {"name": "forbidden", "version": "1.0.0", "source": "user"},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(response.status_code, 403, response.content)
        deploy = self.client.post(
            f"{BASE}/artifacts/{uuid.uuid4()}/deploy/",
            {},
            format="json",
            HTTP_AUTHORIZATION=f"Bearer {token}",
        )
        self.assertEqual(deploy.status_code, 403, deploy.content)

    def testTenantIsolationForLists(self):
        self.createDatasetPipeline()
        other = ensureTenant("learning_api_other")
        alien = ensureUser(other, "learning_api_alien")
        grantLearning(alien, other)
        token = sessionTokenFor(alien.id, other.id)
        response = self.client.get(f"{BASE}/datasets/", HTTP_AUTHORIZATION=f"Bearer {token}")
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"], [])

    def testFeedbackRequiresSourceEntity(self):
        response = self.client.post(
            f"{BASE}/feedback/",
            {"source": "operator", "feedbackType": "HUMAN", "score": 0.5},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 422, response.content)
