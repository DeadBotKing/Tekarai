"""Task API views (Phase 18b) — HTTP orchestration only."""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope
from apps.tasks.application.commands.taskCommands import (
    ChangeTaskStatusCommand,
    CreateTaskCommand,
    UpdateTaskCommand,
)
from apps.tasks.application.queries.taskQueries import GetTaskQuery, ListTasksQuery
from apps.tasks.infrastructure import container
from apps.tasks.presentation.api.serializers.taskSerializers import (
    ChangeTaskStatusSerializer,
    CreateTaskSerializer,
    UpdateTaskSerializer,
)

TASK_ERRORS = [
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "PERM_PERMISSION_DENIED",
]


class TaskListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListTasksQuery(
            projectId=str(request.query_params.get("projectId", "")).strip(),
            status=str(request.query_params.get("status", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=int(request.query_params.get("page", 1) or 1),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
        )
        useCase = container.listTasksUseCase()
        useCase.requiredAction = "task.list"
        dto = useCase.execute(query)
        return Response(successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = CreateTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.createTaskUseCase().execute(
            CreateTaskCommand(
                tenantId=str(request.data.get("tenantId", "")),
                projectId=str(serializer.validated_data["projectId"]),
                title=str(serializer.validated_data["title"]),
                priority=str(serializer.validated_data["priority"]),
                assigneeName=str(serializer.validated_data["assigneeName"]),
                dueDate=str(serializer.validated_data["dueDate"]),
                estimate=str(serializer.validated_data["estimate"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class TaskDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, taskId: str) -> Response:
        dto = container.getTaskUseCase().execute(GetTaskQuery(taskId=str(taskId)))
        return Response(successEnvelope(asDict(dto)))

    def patch(self, request: Request, taskId: str) -> Response:
        serializer = UpdateTaskSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.updateTaskUseCase().execute(
            UpdateTaskCommand(
                taskId=str(taskId),
                title=str(serializer.validated_data["title"]),
                priority=str(serializer.validated_data["priority"]),
                assigneeName=str(serializer.validated_data["assigneeName"]),
                dueDate=str(serializer.validated_data["dueDate"]),
                estimate=str(serializer.validated_data["estimate"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class TaskStatusView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, taskId: str) -> Response:
        serializer = ChangeTaskStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.changeTaskStatusUseCase().execute(
            ChangeTaskStatusCommand(
                taskId=str(taskId), target=str(serializer.validated_data["target"])
            )
        )
        return Response(successEnvelope(asDict(dto)))


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


# -- OpenAPI registration (§24 platform docs) -----------------------------------------


def registerTaskEndpoints() -> None:
    specs = [
        EndpointSpec(
            method="GET",
            path="api/v1/tasks",
            summary="List the tenant's tasks.",
            permission="task.list",
            errorCodes=TASK_ERRORS,
            paginated=True,
            filterable=("status", "projectId"),
            sortable=("createdAt", "title", "status", "priority"),
            searchable=True,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/tasks",
            summary="Create a task (idempotent).",
            permission="task.create",
            errorCodes=TASK_ERRORS,
            idempotent=True,
            requestExample={"title": "Validate equipment data contract", "priority": "high"},
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/tasks/{taskId}",
            summary="Task detail.",
            permission="task.view",
            errorCodes=TASK_ERRORS,
        ),
        EndpointSpec(
            method="PATCH",
            path="api/v1/tasks/{taskId}",
            summary="Update a task.",
            permission="task.update",
            errorCodes=TASK_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/tasks/{taskId}/status",
            summary="Transition a task status (idempotent).",
            permission="task.update",
            errorCodes=TASK_ERRORS,
            idempotent=True,
            requestExample={"target": "inProgress"},
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)


registerTaskEndpoints()
