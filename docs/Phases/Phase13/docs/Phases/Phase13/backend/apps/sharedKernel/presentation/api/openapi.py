"""OpenAPI architecture (Phase 06 §24) — dependency-free by design (ADR-020).

Every v1 endpoint registers an ``EndpointSpec`` (method, path, auth,
permission, request/response shape, error codes, pagination/filtering flags,
example). ``buildOpenApiDocument`` turns the registry into an OpenAPI 3.1
document served at ``/api/v1/openapi.json`` with a human list at
``/api/v1/docs``. When the frontend contracts grow, drf-spectacular can
replace the builder — the registry stays the source of truth.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from rest_framework.response import Response
from rest_framework.views import APIView

#: Spec §24: every endpoint documents Method/URL/Authentication/Permission/
#: Request/Response/Errors/Pagination/Filtering/Examples.
REGISTRY: list[EndpointSpec] = []


@dataclass
class EndpointSpec:
    method: str
    path: str
    summary: str
    authentication: str = "bearerSession"
    permission: str = ""
    requestExample: dict[str, Any] = field(default_factory=dict)
    responseExample: dict[str, Any] = field(default_factory=dict)
    errorCodes: list[str] = field(default_factory=list)
    paginated: bool = False
    cursorPaginated: bool = False
    filterable: tuple[str, ...] = ()
    sortable: tuple[str, ...] = ()
    searchable: bool = False
    idempotent: bool = False
    rateLimitScope: str = ""


def registerEndpoint(spec: EndpointSpec) -> EndpointSpec:
    REGISTRY.append(spec)
    return spec


def buildOpenApiDocument() -> dict[str, Any]:
    paths: dict[str, Any] = {}
    for spec in REGISTRY:
        operations = paths.setdefault(f"/{spec.path.strip('/')}", {})
        parameters: list[dict[str, Any]] = []
        if spec.paginated:
            parameters += [
                {"name": "page", "in": "query", "schema": {"type": "integer"}},
                {"name": "pageSize", "in": "query", "schema": {"type": "integer"}},
            ]
        if spec.cursorPaginated:
            parameters.append({"name": "cursor", "in": "query", "schema": {"type": "string"}})
        if spec.filterable:
            parameters.append(
                {
                    "name": "filter fields",
                    "in": "query",
                    "description": f"allowed: {', '.join(spec.filterable)}",
                    "schema": {"type": "string"},
                }
            )
        if spec.sortable:
            parameters.append(
                {
                    "name": "ordering",
                    "in": "query",
                    "description": f"allowed: {', '.join(spec.sortable)}",
                    "schema": {"type": "string"},
                }
            )
        if spec.searchable:
            parameters.append({"name": "search", "in": "query", "schema": {"type": "string"}})
        operations[spec.method.lower()] = {
            "summary": spec.summary,
            "tags": [
                spec.path.strip("/").split("/")[1] if spec.path.count("/") > 1 else "platform"
            ],
            "security": [{"bearerSession": []}] if spec.authentication == "bearerSession" else [],
            "parameters": parameters,
            "responses": {
                "200": {
                    "description": "Standard envelope",
                    "content": {"application/json": {"example": spec.responseExample}},
                },
                "default": {
                    "description": "Error envelope",
                    "content": {
                        "application/json": {
                            "example": {
                                "success": False,
                                "data": None,
                                "meta": {},
                                "errors": [
                                    {"code": code, "message": "..."} for code in spec.errorCodes[:3]
                                ],
                            }
                        }
                    },
                },
            },
        }
        if spec.requestExample:
            operations[spec.method.lower()]["requestBody"] = {
                "content": {"application/json": {"example": spec.requestExample}},
                "required": True,
            }
    return {
        "openapi": "3.1.0",
        "info": {
            "title": "Tekarai API",
            "version": "v1",
            "description": (
                "Tekarai platform API — every response uses the standard "
                "envelope {success, data, meta, errors}; every error carries a "
                "stable code from docs/database/ErrorCodeCatalog.md."
            ),
        },
        "servers": [{"url": "/api/v1"}],
        "components": {"securitySchemes": {"bearerSession": {"type": "http", "scheme": "bearer"}}},
        "paths": paths,
    }


class OpenApiJsonView(APIView):
    """GET /api/v1/openapi.json — machine-readable contract (§24)."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request) -> Response:  # noqa: ANN001 — DRF signature
        return Response(buildOpenApiDocument())


class OpenApiDocsView(APIView):
    """GET /api/v1/docs — human-readable endpoint list (§24)."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def get(self, request) -> Response:  # noqa: ANN001 — DRF signature
        rows = "\n".join(
            f"<tr><td><code>{spec.method}</code></td>"
            f"<td><code>/{spec.path.strip('/')}</code></td>"
            f"<td>{spec.summary}</td>"
            f"<td><code>{spec.permission or 'authenticated'}</code></td>"
            f"<td><code>{'</code> <code>'.join(spec.errorCodes)}</code></td></tr>"
            for spec in REGISTRY
        )
        html = (
            "<html><head><title>Tekarai API v1</title>"
            "<style>body{font-family:sans-serif;margin:2rem}"
            "td,th{padding:.35rem .6rem;border:1px solid #ddd;text-align:left}"
            "code{background:#f4f4f4}</style></head><body>"
            "<h1>Tekarai API — v1</h1>"
            "<p>Machine-readable contract: <a href='../openapi.json'>openapi.json</a></p>"
            "<table><tr><th>Method</th><th>Path</th><th>Summary</th>"
            f"<th>Permission</th><th>Errors</th></tr>{rows}</table></body></html>"
        )
        from django.http import HttpResponse

        return HttpResponse(html)
