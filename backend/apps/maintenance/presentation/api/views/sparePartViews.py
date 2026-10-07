"""Spare-parts inventory HTTP endpoints."""

from __future__ import annotations

import dataclasses

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.commands.sparePartCommands import (
    ConsumeSparePartCommand,
    CreateSparePartCommand,
    ListPartTransactionsQuery,
    ListSparePartsQuery,
    ListWorkOrderPartUsageQuery,
    RecordPartTransactionCommand,
    UpdateSparePartCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.presentation.api.serializers.maintenanceSerializers import (
    ConsumeSparePartSerializer,
    CreateSparePartSerializer,
    RecordPartTransactionSerializer,
    UpdateSparePartSerializer,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated
from apps.sharedKernel.presentation.api.response import successEnvelope


class SparePartListView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        result = container.listSparePartsUseCase().execute(
            ListSparePartsQuery(search=str(request.query_params.get("search", "")))
        )
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in result.items], meta=result.asMeta()
            )
        )

    def post(self, request: Request) -> Response:
        serializer = CreateSparePartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.createSparePartUseCase().execute(
            CreateSparePartCommand(
                code=str(data["code"]),
                name=str(data["name"]),
                unit=str(data["unit"]),
                quantityOnHand=str(data["quantityOnHand"]),
                minimumStock=str(data["minimumStock"]),
                unitCost=str(data.get("unitCost", 0)),
                reorderQuantity=str(data.get("reorderQuantity", 0)),
                autoReorder=bool(data.get("autoReorder", True)),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class SparePartDetailView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def patch(self, request: Request, partId: str) -> Response:
        serializer = UpdateSparePartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.updateSparePartUseCase().execute(
            UpdateSparePartCommand(
                partId=str(partId),
                name=str(data["name"]),
                unit=str(data["unit"]),
                quantityOnHand=str(data["quantityOnHand"]),
                minimumStock=str(data["minimumStock"]),
                unitCost=str(data.get("unitCost", 0)),
                reorderQuantity=str(data.get("reorderQuantity", 0)),
                autoReorder=bool(data.get("autoReorder", True)),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)))


class WorkOrderPartUsageView(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, workOrderId: str) -> Response:
        result = container.listWorkOrderPartUsageUseCase().execute(
            ListWorkOrderPartUsageQuery(workOrderId=str(workOrderId))
        )
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in result.items], meta=result.asMeta()
            )
        )

    def post(self, request: Request, workOrderId: str) -> Response:
        serializer = ConsumeSparePartSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.consumeSparePartUseCase().execute(
            ConsumeSparePartCommand(
                workOrderId=str(workOrderId),
                partId=str(data["partId"]),
                quantity=str(data["quantity"]),
                note=str(data["note"]),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)


class PartTransactionsView(IdempotencyMixin, APIView):
    """دفتر تراکنش یک قطعه — GET برای نمایش دفتر، POST برای ثبت تراکنش جدید."""

    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get(self, request: Request, partId: str) -> Response:
        result = container.listPartTransactionsUseCase().execute(
            ListPartTransactionsQuery(partId=str(partId))
        )
        return Response(
            successEnvelope(
                [dataclasses.asdict(item) for item in result.items], meta=result.asMeta()
            )
        )

    def post(self, request: Request, partId: str) -> Response:
        serializer = RecordPartTransactionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        result = container.recordPartTransactionUseCase().execute(
            RecordPartTransactionCommand(
                partId=str(partId),
                transactionType=str(data["transactionType"]),
                quantity=str(data["quantity"]),
                note=str(data.get("note", "")),
                reference=str(data.get("reference", "")),
            )
        )
        return Response(successEnvelope(dataclasses.asdict(result)), status=201)
