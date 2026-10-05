"""Meter-reading DTOs — the shape the API returns.

Every decimal crosses the wire as a **string**. JSON numbers are IEEE-754
doubles in every browser, so an hour meter at ``124578901.2345`` would lose
its last digits on the way into a JavaScript chart. Strings keep the value the
plant actually recorded.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from apps.maintenance.domain.entities.meterReading import (
    MeterPoint,
    MeterPointSummary,
    MeterReading,
)
from apps.maintenance.domain.services.meterReadingRules import TriggerEvaluation


def decimalText(value: Decimal | None) -> str:
    """Render a Decimal without scientific notation; empty string for None."""
    return format(value, "f") if value is not None else ""


def momentText(value: datetime | None) -> str:
    return value.isoformat() if value is not None else ""


@dataclass(frozen=True)
class MeterPointDto:
    id: str
    deviceId: str
    code: str
    name: str
    unit: str = ""
    kind: str = "gauge"
    sensorKey: str = ""
    minimumValue: str = ""
    maximumValue: str = ""
    rolloverMaximum: str = ""
    maximumStepPerHour: str = ""
    drivesRunningHours: bool = False
    active: bool = True
    lastValue: str = ""
    lastReadingAt: str = ""
    lastCaptureMode: str = ""
    readingCount: int = 0
    createdAt: str = ""
    updatedAt: str = ""


@dataclass(frozen=True)
class MeterReadingDto:
    id: str
    deviceId: str
    meterPointId: str
    meterCode: str = ""
    meterName: str = ""
    unit: str = ""
    value: str = ""
    delta: str = ""
    capturedAt: str = ""
    captureMode: str = "manual"
    quality: str = "good"
    rolloverApplied: bool = False
    note: str = ""
    sensorKey: str = ""
    sourceRef: str = ""
    ingestionKey: str = ""
    recordedById: str = ""
    recordedByName: str = ""
    provenance: str = ""
    correctsReadingId: str = ""
    supersededByReadingId: str = ""
    superseded: bool = False
    createdAt: str = ""


@dataclass(frozen=True)
class MeterReadingListDto:
    items: list[MeterReadingDto] = field(default_factory=list)
    total: int = 0
    page: int = 1
    pageSize: int = 100

    def asMeta(self) -> dict[str, object]:
        return {
            "total": self.total,
            "page": self.page,
            "pageSize": self.pageSize,
            "pageCount": (self.total + self.pageSize - 1) // self.pageSize if self.pageSize else 0,
        }


@dataclass(frozen=True)
class MeterPointSummaryDto:
    meterPointId: str
    code: str
    name: str
    unit: str
    kind: str
    readingCount: int = 0
    manualCount: int = 0
    sensorCount: int = 0
    suspectCount: int = 0
    firstValue: str = ""
    lastValue: str = ""
    minimumValue: str = ""
    maximumValue: str = ""
    averageValue: str = ""
    totalConsumption: str = ""
    firstCapturedAt: str = ""
    lastCapturedAt: str = ""


@dataclass(frozen=True)
class IngestResultDto:
    """Per-item outcome of a sensor batch.

    A batch is *not* all-or-nothing. A gateway flushing a minute of samples
    must not lose 499 good points because one arrived malformed — telemetry
    that rejects wholesale simply gets dropped on the floor by the field
    device. Each item reports its own fate and the caller can retry only what
    failed.
    """

    index: int
    status: str = "accepted"  # accepted | duplicate | rejected
    readingId: str = ""
    meterPointId: str = ""
    sensorKey: str = ""
    quality: str = ""
    delta: str = ""
    errorCode: str = ""
    message: str = ""


@dataclass(frozen=True)
class IngestBatchDto:
    accepted: int = 0
    duplicates: int = 0
    rejected: int = 0
    results: list[IngestResultDto] = field(default_factory=list)

    def asMeta(self) -> dict[str, object]:
        return {
            "accepted": self.accepted,
            "duplicates": self.duplicates,
            "rejected": self.rejected,
            "received": self.accepted + self.duplicates + self.rejected,
        }


@dataclass(frozen=True)
class MeterTriggerStatusDto:
    """Where one meter-driven PM plan stands against its meter."""

    planId: str
    deviceId: str
    deviceCode: str = ""
    deviceName: str = ""
    title: str = ""
    discipline: str = ""
    triggerType: str = "meter"
    metricType: str = ""
    metricUnit: str = ""
    status: str = "unknown"
    currentValue: str = ""
    dueAtValue: str = ""
    remaining: str = ""
    interval: str = ""
    thresholdOperator: str = ""
    thresholdValue: str = ""
    lastReadingAt: str = ""
    reason: str = ""


# =====================================================================================
# Mappers
# =====================================================================================
def meterPointDto(point: MeterPoint) -> MeterPointDto:
    return MeterPointDto(
        id=str(point.id),
        deviceId=str(point.deviceId),
        code=point.code,
        name=point.name,
        unit=point.unit,
        kind=point.kind,
        sensorKey=point.sensorKey,
        minimumValue=decimalText(point.minimumValue),
        maximumValue=decimalText(point.maximumValue),
        rolloverMaximum=decimalText(point.rolloverMaximum),
        maximumStepPerHour=decimalText(point.maximumStepPerHour),
        drivesRunningHours=point.drivesRunningHours,
        active=point.active,
        lastValue=decimalText(point.lastValue),
        lastReadingAt=momentText(point.lastReadingAt),
        lastCaptureMode=point.lastCaptureMode,
        readingCount=point.readingCount,
        createdAt=momentText(point.createdAt),
        updatedAt=momentText(point.updatedAt),
    )


def meterReadingDto(reading: MeterReading, point: MeterPoint | None = None) -> MeterReadingDto:
    return MeterReadingDto(
        id=str(reading.id),
        deviceId=str(reading.deviceId),
        meterPointId=str(reading.meterPointId),
        meterCode=point.code if point else "",
        meterName=point.name if point else "",
        unit=point.unit if point else "",
        value=decimalText(reading.value),
        delta=decimalText(reading.delta),
        capturedAt=momentText(reading.capturedAt),
        captureMode=reading.captureMode,
        quality=reading.quality,
        rolloverApplied=reading.rolloverApplied,
        note=reading.note,
        sensorKey=reading.sensorKey,
        sourceRef=reading.sourceRef,
        ingestionKey=reading.ingestionKey,
        recordedById=str(reading.recordedById) if reading.recordedById else "",
        recordedByName=reading.recordedByName,
        provenance=reading.provenance(),
        correctsReadingId=str(reading.correctsReadingId) if reading.correctsReadingId else "",
        supersededByReadingId=(
            str(reading.supersededByReadingId) if reading.supersededByReadingId else ""
        ),
        superseded=reading.isSuperseded,
        createdAt=momentText(reading.createdAt),
    )


def meterPointSummaryDto(summary: MeterPointSummary) -> MeterPointSummaryDto:
    return MeterPointSummaryDto(
        meterPointId=str(summary.meterPointId),
        code=summary.code,
        name=summary.name,
        unit=summary.unit,
        kind=summary.kind,
        readingCount=summary.readingCount,
        manualCount=summary.manualCount,
        sensorCount=summary.sensorCount,
        suspectCount=summary.suspectCount,
        firstValue=decimalText(summary.firstValue),
        lastValue=decimalText(summary.lastValue),
        minimumValue=decimalText(summary.minimumValue),
        maximumValue=decimalText(summary.maximumValue),
        averageValue=decimalText(summary.averageValue),
        totalConsumption=decimalText(summary.totalConsumption),
        firstCapturedAt=momentText(summary.firstCapturedAt),
        lastCapturedAt=momentText(summary.lastCapturedAt),
    )


def meterTriggerStatusDto(
    plan: object,
    evaluation: TriggerEvaluation,
    *,
    deviceCode: str = "",
    deviceName: str = "",
    lastReadingAt: datetime | None = None,
) -> MeterTriggerStatusDto:
    return MeterTriggerStatusDto(
        planId=str(getattr(plan, "id", "")),
        deviceId=str(getattr(plan, "deviceId", "")),
        deviceCode=deviceCode,
        deviceName=deviceName,
        title=getattr(plan, "title", ""),
        discipline=getattr(plan, "discipline", ""),
        triggerType=getattr(plan, "triggerType", ""),
        metricType=getattr(plan, "metricType", ""),
        metricUnit=getattr(plan, "metricUnit", ""),
        status=evaluation.status,
        currentValue=decimalText(evaluation.currentValue),
        dueAtValue=decimalText(evaluation.dueAtValue),
        remaining=decimalText(evaluation.remaining),
        interval=decimalText(getattr(plan, "metricInterval", None)),
        thresholdOperator=getattr(plan, "thresholdOperator", ""),
        thresholdValue=decimalText(getattr(plan, "thresholdValue", None)),
        lastReadingAt=momentText(lastReadingAt),
        reason=evaluation.reason,
    )


__all__ = [
    "IngestBatchDto",
    "IngestResultDto",
    "MeterPointDto",
    "MeterPointSummaryDto",
    "MeterReadingDto",
    "MeterReadingListDto",
    "MeterTriggerStatusDto",
    "decimalText",
    "meterPointDto",
    "meterPointSummaryDto",
    "meterReadingDto",
    "meterTriggerStatusDto",
    "momentText",
]
