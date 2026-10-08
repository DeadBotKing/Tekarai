"""Organisation chart API: units, positions, postings and the matrix.

Thin: every refusal comes from ``orgService``. A rule violation returns 422
with a stable code and a Persian sentence — the request was well-formed,
the *organisation* would not allow the change.

Note the permission split on these endpoints. Reading the chart is open to
anyone who can see the CMMS, because "which unit is Ali in" is ordinary
information. Editing the matrix is its own permission, separate from
editing the structure, because moving a person between units is routine
while changing what a title may approve rewrites what the system refuses.
"""

from __future__ import annotations

import uuid

from django.utils import timezone
from rest_framework import serializers, status
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.organization.application.services import orgService
from apps.organization.application.services.accessContract import accessProfileFor
from apps.organization.application.services.orgService import (
    Actor,
    OrganizationRuleViolation,
)
from apps.organization.domain.valueObjects.orgStructure import (
    ACTION_LABELS_FA,
    ACTIONS,
    CAPABILITIES,
    DEPARTMENT_STATUSES,
    SCOPE_LABELS_FA,
    SCOPES,
    STATUS_LABELS_FA,
    actionsFor,
    isScoped,
)
from apps.organization.infrastructure import orgRepository
from apps.organization.infrastructure.orgRepository import OrganizationNotFound
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated, actionPermission
from apps.sharedKernel.presentation.api.response import successEnvelope


def tenant() -> uuid.UUID:
    context = currentContext()
    value = context.tenantId or context.actorTenantId
    if not value:
        raise ValueError("Tenant scope could not be resolved.")
    return uuid.UUID(str(value))


def actor() -> Actor:
    context = currentContext()
    try:
        actorId: uuid.UUID | None = uuid.UUID(str(getattr(context, "actorId", "")))
    except (ValueError, TypeError):
        actorId = None
    name = (
        getattr(context, "actorDisplayName", "")
        or getattr(context, "actorName", "")
        or getattr(context, "actorEmail", "")
        or ""
    )
    return Actor(id=actorId, name=str(name)[:160])


def departmentRow(row, *, memberCount: int | None = None) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "status": row.status,
        "statusLabel": STATUS_LABELS_FA.get(row.status, row.status),
        "parentId": str(row.parentId) if row.parentId else None,
        "managerUserId": str(row.managerUserId) if row.managerUserId else None,
        "managerName": row.managerName,
        "isSystem": row.isSystem,
        "memberCount": memberCount,
        "createdAt": row.createdAt.isoformat() if row.createdAt else None,
    }


def positionRow(row, *, memberCount: int | None = None) -> dict:
    return {
        "id": str(row.id),
        "code": row.code,
        "name": row.name,
        "description": row.description,
        "level": row.level,
        "isActive": row.isActive,
        "isSystem": row.isSystem,
        "memberCount": memberCount,
    }


def assignmentRow(row, *, departments: dict, positions: dict) -> dict:
    department = departments.get(str(row.departmentId))
    position = positions.get(str(row.positionId))
    return {
        "id": str(row.id),
        "userId": str(row.userId),
        "userDisplayName": row.userDisplayName,
        "departmentId": str(row.departmentId),
        "departmentName": department.name if department else "",
        "positionId": str(row.positionId),
        "positionName": position.name if position else "",
        "positionLevel": position.level if position else 0,
        "isPrimary": row.isPrimary,
        "isActive": row.isActive,
        "reportsToUserId": str(row.reportsToUserId) if row.reportsToUserId else None,
    }


def capabilityCatalogueView() -> list[dict]:
    """The grid definition the UI renders its columns from.

    Shipped with every matrix response so the screen never hardcodes which
    verbs a capability supports — an unsupported cell must not be drawable,
    because a tick that grants nothing is worse than no tick.
    """
    return [
        {
            "key": capability["key"],
            "label": capability["labelFa"],
            "group": capability["group"],
            "scoped": isScoped(capability["key"]),
            "actions": [
                {"value": action, "label": ACTION_LABELS_FA.get(action, action)}
                for action in actionsFor(capability["key"])
            ],
        }
        for capability in CAPABILITIES
    ]


def organizationRefusal(error: OrganizationRuleViolation) -> Response:
    return Response(
        {
            "success": False,
            "error": {
                "code": error.code,
                "message": error.message,
                "category": "organizationRule",
            },
        },
        status=status.HTTP_422_UNPROCESSABLE_ENTITY,
    )


class Base(APIView):
    authentication_classes = [BearerSessionAuthentication]
    #: Subclasses declare the pair; writes need the heavier one.
    readAction = "organization.department.view"
    writeAction = "organization.department.manage"

    def get_permissions(self):
        action = (
            self.writeAction
            if self.request.method in ("POST", "PATCH", "PUT", "DELETE")
            else self.readAction
        )
        return [IsAuthenticated(), actionPermission(action)()]

    def handle_exception(self, exc):
        if isinstance(exc, OrganizationRuleViolation):
            return organizationRefusal(exc)
        if isinstance(exc, OrganizationNotFound):
            return Response(
                {
                    "success": False,
                    "error": {"code": "organization.notFound", "message": "مورد یافت نشد."},
                },
                status=status.HTTP_404_NOT_FOUND,
            )
        return super().handle_exception(exc)


# --- Departments -----------------------------------------------------------


class DepartmentSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    parentId = serializers.UUIDField(required=False, allow_null=True)
    managerUserId = serializers.UUIDField(required=False, allow_null=True)
    managerName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    status = serializers.ChoiceField(choices=DEPARTMENT_STATUSES, required=False)


class DepartmentListView(Base):
    readAction = "organization.department.view"
    writeAction = "organization.department.manage"

    def get(self, request):
        tenantId = tenant()
        departments = orgRepository.listDepartments(tenantId)
        counts = {
            str(x.id): orgRepository.departmentAssignmentCount(tenantId, x.id) for x in departments
        }
        return Response(
            successEnvelope(
                {
                    "items": [departmentRow(x, memberCount=counts[str(x.id)]) for x in departments],
                    "statuses": [
                        {"value": x, "label": STATUS_LABELS_FA.get(x, x)}
                        for x in DEPARTMENT_STATUSES
                    ],
                }
            )
        )

    def post(self, request):
        serializer = DepartmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("status", None)
        department = orgService.createDepartment(tenant(), actor=actor(), **data)
        return Response(successEnvelope(departmentRow(department)), status=status.HTTP_201_CREATED)


class DepartmentDetailView(Base):
    readAction = "organization.department.view"
    writeAction = "organization.department.manage"

    def get(self, request, departmentId):
        tenantId = tenant()
        department = orgRepository.getDepartment(tenantId, departmentId)
        return Response(
            successEnvelope(
                departmentRow(
                    department,
                    memberCount=orgRepository.departmentAssignmentCount(tenantId, departmentId),
                )
            )
        )

    def patch(self, request, departmentId):
        serializer = DepartmentSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        department = orgService.updateDepartment(
            tenant(), departmentId, actor=actor(), **serializer.validated_data
        )
        return Response(successEnvelope(departmentRow(department)))

    def delete(self, request, departmentId):
        orgService.deleteDepartment(tenant(), departmentId, actor=actor())
        return Response(successEnvelope({"deleted": True}))


# --- Positions -------------------------------------------------------------


class PositionSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=160)
    code = serializers.CharField(max_length=32, required=False, allow_blank=True, default="")
    description = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    level = serializers.IntegerField(required=False, default=0)
    isActive = serializers.BooleanField(required=False)


class PositionListView(Base):
    readAction = "organization.position.view"
    writeAction = "organization.position.manage"

    def get(self, request):
        tenantId = tenant()
        positions = orgRepository.listPositions(tenantId)
        return Response(
            successEnvelope(
                {
                    "items": [
                        positionRow(
                            x,
                            memberCount=orgRepository.positionAssignmentCount(tenantId, x.id),
                        )
                        for x in positions
                    ]
                }
            )
        )

    def post(self, request):
        serializer = PositionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        data.pop("isActive", None)
        position = orgService.createPosition(tenant(), actor=actor(), **data)
        return Response(successEnvelope(positionRow(position)), status=status.HTTP_201_CREATED)


class PositionDetailView(Base):
    readAction = "organization.position.view"
    writeAction = "organization.position.manage"

    def patch(self, request, positionId):
        serializer = PositionSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        position = orgService.updatePosition(
            tenant(), positionId, actor=actor(), **serializer.validated_data
        )
        return Response(successEnvelope(positionRow(position)))

    def delete(self, request, positionId):
        orgService.deletePosition(tenant(), positionId, actor=actor())
        return Response(successEnvelope({"deleted": True}))


# --- Assignments -----------------------------------------------------------


class AssignmentSerializer(serializers.Serializer):
    userId = serializers.UUIDField()
    departmentId = serializers.UUIDField()
    positionId = serializers.UUIDField()
    userDisplayName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    isPrimary = serializers.BooleanField(required=False, default=True)
    reportsToUserId = serializers.UUIDField(required=False, allow_null=True)


class AssignmentPatchSerializer(serializers.Serializer):
    departmentId = serializers.UUIDField(required=False)
    positionId = serializers.UUIDField(required=False)
    isPrimary = serializers.BooleanField(required=False)
    isActive = serializers.BooleanField(required=False)
    reportsToUserId = serializers.UUIDField(required=False, allow_null=True)


class AssignmentListView(Base):
    readAction = "organization.assignment.view"
    writeAction = "organization.assignment.manage"

    def get(self, request):
        tenantId = tenant()
        rows = orgRepository.listAssignments(
            tenantId,
            departmentId=request.query_params.get("departmentId") or None,
            userId=request.query_params.get("userId") or None,
            includeInactive=request.query_params.get("includeInactive") == "true",
        )
        departments = {str(x.id): x for x in orgRepository.listDepartments(tenantId)}
        positions = {str(x.id): x for x in orgRepository.listPositions(tenantId)}
        return Response(
            successEnvelope(
                {
                    "items": [
                        assignmentRow(x, departments=departments, positions=positions) for x in rows
                    ]
                }
            )
        )

    def post(self, request):
        serializer = AssignmentSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        tenantId = tenant()
        assignment = orgService.assignUser(tenantId, actor=actor(), **serializer.validated_data)
        departments = {str(x.id): x for x in orgRepository.listDepartments(tenantId)}
        positions = {str(x.id): x for x in orgRepository.listPositions(tenantId)}
        return Response(
            successEnvelope(
                assignmentRow(assignment, departments=departments, positions=positions)
            ),
            status=status.HTTP_201_CREATED,
        )


class AssignmentDetailView(Base):
    readAction = "organization.assignment.view"
    writeAction = "organization.assignment.manage"

    def patch(self, request, assignmentId):
        serializer = AssignmentPatchSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        tenantId = tenant()
        assignment = orgService.updateAssignment(
            tenantId, assignmentId, actor=actor(), **serializer.validated_data
        )
        departments = {str(x.id): x for x in orgRepository.listDepartments(tenantId)}
        positions = {str(x.id): x for x in orgRepository.listPositions(tenantId)}
        return Response(
            successEnvelope(assignmentRow(assignment, departments=departments, positions=positions))
        )

    def delete(self, request, assignmentId):
        orgService.removeAssignment(tenant(), assignmentId, actor=actor())
        return Response(successEnvelope({"deleted": True}))


# --- The matrix ------------------------------------------------------------


class AccessCellSerializer(serializers.Serializer):
    positionId = serializers.UUIDField()
    capability = serializers.CharField(max_length=40)
    action = serializers.ChoiceField(choices=ACTIONS)
    scope = serializers.ChoiceField(choices=SCOPES, required=False, allow_blank=True, default="")
    departmentId = serializers.UUIDField(required=False, allow_null=True)
    #: ``false`` revokes the cell. One endpoint for both directions so the
    #: UI toggles a checkbox rather than choosing between two calls.
    granted = serializers.BooleanField(required=False, default=True)


class AccessMatrixView(Base):
    readAction = "organization.accessRule.view"
    writeAction = "organization.accessRule.manage"

    def get(self, request):
        tenantId = tenant()
        departmentId = request.query_params.get("departmentId") or None
        return Response(
            successEnvelope(
                {
                    "departmentId": str(departmentId) if departmentId else None,
                    "matrix": orgService.accessMatrixFor(tenantId, departmentId),
                    "positions": [
                        positionRow(x)
                        for x in orgRepository.listPositions(tenantId, includeInactive=False)
                    ],
                    "capabilities": capabilityCatalogueView(),
                    "scopes": [{"value": x, "label": SCOPE_LABELS_FA.get(x, x)} for x in SCOPES],
                }
            )
        )

    def post(self, request):
        serializer = AccessCellSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = dict(serializer.validated_data)
        granted = data.pop("granted", True)
        tenantId = tenant()
        if granted:
            orgService.setAccessCell(tenantId, actor=actor(), **data)
        else:
            data.pop("scope", None)
            orgService.clearAccessCell(tenantId, actor=actor(), **data)
        return Response(
            successEnvelope(
                {
                    "matrix": orgService.accessMatrixFor(tenantId, data.get("departmentId")),
                }
            )
        )


class MyAccessView(APIView):
    """What the signed-in user may do, and how far it reaches.

    Deliberately requires no permission beyond being logged in: a person
    must always be able to see their own access. Being unable to find out
    why a button is missing is what generates support tickets and shared
    passwords.
    """

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request):
        tenantId = tenant()
        context = currentContext()
        userId = uuid.UUID(str(context.actorId))
        profile = accessProfileFor(tenantId, userId)

        departments = {str(x.id): x for x in orgRepository.listDepartments(tenantId)}
        positions = {str(x.id): x for x in orgRepository.listPositions(tenantId)}

        byCapability: dict[str, dict[str, str]] = {}
        for grant in profile.grants:
            byCapability.setdefault(grant.capability, {})[grant.action] = grant.scope

        return Response(
            successEnvelope(
                {
                    "userId": str(userId),
                    "assignments": [
                        {
                            "departmentId": x.departmentId,
                            "departmentName": getattr(departments.get(x.departmentId), "name", ""),
                            "positionId": x.positionId,
                            "positionName": getattr(positions.get(x.positionId), "name", ""),
                        }
                        for x in profile.assignments
                    ],
                    "capabilities": byCapability,
                    "actionCodes": sorted({x.actionCode for x in profile.grants}),
                    "scopes": [{"value": x, "label": SCOPE_LABELS_FA.get(x, x)} for x in SCOPES],
                    "catalogue": capabilityCatalogueView(),
                }
            )
        )


class OrganizationAuditView(Base):
    readAction = "organization.accessRule.view"
    writeAction = "organization.accessRule.manage"

    def get(self, request):
        rows = orgRepository.listAudit(tenant(), limit=200)
        return Response(
            successEnvelope(
                {
                    "items": [
                        {
                            "id": str(x.id),
                            "entity": x.entity,
                            "action": x.action,
                            "summary": x.summary,
                            "actorName": x.actorName,
                            "occurredAt": x.occurredAt.isoformat() if x.occurredAt else None,
                        }
                        for x in rows
                    ]
                }
            )
        )


class SeedOrganizationView(Base):
    readAction = "organization.department.view"
    writeAction = "organization.department.manage"

    def post(self, request):
        """Create the starting units, positions and matrix. Idempotent."""
        created = orgService.seedDefaults(tenant(), now=timezone.now())
        return Response(successEnvelope(created))
