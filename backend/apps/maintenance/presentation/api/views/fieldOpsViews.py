"""Field-operations API views — work timers, code scanning, offline sync.

HTTP orchestration only: parse, delegate, envelope. The interesting
decisions (what counts as a duplicate, when a timer may start) live in the
domain and application layers.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.useCases.offlineSyncUseCases import (
    ApplySyncBatchCommand,
    SyncHistoryQuery,
    SyncOperationCommand,
)
from apps.maintenance.application.useCases.scanUseCases import ResolveScanQuery
from apps.maintenance.application.useCases.workTimerUseCases import (
    CancelWorkTimerCommand,
    ListWorkTimersQuery,
    StartWorkTimerCommand,
    StopWorkTimerCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.fieldOpsSerializers import (
    ScanQuerySerializer,
    StartWorkTimerSerializer,
    StopWorkTimerSerializer,
    SyncBatchSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


def flag(request: Request, name: str, default: bool = False) -> bool:
    raw = str(request.query_params.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


class FieldOpsView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]


# =====================================================================================
# Work timers
# =====================================================================================
class WorkOrderTimerStartView(FieldOpsView):
    """``POST /maintenance/work-orders/{id}/timer/start``"""

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = StartWorkTimerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.startWorkTimerUseCase().execute(
            StartWorkTimerCommand(
                workOrderId=str(workOrderId),
                technicianName=str(data["technicianName"]),
                startedAt=str(data["startedAt"]),
                hourlyRate=str(data["hourlyRate"]),
                note=str(data["note"]),
                capturedOffline=bool(data["capturedOffline"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class WorkOrderTimerStopView(FieldOpsView):
    """``POST /maintenance/work-orders/{id}/timer/stop``"""

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = StopWorkTimerSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.stopWorkTimerUseCase().execute(
            StopWorkTimerCommand(
                workOrderId=str(workOrderId),
                timerId=str(data["timerId"]),
                technicianName=str(data["technicianName"]),
                endedAt=str(data["endedAt"]),
                note=str(data["note"]),
                pausedSeconds=int(data["pausedSeconds"]),
                capturedOffline=bool(data["capturedOffline"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class WorkOrderTimerListView(FieldOpsView):
    """``GET /maintenance/work-orders/{id}/timers``"""

    def get(self, request: Request, workOrderId: str) -> Response:
        items = container.listWorkTimersUseCase().execute(
            ListWorkTimersQuery(
                workOrderId=str(workOrderId),
                runningOnly=flag(request, "runningOnly"),
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))


class WorkTimerDetailView(FieldOpsView):
    """``DELETE /maintenance/work-timers/{id}`` — discard a mis-tapped span."""

    def delete(self, request: Request, timerId: str) -> Response:
        dto = container.cancelWorkTimerUseCase().execute(
            CancelWorkTimerCommand(timerId=str(timerId))
        )
        return Response(successEnvelope(asDict(dto)))


class MyRunningTimersView(FieldOpsView):
    """``GET /maintenance/work-timers/active`` — resume after an app restart."""

    def get(self, request: Request) -> Response:
        items = container.getMyRunningTimersUseCase().execute(
            ListWorkTimersQuery(
                technicianName=str(request.query_params.get("technicianName", "")).strip()
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))


# =====================================================================================
# Scanning
# =====================================================================================
class ScanResolveView(FieldOpsView):
    """``GET /maintenance/scan?code=…&symbology=qr_code``"""

    def get(self, request: Request) -> Response:
        serializer = ScanQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.resolveScanUseCase().execute(
            ResolveScanQuery(code=str(data["code"]), symbology=str(data["symbology"]))
        )
        return Response(successEnvelope(asDict(dto)))


# =====================================================================================
# Offline sync
# =====================================================================================
class OfflineSyncView(FieldOpsView):
    """``POST /maintenance/sync`` — replay a phone's queue.

    Always 200 on a well-formed batch, even when individual items were
    rejected: the per-item verdicts are the payload, and an HTTP error would
    make the queue retry items that can never succeed.
    """

    def post(self, request: Request) -> Response:
        serializer = SyncBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        operations = [
            SyncOperationCommand(
                clientRequestId=str(item["clientRequestId"]),
                kind=str(item["kind"]),
                payload=dict(item.get("payload") or {}),
                occurredAt=str(item.get("occurredAt") or ""),
            )
            for item in data["operations"]
        ]
        result = container.applySyncBatchUseCase().execute(
            ApplySyncBatchCommand(
                operations=operations,
                deviceLabel=str(data["deviceLabel"]),
                atomic=bool(data["atomic"]),
            )
        )
        return Response(
            successEnvelope([asDict(item) for item in result.results], meta=result.asMeta())
        )


class SyncHistoryView(FieldOpsView):
    """``GET /maintenance/sync/history`` — what phones have replayed lately."""

    def get(self, request: Request) -> Response:
        raw = str(request.query_params.get("limit", "50")).strip()
        limit = int(raw) if raw.isdigit() else 50
        items = container.listSyncHistoryUseCase().execute(SyncHistoryQuery(limit=limit))
        return Response(successEnvelope([asDict(item) for item in items]))
