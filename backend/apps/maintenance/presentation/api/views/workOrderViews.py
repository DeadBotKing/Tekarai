"""Work order API views (Phase 21) — HTTP orchestration only."""

from __future__ import annotations

import dataclasses
from typing import Any

from django.http import HttpResponse
from django.utils.http import content_disposition_header
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.commands.maintenanceCommands import (
    ApproveWorkOrderCommand,
    AssignWorkOrderCommand,
    ChangeWorkOrderStatusCommand,
    GeneratePmWorkOrdersCommand,
    RejectWorkOrderCommand,
    RouteWorkOrderCommand,
    SubmitWorkOrderCommand,
    UpdateWorkOrderCommand,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    DeviceMaintenanceReportQuery,
    GetWorkOrderQuery,
    ListWorkOrderHistoryQuery,
    ListWorkOrdersQuery,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.reports.reportExporters import (
    buildDeviceReportCsv,
    buildDeviceReportPdf,
    buildDeviceReportXlsx,
)
from apps.maintenance.presentation.api.serializers.maintenanceSerializers import (
    ApproveWorkOrderSerializer,
    AssignWorkOrderSerializer,
    ChangeWorkOrderStatusSerializer,
    DeviceReportQuerySerializer,
    RejectWorkOrderSerializer,
    RouteWorkOrderSerializer,
    SubmitWorkOrderSerializer,
    UpdateWorkOrderSerializer,
)
from apps.sharedKernel.domain.errors import PermissionDeniedError
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)



def currentActorId() -> str:
    """The signed-in user's id, or "" when there is no request actor."""
    from apps.sharedKernel.application.requestContext import currentContext

    return str(getattr(currentContext(), "actorId", "") or "")


def assertRecordInScope(workOrderId: str, action: str) -> None:
    """Refuse a single record the caller's scope does not cover.

    The list query and this check read the same resolution, so a user can
    never be shown a row in a list that they are then refused on open —
    the inconsistency that teaches people the permissions are arbitrary.
    """
    import uuid as _uuid

    from apps.maintenance.infrastructure.models import WorkOrderModel
    from apps.sharedKernel.application.requestContext import currentContext

    context = currentContext()
    actorId = str(getattr(context, "actorId", "") or "")
    tenantRaw = getattr(context, "tenantId", None) or getattr(context, "actorTenantId", None)
    if not actorId or not tenantRaw:
        return
    try:
        from apps.organization.application.services.accessContract import (
            hasOrganizationStructure,
            userCanActOnRecord,
        )

        tenantId = _uuid.UUID(str(tenantRaw))
        if not hasOrganizationStructure(tenantId):
            return
        row = (
            WorkOrderModel.objects.filter(id=workOrderId, tenantId=tenantId)
            .values("orgDepartmentId", "requestedByUserId", "assignedToUserId")
            .first()
        )
        if row is None:
            return
        allowed = userCanActOnRecord(
            tenantId,
            _uuid.UUID(actorId),
            action,
            ownerUserId=str(row["requestedByUserId"] or ""),
            departmentId=str(row["orgDepartmentId"] or ""),
        ) or userCanActOnRecord(
            tenantId,
            _uuid.UUID(actorId),
            action,
            # A technician assigned to a job owns it for access purposes
            # even when somebody else raised it; otherwise «کار خودش»
            # would exclude the work he was told to do.
            ownerUserId=str(row["assignedToUserId"] or ""),
            departmentId=str(row["orgDepartmentId"] or ""),
        )
    except (ImportError, ValueError):
        return
    if not allowed:
        raise PermissionDeniedError(action)

class WorkOrderListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response | HttpResponse:
        exportFormat = str(request.query_params.get("export", "")).strip().lower()

        def buildQuery(page: int, pageSize: int) -> ListWorkOrdersQuery:
            return ListWorkOrdersQuery(
                # Phase 28: the list is narrowed by the caller's postings.
                # Passed from the view because the actor is a request fact,
                # and taken from the session rather than any parameter — a
                # client must not be able to ask for someone else's scope.
                actorUserId=currentActorId(),
                deviceId=str(request.query_params.get("deviceId", "")).strip(),
                status=str(request.query_params.get("status", "")).strip(),
                orderType=str(request.query_params.get("orderType", "")).strip(),
                priority=str(request.query_params.get("priority", "")).strip(),
                department=str(request.query_params.get("department", "")).strip(),
                search=str(request.query_params.get("search", "")).strip(),
                ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
                page=page,
                pageSize=pageSize,
            )

        if exportFormat in ("csv", "xlsx", "pdf"):
            # Exports always carry the FULL filtered result set, not one page.
            from apps.maintenance.presentation.api.reports.listExporters import (
                EXPORT_CONTENT_TYPES as LIST_EXPORT_TYPES,
            )
            from apps.maintenance.presentation.api.reports.listExporters import (
                buildWorkOrdersExport,
            )

            collected: list[Any] = []
            page = 1
            while True:
                dto = container.listWorkOrdersUseCase().execute(buildQuery(page, 250))
                collected.extend(dto.items)
                if len(collected) >= dto.totalCount or not dto.items:
                    break
                page += 1
            content = buildWorkOrdersExport(collected, exportFormat)
            response = HttpResponse(content, content_type=LIST_EXPORT_TYPES[exportFormat])
            response["Content-Disposition"] = content_disposition_header(
                as_attachment=True, filename=f"work-orders.{exportFormat}"
            )
            return response

        dto = container.listWorkOrdersUseCase().execute(
            buildQuery(
                page=int(request.query_params.get("page", 1) or 1),
                pageSize=int(request.query_params.get("pageSize", 50) or 50),
            )
        )
        return Response(successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = SubmitWorkOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.submitWorkOrderUseCase().execute(
            SubmitWorkOrderCommand(
                tenantId=str(request.data.get("tenantId", "")),
                deviceId=str(serializer.validated_data["deviceId"]),
                title=str(serializer.validated_data["title"]),
                description=str(serializer.validated_data["description"]),
                orderType=str(serializer.validated_data["orderType"]),
                priority=str(serializer.validated_data["priority"]),
                department=str(serializer.validated_data["department"]),
                requestedByName=str(serializer.validated_data["requestedByName"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class WorkOrderDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workOrderId: str) -> Response:
        assertRecordInScope(str(workOrderId), "maintenance.workorder.view")
        dto = container.getWorkOrderUseCase().execute(
            GetWorkOrderQuery(workOrderId=str(workOrderId))
        )
        return Response(successEnvelope(asDict(dto)))

    def patch(self, request: Request, workOrderId: str) -> Response:
        assertRecordInScope(str(workOrderId), "maintenance.workorder.update")
        serializer = UpdateWorkOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.updateWorkOrderUseCase().execute(
            UpdateWorkOrderCommand(
                workOrderId=str(workOrderId),
                title=str(serializer.validated_data["title"]),
                description=str(serializer.validated_data["description"]),
                priority=str(serializer.validated_data["priority"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class WorkOrderGeneratePmView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        dto = container.generatePmWorkOrdersUseCase().execute(
            GeneratePmWorkOrdersCommand(
                tenantId=str(request.data.get("tenantId", "")),
            )
        )
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()),
            status=201,
        )


class WorkOrderRouteView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = RouteWorkOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.routeWorkOrderUseCase().execute(
            RouteWorkOrderCommand(
                workOrderId=str(workOrderId),
                department=str(serializer.validated_data["department"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class WorkOrderAssignView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = AssignWorkOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = AssignWorkOrderCommand(
            workOrderId=str(workOrderId),
            assignedToName=str(serializer.validated_data["assignedToName"]),
        )
        # ``auto`` picks the least-loaded technician of the order's department.
        if serializer.validated_data.get("auto"):
            dto = container.autoAssignWorkOrderUseCase().execute(command)
        else:
            dto = container.assignWorkOrderUseCase().execute(command)
        return Response(successEnvelope(asDict(dto)))


class WorkOrderApproveView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = ApproveWorkOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.approveWorkOrderUseCase().execute(
            ApproveWorkOrderCommand(
                workOrderId=str(workOrderId),
                note=str(serializer.validated_data["note"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class WorkOrderRejectView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = RejectWorkOrderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.rejectWorkOrderUseCase().execute(
            RejectWorkOrderCommand(
                workOrderId=str(workOrderId),
                note=str(serializer.validated_data["note"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class WorkOrderHistoryView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workOrderId: str) -> Response:
        dto = container.listWorkOrderHistoryUseCase().execute(
            ListWorkOrderHistoryQuery(workOrderId=str(workOrderId))
        )
        return Response(successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()))


class WorkOrderStatusView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = ChangeWorkOrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.changeWorkOrderStatusUseCase().execute(
            ChangeWorkOrderStatusCommand(
                workOrderId=str(workOrderId),
                target=str(serializer.validated_data["target"]),
                resolutionNote=str(serializer.validated_data["resolutionNote"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class DeviceMaintenanceReportView(APIView):
    """Full maintenance history + stats for one device (Phase 23 reporting).

    Returns JSON by default; ``?export=csv`` or ``?export=xlsx`` stream a
    Persian-labelled download. Optional ``fromDate``/``toDate`` (YYYY-MM-DD)
    bound the work orders by creation date. The printable PDF is produced by
    the frontend's browser-print report page from the same JSON payload.
    """

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, deviceId: str) -> Response | HttpResponse:
        params = DeviceReportQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        fromDate = params.validated_data.get("fromDate")
        toDate = params.validated_data.get("toDate")
        exportFormat = params.validated_data.get("export") or "json"

        report = container.deviceMaintenanceReportUseCase().execute(
            DeviceMaintenanceReportQuery(
                deviceId=str(deviceId),
                fromDate=fromDate.isoformat() if fromDate else "",
                toDate=toDate.isoformat() if toDate else "",
            )
        )

        if exportFormat == "csv":
            content = buildDeviceReportCsv(report)
            filename = f"maintenance-report-{report.device.code}.csv"
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = content_disposition_header(
                as_attachment=True, filename=filename
            )
            return response

        if exportFormat == "xlsx":
            content = buildDeviceReportXlsx(report)
            filename = f"maintenance-report-{report.device.code}.xlsx"
            response = HttpResponse(
                content,
                content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            )
            response["Content-Disposition"] = content_disposition_header(
                as_attachment=True, filename=filename
            )
            return response

        if exportFormat == "pdf":
            content = buildDeviceReportPdf(report)
            filename = f"maintenance-report-{report.device.code}.pdf"
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = content_disposition_header(
                as_attachment=True, filename=filename
            )
            return response

        return Response(successEnvelope(asDict(report), meta=report.asMeta()))
