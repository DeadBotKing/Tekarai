"""MetricDefinition aggregate — governs valid MetricReading values."""

from __future__ import annotations

import uuid
from datetime import datetime
from decimal import Decimal
from typing import Any

from apps.analytics.domain.valueObjects.metricTypes import (
    MetricCode,
    normalizeAggregation,
    normalizeMetricValue,
)
from apps.sharedKernel.domain.entities import AggregateRoot, newId
from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.events import DomainEvent
from apps.sharedKernel.domain.valueObjects import requireMaxLength, requireNonEmpty


class MetricDefinition(AggregateRoot):
    """Tenant-scoped metric schema and optional accepted numeric range."""

    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        code: MetricCode,
        name: str,
        description: str,
        formula: str,
        unit: str,
        aggregation: str,
        minimumValue: Decimal | None,
        maximumValue: Decimal | None,
        isActive: bool,
        createdAt: datetime,
        updatedAt: datetime | None = None,
        deletedAt: datetime | None = None,
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.code = code
        self.name = requireMaxLength(requireNonEmpty(name, "name"), 200, "name")
        self.description = requireMaxLength(description.strip(), 1000, "description")
        self.formula = requireMaxLength(formula.strip(), 500, "formula")
        self.unit = requireMaxLength(unit.strip(), 32, "unit")
        self.aggregation = normalizeAggregation(aggregation)
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue
        self.isActive = bool(isActive)
        self.createdAt = createdAt
        self.updatedAt = updatedAt
        self.deletedAt = deletedAt
        self._validateRange()

    @staticmethod
    def create(
        *,
        tenantId: uuid.UUID,
        code: MetricCode,
        name: str,
        description: str,
        formula: str,
        unit: str,
        aggregation: str,
        minimumValue: Decimal | None,
        maximumValue: Decimal | None,
        now: datetime,
    ) -> MetricDefinition:
        definition = MetricDefinition(
            id=newId(),
            tenantId=tenantId,
            code=code,
            name=name,
            description=description,
            formula=formula,
            unit=unit,
            aggregation=aggregation,
            minimumValue=minimumValue,
            maximumValue=maximumValue,
            isActive=True,
            createdAt=now,
        )
        definition.recordEvent(
            DomainEvent(
                name="metricDefinitionCreated",
                occurredAt=now,
                tenantId=tenantId,
                payload={"metricId": str(definition.id), "code": str(code)},
            )
        )
        return definition

    def update(
        self,
        *,
        name: str,
        description: str,
        formula: str,
        unit: str,
        aggregation: str,
        minimumValue: Decimal | None,
        maximumValue: Decimal | None,
        isActive: bool,
        now: datetime,
    ) -> None:
        self.name = requireMaxLength(requireNonEmpty(name, "name"), 200, "name")
        self.description = requireMaxLength(description.strip(), 1000, "description")
        self.formula = requireMaxLength(formula.strip(), 500, "formula")
        self.unit = requireMaxLength(unit.strip(), 32, "unit")
        self.aggregation = normalizeAggregation(aggregation)
        self.minimumValue = minimumValue
        self.maximumValue = maximumValue
        self.isActive = bool(isActive)
        self.updatedAt = now
        self._validateRange()
        self.recordEvent(
            DomainEvent(
                name="metricDefinitionUpdated",
                occurredAt=now,
                tenantId=self.tenantId,
                payload={"metricId": str(self.id), "isActive": self.isActive},
            )
        )

    def validateReadingValue(self, value: Decimal) -> None:
        if not self.isActive or self.deletedAt is not None:
            raise ValidationFailedError(
                "Metric definition is inactive.", fieldErrors={"metric": str(self.code)}
            )
        if self.minimumValue is not None and value < self.minimumValue:
            raise ValidationFailedError(
                "Metric value is below the definition minimum.",
                fieldErrors={"value": f"minimum {self.minimumValue}"},
            )
        if self.maximumValue is not None and value > self.maximumValue:
            raise ValidationFailedError(
                "Metric value exceeds the definition maximum.",
                fieldErrors={"value": f"maximum {self.maximumValue}"},
            )

    def _validateRange(self) -> None:
        if self.minimumValue is not None:
            self.minimumValue = normalizeMetricValue(self.minimumValue, "minimumValue")
        if self.maximumValue is not None:
            self.maximumValue = normalizeMetricValue(self.maximumValue, "maximumValue")
        if (
            self.minimumValue is not None
            and self.maximumValue is not None
            and self.minimumValue > self.maximumValue
        ):
            raise ValidationFailedError(
                "Metric minimum cannot exceed maximum.",
                fieldErrors={"minimumValue": "must be <= maximumValue"},
            )

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "tenantId": str(self.tenantId),
            "code": str(self.code),
            "name": self.name,
            "unit": self.unit,
            "aggregation": self.aggregation,
            "minimumValue": str(self.minimumValue) if self.minimumValue is not None else None,
            "maximumValue": str(self.maximumValue) if self.maximumValue is not None else None,
            "isActive": self.isActive,
        }
