"""Analytics command carriers (HTTP/framework independent)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class CreateMetricDefinitionCommand(Command):
    tenantId: str
    code: str
    name: str
    description: str = ""
    formula: str = ""
    unit: str = ""
    aggregation: str = "LAST"
    minimumValue: Decimal | None = None
    maximumValue: Decimal | None = None


@dataclass(frozen=True)
class UpdateMetricDefinitionCommand(Command):
    definitionId: str
    name: str
    description: str = ""
    formula: str = ""
    unit: str = ""
    aggregation: str = "LAST"
    minimumValue: Decimal | None = None
    maximumValue: Decimal | None = None
    isActive: bool = True


@dataclass(frozen=True)
class MetricReadingInput:
    metricId: str = ""
    metricCode: str = ""
    value: Decimal | str | int | float = "0"
    periodStart: datetime | None = None
    periodEnd: datetime | None = None
    dimensions: dict[str, Any] = field(default_factory=dict)
    quality: str = "GOOD"
    sourceType: str = ""
    sourceId: str = ""
    ingestionKey: str = ""


@dataclass(frozen=True)
class RecordMetricReadingCommand(Command):
    reading: MetricReadingInput


@dataclass(frozen=True)
class RecordMetricReadingsBatchCommand(Command):
    readings: tuple[MetricReadingInput, ...]
