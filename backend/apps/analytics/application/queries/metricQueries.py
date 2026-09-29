"""Analytics query carriers."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from apps.sharedKernel.application.messaging import Query


@dataclass(frozen=True)
class ListMetricDefinitionsQuery(Query):
    search: str = ""
    isActive: bool | None = None
    page: int = 1
    pageSize: int = 50


@dataclass(frozen=True)
class GetMetricDefinitionQuery(Query):
    definitionId: str


@dataclass(frozen=True)
class ListMetricReadingsQuery(Query):
    metricId: str = ""
    metricCode: str = ""
    quality: str = ""
    sourceType: str = ""
    sourceId: str = ""
    fromTime: datetime | None = None
    toTime: datetime | None = None
    ordering: str = "-periodStart"
    page: int = 1
    pageSize: int = 100


@dataclass(frozen=True)
class GetMetricReadingQuery(Query):
    readingId: str


@dataclass(frozen=True)
class SummarizeMetricReadingsQuery(Query):
    metricId: str = ""
    metricCode: str = ""
    quality: str = ""
    sourceType: str = ""
    sourceId: str = ""
    fromTime: datetime | None = None
    toTime: datetime | None = None
