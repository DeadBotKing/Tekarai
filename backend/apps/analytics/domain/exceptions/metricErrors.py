"""Analytics-specific, stable domain errors."""

from __future__ import annotations

from apps.sharedKernel.domain.errors import ConflictError, DomainError


class MetricIngestionConflictError(ConflictError):
    """An ingestion key was reused for a different observation."""

    code = "ANALYTICS_INGESTION_CONFLICT"
    httpStatus = 409


class MetricReadingImmutableError(DomainError):
    """Metric readings are append-only and cannot be edited in place."""

    code = "ANALYTICS_READING_IMMUTABLE"
    httpStatus = 409
