"""Meter-reading use cases — ثبت قرائت دستی و سنسوری.

Three entry points write to the reading stream, and they are deliberately
separate even though they share a core:

* :class:`RecordManualMeterReadingUseCase` — one reading typed by a person.
  Attribution comes from the session, so the operator never supplies it.
* :class:`IngestSensorReadingsUseCase` — a batch pushed by a gateway, keyed by
  ``sensorKey``, idempotent, and tolerant of partial failure.
* :class:`CorrectMeterReadingUseCase` — appends a replacement for a wrong
  reading and links the two. Never an update.

Keeping them apart is what lets each carry its own permission: a field
gateway's API key can ingest but must not be able to type a "manual" reading
attributed to a human, and a technician can correct a typo without being
granted gateway credentials.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from apps.maintenance.application.dto.meterDtos import (
    IngestBatchDto,
    IngestResultDto,
    MeterPointDto,
    MeterPointSummaryDto,
    MeterReadingDto,
    MeterReadingListDto,
    MeterTriggerStatusDto,
    decimalText,
    meterPointDto,
    meterPointSummaryDto,
    meterReadingDto,
    meterTriggerStatusDto,
)
from apps.maintenance.application.services.tenantResolver import resolveTenantId
from apps.maintenance.domain.entities.meterReading import MeterPoint
from apps.maintenance.domain.exceptions.meterErrors import (
    MeterIngestionConflictError,
    MeterPointNotBoundError,
    MeterReadingAlreadyCorrectedError,
)
from apps.maintenance.domain.services.meterReadingRules import (
    assessReading,
    evaluatePlanTrigger,
)
from apps.maintenance.domain.valueObjects.meterTypes import (
    CAPTURE_MANUAL,
    CAPTURE_SENSOR,
    MAX_INGEST_BATCH,
    MAX_INGESTION_KEY_LENGTH,
    METER_CUMULATIVE,
    QUALITY_GOOD,
    TRIGGER_CALENDAR,
    TRIGGER_CONDITION,
    TRIGGER_METER,
    MeterValue,
    ensureMeterKind,
    ensureQuality,
    normalizeMeterCode,
    normalizeSensorKey,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.application.useCase import AUDIT_CREATE, AUDIT_DELETE, AUDIT_UPDATE, UseCase
from apps.sharedKernel.domain.errors import (
    EntityNotFoundError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.events import DomainEvent

if TYPE_CHECKING:  # pragma: no cover — typing only
    from apps.maintenance.domain.repositories.maintenanceRepositories import (
        MeterReadingRepository,
    )

PERMISSION_METER_VIEW = "maintenance.meter.view"
PERMISSION_METER_MANAGE = "maintenance.meter.manage"
PERMISSION_METER_RECORD = "maintenance.meter.record"
PERMISSION_METER_INGEST = "maintenance.meter.ingest"

#: Conventional code of the hour meter that owns ``Device.runningHours``.
RUNNING_HOURS_CODE = "RUNNING_HOURS"

MAX_PAGE_SIZE = 500
DEFAULT_PAGE_SIZE = 100
#: Device sweep size for the fleet-wide meter-PM status feed.
DEVICE_SCAN_PAGE_SIZE = 500


# =====================================================================================
# Commands / queries
# =====================================================================================
@dataclass(frozen=True)
class SaveMeterPointCommand:
    deviceId: str = ""
    meterPointId: str = ""
    code: str = ""
    name: str = ""
    unit: str = ""
    kind: str = "gauge"
    sensorKey: str = ""
    minimumValue: str = ""
    maximumValue: str = ""
    rolloverMaximum: str = ""
    maximumStepPerHour: str = ""
    drivesRunningHours: bool = False
    active: bool = True


@dataclass(frozen=True)
class DeleteMeterPointCommand:
    meterPointId: str


@dataclass(frozen=True)
class ListMeterPointsQuery:
    deviceId: str = ""
    search: str = ""
    kind: str = ""
    activeOnly: bool = False


@dataclass(frozen=True)
class RecordManualReadingCommand:
    deviceId: str = ""
    meterPointId: str = ""
    meterCode: str = ""
    value: str = ""
    capturedAt: str = ""
    note: str = ""
    quality: str = QUALITY_GOOD


@dataclass(frozen=True)
class SensorSampleCommand:
    sensorKey: str = ""
    meterPointId: str = ""
    value: str = ""
    capturedAt: str = ""
    quality: str = QUALITY_GOOD
    ingestionKey: str = ""
    sourceRef: str = ""


@dataclass(frozen=True)
class IngestSensorReadingsCommand:
    samples: tuple[SensorSampleCommand, ...] = ()
    #: When true a single bad sample rolls the whole batch back. Off by
    #: default: see IngestResultDto for why telemetry prefers partial success.
    atomic: bool = False


@dataclass(frozen=True)
class CorrectMeterReadingCommand:
    readingId: str = ""
    value: str = ""
    note: str = ""


@dataclass(frozen=True)
class ListMeterReadingsQuery:
    deviceId: str = ""
    meterPointId: str = ""
    captureMode: str = ""
    quality: str = ""
    fromMoment: str = ""
    toMoment: str = ""
    includeSuperseded: bool = True
    page: int = 1
    pageSize: int = DEFAULT_PAGE_SIZE


@dataclass(frozen=True)
class MeterPointSummaryQuery:
    meterPointId: str = ""
    fromMoment: str = ""
    toMoment: str = ""


@dataclass(frozen=True)
class MeterPmStatusQuery:
    deviceId: str = ""
    statusFilter: str = ""


# =====================================================================================
# Helpers
# =====================================================================================
def parseMoment(raw: str, fallback: datetime | None = None) -> datetime | None:
    """Parse an ISO-8601 instant, normalising ``Z`` and naive values to UTC.

    A naive timestamp is interpreted as UTC rather than rejected: field
    gateways are notoriously inconsistent about offsets, and refusing the
    sample would lose data that is otherwise perfectly usable.
    """
    text = str(raw or "").strip()
    if not text:
        return fallback
    if text.endswith(("z", "Z")):
        text = f"{text[:-1]}+00:00"
    try:
        moment = datetime.fromisoformat(text)
    except ValueError as error:
        raise ValidationFailedError(
            "Timestamp must be ISO-8601.", fieldErrors={"capturedAt": "invalid"}
        ) from error
    if moment.tzinfo is None:
        from datetime import UTC

        return moment.replace(tzinfo=UTC)
    return moment


def optionalDecimal(raw: str, fieldName: str) -> Decimal | None:
    text = str(raw or "").strip()
    if not text:
        return None
    return MeterValue.parse(text, fieldName=fieldName).amount


class MeterUseCaseBase(UseCase):
    """Shared wiring for every meter use case."""

    def __init__(
        self,
        *,
        pointRepository,  # noqa: ANN001 — protocol, injected by the container
        readingRepository,  # noqa: ANN001
        deviceRepository,  # noqa: ANN001
        unitOfWork,  # noqa: ANN001
        auditRecorder,  # noqa: ANN001
        eventDispatcher,  # noqa: ANN001
        permissionGate,  # noqa: ANN001
        clock,  # noqa: ANN001
        registryRepository=None,  # noqa: ANN001 — only the PM status feed needs it
    ) -> None:
        super().__init__(unitOfWork, auditRecorder, eventDispatcher, permissionGate, clock)
        self.pointRepository = pointRepository
        self.readingRepository = readingRepository
        self.deviceRepository = deviceRepository
        self.registryRepository = registryRepository

    def requireDevice(self, tenantId: uuid.UUID, deviceId: str):  # noqa: ANN201
        try:
            identifier = uuid.UUID(str(deviceId))
        except (ValueError, AttributeError, TypeError) as error:
            raise ValidationFailedError(
                "Device id must be a UUID.", fieldErrors={"deviceId": "invalid"}
            ) from error
        device = self.deviceRepository.getById(tenantId, identifier)
        if device is None:
            raise EntityNotFoundError("Device")
        return device

    def requirePoint(self, tenantId: uuid.UUID, pointId: str) -> MeterPoint:
        try:
            identifier = uuid.UUID(str(pointId))
        except (ValueError, AttributeError, TypeError) as error:
            raise ValidationFailedError(
                "Meter point id must be a UUID.", fieldErrors={"meterPointId": "invalid"}
            ) from error
        point = self.pointRepository.getById(tenantId, identifier)
        if point is None:
            raise EntityNotFoundError("Meter point")
        return point

    def resolvePoint(
        self, tenantId: uuid.UUID, deviceId: str, pointId: str, code: str
    ) -> MeterPoint:
        """Accept either the point id or the device + meter code.

        Exactly one addressing mode may be used, so a payload that names both
        and contradicts itself is a hard error rather than a silent preference.
        """
        if pointId and code:
            raise ValidationFailedError(
                "Provide exactly one of meterPointId or meterCode.",
                fieldErrors={"meterPointId": "ambiguous"},
            )
        if pointId:
            return self.requirePoint(tenantId, pointId)
        if not code:
            raise ValidationFailedError(
                "Provide meterPointId or meterCode.",
                fieldErrors={"meterCode": "required"},
            )
        device = self.requireDevice(tenantId, deviceId)
        point = self.pointRepository.getByCode(tenantId, device.id, normalizeMeterCode(code))
        if point is None:
            raise EntityNotFoundError("Meter point")
        return point


# =====================================================================================
# Meter point definitions
# =====================================================================================
class SaveMeterPointUseCase(MeterUseCaseBase):
    """Create or update the definition of one measurable channel."""

    requiredAction = PERMISSION_METER_MANAGE

    def validateCommand(self, command: SaveMeterPointCommand) -> None:
        if not command.meterPointId:
            if not command.deviceId:
                raise ValidationFailedError(
                    "Device is required.", fieldErrors={"deviceId": "required"}
                )
            normalizeMeterCode(command.code)
        if command.kind:
            ensureMeterKind(command.kind)
        normalizeSensorKey(command.sensorKey)

        minimum = optionalDecimal(command.minimumValue, "minimumValue")
        maximum = optionalDecimal(command.maximumValue, "maximumValue")
        if minimum is not None and maximum is not None and minimum > maximum:
            raise ValidationFailedError(
                "Minimum must not exceed maximum.",
                fieldErrors={"minimumValue": "greaterThanMaximum"},
            )
        rollover = optionalDecimal(command.rolloverMaximum, "rolloverMaximum")
        if rollover is not None and rollover <= 0:
            raise ValidationFailedError(
                "Counter capacity must be positive.",
                fieldErrors={"rolloverMaximum": "notPositive"},
            )
        step = optionalDecimal(command.maximumStepPerHour, "maximumStepPerHour")
        if step is not None and step <= 0:
            raise ValidationFailedError(
                "Maximum step per hour must be positive.",
                fieldErrors={"maximumStepPerHour": "notPositive"},
            )
        kind = ensureMeterKind(command.kind) if command.kind else METER_CUMULATIVE
        if rollover is not None and kind != METER_CUMULATIVE:
            raise ValidationFailedError(
                "Only cumulative counters can roll over.",
                fieldErrors={"rolloverMaximum": "gaugeCannotRollOver"},
            )
        if command.drivesRunningHours and kind != METER_CUMULATIVE:
            raise ValidationFailedError(
                "Running hours must come from a cumulative counter.",
                fieldErrors={"drivesRunningHours": "requiresCumulative"},
            )

    def perform(self, command: SaveMeterPointCommand) -> MeterPointDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        payload: dict[str, object] = {
            "name": command.name.strip(),
            "unit": command.unit.strip(),
            "sensorKey": normalizeSensorKey(command.sensorKey),
            "minimumValue": optionalDecimal(command.minimumValue, "minimumValue"),
            "maximumValue": optionalDecimal(command.maximumValue, "maximumValue"),
            "rolloverMaximum": optionalDecimal(command.rolloverMaximum, "rolloverMaximum"),
            "maximumStepPerHour": optionalDecimal(command.maximumStepPerHour, "maximumStepPerHour"),
            "drivesRunningHours": command.drivesRunningHours,
            "active": command.active,
        }

        if command.meterPointId:
            existing = self.requirePoint(tenantId, command.meterPointId)
            point = self.pointRepository.update(tenantId, existing.id, payload, now)
            self.audit(
                AUDIT_UPDATE,
                "MeterPoint",
                str(point.id),
                tenantId,
                before=existing.snapshot(),
                after=point.snapshot(),
            )
        else:
            device = self.requireDevice(tenantId, command.deviceId)
            payload["code"] = normalizeMeterCode(command.code)
            payload["kind"] = ensureMeterKind(command.kind or METER_CUMULATIVE)
            payload["name"] = payload["name"] or str(payload["code"])
            point = self.pointRepository.create(tenantId, device.id, payload, now)
            self.audit(AUDIT_CREATE, "MeterPoint", str(point.id), tenantId, after=point.snapshot())
            self._pendingEvents.append(
                DomainEvent(
                    name="meterPointDefined",
                    occurredAt=now,
                    tenantId=tenantId,
                    payload={
                        "meterPointId": str(point.id),
                        "deviceId": str(point.deviceId),
                        "code": point.code,
                        "kind": point.kind,
                        "sensorKey": point.sensorKey,
                    },
                )
            )
        return meterPointDto(point)


class ListMeterPointsUseCase(MeterUseCaseBase):
    requiredAction = PERMISSION_METER_VIEW

    def perform(self, query: ListMeterPointsQuery) -> list[MeterPointDto]:
        tenantId = resolveTenantId("")
        if query.deviceId:
            device = self.requireDevice(tenantId, query.deviceId)
            points = self.pointRepository.listForDevice(
                tenantId, device.id, includeInactive=not query.activeOnly
            )
        else:
            points = self.pointRepository.listForTenant(
                tenantId,
                search=query.search.strip(),
                kind=query.kind.strip(),
                activeOnly=query.activeOnly,
            )
        return [meterPointDto(point) for point in points]


class DeleteMeterPointUseCase(MeterUseCaseBase):
    """Retire a meter point. Its readings are kept."""

    requiredAction = PERMISSION_METER_MANAGE

    def perform(self, command: DeleteMeterPointCommand) -> None:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        point = self.requirePoint(tenantId, command.meterPointId)
        self.pointRepository.softDelete(tenantId, point.id, now)
        self.audit(AUDIT_DELETE, "MeterPoint", str(point.id), tenantId, before=point.snapshot())


# =====================================================================================
# Writing readings
# =====================================================================================
class MeterAppendMixin:
    """The shared append path used by manual entry, ingestion and corrections.

    Mixed into use cases that already own these collaborators; the
    annotations below state that contract for the type checker without
    creating a second source of truth at runtime.
    """

    if TYPE_CHECKING:  # pragma: no cover — supplied by the use-case base
        readingRepository: MeterReadingRepository
        _pendingEvents: list

    def appendReading(
        self,
        tenantId: uuid.UUID,
        point: MeterPoint,
        *,
        value: Decimal,
        capturedAt: datetime,
        captureMode: str,
        now: datetime,
        requestedQuality: str = QUALITY_GOOD,
        note: str = "",
        sensorKey: str = "",
        sourceRef: str = "",
        ingestionKey: str = "",
        correctsReadingId: uuid.UUID | None = None,
    ):  # noqa: ANN201 — returns a MeterReading
        """Lock the point, judge the value, append, refresh derived state."""
        locked = self.readingRepository.lockPoint(tenantId, point.id)
        previous = self.readingRepository.previousReading(tenantId, locked.id, capturedAt)
        assessment = assessReading(
            locked, value, capturedAt, previous, now, requestedQuality=requestedQuality
        )
        context = currentContext()
        reading = self.readingRepository.append(
            tenantId,
            locked,
            {
                "value": value,
                "delta": assessment.delta,
                "capturedAt": capturedAt,
                "captureMode": captureMode,
                "quality": assessment.quality,
                "rolloverApplied": assessment.rolloverApplied,
                "note": note,
                "sensorKey": sensorKey or locked.sensorKey,
                "sourceRef": sourceRef,
                "ingestionKey": ingestionKey,
                "recordedById": uuid.UUID(context.actorId) if context.actorId else None,
                "recordedByName": context.actorName,
                "correctsReadingId": correctsReadingId,
                "correlationId": context.correlationId,
            },
            now,
        )
        self._pendingEvents.append(
            DomainEvent(
                name="meterReadingRecorded",
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "readingId": str(reading.id),
                    "deviceId": str(reading.deviceId),
                    "meterPointId": str(reading.meterPointId),
                    "meterCode": locked.code,
                    "value": decimalText(reading.value),
                    "delta": decimalText(reading.delta),
                    "captureMode": reading.captureMode,
                    "quality": reading.quality,
                    "rolloverApplied": reading.rolloverApplied,
                    "reason": assessment.reason,
                },
            )
        )
        # A suspect point is the earliest warning that an instrument is
        # drifting or a keypad entry went wrong, so it gets its own event that
        # the notification rules can subscribe to.
        if assessment.quality != QUALITY_GOOD:
            self._pendingEvents.append(
                DomainEvent(
                    name="meterReadingFlagged",
                    occurredAt=now,
                    tenantId=tenantId,
                    payload={
                        "eventId": f"meterReadingFlagged:{reading.id}",
                        "sourceId": str(reading.id),
                        "deviceId": str(reading.deviceId),
                        "meterCode": locked.code,
                        "quality": assessment.quality,
                        "reason": assessment.reason,
                        "value": decimalText(reading.value),
                    },
                )
            )
        return reading, locked


class RecordManualMeterReadingUseCase(MeterAppendMixin, MeterUseCaseBase):
    """One reading typed by an operator or technician."""

    requiredAction = PERMISSION_METER_RECORD

    def validateCommand(self, command: RecordManualReadingCommand) -> None:
        if not str(command.value or "").strip():
            raise ValidationFailedError(
                "Reading value is required.", fieldErrors={"value": "required"}
            )
        MeterValue.parse(command.value)
        if command.quality:
            ensureQuality(command.quality)
        if len(command.note or "") > 500:
            raise ValidationFailedError(
                "Note must not exceed 500 characters.", fieldErrors={"note": "tooLong"}
            )

    def perform(self, command: RecordManualReadingCommand) -> MeterReadingDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        point = self.resolvePoint(
            tenantId, command.deviceId, command.meterPointId, command.meterCode
        )
        reading, locked = self.appendReading(
            tenantId,
            point,
            value=MeterValue.parse(command.value).amount,
            capturedAt=parseMoment(command.capturedAt, now) or now,
            captureMode=CAPTURE_MANUAL,
            now=now,
            requestedQuality=ensureQuality(command.quality or QUALITY_GOOD),
            note=command.note.strip(),
        )
        self.audit(
            AUDIT_CREATE, "MeterReading", str(reading.id), tenantId, after=reading.snapshot()
        )
        return meterReadingDto(reading, locked)


class IngestSensorReadingsUseCase(MeterAppendMixin, MeterUseCaseBase):
    """Batch ingestion for PLC / SCADA / IoT gateways.

    Resolution is by ``sensorKey`` so a gateway never needs to know Tekarai's
    UUIDs — it quotes the tag name it already has in its own configuration.
    """

    requiredAction = PERMISSION_METER_INGEST

    def validateCommand(self, command: IngestSensorReadingsCommand) -> None:
        if not command.samples:
            raise ValidationFailedError(
                "At least one sample is required.", fieldErrors={"readings": "required"}
            )
        if len(command.samples) > MAX_INGEST_BATCH:
            raise ValidationFailedError(
                f"A batch must not exceed {MAX_INGEST_BATCH} samples.",
                fieldErrors={"readings": "tooMany"},
            )
        keys = [s.ingestionKey for s in command.samples if s.ingestionKey]
        if len(keys) != len(set(keys)):
            # Catching this here gives a clear message instead of a unique
            # constraint violation halfway through the batch.
            raise ValidationFailedError(
                "Ingestion keys must be unique within one batch.",
                fieldErrors={"ingestionKey": "duplicatedInBatch"},
            )
        for key in keys:
            if len(key) > MAX_INGESTION_KEY_LENGTH:
                raise ValidationFailedError(
                    f"Ingestion key must not exceed {MAX_INGESTION_KEY_LENGTH} characters.",
                    fieldErrors={"ingestionKey": "tooLong"},
                )

    def perform(self, command: IngestSensorReadingsCommand) -> IngestBatchDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        results: list[IngestResultDto] = []
        accepted = duplicates = rejected = 0

        for index, sample in enumerate(command.samples):
            try:
                outcome = self._ingestOne(tenantId, sample, index, now)
            except Exception as error:  # noqa: BLE001 — per-item isolation is the point
                if command.atomic:
                    raise
                rejected += 1
                results.append(
                    IngestResultDto(
                        index=index,
                        status="rejected",
                        sensorKey=sample.sensorKey,
                        errorCode=getattr(error, "code", "SYS_VALIDATION_FAILED"),
                        message=getattr(error, "message", str(error))[:300],
                    )
                )
                continue
            results.append(outcome)
            if outcome.status == "accepted":
                accepted += 1
            elif outcome.status == "duplicate":
                duplicates += 1
            else:  # pragma: no cover — defensive
                rejected += 1

        return IngestBatchDto(
            accepted=accepted, duplicates=duplicates, rejected=rejected, results=results
        )

    def _ingestOne(
        self,
        tenantId: uuid.UUID,
        sample: SensorSampleCommand,
        index: int,
        now: datetime,
    ) -> IngestResultDto:
        if sample.sensorKey and sample.meterPointId:
            raise ValidationFailedError(
                "Provide exactly one of sensorKey or meterPointId.",
                fieldErrors={"sensorKey": "ambiguous"},
            )

        if sample.meterPointId:
            point = self.requirePoint(tenantId, sample.meterPointId)
        else:
            key = normalizeSensorKey(sample.sensorKey)
            if not key:
                raise ValidationFailedError(
                    "Sensor key is required.", fieldErrors={"sensorKey": "required"}
                )
            point = self.pointRepository.getBySensorKey(tenantId, key)
            if point is None:
                raise MeterPointNotBoundError(f"No meter point is bound to sensor key '{key}'.")
            if not point.active:
                raise MeterPointNotBoundError(f"Meter point for sensor key '{key}' is inactive.")

        value = MeterValue.parse(sample.value).amount
        capturedAt = parseMoment(sample.capturedAt, now) or now
        quality = ensureQuality(sample.quality or QUALITY_GOOD)

        # Idempotency: a retried batch returns the stored row rather than
        # double-counting a counter. A *different* value under the same key is
        # a gateway bug and is surfaced, never silently absorbed.
        if sample.ingestionKey:
            existing = self.readingRepository.findByIngestionKey(tenantId, sample.ingestionKey)
            if existing is not None:
                if existing.value != value or existing.meterPointId != point.id:
                    raise MeterIngestionConflictError(
                        f"Ingestion key '{sample.ingestionKey}' already stored a different reading."
                    )
                return IngestResultDto(
                    index=index,
                    status="duplicate",
                    readingId=str(existing.id),
                    meterPointId=str(existing.meterPointId),
                    sensorKey=existing.sensorKey,
                    quality=existing.quality,
                    delta=decimalText(existing.delta),
                )

        reading, _ = self.appendReading(
            tenantId,
            point,
            value=value,
            capturedAt=capturedAt,
            captureMode=CAPTURE_SENSOR,
            now=now,
            requestedQuality=quality,
            sensorKey=point.sensorKey,
            sourceRef=sample.sourceRef.strip(),
            ingestionKey=sample.ingestionKey.strip(),
        )
        return IngestResultDto(
            index=index,
            status="accepted",
            readingId=str(reading.id),
            meterPointId=str(reading.meterPointId),
            sensorKey=reading.sensorKey,
            quality=reading.quality,
            delta=decimalText(reading.delta),
        )


class CorrectMeterReadingUseCase(MeterAppendMixin, MeterUseCaseBase):
    """Append a replacement for a wrong reading and link the two.

    Both rows survive. The original stays visible and is marked superseded,
    which is the only honest way to fix a number that other records already
    depend on.
    """

    requiredAction = PERMISSION_METER_RECORD

    def validateCommand(self, command: CorrectMeterReadingCommand) -> None:
        if not str(command.value or "").strip():
            raise ValidationFailedError(
                "Corrected value is required.", fieldErrors={"value": "required"}
            )
        MeterValue.parse(command.value)
        if not str(command.note or "").strip():
            # A correction with no stated reason is indistinguishable from
            # tampering when someone reviews the trail a year later.
            raise ValidationFailedError(
                "A correction must state why.", fieldErrors={"note": "required"}
            )

    def perform(self, command: CorrectMeterReadingCommand) -> MeterReadingDto:
        tenantId = resolveTenantId("")
        now = self.clock.nowUtc()
        try:
            readingId = uuid.UUID(str(command.readingId))
        except (ValueError, AttributeError, TypeError) as error:
            raise ValidationFailedError(
                "Reading id must be a UUID.", fieldErrors={"readingId": "invalid"}
            ) from error

        original = self.readingRepository.getById(tenantId, readingId)
        if original is None:
            raise EntityNotFoundError("Meter reading")
        if original.isSuperseded:
            raise MeterReadingAlreadyCorrectedError("This reading has already been corrected.")

        point = self.requirePoint(tenantId, str(original.meterPointId))
        correction, locked = self.appendReading(
            tenantId,
            point,
            value=MeterValue.parse(command.value).amount,
            # The correction carries the *original* observation time: the dial
            # was read when it was read, only the transcription was wrong.
            capturedAt=original.capturedAt,
            captureMode=original.captureMode,
            now=now,
            note=command.note.strip(),
            sensorKey=original.sensorKey,
            sourceRef=original.sourceRef,
            correctsReadingId=original.id,
        )
        self.readingRepository.markSuperseded(tenantId, original.id, correction.id)
        self.audit(
            AUDIT_UPDATE,
            "MeterReading",
            str(original.id),
            tenantId,
            before=original.snapshot(),
            after=correction.snapshot(),
        )
        self._pendingEvents.append(
            DomainEvent(
                name="meterReadingCorrected",
                occurredAt=now,
                tenantId=tenantId,
                payload={
                    "readingId": str(correction.id),
                    "correctsReadingId": str(original.id),
                    "deviceId": str(original.deviceId),
                    "previousValue": decimalText(original.value),
                    "correctedValue": decimalText(correction.value),
                    "note": command.note.strip(),
                },
            )
        )
        return meterReadingDto(correction, locked)


# =====================================================================================
# Reading readings
# =====================================================================================
class ListMeterReadingsUseCase(MeterUseCaseBase):
    requiredAction = PERMISSION_METER_VIEW

    def perform(self, query: ListMeterReadingsQuery) -> MeterReadingListDto:
        tenantId = resolveTenantId("")
        pageSize = max(1, min(int(query.pageSize or DEFAULT_PAGE_SIZE), MAX_PAGE_SIZE))
        page = max(1, int(query.page or 1))

        deviceId = None
        if query.deviceId:
            deviceId = self.requireDevice(tenantId, query.deviceId).id
        pointId = None
        pointsByCode: dict[uuid.UUID, MeterPoint] = {}
        if query.meterPointId:
            point = self.requirePoint(tenantId, query.meterPointId)
            pointId = point.id
            pointsByCode[point.id] = point

        rows, total = self.readingRepository.listReadings(
            tenantId,
            deviceId=deviceId,
            pointId=pointId,
            captureMode=query.captureMode.strip(),
            quality=query.quality.strip(),
            fromMoment=parseMoment(query.fromMoment),
            toMoment=parseMoment(query.toMoment),
            includeSuperseded=query.includeSuperseded,
            offset=(page - 1) * pageSize,
            limit=pageSize,
        )

        # Resolve the point labels in one pass instead of per row.
        missing = {row.meterPointId for row in rows} - set(pointsByCode)
        for identifier in missing:
            resolved = self.pointRepository.getById(tenantId, identifier)
            if resolved is not None:
                pointsByCode[identifier] = resolved

        return MeterReadingListDto(
            items=[meterReadingDto(row, pointsByCode.get(row.meterPointId)) for row in rows],
            total=total,
            page=page,
            pageSize=pageSize,
        )


class GetMeterPointSummaryUseCase(MeterUseCaseBase):
    requiredAction = PERMISSION_METER_VIEW

    def perform(self, query: MeterPointSummaryQuery) -> MeterPointSummaryDto:
        tenantId = resolveTenantId("")
        point = self.requirePoint(tenantId, query.meterPointId)
        summary = self.readingRepository.summarise(
            tenantId,
            point,
            fromMoment=parseMoment(query.fromMoment),
            toMoment=parseMoment(query.toMoment),
        )
        return meterPointSummaryDto(summary)


class GetMeterPmStatusUseCase(MeterUseCaseBase):
    """The feed that makes meter-driven PM visible.

    Every active plan whose trigger is meter- or condition-based is evaluated
    against the current value of the meter point named by ``metricType``. This
    is the read model that replaces the old behaviour where such plans simply
    never appeared anywhere.
    """

    requiredAction = PERMISSION_METER_VIEW

    def perform(self, query: MeterPmStatusQuery) -> list[MeterTriggerStatusDto]:
        tenantId = resolveTenantId("")
        if self.registryRepository is None:  # pragma: no cover — wiring guard
            return []

        devices = self._devices(tenantId, query.deviceId)
        statuses: list[MeterTriggerStatusDto] = []
        for device in devices:
            plans = self.registryRepository.listPlans(tenantId, device.id)
            meterPlans = [
                plan
                for plan in plans
                if plan.active and plan.triggerType in (TRIGGER_METER, TRIGGER_CONDITION)
            ]
            if not meterPlans:
                continue
            points = {
                point.code: point
                for point in self.pointRepository.listForDevice(tenantId, device.id)
            }
            for plan in meterPlans:
                point = points.get(plan.metricType)
                evaluation = evaluatePlanTrigger(
                    plan, point.lastValue if point else plan.lastMetricValue
                )
                statuses.append(
                    meterTriggerStatusDto(
                        plan,
                        evaluation,
                        deviceCode=device.code,
                        deviceName=device.name,
                        lastReadingAt=point.lastReadingAt if point else None,
                    )
                )

        wanted = query.statusFilter.strip()
        if wanted:
            statuses = [item for item in statuses if item.status == wanted]
        # Due first, then warnings — the order a planner reads the screen in.
        priority = {"due": 0, "warning": 1, "ok": 2, "unknown": 3}
        statuses.sort(key=lambda item: (priority.get(item.status, 9), item.deviceCode))
        return statuses

    def _devices(self, tenantId: uuid.UUID, deviceId: str) -> list:
        if deviceId:
            return [self.requireDevice(tenantId, deviceId)]
        from apps.maintenance.domain.repositories.maintenanceRepositories import DeviceFilters

        page = self.deviceRepository.list(
            DeviceFilters(tenantId=tenantId, page=1, pageSize=DEVICE_SCAN_PAGE_SIZE)
        )
        return list(page.items)


__all__ = [
    "DEFAULT_PAGE_SIZE",
    "MAX_PAGE_SIZE",
    "PERMISSION_METER_INGEST",
    "PERMISSION_METER_MANAGE",
    "PERMISSION_METER_RECORD",
    "PERMISSION_METER_VIEW",
    "RUNNING_HOURS_CODE",
    "TRIGGER_CALENDAR",
    "CorrectMeterReadingCommand",
    "CorrectMeterReadingUseCase",
    "DeleteMeterPointCommand",
    "DeleteMeterPointUseCase",
    "GetMeterPmStatusUseCase",
    "GetMeterPointSummaryUseCase",
    "IngestSensorReadingsCommand",
    "IngestSensorReadingsUseCase",
    "ListMeterPointsQuery",
    "ListMeterPointsUseCase",
    "ListMeterReadingsQuery",
    "ListMeterReadingsUseCase",
    "MeterPmStatusQuery",
    "MeterPointSummaryQuery",
    "RecordManualMeterReadingUseCase",
    "RecordManualReadingCommand",
    "SaveMeterPointCommand",
    "SaveMeterPointUseCase",
    "SensorSampleCommand",
    "parseMoment",
]
