"""Phase 07 §32 endpoints — password, verification, RBAC, API keys,
service accounts, MFA and session self-service.

Thin by contract (§11 views): serialize → command/query → envelope. No
authorization logic lives here (§20); the permission classes and the use
cases' requiredAction carry the decisions.
"""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.application.commands.identityCommands import (
    AssignRoleCommand,
    ChangePasswordCommand,
    ConfirmMfaCommand,
    ConfirmPasswordResetCommand,
    CreateApiKeyCommand,
    CreateRoleCommand,
    CreateServiceAccountCommand,
    DeleteRoleCommand,
    DisableMfaCommand,
    DisableServiceAccountCommand,
    EnableServiceAccountCommand,
    RemoveRoleCommand,
    RequestPasswordResetCommand,
    RevokeAllSessionsCommand,
    RevokeApiKeyCommand,
    RevokeSessionCommand,
    SendVerificationCommand,
    SetupMfaCommand,
    UpdateRoleCommand,
    VerifyEmailCommand,
    VerifyPhoneCommand,
)
from apps.identity.application.queries.identityQueries import (
    ListApiKeysQuery,
    ListRolesQuery,
    ListServiceAccountsQuery,
    ListSessionsQuery,
)
from apps.identity.infrastructure import container
from apps.identity.presentation.api.serializers.identitySerializers import (
    ApiKeyCreateSerializer,
    AssignRoleSerializer,
    ChangePasswordSerializer,
    ConfirmMfaSerializer,
    CreateRoleSerializer,
    CreateServiceAccountSerializer,
    DisableMfaSerializer,
    PasswordResetConfirmSerializer,
    PasswordResetRequestSerializer,
    SendVerificationSerializer,
    SetupMfaSerializer,
    UpdateRoleSerializer,
    VerifyChannelSerializer,
)
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope

PASSWORD_ERRORS = [
    "AUTH_CREDENTIALS_INVALID",
    "SYS_VALIDATION_FAILED",
    "AUTH_AUTHENTICATION_REQUIRED",
]


# -- password self-service (§23/§25) --------------------------------------------


class ChangePasswordView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ChangePasswordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.changePasswordUseCase().execute(
            ChangePasswordCommand(
                currentPassword=str(serializer.validated_data["currentPassword"]),
                newPassword=str(serializer.validated_data["newPassword"]),
            )
        )
        return Response(successEnvelope(result))


class PasswordResetRequestView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request: Request) -> Response:
        serializer = PasswordResetRequestSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.requestPasswordResetUseCase().execute(
            RequestPasswordResetCommand(
                tenantCode=str(serializer.validated_data["tenantCode"]),
                identifier=str(serializer.validated_data["identifier"]),
            )
        )
        return Response(successEnvelope(result))


class PasswordResetConfirmView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request: Request) -> Response:
        serializer = PasswordResetConfirmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.confirmPasswordResetUseCase().execute(
            ConfirmPasswordResetCommand(
                token=str(serializer.validated_data["token"]),
                newPassword=str(serializer.validated_data["newPassword"]),
            )
        )
        return Response(successEnvelope(result))


class SendVerificationView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SendVerificationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.sendVerificationUseCase().execute(
            SendVerificationCommand(
                userId=str(serializer.validated_data["userId"]),
                channel=str(serializer.validated_data["channel"]),
            )
        )
        return Response(successEnvelope(result))


class VerifyEmailView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request: Request) -> Response:
        serializer = VerifyChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.verifyChannelUseCase().execute(
            VerifyEmailCommand(token=str(serializer.validated_data["token"]))
        )
        return Response(successEnvelope(result))


class VerifyPhoneView(APIView):
    authentication_classes: list[type] = []
    permission_classes: list[type] = []

    def post(self, request: Request) -> Response:
        serializer = VerifyChannelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.verifyChannelUseCase().execute(
            VerifyPhoneCommand(token=str(serializer.validated_data["token"]))
        )
        return Response(successEnvelope(result))


# -- RBAC administration (§14–§17) -------------------------------------------------


class RoleListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        roles = container.listRolesUseCase().execute(ListRolesQuery())
        return Response(successEnvelope([dataclasses.asdict(role) for role in roles]))

    def post(self, request: Request) -> Response:
        serializer = CreateRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = container.createRoleUseCase().execute(
            CreateRoleCommand(
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
                scopeType=str(serializer.validated_data.get("scopeType", "TENANT")),
                actions=list(serializer.validated_data.get("actions", [])),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(role)))


class RoleDetailView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, roleId: object) -> Response:
        serializer = UpdateRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        role = container.updateRoleUseCase().execute(
            UpdateRoleCommand(
                roleId=str(roleId),
                name=str(serializer.validated_data.get("name", "")),
                actions=list(serializer.validated_data.get("actions", [])),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(role)))

    def delete(self, request: Request, roleId: object) -> Response:
        result = container.deleteRoleUseCase().execute(DeleteRoleCommand(roleId=str(roleId)))
        return Response(successEnvelope(result))


class UserRoleView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, userId: object) -> Response:
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.assignRoleUseCase().execute(
            AssignRoleCommand(
                userId=str(userId),
                roleId=str(serializer.validated_data["roleId"]),
                tenantId=str(serializer.validated_data.get("tenantId", "")),
            )
        )
        return Response(successEnvelope(result))

    def delete(self, request: Request, userId: object) -> Response:
        serializer = AssignRoleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.removeRoleUseCase().execute(
            RemoveRoleCommand(userId=str(userId), roleId=str(serializer.validated_data["roleId"]))
        )
        return Response(successEnvelope(result))


# -- API keys (§22) -----------------------------------------------------------------


class ApiKeyListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        keys = container.listApiKeysUseCase().execute(
            ListApiKeysQuery(
                ownerType=str(request.query_params.get("ownerType", "user")),
                ownerId=str(request.query_params.get("ownerId", "")),
            )
        )
        return Response(successEnvelope([dataclasses.asdict(k) for k in keys]))

    def post(self, request: Request) -> Response:
        serializer = ApiKeyCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        created = container.createApiKeyUseCase().execute(
            CreateApiKeyCommand(
                tenantId=str(serializer.validated_data["tenantId"]),
                name=str(serializer.validated_data["name"]),
                ownerType=str(serializer.validated_data.get("ownerType", "user")),
                ownerId=str(serializer.validated_data.get("ownerId", "")),
                scopes=list(serializer.validated_data.get("scopes", [])),
                expiresAt=str(serializer.validated_data.get("expiresAt", "") or ""),
            )
        )
        payload = dataclasses.asdict(created)
        payload["apiKey"] = dataclasses.asdict(created.apiKey)
        return Response(successEnvelope(payload))


class ApiKeyDetailView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, apiKeyId: object) -> Response:
        result = container.revokeApiKeyUseCase().execute(
            RevokeApiKeyCommand(apiKeyId=str(apiKeyId))
        )
        return Response(successEnvelope(result))


# -- service accounts (§21) ------------------------------------------------------------


class ServiceAccountListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        accounts = container.listServiceAccountsUseCase().execute(
            ListServiceAccountsQuery(tenantId=str(request.query_params.get("tenantId", "")))
        )
        return Response(successEnvelope([dataclasses.asdict(a) for a in accounts]))

    def post(self, request: Request) -> Response:
        serializer = CreateServiceAccountSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        account = container.createServiceAccountUseCase().execute(
            CreateServiceAccountCommand(
                tenantId=str(serializer.validated_data["tenantId"]),
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
                description=str(serializer.validated_data.get("description", "")),
                scopes=list(serializer.validated_data.get("scopes", [])),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(account)))


class ServiceAccountDetailView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, accountId: object) -> Response:
        action = str(request.data.get("action", ""))
        if action == "enable":
            dto = container.enableServiceAccountUseCase().execute(
                EnableServiceAccountCommand(accountId=str(accountId))
            )
        else:
            dto = container.disableServiceAccountUseCase().execute(
                DisableServiceAccountCommand(accountId=str(accountId))
            )
        return Response(successEnvelope(dataclasses.asdict(dto)))


# -- MFA (§24) ---------------------------------------------------------------------------


class MfaSetupView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = SetupMfaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.setupMfaUseCase().execute(
            SetupMfaCommand(factorType=str(serializer.validated_data.get("factorType", "totp")))
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


class MfaConfirmView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = ConfirmMfaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.confirmMfaUseCase().execute(
            ConfirmMfaCommand(
                factorId=str(serializer.validated_data["factorId"]),
                code=str(serializer.validated_data["code"]),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(dto)))


class MfaDisableView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = DisableMfaSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.disableMfaUseCase().execute(
            DisableMfaCommand(password=str(serializer.validated_data["password"]))
        )
        return Response(successEnvelope(result))


# -- session self-service (§9) ---------------------------------------------------------------


class SessionListView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        sessions = container.listSessionsUseCase().execute(
            ListSessionsQuery(userId=str(request.query_params.get("userId", "")))
        )
        return Response(successEnvelope([dataclasses.asdict(s) for s in sessions]))


class SessionRevokeView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, sessionId: object) -> Response:
        result = container.revokeSessionUseCase().execute(
            RevokeSessionCommand(
                sessionId=str(sessionId),
                userId=str(request.query_params.get("userId", "")),
            )
        )
        return Response(successEnvelope(result))


class LogoutAllView(IdempotencyMixin, APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        result = container.revokeAllSessionsUseCase().execute(
            RevokeAllSessionsCommand(userId=str(request.data.get("userId", "")))
        )
        return Response(successEnvelope(result))


def registerPhase7Endpoints() -> None:
    specs = [
        EndpointSpec(
            method="POST",
            path="api/v1/auth/password/change",
            summary="Change own password (policy + history, revokes sessions).",
            permission="authenticated",
            errorCodes=PASSWORD_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/auth/password/reset/request",
            summary="Request a password-reset token (§25, no enumeration).",
            authentication="none",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/auth/password/reset/confirm",
            summary="Consume the single-use reset token (§25).",
            authentication="none",
            errorCodes=PASSWORD_ERRORS,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/auth/verify-email",
            summary="Verify the email channel (§26).",
            authentication="none",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/auth/verify-phone",
            summary="Verify the phone channel (§26).",
            authentication="none",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/auth/verification/send",
            summary="Issue an email/phone verification token.",
            permission="authenticated",
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/roles",
            summary="List roles with their permission patterns (§16).",
            permission="role.list",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/roles",
            summary="Create a role (§15; unique code per scope §34).",
            permission="role.create",
            errorCodes=["DUP_IDENTIFIER", "SYS_VALIDATION_FAILED"],
        ),
        EndpointSpec(
            method="PATCH",
            path="api/v1/roles/{roleId}",
            summary="Update role name/actions (§15).",
            permission="role.update",
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/roles/{roleId}",
            summary="Delete an unassigned role (§17).",
            permission="role.delete",
            errorCodes=["SYS_CONFLICT"],
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/users/{userId}/roles",
            summary="Assign a role (audit + cache invalidation §28).",
            permission="user.assignRole",
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/users/{userId}/roles",
            summary="Remove a role (effective immediately §28).",
            permission="user.assignRole",
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/api-keys",
            summary="List own API keys (metadata only §22).",
            permission="authenticated",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/api-keys",
            summary="Create an API key — raw key returned once (§22).",
            permission="apikey.create",
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/api-keys/{apiKeyId}",
            summary="Revoke an API key (§35.6 immediate).",
            permission="apikey.revoke",
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/service-accounts",
            summary="List service accounts of the tenant (§21).",
            permission="serviceaccount.list",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/service-accounts",
            summary="Create a service account (§21).",
            permission="serviceaccount.create",
            errorCodes=["DUP_IDENTIFIER"],
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/service-accounts/{accountId}",
            summary="Disable / enable a service account (§21).",
            permission="serviceaccount.disable",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/me/mfa/setup",
            summary="Start TOTP enrolment — secret shown once (§24).",
            permission="authenticated",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/me/mfa/confirm",
            summary="Confirm TOTP + receive recovery codes (§24).",
            permission="authenticated",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/me/mfa/disable",
            summary="Disable MFA (password required).",
            permission="authenticated",
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/me/sessions",
            summary="List own active sessions (§9).",
            permission="authenticated",
        ),
        EndpointSpec(
            method="DELETE",
            path="api/v1/me/sessions/{sessionId}",
            summary="Revoke one of your sessions (§9).",
            permission="authenticated",
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/me/sessions/revoke-all",
            summary="Logout everywhere (§9).",
            permission="authenticated",
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)
