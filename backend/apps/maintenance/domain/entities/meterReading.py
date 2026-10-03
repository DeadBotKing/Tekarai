"""Meter point and meter reading entities (ثبت قرائت دستی و سنسوری).

``MeterPoint`` is the *definition* of a measurable channel on one device.
``MeterReading`` is one observed value of that channel — append-only.

Why readings are append-only
----------------------------
A meter reading is a historical observation, not a mutable record. Editing
yesterday's hour-meter value in place silently rewrites every delta, every
consumption report and every PM due-date derived from it, with no trace. So a
wrong reading is never updated or deleted: a **correction** is appended that
supersedes it, and both rows survive. ``supersededByReadingId`` links the
mistake to its replacement, which is exactly what an auditor needs to see.

Why the device's running hours are derived, not typed
-----------------------------------------------------
``Device.runningHours`` used to be a free-form nameplate field: an overwrite
with no history and no author. A meter point flagged ``drivesRunningHours``
now owns that number, so it always traces back to a dated, attributed reading.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

from apps.maintenance.domain.valueObjects.meterTypes import (
    CAPTURE_MANUAL,
    CAPTURE_SENSOR,
    METER_CUMULATIVE,
    METER_GAUGE,
    QUALITY_GOOD,
    TRUSTED_QUALITIES,
    quantiseValue,
)


@dataclass(frozen=True)
class MeterPoint:
    """One measurable channel on a device (hour meter, kWh, temperature …).

    ``sensorKey`` is the binding to the outside world: the PLC tag, OPC-UA node
    or MQTT topic a gateway quotes when pushing a value. It is optional, which
    is what allows a purely manual meter (a dial with no instrumentation) and a
    purely automatic one to live side by side under the same model.
    """

    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    code: str
    name: str
    unit: str = ""
    kind: str = METER_GAUGE
    sensorKey: str = ""
    #: Physically impossible values are rejected before they poison a trend.
    minimumValue: Decimal | None = None
    maximumValue: Decimal | None = None
    #: Counter capacity. A 6-digit hour meter wraps at 999999 back to 0; without
    #: this the wrap reads as a 999999-hour negative jump.
    rolloverMaximum: Decimal | None = None
    #: Spike guard for cumulative points: a pump cannot accumulate 90 running
    #: hours in one hour. ``None`` disables the check.
    maximumStepPerHour: Decimal | None = None
    #: When true this point is the authoritative source of Device.runningHours.
    drivesRunningHours: bool = False
    active: bool = True
    #: Denormalised "current state", maintained by the repository on append so
    #: the device list does not need a sub-query per row.
    lastValue: Decimal | None = None
    lastReadingAt: datetime | None = None
    lastCaptureMode: str = ""
    readingCount: int = 0
    createdAt: datetime | None = None
    updatedAt: datetime | None = None

    @property
    def isCumulative(self) -> bool:
        return self.kind == METER_CUMULATIVE

    @property
    def isGauge(self) -> bool:
        return self.kind == METER_GAUGE

    @property
    def acceptsSensorInput(self) -> bool:
        """A sensor can only reach a point that declares a binding key."""
        return bool(self.sensorKey) and self.active

    def label(self) -> str:
        return f"{self.name} ({self.unit})" if self.unit else self.name

    def withinBounds(self, value: Decimal) -> bool:
        if self.minimumValue is not None and value < self.minimumValue:
            return False
        return not (self.maximumValue is not None and value > self.maximumValue)

    def snapshot(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "deviceId": str(self.deviceId),
            "code": self.code,
            "name": self.name,
            "unit": self.unit,
            "kind": self.kind,
            "sensorKey": self.sensorKey,
            "active": self.active,
            "drivesRunningHours": self.drivesRunningHours,
        }


@dataclass(frozen=True)
class MeterReading:
    """One observed value of a meter point — immutable once written.

    ``delta`` is pre-computed at write time for cumulative points. Computing it
    on read would mean re-walking the whole series for every chart, and would
    produce a different answer after a back-dated reading is inserted. Freezing
    it at write time keeps consumption reports stable and reproducible.
    """

    id: uuid.UUID
    tenantId: uuid.UUID
    deviceId: uuid.UUID
    meterPointId: uuid.UUID
    value: Decimal
    capturedAt: datetime
    captureMode: str = CAPTURE_MANUAL
    quality: str = QUALITY_GOOD
    #: Consumption since the previous trusted reading (cumulative points only).
    delta: Decimal | None = None
    #: True when ``delta`` was reconstructed across a counter wrap-around.
    rolloverApplied: bool = False
    #: Free-text explanation — mandatory for corrections, optional otherwise.
    note: str = ""
    #: Sensor provenance.
    sensorKey: str = ""
    sourceRef: str = ""
    ingestionKey: str = ""
    #: Human provenance.
    recordedById: uuid.UUID | None = None
    recordedByName: str = ""
    #: Correction chain. A reading is never edited; it is superseded.
    correctsReadingId: uuid.UUID | None = None
    supersededByReadingId: uuid.UUID | None = None
    correlationId: str = ""
    createdAt: datetime | None = None

    @property
    def isManual(self) -> bool:
        return self.captureMode == CAPTURE_MANUAL

    @property
    def isSensor(self) -> bool:
        return self.captureMode == CAPTURE_SENSOR

    @property
    def isSuperseded(self) -> bool:
        return self.supersededByReadingId is not None

    @property
    def isTrusted(self) -> bool:
        """Only trusted, un-superseded points drive deltas and PM triggers."""
        return self.quality in TRUSTED_QUALITIES and not self.isSuperseded

    def consumption(self) -> Decimal:
        return quantiseValue(self.delta) if self.delta is not None else Decimal("0.0000")

    def provenance(self) -> str:
        """Short human description of where this number came from."""
        if self.isSensor:
            return f"sensor:{self.sensorKey}" if self.sensorKey else "sensor"
        return f"manual:{self.recordedByName}" if self.recordedByName else "manual"

    def snapshot(self) -> dict[str, object]:
        return {
            "id": str(self.id),
            "deviceId": str(self.deviceId),
            "meterPointId": str(self.meterPointId),
            "value": format(self.value, "f"),
            "capturedAt": self.capturedAt.isoformat(),
            "captureMode": self.captureMode,
            "quality": self.quality,
            "delta": format(self.delta, "f") if self.delta is not None else None,
            "provenance": self.provenance(),
        }


@dataclass(frozen=True)
class MeterPointSummary:
    """Aggregated view of one meter point over a window.

    ``totalConsumption`` only means something for cumulative points, and
    ``averageValue`` only for gauges — the API exposes both and the caller
    reads the one that matches ``kind`` rather than the server guessing.
    """

    meterPointId: uuid.UUID
    code: str
    name: str
    unit: str
    kind: str
    readingCount: int = 0
    manualCount: int = 0
    sensorCount: int = 0
    suspectCount: int = 0
    firstValue: Decimal | None = None
    lastValue: Decimal | None = None
    minimumValue: Decimal | None = None
    maximumValue: Decimal | None = None
    averageValue: Decimal | None = None
    totalConsumption: Decimal | None = None
    firstCapturedAt: datetime | None = None
    lastCapturedAt: datetime | None = None

    def hasData(self) -> bool:
        return self.readingCount > 0


__all__ = [
    "METER_CUMULATIVE",
    "METER_GAUGE",
    "MeterPoint",
    "MeterPointSummary",
    "MeterReading",
]
