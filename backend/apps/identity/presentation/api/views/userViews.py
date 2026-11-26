"""User management + /me endpoints (§12 views; §17 permissions)."""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.identity.application.commands.identityCommands import (
    AssignUserToTenantCommand,
)
from apps.identity.application.queries.identityQueries import (
    GetCurrentAccountQuery,
    GetUserQuery,
    ListUsersQuery,
)
from apps.identity.infrastructure import container
from apps.identity.presentation.api.serializers.identitySerializers import (
    AssignMembershipSerializer,
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


class UserListView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        requestedPage = max(1, int(request.query_params.get("page", 1) or 1))
        requestedPageSize = min(100, max(1, int(request.query_params.get("pageSize", 50) or 50)))
        query = ListUsersQuery(
            status=str(request.query_params.get("status", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=requestedPage,
            pageSize=requestedPageSize,
            tenantId=str(request.query_params.get("tenantId", "")).strip(),
        )
        # Resolve the organisation scope before listing. The shared roster is
        # fetched once (up to the API's 100-row cap), then filtered before
        # pagination so team members never disappear on later pages.
        from apps.sharedKernel.application.requestContext import currentContext
        context = currentContext()
        actorId = str(context.actorId or "")
        tenantId = str(context.tenantId or context.actorTenantId or "")
        from apps.organization.application.services.accessContract import scopeFilterForUser
        import uuid
        scope = scopeFilterForUser(
            uuid.UUID(tenantId), uuid.UUID(actorId), "organization.assignment.view"
        )
        from apps.identity.application.services.principalDirectory import isTenantAdministratorForAction
        isAdmin = isTenantAdministratorForAction(
            uuid.UUID(tenantId), uuid.UUID(actorId), "organization.assignment.view"
        )
        from apps.organization.infrastructure import orgRepository
        directReports = orgRepository.teamMemberIdsFor(
            uuid.UUID(tenantId), uuid.UUID(actorId)
        )
        from apps.organization.application.services.accessContract import restrictedDepartmentIdsForUser
        restrictedDepartmentIds = {
            str(value).replace("-", "")
            for value in restrictedDepartmentIdsForUser(uuid.UUID(tenantId), uuid.UUID(actorId))
        }
        restrictToUnitTeam = not isAdmin and (bool(directReports) or scope.scope == "team")
        if restrictToUnitTeam or restrictedDepartmentIds:
            teamIds = {str(actorId).replace("-", "")}
            teamIds.update(str(value).replace("-", "") for value in directReports)
            if scope.scope == "team":
                teamIds.update(str(value).replace("-", "") for value in scope.userIds)
            departmentIds = {
                str(value).replace("-", "")
                for value in orgRepository.departmentIdsForUser(
                    uuid.UUID(tenantId), uuid.UUID(actorId)
                )
            }
            assignments = orgRepository.listAssignments(uuid.UUID(tenantId))
            teamDepartmentUserIds = {
                str(assignment.userId).replace("-", "")
                for assignment in assignments
                if (not restrictToUnitTeam or str(assignment.userId).replace("-", "") in teamIds)
                and (not restrictToUnitTeam or str(assignment.departmentId).replace("-", "") in departmentIds)
                and str(assignment.departmentId).replace("-", "") not in restrictedDepartmentIds
            }
            freezeOnlyUserIds = {
                str(assignment.userId).replace("-", "")
                for assignment in assignments
                if str(assignment.departmentId).replace("-", "") in restrictedDepartmentIds
            } - teamDepartmentUserIds
            # Filter before page slicing so team membership and the protected
            # department rule both apply consistently across pages.
            query = dataclasses.replace(query, page=1, pageSize=100)
            pageDto = container.listUsersUseCase().execute(query)
            filtered = [
                item for item in pageDto.items
                if str(item.id).replace("-", "") not in freezeOnlyUserIds
                and (not restrictToUnitTeam or str(item.id).replace("-", "") in teamDepartmentUserIds)
            ]
            totalCount = len(filtered)
            startIndex = (requestedPage - 1) * requestedPageSize
            pageDto = dataclasses.replace(
                pageDto,
                items=filtered[startIndex:startIndex + requestedPageSize],
                totalCount=totalCount,
                page=requestedPage,
                pageSize=requestedPageSize,
            )
        else:
            pageDto = container.listUsersUseCase().execute(query)
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in pageDto.items],
                meta=pageDto.asMeta(),
            )
        )

    def post(self, request: Request) -> Response:
        from apps.identity.presentation.api.views.mobileViews import createAccountResponse
        return createAccountResponse(request)


class UserDetailView(APIView):
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, userId: str) -> Response:
        from apps.sharedKernel.application.requestContext import currentContext
        from apps.organization.application.services.accessContract import restrictedDepartmentIdsForUser
        from apps.organization.infrastructure import orgRepository
        import uuid
        context = currentContext()
        tenantId = uuid.UUID(str(context.tenantId or context.actorTenantId))
        actorId = uuid.UUID(str(context.actorId))
        restricted = set(restrictedDepartmentIdsForUser(tenantId, actorId))
        if restricted:
            visibleAssignment = any(
                str(row.userId) == str(userId) and str(row.departmentId) not in restricted
                for row in orgRepository.listAssignments(tenantId)
            )
            restrictedOnly = any(
                str(row.userId) == str(userId) and str(row.departmentId) in restricted
                for row in orgRepository.listAssignments(tenantId)
            ) and not visibleAssignment
            if restrictedOnly:
                return Response(
                    {"success": False, "error": {"code": "identity.userNotFound", "message": "مورد یافت نشد."}},
                    status=404,
                )
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
            summary="Create a mobile account; generated temporary credential is returned once.",
            permission="user.create",
            requestExample={"phone": "09123456789", "displayName": "Sara", "email": "sara@acme.com"},
            errorCodes=USER_ERRORS,
            idempotent=False,
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
