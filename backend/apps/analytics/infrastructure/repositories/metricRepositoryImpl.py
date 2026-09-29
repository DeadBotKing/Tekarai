"""Django ORM adapters for Analytics repository ports."""

from __future__ import annotations

import uuid

from django.db import IntegrityError, transaction
from django.db.models import Avg, Count, Max, Min, Q, Sum

from apps.analytics.domain.entities.metricDefinition import MetricDefinition
from apps.analytics.domain.entities.metricReading import MetricReading
from apps.analytics.domain.exceptions.metricErrors import MetricIngestionConflictError
from apps.analytics.domain.repositories.metricRepository import (
    MetricDefinitionFilters,
    MetricDefinitionPage,
    MetricReadingFilters,
    MetricReadingPage,
    MetricReadingSummary,
)
from apps.analytics.domain.valueObjects.metricTypes import MetricCode
from apps.analytics.infrastructure.models import MetricDefinitionModel, MetricReadingModel
from apps.sharedKernel.domain.errors import DuplicateBusinessCodeError, ValidationFailedError

READING_SORT_COLUMNS = {
    "periodStart": "periodStart",
    "periodEnd": "periodEnd",
    "recordedAt": "recordedAt",
    "value": "value",
    "quality": "quality",
}


class MetricDefinitionRepositoryDjango:
    def create(self, definition: MetricDefinition) -> None:
        try:
            MetricDefinitionModel.objects.create(
                id=definition.id,
                tenantId=definition.tenantId,
                code=str(definition.code),
                name=definition.name,
                description=definition.description,
                formula=definition.formula,
                unit=definition.unit,
                aggregation=definition.aggregation,
                minimumValue=definition.minimumValue,
                maximumValue=definition.maximumValue,
                isActive=definition.isActive,
                createdAt=definition.createdAt,
            )
        except IntegrityError as exc:
            raise DuplicateBusinessCodeError("Metric code already exists in this tenant.") from exc

    def update(self, definition: MetricDefinition) -> None:
        MetricDefinitionModel.objects.filter(
            id=definition.id,
            tenantId=definition.tenantId,
            deletedAt__isnull=True,
        ).update(
            name=definition.name,
            description=definition.description,
            formula=definition.formula,
            unit=definition.unit,
            aggregation=definition.aggregation,
            minimumValue=definition.minimumValue,
            maximumValue=definition.maximumValue,
            isActive=definition.isActive,
            updatedAt=definition.updatedAt,
        )

    def getById(self, tenantId: uuid.UUID, definitionId: uuid.UUID) -> MetricDefinition | None:
        model = MetricDefinitionModel.objects.filter(
            id=definitionId,
            tenantId=tenantId,
            deletedAt__isnull=True,
        ).first()
        return self.toDomain(model) if model else None

    def getByCode(self, tenantId: uuid.UUID, code: str) -> MetricDefinition | None:
        model = MetricDefinitionModel.objects.filter(
            tenantId=tenantId,
            code=str(code).strip().upper(),
            deletedAt__isnull=True,
        ).first()
        return self.toDomain(model) if model else None

    def existsByCode(self, tenantId: uuid.UUID, code: str) -> bool:
        return MetricDefinitionModel.objects.filter(
            tenantId=tenantId,
            code=str(code).strip().upper(),
            deletedAt__isnull=True,
        ).exists()

    def list(self, filters: MetricDefinitionFilters) -> MetricDefinitionPage:
        queryset = MetricDefinitionModel.objects.filter(
            tenantId=filters.tenantId,
            deletedAt__isnull=True,
        )
        if filters.search:
            queryset = queryset.filter(
                Q(code__icontains=filters.search)
                | Q(name__icontains=filters.search)
                | Q(description__icontains=filters.search)
            )
        if filters.isActive is not None:
            queryset = queryset.filter(isActive=filters.isActive)
        totalCount = queryset.count()
        start = (filters.page - 1) * filters.pageSize
        models = queryset.order_by("code", "id")[start : start + filters.pageSize]
        return MetricDefinitionPage(
            items=[self.toDomain(model) for model in models],
            totalCount=totalCount,
        )

    @staticmethod
    def toDomain(model: MetricDefinitionModel) -> MetricDefinition:
        return MetricDefinition(
            id=model.id,
            tenantId=model.tenantId,
            code=MetricCode(model.code),
            name=model.name,
            description=model.description,
            formula=model.formula,
            unit=model.unit,
            aggregation=model.aggregation,
            minimumValue=model.minimumValue,
            maximumValue=model.maximumValue,
            isActive=model.isActive,
            createdAt=model.createdAt,
            updatedAt=model.updatedAt,
            deletedAt=model.deletedAt,
        )


class MetricReadingRepositoryDjango:
    def create(self, reading: MetricReading) -> tuple[MetricReading, bool]:
        if reading.ingestionKey:
            existing = self.getByIngestionKey(reading.tenantId, reading.ingestionKey)
            if existing is not None:
                return existing, False
        try:
            # Savepoint is required: a concurrent unique-key race must not mark
            # the outer use-case transaction as broken before we load the winner.
            with transaction.atomic():
                MetricReadingModel.objects.create(
                    id=reading.id,
                    tenantId=reading.tenantId,
                    metric_id=reading.metricId,
                    value=reading.value,
                    dimensions=dict(reading.dimensions),
                    quality=reading.quality,
                    periodStart=reading.periodStart,
                    periodEnd=reading.periodEnd,
                    sourceType=reading.sourceType,
                    sourceId=reading.sourceId,
                    ingestionKey=reading.ingestionKey or None,
                    recordedAt=reading.recordedAt,
                    recordedById=reading.recordedById,
                    correlationId=reading.correlationId,
                )
            return reading, True
        except IntegrityError as exc:
            if reading.ingestionKey:
                existing = self.getByIngestionKey(reading.tenantId, reading.ingestionKey)
                if existing is not None:
                    return existing, False
            raise MetricIngestionConflictError(
                "Metric reading could not be inserted without violating integrity."
            ) from exc

    def getById(self, tenantId: uuid.UUID, readingId: uuid.UUID) -> MetricReading | None:
        model = MetricReadingModel.objects.filter(id=readingId, tenantId=tenantId).first()
        return self.toDomain(model) if model else None

    def getByIngestionKey(self, tenantId: uuid.UUID, ingestionKey: str) -> MetricReading | None:
        if not ingestionKey:
            return None
        model = MetricReadingModel.objects.filter(
            tenantId=tenantId,
            ingestionKey=ingestionKey,
        ).first()
        return self.toDomain(model) if model else None

    def list(self, filters: MetricReadingFilters) -> MetricReadingPage:
        queryset = self.filteredQueryset(filters)
        orderField = filters.ordering.strip() or "-periodStart"
        requested = orderField.lstrip("-")
        if requested not in READING_SORT_COLUMNS:
            raise ValidationFailedError(
                "Field is not sortable.", fieldErrors={"ordering": requested}
            )
        column = READING_SORT_COLUMNS[requested]
        primaryOrdering = f"-{column}" if orderField.startswith("-") else column
        identifierOrdering = "-id" if orderField.startswith("-") else "id"
        totalCount = queryset.count()
        start = (filters.page - 1) * filters.pageSize
        models = queryset.order_by(primaryOrdering, identifierOrdering)[
            start : start + filters.pageSize
        ]
        return MetricReadingPage(
            items=[self.toDomain(model) for model in models],
            totalCount=totalCount,
        )

    def summarize(self, filters: MetricReadingFilters) -> MetricReadingSummary:
        queryset = self.filteredQueryset(filters)
        values = queryset.aggregate(
            count=Count("id"),
            minimum=Min("value"),
            maximum=Max("value"),
            average=Avg("value"),
            total=Sum("value"),
        )
        firstModel = queryset.order_by("periodStart", "id").first()
        lastModel = queryset.order_by("-periodStart", "-id").first()
        return MetricReadingSummary(
            count=int(values["count"] or 0),
            minimum=values["minimum"],
            maximum=values["maximum"],
            average=values["average"],
            total=values["total"],
            first=self.toDomain(firstModel) if firstModel else None,
            last=self.toDomain(lastModel) if lastModel else None,
        )

    @staticmethod
    def filteredQueryset(filters: MetricReadingFilters):  # noqa: ANN205
        queryset = MetricReadingModel.objects.filter(tenantId=filters.tenantId)
        if filters.metricId:
            queryset = queryset.filter(metric_id=filters.metricId)
        if filters.quality:
            queryset = queryset.filter(quality=filters.quality)
        if filters.sourceType:
            queryset = queryset.filter(sourceType=filters.sourceType)
        if filters.sourceId:
            queryset = queryset.filter(sourceId=filters.sourceId)
        # Overlap semantics include a reading whose period intersects the
        # requested window instead of dropping long-running intervals.
        if filters.fromTime:
            queryset = queryset.filter(periodEnd__gte=filters.fromTime)
        if filters.toTime:
            queryset = queryset.filter(periodStart__lte=filters.toTime)
        return queryset

    @staticmethod
    def toDomain(model: MetricReadingModel) -> MetricReading:
        return MetricReading(
            id=model.id,
            tenantId=model.tenantId,
            metricId=model.metric_id,
            value=model.value,
            periodStart=model.periodStart,
            periodEnd=model.periodEnd,
            dimensions=dict(model.dimensions or {}),
            quality=model.quality,
            sourceType=model.sourceType,
            sourceId=model.sourceId,
            ingestionKey=model.ingestionKey or "",
            recordedAt=model.recordedAt,
            recordedById=model.recordedById,
            correlationId=model.correlationId,
        )
