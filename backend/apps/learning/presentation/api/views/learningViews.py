"""Thin, permissioned Phase 16 REST interface."""

from __future__ import annotations

from rest_framework.exceptions import ValidationError
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.learning.application.commands.learningCommands import (
    ArtifactActionCommand,
    BuildDatasetCommand,
    CreateDatasetCommand,
    CreateExperienceCommand,
    CreateExperimentCommand,
    DetectDriftCommand,
    LearningListQuery,
    RecordFeedbackCommand,
    RecordMetricsCommand,
    RunExperimentCommand,
    ValidateDatasetCommand,
)
from apps.learning.infrastructure import container
from apps.learning.presentation.api.serializers.learningSerializers import (
    ArtifactActionSerializer,
    BuildDatasetSerializer,
    DatasetSerializer,
    DriftSerializer,
    ExperienceSerializer,
    ExperimentSerializer,
    FeedbackSerializer,
    MetricsSerializer,
    RunExperimentSerializer,
    ValidateDatasetSerializer,
)
from apps.sharedKernel.presentation.api.permissions import actionPermission
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope


def _validated(serializerClass, data):
    serializer = serializerClass(data=data)
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


class ExperienceListView(APIView):
    def get_permissions(self):
        action = "learning.observe" if self.request.method == "POST" else "learning.view"
        return [actionPermission(action)()]

    def get(self, request: Request) -> Response:
        try:
            limit = int(request.query_params.get("limit", 100))
        except (TypeError, ValueError) as exc:
            raise ValidationError({"limit": "must be an integer"}) from exc
        if limit < 1 or limit > 500:
            raise ValidationError({"limit": "must be between 1 and 500"})
        result = container.queryService().execute(LearningListQuery("experiences", limit))
        return Response(successEnvelope(result))

    @enforceRateLimit("learning:observe")
    def post(self, request: Request) -> Response:
        data = _validated(ExperienceSerializer, request.data)
        result = container.createExperienceService().execute(
            CreateExperienceCommand(
                source=data["source"],
                context=data["context"],
                input=data["input"],
                action=data["action"],
                expectedOutcome=data["expectedOutcome"],
                actualOutcome=data["actualOutcome"],
                reward=data["reward"],
                success=data["success"],
                traceId=data["traceId"],
                metadata=data["metadata"],
            )
        )
        return Response(successEnvelope(result), status=201)


class DatasetListView(APIView):
    def get_permissions(self):
        action = "learning.manage" if self.request.method == "POST" else "learning.view"
        return [actionPermission(action)()]

    def get(self, request: Request) -> Response:
        return Response(
            successEnvelope(container.queryService().execute(LearningListQuery("datasets")))
        )

    @enforceRateLimit("learning:manage")
    def post(self, request: Request) -> Response:
        data = _validated(DatasetSerializer, request.data)
        result = container.createDatasetService().execute(CreateDatasetCommand(**data))
        return Response(successEnvelope(result), status=201)


class DatasetBuildView(APIView):
    permission_classes = [actionPermission("learning.manage")]

    @enforceRateLimit("learning:manage")
    def post(self, request: Request, datasetId: str) -> Response:
        data = _validated(BuildDatasetSerializer, request.data)
        result = container.buildDatasetService().execute(
            BuildDatasetCommand(
                datasetId=datasetId, samples=tuple(dict(sample) for sample in data["samples"])
            )
        )
        return Response(successEnvelope(result))


class DatasetValidateView(APIView):
    permission_classes = [actionPermission("learning.manage")]

    def post(self, request: Request, datasetId: str) -> Response:
        data = _validated(ValidateDatasetSerializer, request.data)
        result = container.validateDatasetService().execute(
            ValidateDatasetCommand(datasetId, data["minimumSamples"])
        )
        return Response(successEnvelope(result))


class ExperimentListView(APIView):
    def get_permissions(self):
        action = "learning.manage" if self.request.method == "POST" else "learning.view"
        return [actionPermission(action)()]

    def get(self, request: Request) -> Response:
        return Response(
            successEnvelope(container.queryService().execute(LearningListQuery("experiments")))
        )

    @enforceRateLimit("learning:manage")
    def post(self, request: Request) -> Response:
        data = _validated(ExperimentSerializer, request.data)
        baseline = str(data["baselineArtifactId"]) if data["baselineArtifactId"] else ""
        result = container.createExperimentService().execute(
            CreateExperimentCommand(
                name=data["name"],
                description=data["description"],
                datasetId=str(data["datasetId"]),
                algorithm=data["algorithm"],
                configuration=data["configuration"],
                baselineArtifactId=baseline,
            )
        )
        return Response(successEnvelope(result), status=201)


class ExperimentRunView(APIView):
    permission_classes = [actionPermission("learning.run")]

    @enforceRateLimit("learning:run")
    def post(self, request: Request, experimentId: str) -> Response:
        data = _validated(RunExperimentSerializer, request.data)
        result = container.queueExperimentService().execute(
            RunExperimentCommand(
                experimentId=experimentId,
                idempotencyKey=data["idempotencyKey"],
                priority=data["priority"],
            )
        )
        return Response(successEnvelope(result), status=202)


class ArtifactListView(APIView):
    permission_classes = [actionPermission("learning.view")]

    def get(self, request: Request) -> Response:
        return Response(
            successEnvelope(container.queryService().execute(LearningListQuery("artifacts")))
        )


class ArtifactDetailView(APIView):
    permission_classes = [actionPermission("learning.view")]

    def get(self, request: Request, artifactId: str) -> Response:
        return Response(
            successEnvelope(
                container.queryService().execute(
                    LearningListQuery("artifacts", identifier=artifactId)
                )
            )
        )


class ArtifactActionView(APIView):
    @enforceRateLimit("learning:action")
    def post(self, request: Request, artifactId: str, action: str) -> Response:
        data = _validated(ArtifactActionSerializer, request.data)
        result = container.artifactLifecycleService().execute(
            ArtifactActionCommand(
                artifactId=artifactId,
                action=action,
                reason=data["reason"],
                environment=data["environment"],
                trafficPercentage=data["trafficPercentage"],
                policy=data["policy"],
            )
        )
        return Response(successEnvelope(result))


class DeploymentListView(APIView):
    permission_classes = [actionPermission("learning.view")]

    def get(self, request: Request) -> Response:
        return Response(
            successEnvelope(container.queryService().execute(LearningListQuery("deployments")))
        )


class JobDetailView(APIView):
    permission_classes = [actionPermission("learning.view")]

    def get(self, request: Request, jobId: str) -> Response:
        return Response(
            successEnvelope(
                container.queryService().execute(LearningListQuery("jobs", identifier=jobId))
            )
        )


class FeedbackView(APIView):
    permission_classes = [actionPermission("learning.feedback")]

    @enforceRateLimit("learning:feedback")
    def post(self, request: Request) -> Response:
        data = _validated(FeedbackSerializer, request.data)
        result = container.feedbackService().execute(
            RecordFeedbackCommand(
                source=data["source"],
                feedbackType=data["feedbackType"],
                experienceId=str(data["experienceId"]) if data["experienceId"] else "",
                deploymentId=str(data["deploymentId"]) if data["deploymentId"] else "",
                artifactId=str(data["artifactId"]) if data["artifactId"] else "",
                humanAction=data["humanAction"],
                score=data["score"],
                comment=data["comment"],
                metadata=data["metadata"],
            )
        )
        return Response(successEnvelope(result), status=201)


class MetricsView(APIView):
    def get_permissions(self):
        action = "learning.monitor" if self.request.method == "POST" else "learning.view"
        return [actionPermission(action)()]

    def get(self, request: Request) -> Response:
        return Response(
            successEnvelope(container.queryService().execute(LearningListQuery("metrics")))
        )

    @enforceRateLimit("learning:monitor")
    def post(self, request: Request) -> Response:
        data = _validated(MetricsSerializer, request.data)
        result = container.monitoringService().execute(
            RecordMetricsCommand(
                artifactId=str(data["artifactId"]),
                deploymentId=str(data["deploymentId"]) if data["deploymentId"] else "",
                metrics=dict(data["metrics"]),
            )
        )
        return Response(successEnvelope(result), status=201)


class DriftView(APIView):
    permission_classes = [actionPermission("learning.monitor")]

    @enforceRateLimit("learning:monitor")
    def post(self, request: Request) -> Response:
        data = _validated(DriftSerializer, request.data)
        result = container.monitoringService().execute(
            DetectDriftCommand(
                artifactId=str(data["artifactId"]),
                driftType=data["driftType"],
                baselineMetrics=dict(data["baselineMetrics"]),
                thresholds=dict(data["thresholds"]),
            )
        )
        return Response(successEnvelope(result))
