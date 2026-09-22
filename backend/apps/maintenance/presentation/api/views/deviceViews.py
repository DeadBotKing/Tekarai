"""Device API views (Phase 21) — HTTP orchestration only."""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.commands.maintenanceCommands import (
    ChangeDeviceStatusCommand,
    RecordDevicePmCommand,
    RegisterDeviceCommand,
    UpdateDeviceCommand,
)
from apps.maintenance.application.queries.maintenanceQueries import (
    GetDeviceQuery,
    ListDevicesQuery,
    ListDuePmQuery,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.maintenanceSerializers import (
    ChangeDeviceStatusSerializer,
    RecordDevicePmSerializer,
    RegisterDeviceSerializer,
    UpdateDeviceSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope

MAINTENANCE_ERRORS = [
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "DUP_BUSINESS_CODE",
    "STATE_INVALID_TRANSITION",
    "PERM_PERMISSION_DENIED",
]


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


class DeviceListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        query = ListDevicesQuery(
            status=str(request.query_params.get("status", "")).strip(),
            search=str(request.query_params.get("search", "")).strip(),
            ordering=str(request.query_params.get("ordering", "-createdAt")).strip(),
            page=int(request.query_params.get("page", 1) or 1),
            pageSize=int(request.query_params.get("pageSize", 50) or 50),
        )
        dto = container.listDevicesUseCase().execute(query)
        return Response(successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = RegisterDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.registerDeviceUseCase().execute(
            RegisterDeviceCommand(
                tenantId=str(request.data.get("tenantId", "")),
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
                location=str(serializer.validated_data["location"]),
                pmIntervalDays=int(serializer.validated_data["pmIntervalDays"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class DeviceDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, deviceId: str) -> Response:
        dto = container.getDeviceUseCase().execute(GetDeviceQuery(deviceId=str(deviceId)))
        return Response(successEnvelope(asDict(dto)))

    def patch(self, request: Request, deviceId: str) -> Response:
        serializer = UpdateDeviceSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.updateDeviceUseCase().execute(
            UpdateDeviceCommand(
                deviceId=str(deviceId),
                name=str(serializer.validated_data["name"]),
                location=str(serializer.validated_data["location"]),
                pmIntervalDays=int(serializer.validated_data["pmIntervalDays"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class DeviceStatusView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = ChangeDeviceStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.changeDeviceStatusUseCase().execute(
            ChangeDeviceStatusCommand(
                deviceId=str(deviceId), target=str(serializer.validated_data["target"])
            )
        )
        return Response(successEnvelope(asDict(dto)))


class DevicePmView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = RecordDevicePmSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.recordDevicePmUseCase().execute(
            RecordDevicePmCommand(
                deviceId=str(deviceId),
                performedOn=str(serializer.validated_data["performedOn"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class DuePmListView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        dto = container.listDuePmUseCase().execute(ListDuePmQuery())
        return Response(successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta()))
