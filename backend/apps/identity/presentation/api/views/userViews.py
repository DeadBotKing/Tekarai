"""User management + /me endpoints (§12 views; §17 permissions)."""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.application.commands.identityCommands import (
    AssignUserToTenantCommand,
    CreateUserCommand,
)
from apps.identity.application.queries.identityQueries import (
    GetCurrentAccountQuery,
    GetUserQuery,
    ListUsersQuery,
)
from apps.identity.infrastructure import container
from apps.identity.presentation.api.serializers.identitySerializers import (
    AssignMembershipSerializer,
    CreateUserSerializer,
)
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope

USER_ERRORS = [
    "PERM_PERMISSION_DENIED",
    "TENANT_ACCESS_DENIED",
    "DUP_IDENTIFIER",
    "DUP_ACTIVE_MEMBERSHIP",
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
]


class UserListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListUsersQuery(
            status=str(request.query_params.get("status", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=int(request.query_params.get("page", 1) or 1),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
            tenantId=str(request.query_params.get("tenantId", "")).strip(),
        )
        pageDto = container.listUsersUseCase().execute(query)
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in pageDto.items],
                meta=pageDto.asMeta(),
            )
        )

    def post(self, request: Request) -> Response:
        serializer = CreateUserSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        from apps.sharedKernel.application.requestContext import currentContext

        context = currentContext()
        dto = container.createUserUseCase().execute(
            CreateUserCommand(
                tenantId=context.tenantId or context.actorTenantId,
                username=str(serializer.validated_data["username"]),
                email=str(serializer.validated_data["email"]),
                password=str(serializer.validated_data["password"]),
                displayName=str(serializer.validated_data.get("displayName", "")),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(dto)), status=201)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, userId: str) -> Response:
        dto = container.getUserUseCase().execute(GetUserQuery(userId=userId))
        return Response(successEnvelope(dataclasses.asdict(dto)))


class UserMembershipView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, userId: str) -> Response:
        serializer = AssignMembershipSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.assignUserToTenantUseCase().execute(
            AssignUserToTenantCommand(
                userId=userId,
                targetTenantId=str(serializer.validated_data["tenantId"]),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(dto)), status=201)


class MeView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        account = container.getCurrentAccountUseCase().execute(GetCurrentAccountQuery())
        payload = {
            "user": dataclasses.asdict(account.user),
            "permissions": account.permissions,
        }
        return Response(successEnvelope(payload))


def registerUserEndpoints() -> None:
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/users",
            summary="List users (tenant scoped; platform may pass tenantId).",
            permission="user.list",
            errorCodes=USER_ERRORS,
            paginated=True,
            filterable=("status", "tenantId"),
            sortable=("createdAt", "username", "status"),
            searchable=True,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/users",
            summary="Create a user in the caller's tenant.",
            permission="user.create",
            requestExample={"username": "sara", "email": "sara@acme.com", "password": "…"},
            errorCodes=USER_ERRORS,
            idempotent=True,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/users/{userId}",
            summary="Get a user (own tenant; GLOBAL grant crosses tenants).",
            permission="user.view",
            errorCodes=USER_ERRORS,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/users/{userId}/memberships",
            summary="Assign a user to a tenant.",
            permission="user.assignTenant",
            requestExample={"tenantId": "00000000-0000-0000-0000-000000000000"},
            errorCodes=USER_ERRORS,
            idempotent=True,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/me",
            summary="Current account + effective permissions.",
            permission="authenticated",
            errorCodes=USER_ERRORS[:1],
        )
    )
