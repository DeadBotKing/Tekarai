"""Authenticated, tenant-scoped REST API for metric readings."""

from __future__ import annotations

import dataclasses
from typing import Any

from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.analytics.application.commands.metricCommands import (
    CreateMetricDefinitionCommand,
    MetricReadingInput,
    RecordMetricReadingCommand,
    RecordMetricReadingsBatchCommand,
    UpdateMetricDefinitionCommand,
)
from apps.analytics.application.queries.metricQueries import (
    GetMetricDefinitionQuery,
    GetMetricReadingQuery,
    ListMetricDefinitionsQuery,
    ListMetricReadingsQuery,
    SummarizeMetricReadingsQuery,
)
from apps.analytics.infrastructure import container
from apps.analytics.presentation.api.serializers.metricSerializers import (
    MetricDefinitionCreateSerializer,
    MetricDefinitionListQuerySerializer,
    MetricDefinitionUpdateSerializer,
    MetricReadingBatchSerializer,
    MetricReadingInputSerializer,
    MetricReadingListQuerySerializer,
    MetricReadingSummaryQuerySerializer,
    optionalDecimal,
)
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.openapi import EndpointSpec, registerEndpoint
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated, actionPermission
from apps.sharedKernel.presentation.api.rateLimiting import enforceRateLimit
from apps.sharedKernel.presentation.api.response import successEnvelope

ANALYTICS_ERRORS = [
    "VALIDATION_ERROR",
    "SYS_VALIDATION_FAILED",
    "SYS_RECORD_NOT_FOUND",
    "PERM_PERMISSION_DENIED",
    "DUP_BUSINESS_CODE",
    "ANALYTICS_INGESTION_CONFLICT",
]


class AnalyticsApiView(APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]
    requiredAction = "analytics.metricReading.view"

    def get_permissions(self):  # noqa: ANN201 — DRF contract
        return [IsAuthenticated(), actionPermission(self.requiredAction)()]


class MetricDefinitionListView(IdempotencyMixin, AnalyticsApiView):
    def get_permissions(self):  # noqa: ANN201 — DRF contract
        action = (
            "analytics.metricDefinition.view"
            if self.request.method == "GET"
            else "analytics.metricDefinition.manage"
        )
        return [IsAuthenticated(), actionPermission(action)()]

    def get(self, request: Request) -> Response:
        serializer = MetricDefinitionListQuerySerializer(data=request.query_params)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        dto = container.listMetricDefinitionsUseCase().execute(
            ListMetricDefinitionsQuery(
                search=str(values["search"]),
                isActive=values["isActive"],
                page=int(values["page"]),
                pageSize=int(values["pageSize"]),
            )
        )
        return Response(successEnvelope([asDict(item) for item in dto.items], dto.asMeta()))

    def post(self, request: Request) -> Response:
        serializer = MetricDefinitionCreateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        dto = container.createMetricDefinitionUseCase().execute(
            CreateMetricDefinitionCommand(
                tenantId=str(request.data.get("tenantId", "")),
                code=str(values["code"]),
                name=str(values["name"]),
                description=str(values["description"]),
                formula=str(values["formula"]),
                unit=str(values["unit"]),
                aggregation=str(values["aggregation"]),
                minimumValue=values["minimumValue"],
                maximumValue=values["maximumValue"],
            )
        )
        return Response(successEnvelope(asDict(dto)), status=201)


class MetricDefinitionDetailView(AnalyticsApiView):
    def get_permissions(self):  # noqa: ANN201 — DRF contract
        action = (
            "analytics.metricDefinition.view"
            if self.request.method == "GET"
            else "analytics.metricDefinition.manage"
        )
        return [IsAuthenticated(), actionPermission(action)()]

    def get(self, request: Request, definitionId: str) -> Response:
        dto = container.getMetricDefinitionUseCase().execute(
            GetMetricDefinitionQuery(definitionId=str(definitionId))
        )
        return Response(successEnvelope(asDict(dto)))

    def patch(self, request: Request, definitionId: str) -> Response:
        serializer = MetricDefinitionUpdateSerializer(data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        values = serializer.validated_data
        current = container.getMetricDefinitionUseCase().execute(
            GetMetricDefinitionQuery(definitionId=str(definitionId))
        )
        minimum = (
            values["minimumValue"]
            if "minimumValue" in values
            else optionalDecimal(current.minimumValue)
        )
        maximum = (
            values["maximumValue"]
            if "maximumValue" in values
            else optionalDecimal(current.maximumValue)
        )
        dto = container.updateMetricDefinitionUseCase().execute(
            UpdateMetricDefinitionCommand(
                definitionId=str(definitionId),
                name=str(values.get("name", current.name)),
                description=str(values.get("description", current.description)),
                formula=str(values.get("formula", current.formula)),
                unit=str(values.get("unit", current.unit)),
                aggregation=str(values.get("aggregation", current.aggregation)),
                minimumValue=minimum,
                maximumValue=maximum,
                isActive=bool(values.get("isActive", current.isActive)),
            )
        )
        return Response(successEnvelope(asDict(dto)))


class MetricReadingListView(IdempotencyMixin, AnalyticsApiView):
    def get_permissions(self):  # noqa: ANN201 — DRF contract
        action = (
            "analytics.metricReading.view"
            if self.request.method == "GET"
            else "analytics.metricReading.record"
        )
        return [IsAuthenticated(), actionPermission(action)()]

    def get(self, request: Request) -> Response:
        values = validateReadingQuery(request, MetricReadingListQuerySerializer)
        dto = container.listMetricReadingsUseCase().execute(readingListQuery(values))
        return Response(successEnvelope([asDict(item) for item in dto.items], dto.asMeta()))

    @enforceRateLimit("analytics:metricIngest")
    def post(self, request: Request) -> Response:
        serializer = MetricReadingInputSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        command = RecordMetricReadingCommand(reading=readingInput(serializer.validated_data))
        dto = container.recordMetricReadingUseCase().execute(command)
        return Response(successEnvelope(asDict(dto)), status=200 if dto.replayed else 201)


class MetricReadingBatchView(IdempotencyMixin, AnalyticsApiView):
    requiredAction = "analytics.metricReading.record"

    @enforceRateLimit("analytics:metricBatchIngest")
    def post(self, request: Request) -> Response:
        serializer = MetricReadingBatchSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        dto = container.recordMetricReadingsBatchUseCase().execute(
            RecordMetricReadingsBatchCommand(
                readings=tuple(readingInput(item) for item in serializer.validated_data["readings"])
            )
        )
        statusCode = 201 if dto.createdCount and not dto.replayedCount else 200
        return Response(
            successEnvelope([asDict(item) for item in dto.items], dto.asMeta()),
            status=statusCode,
        )


class MetricReadingDetailView(AnalyticsApiView):
    requiredAction = "analytics.metricReading.view"

    def get(self, request: Request, readingId: str) -> Response:
        dto = container.getMetricReadingUseCase().execute(
            GetMetricReadingQuery(readingId=str(readingId))
        )
        return Response(successEnvelope(asDict(dto)))


class MetricReadingSummaryView(AnalyticsApiView):
    requiredAction = "analytics.metricReading.view"

    def get(self, request: Request) -> Response:
        values = validateReadingQuery(request, MetricReadingSummaryQuerySerializer)
        dto = container.summarizeMetricReadingsUseCase().execute(
            SummarizeMetricReadingsQuery(
                metricId=identifierText(values.get("metricId")),
                metricCode=str(values.get("metricCode", "")),
                quality=str(values.get("quality", "")),
                sourceType=str(values.get("sourceType", "")),
                sourceId=str(values.get("sourceId", "")),
                fromTime=values.get("fromTime"),
                toTime=values.get("toTime"),
            )
        )
        return Response(successEnvelope(asDict(dto)))


def readingInput(values: dict[str, Any]) -> MetricReadingInput:
    return MetricReadingInput(
        metricId=identifierText(values.get("metricId")),
        metricCode=str(values.get("metricCode", "")),
        value=values["value"],
        periodStart=values.get("periodStart"),
        periodEnd=values.get("periodEnd"),
        dimensions=dict(values.get("dimensions") or {}),
        quality=str(values.get("quality", "GOOD")),
        sourceType=str(values.get("sourceType", "")),
        sourceId=str(values.get("sourceId", "")),
        ingestionKey=str(values.get("ingestionKey", "")),
    )


def validateReadingQuery(request: Request, serializerType):  # noqa: ANN001, ANN201
    serializer = serializerType(
        data={
            "metricId": request.query_params.get("metricId") or None,
            "metricCode": request.query_params.get("metricCode", ""),
            "quality": request.query_params.get("quality", ""),
            "sourceType": request.query_params.get("sourceType", ""),
            "sourceId": request.query_params.get("sourceId", ""),
            "fromTime": request.query_params.get("from") or None,
            "toTime": request.query_params.get("to") or None,
            "ordering": request.query_params.get("ordering", "-periodStart"),
            "page": request.query_params.get("page", 1),
            "pageSize": request.query_params.get("pageSize", 100),
        }
    )
    serializer.is_valid(raise_exception=True)
    return serializer.validated_data


def readingListQuery(values: dict[str, Any]) -> ListMetricReadingsQuery:
    return ListMetricReadingsQuery(
        metricId=identifierText(values.get("metricId")),
        metricCode=str(values.get("metricCode", "")),
        quality=str(values.get("quality", "")),
        sourceType=str(values.get("sourceType", "")),
        sourceId=str(values.get("sourceId", "")),
        fromTime=values.get("fromTime"),
        toTime=values.get("toTime"),
        ordering=str(values.get("ordering", "-periodStart")),
        page=int(values.get("page", 1)),
        pageSize=int(values.get("pageSize", 100)),
    )


def identifierText(value: object) -> str:
    return "" if value in (None, "") else str(value)


def asDict(value: Any) -> dict[str, Any]:
    return dataclasses.asdict(value)


# API-first discoverability through Tekarai's in-process OpenAPI registry.
def registerMetricEndpoints() -> None:
    specs = [
        EndpointSpec(
            method="GET",
            path="api/v1/analytics/metric-definitions",
            summary="List tenant metric definitions.",
            permission="analytics.metricDefinition.view",
            errorCodes=ANALYTICS_ERRORS,
            paginated=True,
            searchable=True,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/analytics/metric-definitions",
            summary="Create a governed metric definition.",
            permission="analytics.metricDefinition.manage",
            errorCodes=ANALYTICS_ERRORS,
            idempotent=True,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/analytics/metric-readings",
            summary="Query immutable metric readings.",
            permission="analytics.metricReading.view",
            errorCodes=ANALYTICS_ERRORS,
            paginated=True,
            filterable=(
                "metricId",
                "metricCode",
                "quality",
                "sourceType",
                "sourceId",
                "from",
                "to",
            ),
            sortable=("periodStart", "periodEnd", "recordedAt", "value", "quality"),
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/analytics/metric-readings",
            summary="Record one idempotent metric reading.",
            permission="analytics.metricReading.record",
            errorCodes=ANALYTICS_ERRORS,
            idempotent=True,
        ),
        EndpointSpec(
            method="POST",
            path="api/v1/analytics/metric-readings/batch",
            summary="Atomically record up to 500 metric readings.",
            permission="analytics.metricReading.record",
            errorCodes=ANALYTICS_ERRORS,
            idempotent=True,
        ),
        EndpointSpec(
            method="GET",
            path="api/v1/analytics/metric-readings/summary",
            summary="Aggregate one metric over a filtered time window.",
            permission="analytics.metricReading.view",
            errorCodes=ANALYTICS_ERRORS,
        ),
    ]
    for spec in specs:
        registerEndpoint(spec)


registerMetricEndpoints()
