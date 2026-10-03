"""Meter-reading API views — HTTP orchestration only.

Two authentication paths meet here. Human traffic arrives with a bearer
session; a field gateway arrives with ``X-API-Key``. The ingest endpoint
accepts both, every other endpoint only the session — a gateway credential
leaking off a PLC cabinet must not be able to read the plant's history or
redefine its meters.
"""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.useCases.meterReadingUseCases import (
    CorrectMeterReadingCommand,
    DeleteMeterPointCommand,
    IngestSensorReadingsCommand,
    ListMeterPointsQuery,
    ListMeterReadingsQuery,
    MeterPmStatusQuery,
    MeterPointSummaryQuery,
    RecordManualReadingCommand,
    SaveMeterPointCommand,
    SensorSampleCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.meterSerializers import (
    CorrectMeterReadingSerializer,
    IngestSensorReadingsSerializer,
    RecordManualReadingSerializer,
    SaveMeterPointSerializer,
)
from apps.sharedKernel.presentation.api.authentication import (
    ApiKeyAuthentication,
    BearerSessionAuthentication,
)
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


def flag(request: Request, name: str, default: bool = False) -> bool:
    raw = str(request.query_params.get(name, "")).strip().lower()
    if not raw:
        return default
    return raw in ("1", "true", "yes", "on")


class MeterView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]


# =====================================================================================
# Meter point definitions
# =====================================================================================
class DeviceMeterPointListView(IdempotencyMixin, MeterView):
    """``/maintenance/devices/{deviceId}/meter-points``"""

    def get(self, request: Request, deviceId: str) -> Response:
        items = container.listMeterPointsUseCase().execute(
            ListMeterPointsQuery(
                deviceId=str(deviceId),
                activeOnly=flag(request, "activeOnly"),
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = SaveMeterPointSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.saveMeterPointUseCase().execute(
            SaveMeterPointCommand(
                deviceId=str(deviceId),
                code=str(data["code"]),
                name=str(data["name"]),
                unit=str(data["unit"]),
                kind=str(data["kind"]),
                sensorKey=str(data["sensorKey"]),
                minimumValue=str(data["minimumValue"]),
                maximumValue=str(data["maximumValue"]),
                rolloverMaximum=str(data["rolloverMaximum"]),
                maximumStepPerHour=str(data["maximumStepPerHour"]),
                drivesRunningHours=bool(data["drivesRunningHours"]),
                active=bool(data["active"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class MeterPointListView(MeterView):
    """``/maintenance/meter-points`` — tenant-wide search."""

    def get(self, request: Request) -> Response:
        items = container.listMeterPointsUseCase().execute(
            ListMeterPointsQuery(
                search=str(request.query_params.get("search", "")).strip(),
                kind=str(request.query_params.get("kind", "")).strip(),
                activeOnly=flag(request, "activeOnly"),
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))


class MeterPointDetailView(MeterView):
    """``/maintenance/meter-points/{meterPointId}``"""

    def patch(self, request: Request, meterPointId: str) -> Response:
        serializer = SaveMeterPointSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.saveMeterPointUseCase().execute(
            SaveMeterPointCommand(
                meterPointId=str(meterPointId),
                code=str(data.get("code", "")),
                name=str(data.get("name", "")),
                unit=str(data.get("unit", "")),
                kind=str(data.get("kind", "")),
                sensorKey=str(data.get("sensorKey", "")),
                minimumValue=str(data.get("minimumValue", "")),
                maximumValue=str(data.get("maximumValue", "")),
                rolloverMaximum=str(data.get("rolloverMaximum", "")),
                maximumStepPerHour=str(data.get("maximumStepPerHour", "")),
                drivesRunningHours=bool(data.get("drivesRunningHours", False)),
                active=bool(data.get("active", True)),
            )
        )
        return Response(successEnvelope(asDict(dto)))

    def delete(self, request: Request, meterPointId: str) -> Response:
        container.deleteMeterPointUseCase().execute(
            DeleteMeterPointCommand(meterPointId=str(meterPointId))
        )
        return Response(successEnvelope({"id": str(meterPointId)}))


# =====================================================================================
# Readings
# =====================================================================================
class DeviceMeterReadingView(IdempotencyMixin, MeterView):
    """``/maintenance/devices/{deviceId}/meter-readings`` — manual capture."""

    def get(self, request: Request, deviceId: str) -> Response:
        dto = container.listMeterReadingsUseCase().execute(
            _listQuery(request, deviceId=str(deviceId))
        )
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta())
        )

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = RecordManualReadingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.recordManualMeterReadingUseCase().execute(
            RecordManualReadingCommand(
                deviceId=str(deviceId),
                meterPointId=str(data["meterPointId"]),
                meterCode=str(data["meterCode"]),
                value=str(data["value"]),
                capturedAt=str(data["capturedAt"]),
                note=str(data["note"]),
                quality=str(data["quality"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class MeterReadingListView(MeterView):
    """``/maintenance/meter-readings`` — cross-device query."""

    def get(self, request: Request) -> Response:
        dto = container.listMeterReadingsUseCase().execute(_listQuery(request))
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta())
        )


class MeterPointReadingView(MeterView):
    """``/maintenance/meter-points/{meterPointId}/readings``"""

    def get(self, request: Request, meterPointId: str) -> Response:
        dto = container.listMeterReadingsUseCase().execute(
            _listQuery(request, meterPointId=str(meterPointId))
        )
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta())
        )


class MeterPointSummaryView(MeterView):
    """``/maintenance/meter-points/{meterPointId}/summary``"""

    def get(self, request: Request, meterPointId: str) -> Response:
        dto = container.getMeterPointSummaryUseCase().execute(
            MeterPointSummaryQuery(
                meterPointId=str(meterPointId),
                fromMoment=str(request.query_params.get("from", "")).strip(),
                toMoment=str(request.query_params.get("to", "")).strip(),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class MeterReadingCorrectionView(MeterView):
    """``/maintenance/meter-readings/{readingId}/correct``

    There is deliberately no PATCH or DELETE on a reading anywhere in this
    module: the only way to change what a reading says is to append a new one
    that supersedes it.
    """

    def post(self, request: Request, readingId: str) -> Response:
        serializer = CorrectMeterReadingSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.correctMeterReadingUseCase().execute(
            CorrectMeterReadingCommand(
                readingId=str(readingId),
                value=str(data["value"]),
                note=str(data["note"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class SensorIngestView(APIView):
    """``/maintenance/meter-readings/ingest`` — the gateway endpoint.

    Accepts ``X-API-Key`` as well as a bearer session so a PLC gateway can
    authenticate with a scoped service credential instead of a human login.
    """

    authentication_classes = [ApiKeyAuthentication, BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request) -> Response:
        serializer = IngestSensorReadingsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        samples = tuple(
            SensorSampleCommand(
                sensorKey=str(row["sensorKey"]),
                meterPointId=str(row["meterPointId"]),
                value=str(row["value"]),
                capturedAt=str(row["capturedAt"]),
                quality=str(row["quality"]),
                ingestionKey=str(row["ingestionKey"]),
                sourceRef=str(row["sourceRef"]),
            )
            for row in data["readings"]
        )
        dto = container.ingestSensorReadingsUseCase().execute(
            IngestSensorReadingsCommand(samples=samples, atomic=bool(data["atomic"]))
        )
        # 207-style semantics inside a 200: the batch itself was processed, and
        # each item reports its own fate. A single HTTP status cannot describe
        # "483 accepted, 2 duplicates, 1 rejected".
        return Response(
            successEnvelope([asDict(item) for item in dto.results], meta=dto.asMeta())
        )


class MeterPmStatusView(MeterView):
    """``/maintenance/meter-pm-status`` — meter-driven PM due feed."""

    def get(self, request: Request) -> Response:
        items = container.getMeterPmStatusUseCase().execute(
            MeterPmStatusQuery(
                deviceId=str(request.query_params.get("deviceId", "")).strip(),
                statusFilter=str(request.query_params.get("status", "")).strip(),
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))


def _listQuery(
    request: Request, deviceId: str = "", meterPointId: str = ""
) -> ListMeterReadingsQuery:
    return ListMeterReadingsQuery(
        deviceId=deviceId or str(request.query_params.get("deviceId", "")).strip(),
        meterPointId=meterPointId
        or str(request.query_params.get("meterPointId", "")).strip(),
        captureMode=str(request.query_params.get("captureMode", "")).strip(),
        quality=str(request.query_params.get("quality", "")).strip(),
        fromMoment=str(request.query_params.get("from", "")).strip(),
        toMoment=str(request.query_params.get("to", "")).strip(),
        includeSuperseded=flag(request, "includeSuperseded", default=True),
        page=int(request.query_params.get("page", 1) or 1),
        pageSize=int(request.query_params.get("pageSize", 100) or 100),
    )


__all__ = [
    "DeviceMeterPointListView",
    "DeviceMeterReadingView",
    "MeterPmStatusView",
    "MeterPointDetailView",
    "MeterPointListView",
    "MeterPointReadingView",
    "MeterPointSummaryView",
    "MeterReadingCorrectionView",
    "MeterReadingListView",
    "SensorIngestView",
]
