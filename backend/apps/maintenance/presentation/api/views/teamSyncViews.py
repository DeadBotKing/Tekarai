"""Team-sync endpoints — reservations + inspection templates/records."""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.commands.teamSyncCommands import (
    CloseReservationCommand,
    CommitInspectionTemplateCommand,
    DeleteInspectionTemplateCommand,
    ListInspectionRecordsQuery,
    ListInspectionTemplatesQuery,
    ListReservationsQuery,
    SaveInspectionRecordCommand,
    SaveInspectionTemplateCommand,
    SaveReservationCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.teamSyncSerializers import (
    CloseReservationSerializer,
    SaveInspectionRecordSerializer,
    SaveInspectionTemplateSerializer,
    SaveReservationSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


def _orderedItems(items: list) -> list[dict]:
    return [dataclasses.asdict(item) for item in items]


class TeamReservationListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.listReservationsUseCase().execute(
            ListReservationsQuery(workOrderId=str(request.query_params.get("order", "")))
        )
        return Response(successEnvelope(_orderedItems(result.items), meta=result.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = SaveReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.saveReservationUseCase().execute(
            SaveReservationCommand(
                id=str(data["id"]),
                workOrderId=str(data["orderId"]),
                partCode=str(data["partCode"]),
                quantity=str(data.get("quantity", "0")),
                status=str(data.get("status", "active")),
                reservedByName=str(data.get("reservedByName", "")),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class TeamReservationDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, reservationId: str) -> Response:
        serializer = CloseReservationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        result = container.closeReservationUseCase().execute(
            CloseReservationCommand(
                reservationId=reservationId, status=str(serializer.validated_data["status"])
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)))


class TeamInspectionTemplateListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.listInspectionTemplatesUseCase().execute(ListInspectionTemplatesQuery())
        return Response(successEnvelope(_orderedItems(result.items), meta=result.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = SaveInspectionTemplateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.saveInspectionTemplateUseCase().execute(
            SaveInspectionTemplateCommand(
                id=str(data["id"]),
                name=str(data["name"]),
                description=str(data.get("description", "")),
                deviceCode=str(data.get("deviceCode", "")),
                checks=[str(check) for check in data.get("checks", [])],
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class TeamInspectionTemplateDetailView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def delete(self, request: Request, templateId: str) -> Response:
        container.deleteInspectionTemplateUseCase().execute(
            DeleteInspectionTemplateCommand(templateId=templateId)
        )
        return Response(successEnvelope({"id": templateId, "deleted": True}))


class TeamInspectionTemplateCommitView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def post(self, request: Request, templateId: str) -> Response:
        result = container.commitInspectionTemplateUseCase().execute(
            CommitInspectionTemplateCommand(templateId=templateId)
        )
        return Response(successEnvelope(dataclasses.asdict(result)))


class TeamInspectionRecordListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.listInspectionRecordsUseCase().execute(
            ListInspectionRecordsQuery(workOrderId=str(request.query_params.get("order", "")))
        )
        return Response(successEnvelope(_orderedItems(result.items), meta=result.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = SaveInspectionRecordSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.saveInspectionRecordUseCase().execute(
            SaveInspectionRecordCommand(
                id=str(data["id"]),
                templateId=str(data["templateId"]),
                workOrderId=str(data["workOrderId"]),
                deviceId=str(data["deviceId"]),
                passedChecks=[str(check) for check in data.get("passedChecks", [])],
                failedChecks=[str(check) for check in data.get("failedChecks", [])],
                performedByName=str(data.get("performedByName", "")),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)
