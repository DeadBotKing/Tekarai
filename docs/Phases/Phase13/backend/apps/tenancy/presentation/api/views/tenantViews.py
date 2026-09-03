"""Tenant API views (Phase 06 §12) — HTTP orchestration only.

Each view: authenticate → permission → serialize input → run use case →
wrap DTO in the standard envelope. No business logic, no ORM calls.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope
from apps.tenancy.application.commands.tenantCommands import (
    ChangeTenantStatusCommand,
    CreateTenantCommand,
)
from apps.tenancy.application.queries.tenantQueries import (
    GetTenantQuery,
    ListTenantsQuery,
)
from apps.tenancy.infrastructure import container
from apps.tenancy.presentation.api.serializers.tenantSerializers import (
    ChangeTenantStatusSerializer,
    CreateTenantSerializer,
)

TENANT_ERRORS = [
    "TENANT_ACCESS_DENIED",
    "DUP_BUSINESS_CODE",
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "STATE_INVALID_TRANSITION",
]


class TenantListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListTenantsQuery(
            status=str(request.query_params.get("status", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=int(request.query_params.get("page", 1) or 1),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
        )
        # Platform-only list (tenant.list) — enforced by the use case itself.
        useCase = container.listTenantsUseCase()
        useCase.requiredAction = "tenant.list"
        pageDto = useCase.execute(query)
        return Response(
            successEnvelope([asDict(item) for item in pageDto.items], meta=pageDto.asMeta())
        )

    def post(self, request: Request) -> Response:
        serializer = CreateTenantSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.createTenantUseCase().execute(
            CreateTenantCommand(
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class TenantDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, tenantId: str) -> Response:
        dto = container.getTenantUseCase().execute(GetTenantQuery(tenantId=tenantId))
        return Response(successEnvelope(asDict(dto)))


class TenantStatusView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, tenantId: str) -> Response:
        serializer = ChangeTenantStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.changeTenantStatusUseCase().execute(
            ChangeTenantStatusCommand(
                tenantId=tenantId,
                target=str(serializer.validated_data["target"]),
                reason=str(serializer.validated_data.get("reason", "")),
            )
        )
        return Response(successEnvelope(asDict(dto)))


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


def registerTenancyEndpoints() -> None:
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/tenants",
            summary="Create a tenant (platform administrators).",
            permission="tenant.create",
            requestExample={"code": "acme", "name": "ACME Industries"},
            responseExample={
                "success": True,
                "data": {"id": "…", "code": "acme"},
                "meta": {},
                "errors": [],
            },
            errorCodes=TENANT_ERRORS,
            idempotent=True,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/tenants",
            summary="List tenants (platform scope).",
            permission="tenant.list",
            responseExample={"success": True, "data": [], "meta": {}, "errors": []},
            errorCodes=TENANT_ERRORS + ["PERM_PERMISSION_DENIED"],
            paginated=True,
            filterable=("status",),
            sortable=("createdAt", "name", "code"),
            searchable=True,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/tenants/{tenantId}",
            summary="Get one tenant (own tenant or platform scope).",
            permission="tenant.view",
            errorCodes=TENANT_ERRORS,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/tenants/{tenantId}/status",
            summary="Suspend / reactivate / close a tenant (state machine).",
            permission="tenant.suspend|tenant.activate|tenant.close",
            requestExample={"target": "suspended", "reason": "billing overdue"},
            errorCodes=TENANT_ERRORS,
            idempotent=True,
        )
    )
