"""Phase 10 commands (docs/Phases/Phase10.md).

Frozen command messages for the new capabilities: message revision history,
meeting transcripts, granular meeting permissions, user blocks, and the
provider-agnostic call session. Commands carry data only — no behaviour.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.sharedKernel.application.messaging import Command

# -- message revisions (§11) -------------------------------------------------


@dataclass(frozen=True)
class ListMessageRevisionsQuery(Command):
    messageId: str


# -- transcripts (§34/§35) ---------------------------------------------------


@dataclass(frozen=True)
class RequestTranscriptCommand(Command):
    meetingId: str
    language: str = "en-US"


@dataclass(frozen=True)
class CompleteTranscriptCommand(Command):
    transcriptId: str
    contentReference: str
    segments: list[TranscriptSegmentInput] = field(default_factory=list)


@dataclass(frozen=True)
class TranscriptSegmentInput:
    speakerId: str = ""
    startTimeSeconds: float = 0.0
    endTimeSeconds: float = 0.0
    text: str = ""
    confidence: float = 1.0


@dataclass(frozen=True)
class GetTranscriptQuery(Command):
    meetingId: str


# -- granular meeting permissions (§30) --------------------------------------


@dataclass(frozen=True)
class SetMeetingCapabilityCommand(Command):
    meetingId: str
    userId: str
    capability: str  # CAN_SPEAK / CAN_RECORD / ... (§30)
    granted: bool


@dataclass(frozen=True)
class CheckMeetingCapabilityQuery(Command):
    meetingId: str
    userId: str
    capability: str


# -- user blocks (§70) -------------------------------------------------------


@dataclass(frozen=True)
class BlockUserCommand(Command):
    blockedUserId: str
    scopes: list[str] = field(default_factory=list)  # DIRECT_MESSAGE/CALL/MEETING_INVITATION
    reason: str = ""


@dataclass(frozen=True)
class UnblockUserCommand(Command):
    blockedUserId: str


@dataclass(frozen=True)
class ListBlocksQuery(Command):
    pass


# -- provider-agnostic call session (§25) ------------------------------------


@dataclass(frozen=True)
class CreateCallSessionCommand(Command):
    callId: str
    mediaType: str = "AUDIO"


@dataclass(frozen=True)
class JoinCallSessionCommand(Command):
    callId: str
