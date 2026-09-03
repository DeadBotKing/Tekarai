"""Phase 10 repository contracts (ports) for the new capabilities.

These extend the Phase 08 repository set (``communicationRepositories``) with:
- message revision history (§11),
- meeting transcripts + segments (§34/§35),
- user blocks (§70),
- meeting-capability overrides (§30 role grants/denials per meeting),
- the search provider port (§54) and the CallProvider port (§25).

The domain layer defines Protocol contracts; infrastructure implements them
over the Django ORM. No ORM/Redis/Channels imports here (§62/§74).
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol, runtime_checkable

from apps.communication.domain.entities.phase10Records import (
    MeetingTranscript,
    MessageRevision,
    TranscriptSegment,
    UserBlock,
)

# ---------------------------------------------------------------------------
# message revisions (§11)
# ---------------------------------------------------------------------------


@runtime_checkable
class MessageRevisionRepository(Protocol):
    def add(self, revision: MessageRevision) -> None: ...

    def nextRevisionNumber(
        self, tenantId: uuid.UUID, messageId: uuid.UUID
    ) -> int: ...

    def listForMessage(
        self, tenantId: uuid.UUID, messageId: uuid.UUID
    ) -> list[MessageRevision]: ...


# ---------------------------------------------------------------------------
# transcripts + segments (§34/§35)
# ---------------------------------------------------------------------------


@runtime_checkable
class TranscriptRepository(Protocol):
    def create(self, transcript: MeetingTranscript) -> None: ...

    def update(self, transcript: MeetingTranscript) -> None: ...

    def addSegment(self, segment: TranscriptSegment) -> None: ...

    def getById(
        self, transcriptId: uuid.UUID, tenantId: uuid.UUID | None = None
    ) -> MeetingTranscript | None: ...

    def findForMeeting(
        self, tenantId: uuid.UUID, meetingId: uuid.UUID
    ) -> MeetingTranscript | None: ...

    def listSegments(
        self, tenantId: uuid.UUID, transcriptId: uuid.UUID
    ) -> list[TranscriptSegment]: ...


# ---------------------------------------------------------------------------
# user blocks (§70)
# ---------------------------------------------------------------------------


@runtime_checkable
class UserBlockRepository(Protocol):
    def add(self, block: UserBlock) -> None: ...

    def update(self, block: UserBlock) -> None: ...

    def findActive(
        self,
        tenantId: uuid.UUID,
        blockerId: uuid.UUID,
        blockedUserId: uuid.UUID,
    ) -> UserBlock | None: ...

    def listBlockedUserIds(
        self, tenantId: uuid.UUID, blockerId: uuid.UUID, *, scope: str = ""
    ) -> list[uuid.UUID]: ...

    def listForBlocker(
        self, tenantId: uuid.UUID, blockerId: uuid.UUID
    ) -> list[UserBlock]: ...


# ---------------------------------------------------------------------------
# meeting capability overrides (§30) — per-meeting grant/deny on top of role
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CapabilityOverride:
    meetingId: uuid.UUID
    userId: uuid.UUID
    capability: str
    granted: bool
    tenantId: uuid.UUID | None = None


@runtime_checkable
class MeetingCapabilityRepository(Protocol):
    def setOverride(self, override: CapabilityOverride) -> None: ...

    def overridesForMeeting(
        self, meetingId: uuid.UUID
    ) -> list[CapabilityOverride]: ...

    def find(
        self,
        tenantId: uuid.UUID,
        meetingId: uuid.UUID,
        userId: uuid.UUID,
        capability: str,
    ) -> CapabilityOverride | None: ...


# ---------------------------------------------------------------------------
# search provider port (§54) — SQL ships now; Elasticsearch/OpenSearch later
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SearchResult:
    messageId: uuid.UUID
    conversationId: uuid.UUID
    snippet: str
    createdAt: datetime


@runtime_checkable
class MessageSearchProvider(Protocol):
    def search(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        query: str,
        *,
        conversationIds: list[uuid.UUID] | None = None,
        limit: int = 25,
    ) -> list[SearchResult]: ...

    @property
    def providerKind(self) -> str: ...


# ---------------------------------------------------------------------------
# call provider port (§25) — WebRTC default; Twilio/Agora/Jitsi behind this
# ---------------------------------------------------------------------------


@runtime_checkable
class CallProvider(Protocol):
    """Vendor-neutral media session boundary (§25/§26).

    The domain never calls WebRTC/Twilio/Agora directly. The default adapter
    is a signaling-only WebRTC provider (the SFU/media plane stays external —
    ADR-023); future providers implement this same port without touching the
    domain or application layers.
    """

    def createSession(
        self, *, callId: uuid.UUID, mediaType: str, tenantId: uuid.UUID
    ) -> dict[str, Any]: ...

    def joinSession(
        self, *, sessionRef: str, userId: uuid.UUID
    ) -> dict[str, Any]: ...

    def leaveSession(self, *, sessionRef: str, userId: uuid.UUID) -> None: ...

    def endSession(self, *, sessionRef: str) -> None: ...

    def getSessionStatus(self, *, sessionRef: str) -> str: ...

    @property
    def providerName(self) -> str: ...
