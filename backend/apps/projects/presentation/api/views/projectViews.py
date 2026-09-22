"""Project API views (Phase 18b) — HTTP orchestration only."""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.projects.application.commands.projectCommands import (
    ChangeProjectStatusCommand,
    CreateProjectCommand,
    UpdateProjectCommand,
)
from apps.projects.application.queries.projectQueries import GetProjectQuery, ListProjectsQuery
from apps.projects.infrastructure import container
from apps.projects.presentation.api.serializers.projectSerializers import (
    ChangeProjectStatusSerializer,
    CreateProjectSerializer,
    UpdateProjectSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope

PROJECT_ERRORS = [
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "PERM_PERMISSION_DENIED",
    "CONF_DUPLICATE_BUSINESS_CODE",
    "STATE_INVALID_TRANSITION",
]


class ProjectListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListProjectsQuery(
            status=str(request.query_params.get("status", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=int(request.query_params.get("page", 1) or 1),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
        )
        useCase = container.listProjectsUseCase()
        useCase.requiredAction = "project.list"
        dto = useCase.execute(query)
        return Response(successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = CreateProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.createProjectUseCase().execute(
            CreateProjectCommand(
                tenantId=str(request.data.get("tenantId", "")),
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
                description=str(serializer.validated_data["description"]),
                ownerName=str(serializer.validated_data["ownerName"]),
                dueDate=str(serializer.validated_data["dueDate"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class ProjectDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, projectId: str) -> Response:
        dto = container.getProjectUseCase().execute(GetProjectQuery(projectId=str(projectId)))
        return Response(successEnvelope(asDict(dto)))

    def patch(self, request: Request, projectId: str) -> Response:
        serializer = UpdateProjectSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.updateProjectUseCase().execute(
            UpdateProjectCommand(
                projectId=str(projectId),
                name=str(serializer.validated_data["name"]),
                description=str(serializer.validated_data["description"]),
                ownerName=str(serializer.validated_data["ownerName"]),
                dueDate=str(serializer.validated_data["dueDate"]),
                progress=int(serializer.validated_data["progress"]),
                health=int(serializer.validated_data["health"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class ProjectStatusView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, projectId: str) -> Response:
        serializer = ChangeProjectStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.changeProjectStatusUseCase().execute(
            ChangeProjectStatusCommand(
                projectId=str(projectId), target=str(serializer.validated_data["target"])
            )
        )
        return Response(successEnvelope(asDict(dto)))


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


# -- OpenAPI registration (§24 platform docs) -----------------------------------------


def registerProjectEndpoints() -> None:
    specs = [
        EndpointSpec(
            method="GET",
            path="api/v1/projects",
            summary="List the tenant's projects.",
            permission="project.list",
            errorCodes=PROJECT_ERRORS,
            paginated=True,
            filterable=("status",),
            sortable=("createdAt", "name", "status", "dueDate"),
            searchable=True,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/projects",
            summary="Create a project (idempotent).",
            permission="project.create",
            errorCodes=PROJECT_ERRORS,
            idempotent=True,
            requestExample={"code": "NOVA-24", "name": "Nova Plant Modernization"},
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/projects/{projectId}",
            summary="Project detail.",
            permission="project.view",
            errorCodes=PROJECT_ERRORS,
        ),
        EndpointSpec(
            method="PATCH",
            path="api/v1/projects/{projectId}",
            summary="Update a project.",
            permission="project.update",
            errorCodes=PROJECT_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/projects/{projectId}/status",
            summary="Transition a project status (idempotent).",
            permission="project.update",
            errorCodes=PROJECT_ERRORS,
            idempotent=True,
            requestExample={"target": "completed"},
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)


registerProjectEndpoints()
