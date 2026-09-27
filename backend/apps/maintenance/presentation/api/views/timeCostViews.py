"""Time & cost tracking HTTP endpoints (ثبت زمان و هزینه).

* ``/work-orders/{id}/labour`` — log and list technician work hours;
* ``/work-orders/{id}/cost-summary`` — the cost evidence of one request;
* ``/reports/maintenance-costs`` — گزارش هزینه‌ی نگهداری (JSON / CSV / XLSX).
"""

from __future__ import annotations

import dataclasses

from django.http import HttpResponse
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.commands.timeCostCommands import (
    DeleteLabourEntryCommand,
    ListLabourEntriesQuery,
    LogLabourEntryCommand,
    MaintenanceCostReportQuery,
    WorkOrderCostSummaryQuery,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.reports.costReportExporters import (
    buildCostReportCsv,
    buildCostReportPdf,
    buildCostReportXlsx,
)
from apps.maintenance.presentation.api.serializers.maintenanceSerializers import (
    CostReportQuerySerializer,
    LogLabourEntrySerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class WorkOrderLabourEntryView(IdempotencyMixin, APIView):
    """Log technician work hours on a request and list its logged entries."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workOrderId: str) -> Response:
        result = container.listLabourEntriesUseCase().execute(
            ListLabourEntriesQuery(workOrderId=str(workOrderId))
        )
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in result.items], meta=result.asMeta()
            )
        )

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = LogLabourEntrySerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.logLabourEntryUseCase().execute(
            LogLabourEntryCommand(
                workOrderId=str(workOrderId),
                technicianName=str(data["technicianName"]),
                hours=str(data["hours"]),
                hourlyRate=str(data["hourlyRate"]),
                workedAt=str(data["workedAt"]),
                note=str(data["note"]),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class LabourEntryDetailView(IdempotencyMixin, APIView):
    """Remove a wrongly-logged labour entry (its share leaves the roll-up)."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, entryId: str) -> Response:
        result = container.deleteLabourEntryUseCase().execute(
            DeleteLabourEntryCommand(entryId=str(entryId))
        )
        return Response(successEnvelope(dataclasses.asdict(result)))


class WorkOrderCostSummaryView(APIView):
    """Cost evidence of one request: labour entries + part usages + totals."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workOrderId: str) -> Response:
        result = container.getWorkOrderCostSummaryUseCase().execute(
            WorkOrderCostSummaryQuery(workOrderId=str(workOrderId))
        )
        return Response(successEnvelope(dataclasses.asdict(result)))


class MaintenanceCostReportView(APIView):
    """گزارش هزینه‌ی نگهداری across the tenant.

    JSON by default; ``?export=csv`` or ``?export=xlsx`` streams a
    Persian-labelled download. ``fromDate``/``toDate`` bound work orders by
    creation date and ``deviceId``/``department`` narrow the scope.
    """

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response | HttpResponse:
        params = CostReportQuerySerializer(data=request.query_params)
        params.is_valid(raise_exception=True)
        fromDate = params.validated_data.get("fromDate")
        toDate = params.validated_data.get("toDate")
        deviceId = params.validated_data.get("deviceId")
        exportFormat = params.validated_data.get("export") or "json"

        report = container.getMaintenanceCostReportUseCase().execute(
            MaintenanceCostReportQuery(
                fromDate=fromDate.isoformat() if fromDate else "",
                toDate=toDate.isoformat() if toDate else "",
                deviceId=str(deviceId) if deviceId else "",
                department=str(params.validated_data.get("department") or ""),
            )
        )

        if exportFormat == "csv":
            content = buildCostReportCsv(report)
            response = HttpResponse(content, content_type="text/csv; charset=utf-8")
            response["Content-Disposition"] = (
                f'attachment; filename="maintenance-costs-{report.fromDate}.csv"'
            )
            return response

        if exportFormat == "xlsx":
            content = buildCostReportXlsx(report)
            response = HttpResponse(
                content,
                content_type=("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
            )
            response["Content-Disposition"] = (
                f'attachment; filename="maintenance-costs-{report.fromDate}.xlsx"'
            )
            return response

        if exportFormat == "pdf":
            content = buildCostReportPdf(report)
            response = HttpResponse(content, content_type="application/pdf")
            response["Content-Disposition"] = (
                f'attachment; filename="maintenance-costs-{report.fromDate}.pdf"'
            )
            return response

        return Response(successEnvelope(dataclasses.asdict(report), meta=report.asMeta()))
