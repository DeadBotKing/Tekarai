"""Request serializers for timers, scanning and offline sync.

Timestamps and decimals travel as text for the same reason the meter slice
does it: a JSON number is a double in every browser, and an offline queue
that has been sitting on a phone for a day must deliver *exactly* the moment
it captured, not a re-serialised approximation of it.
"""

from __future__ import annotations

from rest_framework import serializers

from apps.maintenance.domain.valueObjects.fieldOpsTypes import (
    MAX_CLIENT_REQUEST_ID_LENGTH,
    MAX_SYNC_BATCH,
    SCAN_SYMBOLOGIES,
    SYNC_KINDS,
)


class StartWorkTimerSerializer(serializers.Serializer):
    """«شروع کار». Everything is optional — the common case is a bare tap."""

    technicianName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    #: Present only when the start was captured offline and is being replayed.
    startedAt = serializers.CharField(required=False, allow_blank=True, default="")
    hourlyRate = serializers.CharField(required=False, allow_blank=True, default="0")
    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    capturedOffline = serializers.BooleanField(required=False, default=False)


class StopWorkTimerSerializer(serializers.Serializer):
    """«پایان کار» — stop by timer id, or by (order, technician)."""

    timerId = serializers.CharField(required=False, allow_blank=True, default="")
    technicianName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    endedAt = serializers.CharField(required=False, allow_blank=True, default="")
    note = serializers.CharField(
        max_length=500, required=False, allow_blank=True, default=""
    )
    #: Breaks the technician took inside the span (lunch, waiting for a crane).
    pausedSeconds = serializers.IntegerField(required=False, default=0, min_value=0)
    capturedOffline = serializers.BooleanField(required=False, default=False)


class ScanQuerySerializer(serializers.Serializer):
    code = serializers.CharField(max_length=512)
    symbology = serializers.ChoiceField(
        choices=list(SCAN_SYMBOLOGIES), required=False, default="manual"
    )


class SyncOperationSerializer(serializers.Serializer):
    """One queued intent from a phone."""

    clientRequestId = serializers.CharField(max_length=MAX_CLIENT_REQUEST_ID_LENGTH)
    kind = serializers.ChoiceField(choices=list(SYNC_KINDS))
    #: Free-form because each kind has its own shape; the target use case
    #: validates it. Rejecting unknown keys here would break older phones.
    payload = serializers.DictField(required=False, default=dict)
    occurredAt = serializers.CharField(required=False, allow_blank=True, default="")


class SyncBatchSerializer(serializers.Serializer):
    operations = serializers.ListField(
        child=SyncOperationSerializer(), allow_empty=True, max_length=MAX_SYNC_BATCH
    )
    deviceLabel = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    atomic = serializers.BooleanField(required=False, default=False)
