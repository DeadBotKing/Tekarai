"""Persistence ports for metric definitions and immutable readings."""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Protocol, runtime_checkable

from apps.analytics.domain.entities.metricDefinition import MetricDefinition
from apps.analytics.domain.entities.metricReading import MetricReading


@dataclass(frozen=True)
class MetricDefinitionFilters:
    tenantId: uuid.UUID
    search: str = ""
    isActive: bool | None = None
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class MetricReadingFilters:
    tenantId: uuid.UUID
    metricId: uuid.UUID | None = None
    quality: str = ""
    sourceType: str = ""
    sourceId: str = ""
    fromTime: datetime | None = None
    toTime: datetime | None = None
    ordering: str = "-periodStart"
    page: int = 1
    pageSize: int = 100


@dataclass(frozen=True)
class MetricDefinitionPage:
    items: list[MetricDefinition] = field(default_factory=list)
    totalCount: int = 0


@dataclass(frozen=True)
class MetricReadingPage:
    items: list[MetricReading] = field(default_factory=list)
    totalCount: int = 0


@dataclass(frozen=True)
class MetricReadingSummary:
    count: int
    minimum: Decimal | None
    maximum: Decimal | None
    average: Decimal | None
    total: Decimal | None
    first: MetricReading | None
    last: MetricReading | None


@runtime_checkable
class MetricDefinitionRepository(Protocol):
    def create(self, definition: MetricDefinition) -> None: ...

    def update(self, definition: MetricDefinition) -> None: ...

    def getById(self, tenantId: uuid.UUID, definitionId: uuid.UUID) -> MetricDefinition | None: ...

    def getByCode(self, tenantId: uuid.UUID, code: str) -> MetricDefinition | None: ...

    def existsByCode(self, tenantId: uuid.UUID, code: str) -> bool: ...

    def list(self, filters: MetricDefinitionFilters) -> MetricDefinitionPage: ...


@runtime_checkable
class MetricReadingRepository(Protocol):
    def create(self, reading: MetricReading) -> tuple[MetricReading, bool]: ...

    def getById(self, tenantId: uuid.UUID, readingId: uuid.UUID) -> MetricReading | None: ...

    def getByIngestionKey(self, tenantId: uuid.UUID, ingestionKey: str) -> MetricReading | None: ...

    def list(self, filters: MetricReadingFilters) -> MetricReadingPage: ...

    def summarize(self, filters: MetricReadingFilters) -> MetricReadingSummary: ...
