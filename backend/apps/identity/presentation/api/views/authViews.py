"""Authentication endpoints (§16): login / refresh / logout.

Login is rate limited (§23), unauthenticated by design, and performs zero
authorization decisions (§16). Correlation ids flow via middleware (§25).
"""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.application.commands.identityCommands import (
    AuthenticateUserCommand,
    LogoutCommand,
    RefreshSessionCommand,
)
from apps.identity.infrastructure import container
from apps.identity.presentation.api.serializers.identitySerializers import (
    LoginSerializer,
    RefreshSerializer,
)
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope

AUTH_ERRORS = [
    "AUTH_CREDENTIALS_INVALID",
    "AUTH_TOKEN_EXPIRED",
    "AUTH_AUTHENTICATION_REQUIRED",
    "TENANT_SUSPENDED",
    "SYS_RATE_LIMITED",
]


class LoginView(IdempotencyMixin, APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    @enforceRateLimit("auth:login")
    def post(self, request: Request) -> Response:
        serializer = LoginSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.authenticateUserUseCase().execute(
            AuthenticateUserCommand(
                tenantCode=str(serializer.validated_data["tenantCode"]),
                username=str(serializer.validated_data["username"]),
                password=str(serializer.validated_data["password"]),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


class LogoutView(APIView):
    """Authenticated via bearer token; the token is the resource."""

    permission_classes: list[type] = []

    def post(self, request: Request) -> Response:
        token = bearerTokenOf(request)
        result = container.logoutUseCase().execute(LogoutCommand(token=token))
        return Response(successEnvelope(result))


class RefreshView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    @enforceRateLimit("auth:refresh")
    def post(self, request: Request) -> Response:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.refreshSessionUseCase().execute(
            RefreshSessionCommand(token=str(serializer.validated_data["token"]))
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


def bearerTokenOf(request: Request) -> str:
    header: str = request.headers.get("Authorization", "")
    if header.startswith("Bearer "):
        return header[len("Bearer ") :].strip()
    return ""


def registerAuthEndpoints() -> None:
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/auth/login",
            summary="Authenticate (tenant code + username + password).",
            authentication="none",
            requestExample={"tenantCode": "platform", "username": "admin", "password": "…"},
            responseExample={
                "success": True,
                "data": {"token": "…", "tokenType": "Bearer"},
                "meta": {},
                "errors": [],
            },
            errorCodes=AUTH_ERRORS,
            idempotent=True,
            rateLimitScope="auth:login",
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/auth/refresh",
            summary="Rotate the session token (refresh architecture, ADR-019).",
            authentication="none",
            requestExample={"token": "…"},
            errorCodes=AUTH_ERRORS,
            rateLimitScope="auth:refresh",
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/auth/logout",
            summary="Revoke the current session.",
            permission="authenticated",
            errorCodes=AUTH_ERRORS,
        )
    )
