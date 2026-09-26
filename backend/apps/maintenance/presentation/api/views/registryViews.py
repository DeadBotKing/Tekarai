"""Equipment-registry and analytics API views (Phase 26) — HTTP orchestration only."""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.useCases.registryUseCases import (
    DeleteLocationCommand,
    DeletePersonnelCommand,
    DeletePmPlanCommand,
    GetDeviceAnalyticsQuery,
    GetDeviceProfileQuery,
    GetFleetAnalyticsQuery,
    GetPartUsageReportQuery,
    ListLocationsQuery,
    ListPersonnelQuery,
    RecordClosureDetailsCommand,
    RecordPmExecutionCommand,
    RemoveBomItemCommand,
    SaveAssignmentsCommand,
    SaveBomItemCommand,
    SaveLocationCommand,
    SavePersonnelCommand,
    SavePmPlanCommand,
    SaveSpecificationsCommand,
    UpdateNameplateCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.registrySerializers import (
    CloseWorkOrderDetailsSerializer,
    RecordPmExecutionSerializer,
    SaveAssignmentsSerializer,
    SaveBomItemSerializer,
    SaveLocationSerializer,
    SavePersonnelSerializer,
    SavePmPlanSerializer,
    SaveSpecificationsSerializer,
    UpdateDeviceNameplateSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def asDict(dto: Any) -> dict[str, Any]:
    return dataclasses.asdict(dto)


class RegistryView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]


# =====================================================================================
# Locations
# =====================================================================================
class LocationListView(IdempotencyMixin, RegistryView):
    def get(self, request: Request) -> Response:
        dto = container.listLocationsUseCase().execute(
            ListLocationsQuery(search=str(request.query_params.get("search", "")).strip())
        )
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta())
        )

    def post(self, request: Request) -> Response:
        serializer = SaveLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.saveLocationUseCase().execute(
            SaveLocationCommand(
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
                kind=str(serializer.validated_data["kind"]),
                parentId=str(serializer.validated_data["parentId"]),
                note=str(serializer.validated_data["note"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class LocationDetailView(RegistryView):
    def patch(self, request: Request, locationId: str) -> Response:
        serializer = SaveLocationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.saveLocationUseCase().execute(
            SaveLocationCommand(
                locationId=str(locationId),
                code=str(serializer.validated_data["code"]),
                name=str(serializer.validated_data["name"]),
                kind=str(serializer.validated_data["kind"]),
                parentId=str(serializer.validated_data["parentId"]),
                note=str(serializer.validated_data["note"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))

    def delete(self, request: Request, locationId: str) -> Response:
        payload = container.deleteLocationUseCase().execute(
            DeleteLocationCommand(locationId=str(locationId))
        )
        return Response(successEnvelope(payload))


# =====================================================================================
# Personnel
# =====================================================================================
class PersonnelListView(IdempotencyMixin, RegistryView):
    def get(self, request: Request) -> Response:
        dto = container.listPersonnelUseCase().execute(
            ListPersonnelQuery(
                search=str(request.query_params.get("search", "")).strip(),
                specialty=str(request.query_params.get("specialty", "")).strip(),
            )
        )
        return Response(
            successEnvelope([asDict(item) for item in dto.items], meta=dto.asMeta())
        )

    def post(self, request: Request) -> Response:
        serializer = SavePersonnelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.savePersonnelUseCase().execute(
            SavePersonnelCommand(
                personnelCode=str(data["personnelCode"]),
                fullName=str(data["fullName"]),
                specialty=str(data["specialty"]),
                unit=str(data["unit"]),
                phone=str(data["phone"]),
                shift=str(data["shift"]),
                skills=tuple(data["skills"]),
                certifications=tuple(data["certifications"]),
                active=bool(data["active"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class PersonnelDetailView(RegistryView):
    def patch(self, request: Request, personnelId: str) -> Response:
        serializer = SavePersonnelSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.savePersonnelUseCase().execute(
            SavePersonnelCommand(
                personnelId=str(personnelId),
                personnelCode=str(data["personnelCode"]),
                fullName=str(data["fullName"]),
                specialty=str(data["specialty"]),
                unit=str(data["unit"]),
                phone=str(data["phone"]),
                shift=str(data["shift"]),
                skills=tuple(data["skills"]),
                certifications=tuple(data["certifications"]),
                active=bool(data["active"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))

    def delete(self, request: Request, personnelId: str) -> Response:
        payload = container.deletePersonnelUseCase().execute(
            DeletePersonnelCommand(personnelId=str(personnelId))
        )
        return Response(successEnvelope(payload))


# =====================================================================================
# Device registry sections
# =====================================================================================
class DeviceProfileView(RegistryView):
    """The complete equipment file for one device."""

    def get(self, request: Request, deviceId: str) -> Response:
        dto = container.getDeviceProfileUseCase().execute(
            GetDeviceProfileQuery(
                deviceId=str(deviceId),
                fromDate=str(request.query_params.get("fromDate", "")).strip(),
                toDate=str(request.query_params.get("toDate", "")).strip(),
            )
        )
        return Response(successEnvelope(asDict(dto), meta=dto.asMeta()))


class DeviceNameplateView(RegistryView):
    def patch(self, request: Request, deviceId: str) -> Response:
        serializer = UpdateDeviceNameplateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = container.updateDeviceNameplateUseCase().execute(
            UpdateNameplateCommand(
                deviceId=str(deviceId),
                values={
                    key: value
                    for key, value in serializer.validated_data.items()
                    if key in request.data
                },
            )
        )
        return Response(successEnvelope(payload))


class DeviceSpecificationsView(RegistryView):
    def put(self, request: Request, deviceId: str) -> Response:
        serializer = SaveSpecificationsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = container.saveSpecificationsUseCase().execute(
            SaveSpecificationsCommand(
                deviceId=str(deviceId),
                rows=tuple(dict(row) for row in serializer.validated_data["rows"]),
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))


class DevicePmPlanListView(IdempotencyMixin, RegistryView):
    def get(self, request: Request, deviceId: str) -> Response:
        items = container.listPmPlansUseCase().execute(
            GetDeviceProfileQuery(deviceId=str(deviceId))
        )
        return Response(successEnvelope([asDict(item) for item in items]))

    def post(self, request: Request, deviceId: str) -> Response:
        serializer = SavePmPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.savePmPlanUseCase().execute(
            SavePmPlanCommand(
                deviceId=str(deviceId),
                title=str(data["title"]),
                discipline=str(data["discipline"]),
                description=str(data["description"]),
                checklist=tuple(data["checklist"]),
                frequencyEvery=int(data["frequencyEvery"]),
                frequencyUnit=str(data["frequencyUnit"]),
                estimatedMinutes=int(data["estimatedMinutes"]),
                responsibleName=str(data["responsibleName"]),
                active=bool(data["active"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class PmPlanDetailView(RegistryView):
    def patch(self, request: Request, planId: str) -> Response:
        serializer = SavePmPlanSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.savePmPlanUseCase().execute(
            SavePmPlanCommand(
                planId=str(planId),
                title=str(data["title"]),
                discipline=str(data["discipline"]),
                description=str(data["description"]),
                checklist=tuple(data["checklist"]),
                frequencyEvery=int(data["frequencyEvery"]),
                frequencyUnit=str(data["frequencyUnit"]),
                estimatedMinutes=int(data["estimatedMinutes"]),
                responsibleName=str(data["responsibleName"]),
                active=bool(data["active"]),
            )
        )
        return Response(successEnvelope(asDict(dto)))

    def delete(self, request: Request, planId: str) -> Response:
        payload = container.deletePmPlanUseCase().execute(
            DeletePmPlanCommand(planId=str(planId))
        )
        return Response(successEnvelope(payload))


class PmPlanExecutionView(IdempotencyMixin, RegistryView):
    def post(self, request: Request, planId: str) -> Response:
        serializer = RecordPmExecutionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.recordPmExecutionUseCase().execute(
            RecordPmExecutionCommand(
                planId=str(planId),
                performedOn=str(data["performedOn"]),
                performedByName=str(data["performedByName"]),
                durationMinutes=int(data["durationMinutes"]),
                findings=str(data["findings"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class DeviceBomView(IdempotencyMixin, RegistryView):
    def post(self, request: Request, deviceId: str) -> Response:
        serializer = SaveBomItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        dto = container.saveBomItemUseCase().execute(
            SaveBomItemCommand(
                deviceId=str(deviceId),
                partId=str(data["partId"]),
                position=str(data["position"]),
                standardQuantity=str(data["standardQuantity"]),
                note=str(data["note"]),
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class DeviceBomItemView(RegistryView):
    def delete(self, request: Request, deviceId: str, partId: str) -> Response:
        payload = container.removeBomItemUseCase().execute(
            RemoveBomItemCommand(deviceId=str(deviceId), partId=str(partId))
        )
        return Response(successEnvelope(payload))


class DeviceAssignmentsView(RegistryView):
    def put(self, request: Request, deviceId: str) -> Response:
        serializer = SaveAssignmentsSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        items = container.saveAssignmentsUseCase().execute(
            SaveAssignmentsCommand(
                deviceId=str(deviceId),
                rows=tuple(dict(row) for row in serializer.validated_data["rows"]),
            )
        )
        return Response(successEnvelope([asDict(item) for item in items]))


# =====================================================================================
# Analytics
# =====================================================================================
class DeviceAnalyticsView(RegistryView):
    def get(self, request: Request, deviceId: str) -> Response:
        dto = container.getDeviceAnalyticsUseCase().execute(
            GetDeviceAnalyticsQuery(
                deviceId=str(deviceId),
                fromDate=str(request.query_params.get("fromDate", "")).strip(),
                toDate=str(request.query_params.get("toDate", "")).strip(),
            )
        )
        return Response(successEnvelope(asDict(dto), meta=dto.asMeta()))


class FleetAnalyticsView(RegistryView):
    def get(self, request: Request) -> Response:
        dto = container.getFleetAnalyticsUseCase().execute(
            GetFleetAnalyticsQuery(
                fromDate=str(request.query_params.get("fromDate", "")).strip(),
                toDate=str(request.query_params.get("toDate", "")).strip(),
                department=str(request.query_params.get("department", "")).strip(),
                criticality=str(request.query_params.get("criticality", "")).strip(),
                locationId=str(request.query_params.get("locationId", "")).strip(),
            )
        )
        return Response(successEnvelope(asDict(dto), meta=dto.asMeta()))


class PartUsageReportView(RegistryView):
    def get(self, request: Request, partId: str) -> Response:
        dto = container.getPartUsageReportUseCase().execute(
            GetPartUsageReportQuery(
                partId=str(partId),
                fromDate=str(request.query_params.get("fromDate", "")).strip(),
                toDate=str(request.query_params.get("toDate", "")).strip(),
            )
        )
        return Response(successEnvelope(asDict(dto), meta=dto.asMeta()))


class WorkOrderClosureView(RegistryView):
    def patch(self, request: Request, workOrderId: str) -> Response:
        serializer = CloseWorkOrderDetailsSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        payload = container.recordClosureDetailsUseCase().execute(
            RecordClosureDetailsCommand(
                workOrderId=str(workOrderId),
                values={
                    key: value
                    for key, value in serializer.validated_data.items()
                    if key in request.data
                },
            )
        )
        return Response(successEnvelope(payload))
