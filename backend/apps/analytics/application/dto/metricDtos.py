"""Stable DTOs returned by Analytics use cases."""

from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any

from apps.analytics.domain.entities.metricDefinition import MetricDefinition
from apps.analytics.domain.entities.metricReading import MetricReading
from apps.analytics.domain.repositories.metricRepository import MetricReadingSummary


@dataclass(frozen=True)
class MetricDefinitionDto:
    id: str
    code: str
    name: str
    description: str
    formula: str
    unit: str
    aggregation: str
    minimumValue: str | None
    maximumValue: str | None
    isActive: bool
    createdAt: str
    updatedAt: str | None


@dataclass(frozen=True)
class MetricReadingDto:
    id: str
    metricId: str
    metricCode: str
    value: str
    unit: str
    periodStart: str
    periodEnd: str
    dimensions: dict[str, Any]
    quality: str
    sourceType: str
    sourceId: str
    ingestionKey: str
    recordedAt: str
    recordedById: str | None
    replayed: bool = False


@dataclass(frozen=True)
class MetricDefinitionListDto:
    items: list[MetricDefinitionDto] = field(default_factory=list)
    totalCount: int = 0
    page: int = 1
    pageSize: int = 50

    def asMeta(self) -> dict[str, Any]:
        return paginationMeta(self.totalCount, self.page, self.pageSize)


@dataclass(frozen=True)
class MetricReadingListDto:
    items: list[MetricReadingDto] = field(default_factory=list)
    totalCount: int = 0
    page: int = 1
    pageSize: int = 100

    def asMeta(self) -> dict[str, Any]:
        return paginationMeta(self.totalCount, self.page, self.pageSize)


@dataclass(frozen=True)
class MetricReadingBatchDto:
    items: list[MetricReadingDto] = field(default_factory=list)
    createdCount: int = 0
    replayedCount: int = 0

    def asMeta(self) -> dict[str, Any]:
        return {
            "createdCount": self.createdCount,
            "replayedCount": self.replayedCount,
            "totalCount": len(self.items),
        }


@dataclass(frozen=True)
class MetricReadingSummaryDto:
    count: int
    minimum: str | None
    maximum: str | None
    average: str | None
    total: str | None
    first: MetricReadingDto | None
    last: MetricReadingDto | None


def decimalText(value: Decimal | None) -> str | None:
    return format(value, "f") if value is not None else None


def definitionDtoFromDomain(definition: MetricDefinition) -> MetricDefinitionDto:
    return MetricDefinitionDto(
        id=str(definition.id),
        code=str(definition.code),
        name=definition.name,
        description=definition.description,
        formula=definition.formula,
        unit=definition.unit,
        aggregation=definition.aggregation,
        minimumValue=decimalText(definition.minimumValue),
        maximumValue=decimalText(definition.maximumValue),
        isActive=definition.isActive,
        createdAt=definition.createdAt.isoformat(),
        updatedAt=definition.updatedAt.isoformat() if definition.updatedAt else None,
    )


def readingDtoFromDomain(
    reading: MetricReading,
    definition: MetricDefinition,
    *,
    replayed: bool = False,
) -> MetricReadingDto:
    return MetricReadingDto(
        id=str(reading.id),
        metricId=str(reading.metricId),
        metricCode=str(definition.code),
        value=format(reading.value, "f"),
        unit=definition.unit,
        periodStart=reading.periodStart.isoformat(),
        periodEnd=reading.periodEnd.isoformat(),
        dimensions=dict(reading.dimensions),
        quality=reading.quality,
        sourceType=reading.sourceType,
        sourceId=reading.sourceId,
        ingestionKey=reading.ingestionKey,
        recordedAt=reading.recordedAt.isoformat(),
        recordedById=str(reading.recordedById) if reading.recordedById else None,
        replayed=replayed,
    )


def summaryDtoFromDomain(
    summary: MetricReadingSummary,
    definition: MetricDefinition,
) -> MetricReadingSummaryDto:
    return MetricReadingSummaryDto(
        count=summary.count,
        minimum=decimalText(summary.minimum),
        maximum=decimalText(summary.maximum),
        average=decimalText(summary.average),
        total=decimalText(summary.total),
        first=(readingDtoFromDomain(summary.first, definition) if summary.first else None),
        last=(readingDtoFromDomain(summary.last, definition) if summary.last else None),
    )


def paginationMeta(totalCount: int, page: int, pageSize: int) -> dict[str, Any]:
    normalizedPage = max(1, page)
    normalizedSize = max(1, pageSize)
    totalPages = (totalCount + normalizedSize - 1) // normalizedSize
    return {
        "pagination": {
            "totalCount": totalCount,
            "page": normalizedPage,
            "pageSize": normalizedSize,
            "totalPages": totalPages,
            "hasNext": normalizedPage < totalPages,
            "hasPrevious": normalizedPage > 1,
        }
    }
