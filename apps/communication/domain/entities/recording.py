"""Recording aggregate (Phase 08 §15).

Explicit capability with the lifecycle
REQUESTED→STARTED→STOPPED→PROCESSING→AVAILABLE (FAILED from any active
state). Only METADATA lives here — the binary goes to the future
Documents/storage subsystem via ``storageRef`` (§15).
"""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    RECORDING_REQUESTED,
    RECORDING_STARTED,
    RECORDING_STOPPED,
    RECORDING_TRANSITIONS,
)
from apps.sharedKernel.domain.entities import AggregateRoot, DomainEvent, newId
from apps.sharedKernel.domain.errors import InvalidStateTransitionError


class Recording(AggregateRoot):
    def __init__(
        self,
        id: uuid.UUID,  # noqa: A002
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        requestedBy: uuid.UUID,
        createdAt: datetime,
        *,
        recordingStatus: str = RECORDING_REQUESTED,
        startedAt: datetime | None = None,
        stoppedAt: datetime | None = None,
        storageRef: str = "",
        durationSeconds: int = 0,
        failureReason: str = "",
    ) -> None:
        super().__init__(id)
        self.tenantId = tenantId
        self.meetingId = meetingId
        self.requestedBy = requestedBy
        self.createdAt = createdAt
        self.recordingStatus = recordingStatus
        self.startedAt = startedAt
        self.stoppedAt = stoppedAt
        self.storageRef = storageRef
        self.durationSeconds = durationSeconds
        self.failureReason = failureReason

    @staticmethod
    def request(
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        requestedBy: uuid.UUID,
        now: datetime,
    ) -> Recording:
        recording = Recording(
            id=newId(),
            tenantId=tenantId,
            meetingId=meetingId,
            requestedBy=requestedBy,
            createdAt=now,
        )
        recording.recordEvent(
            DomainEvent(
                name="recordingRequested",
                occurredAt=now,
                tenantId=tenantId,
                actorId=requestedBy,
            )
        )
        return recording

    def transitionTo(
        self, target: str, now: datetime, *, reason: str = ""
    ) -> None:
        allowed = RECORDING_TRANSITIONS.get(self.recordingStatus, ())
        if target not in allowed:
            raise InvalidStateTransitionError(
                f"Recording cannot move {self.recordingStatus} → {target}."
            )
        self.recordingStatus = target
        if target == RECORDING_STARTED:
            self.startedAt = now
            self.recordEvent(
                DomainEvent(name="recordingStarted", occurredAt=now, tenantId=self.tenantId)
            )
        elif target == RECORDING_STOPPED:
            self.stoppedAt = now
            if self.startedAt is not None:
                self.durationSeconds = int((now - self.startedAt).total_seconds())
            self.recordEvent(
                DomainEvent(name="recordingStopped", occurredAt=now, tenantId=self.tenantId)
            )
        elif target == "AVAILABLE":
            self.recordEvent(
                DomainEvent(name="recordingAvailable", occurredAt=now, tenantId=self.tenantId)
            )
        elif target == "FAILED":
            self.failureReason = reason[:300]
            self.recordEvent(
                DomainEvent(name="recordingFailed", occurredAt=now, tenantId=self.tenantId)
            )

    def attachStorageRef(self, storageRef: str) -> None:
        """Publication step — the Documents subsystem mints the reference."""
        self.storageRef = storageRef

    def snapshot(self) -> dict[str, Any]:
        return {
            "id": str(self.id),
            "meetingId": str(self.meetingId),
            "status": self.recordingStatus,
            "durationSeconds": self.durationSeconds,
            "storageRef": self.storageRef,
        }
