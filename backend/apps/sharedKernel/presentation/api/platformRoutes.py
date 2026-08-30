"""Platform routes (shared kernel): OpenAPI + audit stream (§24, §19)."""

from __future__ import annotations

from django.urls import path
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.openapi import (
    EndpointSpec,
    OpenApiDocsView,
    OpenApiJsonView,
    registerEndpoint,
)
from apps.sharedKernel.presentation.api.permissions import (
    actionPermission,
)
from apps.sharedKernel.presentation.api.response import successEnvelope


class PlatformOverviewView(APIView):
    """API v1 surface overview (unauthenticated, envelope demo)."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request: Request) -> Response:
        return Response(
            successEnvelope(
                {
                    "service": "tekarai",
                    "api": "v1",
                    "contract": "/api/v1/openapi.json",
                    "docs": "/api/v1/docs",
                }
            )
        )


class AuditEventListView(APIView):
    """Cursor-paginated audit stream (§21; BR-PERF-002 — no offsets).

    Data flows through the AuditStreamReader port — the view never
    touches the ORM.
    """

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [actionPermission("audit.view")]

    def get(self, request: Request) -> Response:
        from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

        reader = sharedKernelProvider("auditStreamReader")()
        page = reader.readPage(
            cursor=str(request.query_params.get("cursor", "")).strip(),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
        )
        return Response(
            successEnvelope(
                page.items,
                meta={
                    "pagination": {
                        "pageSize": len(page.items),
                        "nextCursor": page.nextCursor,
                        "hasNext": page.hasNext,
                    }
                },
            )
        )


urlpatterns = [
    path("platform/overview", PlatformOverviewView.as_view(), name="platformOverview"),
    path("platform/audit-events", AuditEventListView.as_view(), name="auditEvents"),
    path("openapi.json", OpenApiJsonView.as_view(), name="openapiJson"),
    path("docs", OpenApiDocsView.as_view(), name="openapiDocs"),
]


def registerPlatformEndpoints() -> None:
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/platform/overview",
            summary="API v1 surface overview.",
            authentication="none",
            responseExample={
                "success": True,
                "data": {"service": "tekarai"},
                "meta": {},
                "errors": [],
            },
            errorCodes=[],
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/platform/audit-events",
            summary="Cursor-paginated audit stream (audit.view).",
            permission="audit.view",
            errorCodes=["PERM_PERMISSION_DENIED"],
            cursorPaginated=True,
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/openapi.json",
            summary="OpenAPI 3.1 contract (ADR-020).",
            authentication="none",
            errorCodes=[],
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="GET",
            path="api/v1/docs",
            summary="Human-readable endpoint list.",
            authentication="none",
            errorCodes=[],
        )
    )


registerPlatformEndpoints()
