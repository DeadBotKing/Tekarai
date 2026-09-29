"""Framework-free MetricReading value objects and validation rules.

Metric points are high-volume, immutable analytical facts.  Validation is
kept in the domain so API ingestion, jobs and future event consumers all
apply exactly the same rules.
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal, InvalidOperation

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

METRIC_CODE_PATTERN = re.compile(r"^[A-Z0-9][A-Z0-9_.:-]{0,63}$")
DIMENSION_KEY_PATTERN = re.compile(r"^[A-Za-z][A-Za-z0-9_.-]{0,63}$")
METRIC_QUALITIES = ("GOOD", "SUSPECT", "BAD", "UNKNOWN")
METRIC_AGGREGATIONS = ("LAST", "SUM", "AVERAGE", "MIN", "MAX", "COUNT")
MAX_DIMENSIONS = 32
MAX_DIMENSIONS_BYTES = 4096
MAX_DIMENSION_VALUE_LENGTH = 200
MAX_INGESTION_KEY_LENGTH = 128
DECIMAL_QUANTUM = Decimal("0.000001")
MAX_ABSOLUTE_VALUE = Decimal("999999999999.999999")
SENSITIVE_DIMENSION_PARTS = frozenset(
    {
        "authorization",
        "cookie",
        "credential",
        "password",
        "secret",
        "token",
    }
)


@dataclass(frozen=True)
class MetricCode(ValueObject):
    """Tenant-scoped stable metric identity (for example ``ENERGY.KWH``)."""

    value: str

    def __post_init__(self) -> None:
        normalized = str(self.value).strip().upper()
        if not METRIC_CODE_PATTERN.fullmatch(normalized):
            raise ValidationFailedError(
                "Metric code must contain 1-64 characters: A-Z, 0-9, '.', '_', ':' or '-'.",
                fieldErrors={"code": str(self.value)},
            )
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


def normalizeQuality(value: str) -> str:
    quality = str(value or "GOOD").strip().upper()
    if quality not in METRIC_QUALITIES:
        raise ValidationFailedError(
            "Unknown metric quality.",
            fieldErrors={"quality": quality},
        )
    return quality


def normalizeAggregation(value: str) -> str:
    aggregation = str(value or "LAST").strip().upper()
    if aggregation not in METRIC_AGGREGATIONS:
        raise ValidationFailedError(
            "Unknown metric aggregation.",
            fieldErrors={"aggregation": aggregation},
        )
    return aggregation


def normalizeMetricValue(value: object, fieldName: str = "value") -> Decimal:
    """Return an exact finite decimal that fits ``decimal(18,6)``.

    More than six fractional places are rejected instead of silently rounded;
    a reading is evidence and ingestion must never alter it invisibly.
    """

    try:
        decimalValue = value if isinstance(value, Decimal) else Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError) as exc:
        raise ValidationFailedError(
            "Metric value must be a decimal number.",
            fieldErrors={fieldName: "invalid decimal"},
        ) from exc
    if not decimalValue.is_finite():
        raise ValidationFailedError(
            "Metric value must be finite.",
            fieldErrors={fieldName: "NaN and infinity are not allowed"},
        )
    if abs(decimalValue) > MAX_ABSOLUTE_VALUE:
        raise ValidationFailedError(
            "Metric value exceeds decimal(18,6).",
            fieldErrors={fieldName: "out of range"},
        )
    exponent = decimalValue.as_tuple().exponent
    if not isinstance(exponent, int) or exponent < -6:
        raise ValidationFailedError(
            "Metric value supports at most six decimal places.",
            fieldErrors={fieldName: "maximum 6 decimal places"},
        )
    return decimalValue.quantize(DECIMAL_QUANTUM)


def ensureUtc(value: datetime, fieldName: str) -> datetime:
    if not isinstance(value, datetime):
        raise ValidationFailedError(
            "Metric timestamp is required.", fieldErrors={fieldName: "invalid datetime"}
        )
    if value.tzinfo is None or value.utcoffset() is None:
        raise ValidationFailedError(
            "Metric timestamps must include a timezone.",
            fieldErrors={fieldName: "timezone required"},
        )
    return value.astimezone(UTC)


def normalizeDimensions(value: object) -> dict[str, str | int | float | bool | None]:
    """Validate the bounded, flat dimension map used for filtering/grouping."""

    if value in (None, ""):
        return {}
    if not isinstance(value, dict):
        raise ValidationFailedError(
            "Dimensions must be a JSON object.", fieldErrors={"dimensions": "object required"}
        )
    if len(value) > MAX_DIMENSIONS:
        raise ValidationFailedError(
            "Too many metric dimensions.",
            fieldErrors={"dimensions": f"maximum {MAX_DIMENSIONS}"},
        )

    normalized: dict[str, str | int | float | bool | None] = {}
    for rawKey, rawValue in value.items():
        key = str(rawKey).strip()
        if not DIMENSION_KEY_PATTERN.fullmatch(key):
            raise ValidationFailedError(
                "Invalid dimension key.", fieldErrors={"dimensions": key or "empty key"}
            )
        loweredKey = key.lower()
        loweredParts = {part for part in re.split(r"[_.-]", loweredKey)}
        if loweredParts & SENSITIVE_DIMENSION_PARTS or any(
            sensitive in loweredKey for sensitive in SENSITIVE_DIMENSION_PARTS
        ):
            raise ValidationFailedError(
                "Sensitive values must not be stored as metric dimensions.",
                fieldErrors={"dimensions": key},
            )
        if isinstance(rawValue, (dict, list, tuple, set)):
            raise ValidationFailedError(
                "Dimension values must be scalar.", fieldErrors={"dimensions": key}
            )
        if not isinstance(rawValue, (str, int, float, bool, type(None))):
            raise ValidationFailedError(
                "Dimension values must be JSON scalars.", fieldErrors={"dimensions": key}
            )
        if isinstance(rawValue, float) and not math.isfinite(rawValue):
            raise ValidationFailedError(
                "Dimension numbers must be finite.", fieldErrors={"dimensions": key}
            )
        if isinstance(rawValue, str):
            rawValue = rawValue.strip()
            if len(rawValue) > MAX_DIMENSION_VALUE_LENGTH:
                raise ValidationFailedError(
                    "Dimension value is too long.", fieldErrors={"dimensions": key}
                )
        normalized[key] = rawValue

    normalized = dict(sorted(normalized.items()))
    encoded = json.dumps(normalized, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    if len(encoded.encode("utf-8")) > MAX_DIMENSIONS_BYTES:
        raise ValidationFailedError(
            "Dimensions exceed the storage limit.",
            fieldErrors={"dimensions": f"maximum {MAX_DIMENSIONS_BYTES} UTF-8 bytes"},
        )
    return normalized


def normalizeIngestionKey(value: str) -> str:
    key = str(value or "").strip()
    if len(key) > MAX_INGESTION_KEY_LENGTH:
        raise ValidationFailedError(
            "Ingestion key is too long.",
            fieldErrors={"ingestionKey": f"maximum {MAX_INGESTION_KEY_LENGTH}"},
        )
    return key


__all__ = [
    "MAX_DIMENSIONS",
    "METRIC_AGGREGATIONS",
    "METRIC_QUALITIES",
    "MetricCode",
    "ensureUtc",
    "normalizeAggregation",
    "normalizeDimensions",
    "normalizeIngestionKey",
    "normalizeMetricValue",
    "normalizeQuality",
]
