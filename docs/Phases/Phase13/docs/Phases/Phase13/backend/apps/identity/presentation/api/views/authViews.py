"""Authentication endpoints (Phase 07 §10/§32).

Login is rate limited (§10 layer 4), unauthenticated by design, and performs
zero authorization decisions (§20). The response carries the §7 pair:
short-lived JWT access token + opaque rotating refresh token. MFA-enabled
accounts receive a challenge instead of tokens (§24).
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
    VerifyMfaChallengeCommand,
)
from apps.identity.infrastructure import container
from apps.identity.presentation.api.serializers.identitySerializers import (
    LoginSerializer,
    MfaChallengeSerializer,
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
                identifier=str(serializer.validated_data["identifier"]),
                password=str(serializer.validated_data["password"]),
                ipAddress=clientIpOf(request),
                userAgent=str(request.headers.get("User-Agent", ""))[:300],
                device=str(request.data.get("device", ""))[:120],
            )
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


class MfaChallengeView(APIView):
    """§24 — exchange the challenge + TOTP/recovery code for real tokens."""

    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    @enforceRateLimit("auth:mfa")
    def post(self, request: Request) -> Response:
        serializer = MfaChallengeSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.verifyMfaChallengeUseCase().execute(
            VerifyMfaChallengeCommand(
                challengeToken=str(serializer.validated_data["challengeToken"]),
                code=str(serializer.validated_data["code"]),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


class LogoutView(APIView):
    """Revokes the session named by the refresh token (§7)."""

    permission_classes: list[type] = []

    def post(self, request: Request) -> Response:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.logoutUseCase().execute(
            LogoutCommand(refreshToken=str(serializer.validated_data["refreshToken"]))
        )
        return Response(successEnvelope(result))


class RefreshView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    @enforceRateLimit("auth:refresh")
    def post(self, request: Request) -> Response:
        serializer = RefreshSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.refreshSessionUseCase().execute(
            RefreshSessionCommand(refreshToken=str(serializer.validated_data["refreshToken"]))
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


def clientIpOf(request: Request) -> str:
    forwarded: str = request.headers.get("X-Forwarded-For", "")
    if forwarded:
        return forwarded.split(",")[0].strip()[:64]
    return request.META.get("REMOTE_ADDR", "")[:64]


def registerAuthEndpoints() -> None:
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/auth/login",
            summary="Authenticate (tenant code + identifier + password → JWT + refresh).",
            authentication="none",
            requestExample={
                "tenantCode": "platform",
                "identifier": "platform-admin",
                "password": "…",
            },
            responseExample={
                "success": True,
                "data": {
                    "accessToken": "…",
                    "refreshToken": "…",
                    "tokenType": "Bearer",
                    "expiresIn": 900,
                },
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
            path="api/v1/auth/mfa/challenge",
            summary="Complete login with a TOTP or recovery code (§24).",
            authentication="none",
            requestExample={"challengeToken": "…", "code": "123456"},
            errorCodes=AUTH_ERRORS,
            rateLimitScope="auth:mfa",
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/auth/refresh",
            summary="Rotate the refresh token; new JWT access token (§7).",
            authentication="none",
            requestExample={"refreshToken": "…"},
            errorCodes=AUTH_ERRORS,
            rateLimitScope="auth:refresh",
        )
    )
    registerEndpoint(
        EndpointSpec(
            method="POST",
            path="api/v1/auth/logout",
            summary="Revoke the session bound to this refresh token.",
            permission="authenticated",
            requestExample={"refreshToken": "…"},
            errorCodes=AUTH_ERRORS,
        )
    )
