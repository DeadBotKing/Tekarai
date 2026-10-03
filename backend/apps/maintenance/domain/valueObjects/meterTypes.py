"""Meter-reading vocabulary and value objects (ثبت قرائت دستی و سنسوری).

A *meter point* is one measurable channel on a device — running hours, kWh,
produced units, bearing temperature, discharge pressure. A *reading* is one
observed value of that channel at one instant.

Two capture modes share the same stream, deliberately:

* ``manual``  — an operator walks the floor and types what the dial shows.
* ``sensor``  — a PLC/SCADA/IoT gateway pushes the value over the ingest API.

They are the same fact with a different provenance, so they belong in one
append-only series. Mixing them in one table is what lets a plant start with
clipboards, wire up sensors later, and keep a single unbroken history for the
same pump. ``captureMode`` preserves *how* each point arrived, so a report can
always separate the trusted stream from the typed one.

Two meter *kinds* behave very differently and must never be confused:

* ``cumulative`` — a counter that only ever grows (an hour meter, an energy
  meter). What matters is the **delta** between two readings; the raw value is
  meaningless on its own. Counters also *roll over* when they exhaust their
  digits, which looks exactly like someone typing a wrong, smaller number.
* ``gauge`` — an instantaneous measurement (temperature, pressure, vibration).
  It legitimately goes up and down, and a delta carries no meaning.

Encoding the kind is what makes it possible to reject "the hour meter went
backwards" while accepting "the temperature dropped" — the single most common
source of garbage data in meter-driven maintenance.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

from apps.sharedKernel.domain.errors import ValidationFailedError

# -- Capture provenance ------------------------------------------------------------
CAPTURE_MANUAL = "manual"
CAPTURE_SENSOR = "sensor"

#: How a reading entered the system. Stored on every row and never inferred.
CAPTURE_MODES: tuple[str, ...] = (CAPTURE_MANUAL, CAPTURE_SENSOR)

# -- Meter kind --------------------------------------------------------------------
METER_CUMULATIVE = "cumulative"
METER_GAUGE = "gauge"

#: ``cumulative`` counters carry deltas and may roll over; ``gauge`` values do not.
METER_KINDS: tuple[str, ...] = (METER_CUMULATIVE, METER_GAUGE)

# -- Data quality ------------------------------------------------------------------
QUALITY_GOOD = "good"
QUALITY_SUSPECT = "suspect"
QUALITY_ESTIMATED = "estimated"
QUALITY_BAD = "bad"

#: Quality is *assessed*, never silently dropped — a suspect point is still a
#: fact about the plant and is kept, flagged, and excluded from trend maths.
READING_QUALITIES: tuple[str, ...] = (
    QUALITY_GOOD,
    QUALITY_SUSPECT,
    QUALITY_ESTIMATED,
    QUALITY_BAD,
)

#: Qualities that may advance a counter / drive a PM trigger.
TRUSTED_QUALITIES: tuple[str, ...] = (QUALITY_GOOD, QUALITY_ESTIMATED)

# -- PM trigger types (repairs the orphaned 0012 migration) ------------------------
TRIGGER_CALENDAR = "calendar"
TRIGGER_METER = "meter"
TRIGGER_CONDITION = "condition"

#: ``calendar`` = every N days/weeks/months. ``meter`` = every N meter units
#: since the last execution. ``condition`` = when the value crosses a threshold.
PM_TRIGGER_TYPES: tuple[str, ...] = (TRIGGER_CALENDAR, TRIGGER_METER, TRIGGER_CONDITION)

#: Comparison used by ``condition`` triggers.
THRESHOLD_OPERATORS: tuple[str, ...] = (">=", "<=", ">", "<")

# -- Trigger evaluation outcome ----------------------------------------------------
TRIGGER_OK = "ok"
TRIGGER_WARNING = "warning"
TRIGGER_DUE = "due"
TRIGGER_UNKNOWN = "unknown"

TRIGGER_STATUSES: tuple[str, ...] = (TRIGGER_OK, TRIGGER_WARNING, TRIGGER_DUE, TRIGGER_UNKNOWN)

# -- Field limits ------------------------------------------------------------------
#: ``decimal(18,4)`` in the database — four decimals is enough for an hour
#: meter reading to the tenth of a minute and for a pressure gauge in bar.
VALUE_DECIMAL_PLACES = 4
VALUE_MAX_DIGITS = 18
#: Largest magnitude a reading may carry, derived from the column definition.
VALUE_LIMIT = Decimal(10) ** (VALUE_MAX_DIGITS - VALUE_DECIMAL_PLACES) - 1

METER_CODE_PATTERN = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,47}$")
MAX_SENSOR_KEY_LENGTH = 120
MAX_INGESTION_KEY_LENGTH = 128

#: An ingest batch is capped so one gateway cannot monopolise a worker. A
#: gateway buffering a minute of one-second samples fits comfortably.
MAX_INGEST_BATCH = 500


def normalizeMeterCode(value: str) -> str:
    """Canonical meter-point code — uppercase, validated against the pattern."""
    code = " ".join(str(value or "").split()).upper()
    if not METER_CODE_PATTERN.match(code):
        raise ValidationFailedError(
            "Meter code must be 1-48 chars of letters, digits, dot, dash or underscore.",
            fieldErrors={"code": "invalid"},
        )
    return code


def normalizeSensorKey(value: str) -> str:
    """Canonical sensor binding key (the PLC tag / MQTT topic / gateway id).

    Kept case-sensitive — OPC-UA node ids and MQTT topics are case-sensitive —
    but trimmed and length-checked so a stray newline from a gateway config
    cannot silently create a second, unreachable binding.
    """
    key = str(value or "").strip()
    if not key:
        return ""
    if len(key) > MAX_SENSOR_KEY_LENGTH:
        raise ValidationFailedError(
            f"Sensor key must not exceed {MAX_SENSOR_KEY_LENGTH} characters.",
            fieldErrors={"sensorKey": "tooLong"},
        )
    if any(ord(char) < 0x20 or 0x7F <= ord(char) <= 0x9F for char in key):
        raise ValidationFailedError(
            "Sensor key must not contain control characters.",
            fieldErrors={"sensorKey": "invalid"},
        )
    return key


def ensureCaptureMode(value: str) -> str:
    mode = str(value or "").strip().lower()
    if mode not in CAPTURE_MODES:
        raise ValidationFailedError(
            "Capture mode must be 'manual' or 'sensor'.",
            fieldErrors={"captureMode": str(value)},
        )
    return mode


def ensureMeterKind(value: str) -> str:
    kind = str(value or "").strip().lower()
    if kind not in METER_KINDS:
        raise ValidationFailedError(
            "Meter kind must be 'cumulative' or 'gauge'.",
            fieldErrors={"kind": str(value)},
        )
    return kind


def ensureQuality(value: str) -> str:
    quality = str(value or "").strip().lower()
    if quality not in READING_QUALITIES:
        raise ValidationFailedError(
            "Quality must be one of good, suspect, estimated, bad.",
            fieldErrors={"quality": str(value)},
        )
    return quality


def ensureTriggerType(value: str) -> str:
    trigger = str(value or "").strip()
    if trigger not in PM_TRIGGER_TYPES:
        raise ValidationFailedError(
            "PM trigger type must be calendar, meter or condition.",
            fieldErrors={"triggerType": str(value)},
        )
    return trigger


def ensureThresholdOperator(value: str) -> str:
    operator = str(value or "").strip()
    if operator not in THRESHOLD_OPERATORS:
        raise ValidationFailedError(
            "Threshold operator must be one of >=, <=, >, <.",
            fieldErrors={"thresholdOperator": str(value)},
        )
    return operator


@dataclass(frozen=True)
class MeterValue:
    """A validated, quantised meter value.

    Readings arrive as strings from JSON so that a float round-trip can never
    turn ``8421.3`` into ``8421.2999999999997`` before it reaches the database.
    NaN and Infinity are rejected outright: a counter that is "not a number"
    corrupts every delta computed after it.
    """

    amount: Decimal

    @staticmethod
    def parse(raw: object, *, fieldName: str = "value") -> MeterValue:
        if isinstance(raw, float):
            # Accepted for convenience, but routed through ``str`` so the
            # shortest repr (what the operator actually meant) is what lands.
            raw = repr(raw)
        try:
            amount = Decimal(str(raw).strip())
        except (InvalidOperation, ValueError, AttributeError) as error:
            raise ValidationFailedError(
                "Reading value must be a decimal number.",
                fieldErrors={fieldName: "notANumber"},
            ) from error
        if not amount.is_finite():
            raise ValidationFailedError(
                "Reading value must be finite.",
                fieldErrors={fieldName: "notFinite"},
            )
        quantised = amount.quantize(Decimal(1).scaleb(-VALUE_DECIMAL_PLACES))
        if abs(quantised) > VALUE_LIMIT:
            raise ValidationFailedError(
                "Reading value is outside the supported range.",
                fieldErrors={fieldName: "outOfRange"},
            )
        return MeterValue(amount=quantised)

    def __str__(self) -> str:
        return format(self.amount, "f")


def quantiseValue(amount: Decimal) -> Decimal:
    """Snap an already-trusted Decimal onto the stored scale."""
    return amount.quantize(Decimal(1).scaleb(-VALUE_DECIMAL_PLACES))


__all__ = [
    "CAPTURE_MANUAL",
    "CAPTURE_MODES",
    "CAPTURE_SENSOR",
    "MAX_INGEST_BATCH",
    "MAX_INGESTION_KEY_LENGTH",
    "MAX_SENSOR_KEY_LENGTH",
    "METER_CUMULATIVE",
    "METER_GAUGE",
    "METER_KINDS",
    "PM_TRIGGER_TYPES",
    "QUALITY_BAD",
    "QUALITY_ESTIMATED",
    "QUALITY_GOOD",
    "QUALITY_SUSPECT",
    "READING_QUALITIES",
    "THRESHOLD_OPERATORS",
    "TRIGGER_CALENDAR",
    "TRIGGER_CONDITION",
    "TRIGGER_DUE",
    "TRIGGER_METER",
    "TRIGGER_OK",
    "TRIGGER_STATUSES",
    "TRIGGER_UNKNOWN",
    "TRIGGER_WARNING",
    "TRUSTED_QUALITIES",
    "VALUE_DECIMAL_PLACES",
    "VALUE_LIMIT",
    "VALUE_MAX_DIGITS",
    "MeterValue",
    "ensureCaptureMode",
    "ensureMeterKind",
    "ensureQuality",
    "ensureThresholdOperator",
    "ensureTriggerType",
    "normalizeMeterCode",
    "normalizeSensorKey",
    "quantiseValue",
]
