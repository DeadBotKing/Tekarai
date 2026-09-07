"""Thin authenticated Project Intelligence REST contract."""

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projectIntelligence.application.commands.intelligenceCommands import (
    AnalyzeProjectCommand,
    BuildContextCommand,
    CompareSnapshotsCommand,
    CreateSnapshotCommand,
    IntelligenceQuery,
)
from apps.projectIntelligence.infrastructure import container
from apps.projectIntelligence.presentation.api.serializers.intelligenceSerializers import (
    AnalyzeSerializer,
    CompareSerializer,
    ContextSerializer,
    WorkspaceSerializer,
)
from apps.sharedKernel.presentation.api.permissions import actionPermission
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope


def valid(cls, data):
    item = cls(data=data)
    item.is_valid(raise_exception=True)
    return item.validated_data


class OverviewView(APIView):
    permission_classes = [actionPermission("projectIntelligence.view")]

    def get(self, request: Request, projectId) -> Response:
        result = {
            kind: container.queryService().execute(IntelligenceQuery(str(projectId), kind))
            for kind in (
                "state",
                "architecture",
                "knowledge",
                "insights",
                "recommendations",
                "context",
                "resume",
            )
        }
        return Response(successEnvelope(result))


class SnapshotView(APIView):
    permission_classes = [actionPermission("projectIntelligence.manage")]

    @enforceRateLimit("project-intelligence:snapshot")
    def post(self, request: Request, projectId) -> Response:
        data = valid(WorkspaceSerializer, request.data)
        result = container.snapshotService().execute(
            CreateSnapshotCommand(str(projectId), data["workspace"])
        )
        return Response(successEnvelope(result), status=201)


class AnalyzeView(APIView):
    permission_classes = [actionPermission("projectIntelligence.analyze")]
    incremental = False

    @enforceRateLimit("project-intelligence:analyze")
    def post(self, request: Request, projectId) -> Response:
        data = valid(AnalyzeSerializer, request.data)
        result = container.queueService().execute(
            AnalyzeProjectCommand(
                str(projectId),
                data["workspace"],
                self.incremental,
                data["idempotencyKey"],
                data["priority"],
            )
        )
        return Response(successEnvelope(result), status=202)


class ReanalyzeView(AnalyzeView):
    incremental = True


class DataView(APIView):
    permission_classes = [actionPermission("projectIntelligence.view")]
    kind = "state"

    def get(self, request: Request, projectId) -> Response:
        return Response(
            successEnvelope(
                container.queryService().execute(IntelligenceQuery(str(projectId), self.kind))
            )
        )


class StateView(DataView):
    kind = "state"


class ArchitectureView(DataView):
    kind = "architecture"


class DependenciesView(DataView):
    kind = "dependencies"


class InsightsView(DataView):
    kind = "insights"


class RecommendationsView(DataView):
    kind = "recommendations"


class ContextView(DataView):
    kind = "context"


class ResumeView(DataView):
    kind = "resume"


class ChangesView(DataView):
    kind = "changes"


class BuildContextView(APIView):
    permission_classes = [actionPermission("projectIntelligence.context")]

    @enforceRateLimit("project-intelligence:context")
    def post(self, request: Request, projectId) -> Response:
        data = valid(ContextSerializer, request.data)
        result = container.contextService().execute(
            BuildContextCommand(str(projectId), data["task"], data["tokenBudget"])
        )
        return Response(successEnvelope(result), status=201)


class CompareView(APIView):
    permission_classes = [actionPermission("projectIntelligence.view")]

    def post(self, request: Request, projectId) -> Response:
        data = valid(CompareSerializer, request.data)
        target = str(data.get("toSnapshotId") or "")
        result = container.compareService().execute(
            CompareSnapshotsCommand(str(projectId), str(data["fromSnapshotId"]), target)
        )
        return Response(successEnvelope(result))


class JobView(APIView):
    permission_classes = [actionPermission("projectIntelligence.view")]

    def get(self, request: Request, jobId) -> Response:
        return Response(successEnvelope(container.jobQueryService().execute(jobId)))
