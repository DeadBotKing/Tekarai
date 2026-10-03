"""Meter-reading request serializers.

Every numeric field is declared as ``CharField``. That is deliberate: DRF's
``DecimalField`` would accept a JSON number, and a JSON number is a double in
every JavaScript client, so ``124578901.2345`` would arrive already rounded.
Taking the value as text and parsing it with ``MeterValue`` keeps the digits
the plant actually recorded all the way into the database.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.maintenance.domain.valueObjects.meterTypes import (
    CAPTURE_MODES,
    MAX_INGEST_BATCH,
    METER_KINDS,
    READING_QUALITIES,
)

KIND_CHOICES = list(METER_KINDS)
QUALITY_CHOICES = list(READING_QUALITIES)
CAPTURE_MODE_CHOICES = list(CAPTURE_MODES)


class SaveMeterPointSerializer(serializers.Serializer):
    """Define or update a measurable channel on a device."""

    code = serializers.CharField(max_length=48, required=False, allow_blank=True, default="")
    name = serializers.CharField(max_length=200, required=False, allow_blank=True, default="")
    unit = serializers.CharField(max_length=30, required=False, allow_blank=True, default="")
    kind = serializers.ChoiceField(choices=KIND_CHOICES, required=False, default="cumulative")
    sensorKey = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    minimumValue = serializers.CharField(required=False, allow_blank=True, default="")
    maximumValue = serializers.CharField(required=False, allow_blank=True, default="")
    rolloverMaximum = serializers.CharField(required=False, allow_blank=True, default="")
    maximumStepPerHour = serializers.CharField(required=False, allow_blank=True, default="")
    drivesRunningHours = serializers.BooleanField(required=False, default=False)
    active = serializers.BooleanField(required=False, default=True)


class RecordManualReadingSerializer(serializers.Serializer):
    """One reading typed by a person.

    ``recordedBy`` is intentionally absent: attribution comes from the
    authenticated session, so a client cannot claim a reading was taken by
    somebody else.
    """

    meterPointId = serializers.CharField(required=False, allow_blank=True, default="")
    meterCode = serializers.CharField(
        max_length=48, required=False, allow_blank=True, default=""
    )
    value = serializers.CharField()
    capturedAt = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    quality = serializers.ChoiceField(
        choices=QUALITY_CHOICES, required=False, default="good"
    )


class SensorSampleSerializer(serializers.Serializer):
    """One sample inside a gateway batch."""

    sensorKey = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    meterPointId = serializers.CharField(required=False, allow_blank=True, default="")
    value = serializers.CharField()
    capturedAt = serializers.CharField(required=False, allow_blank=True, default="")
    quality = serializers.ChoiceField(
        choices=QUALITY_CHOICES, required=False, default="good"
    )
    #: Idempotency token. A retried batch must not double-count a counter.
    ingestionKey = serializers.CharField(
        max_length=128, required=False, allow_blank=True, default=""
    )
    sourceRef = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )


class IngestSensorReadingsSerializer(serializers.Serializer):
    readings = SensorSampleSerializer(many=True, allow_empty=False, max_length=MAX_INGEST_BATCH)
    #: Opt-in all-or-nothing. Default is partial success — see IngestResultDto.
    atomic = serializers.BooleanField(required=False, default=False)


class CorrectMeterReadingSerializer(serializers.Serializer):
    value = serializers.CharField()
    #: Mandatory. An unexplained correction is indistinguishable from
    #: tampering when the audit trail is reviewed later.
    note = serializers.CharField(max_length=500)


__all__ = [
    "CAPTURE_MODE_CHOICES",
    "KIND_CHOICES",
    "QUALITY_CHOICES",
    "CorrectMeterReadingSerializer",
    "IngestSensorReadingsSerializer",
    "RecordManualReadingSerializer",
    "SaveMeterPointSerializer",
    "SensorSampleSerializer",
]
