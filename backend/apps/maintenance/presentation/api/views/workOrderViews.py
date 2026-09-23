"""Work order API views (Phase 21) — HTTP orchestration only."""

from __future__ import annotations

import dataclasses
from typing import Any

from django.http import HttpResponse
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
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


class WorkOrderListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListWorkOrdersQuery(
            deviceId=str(request.query_params.get("deviceId", "")).strip(),
            status=str(request.query_params.get("status", "")).strip(),
            orderType=str(request.query_params.get("orderType", "")).strip(),
            priority=str(request.query_params.get("priority", "")).strip(),
            department=str(request.query_params.get("department", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=int(request.query_params.get("page", 1) or 1),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
        )
        dto = container.listWorkOrdersUseCase().execute(query)
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
        dto = container.getWorkOrderUseCase().execute(
            GetWorkOrderQuery(workOrderId=str(workOrderId))
        )
        return Response(successEnvelope(asDict(dto)))

    def patch(self, request: Request, workOrderId: str) -> Response:
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
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta())
        )


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

    Returns JSON by default; ``?format=csv`` or ``?format=xlsx`` stream a
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
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        if exportFormat == "xlsx":
            content = buildDeviceReportXlsx(report)
            filename = f"maintenance-report-{report.device.code}.xlsx"
            response = HttpResponse(
                content,
                content_type=(
                    "application/vnd.openxmlformats-officedocument."
                    "spreadsheetml.sheet"
                ),
            )
            response["Content-Disposition"] = f'attachment; filename="{filename}"'
            return response

        return Response(successEnvelope(asDict(report), meta=report.asMeta()))
