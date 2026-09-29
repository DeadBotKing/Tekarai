"""Analytics domain errors."""

from apps.analytics.domain.exceptions.metricErrors import (
    MetricIngestionConflictError,
    MetricReadingImmutableError,
)

__all__ = ["MetricIngestionConflictError", "MetricReadingImmutableError"]
