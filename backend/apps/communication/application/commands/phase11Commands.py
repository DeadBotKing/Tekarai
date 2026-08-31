"""Phase 11 application commands (input contracts)."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.sharedKernel.application.messaging import Command

# -- CommunicationPolicy (§70) ----------------------------------------------


@dataclass(frozen=True)
class UpdateCommunicationPolicyCommand(Command):
    changes: dict = field(default_factory=dict)


# -- MessageDelivery (§19) ---------------------------------------------------


@dataclass(frozen=True)
class RecordDeliveryCommand(Command):
    messageId: str
    recipientId: str
    state: str = "DELIVERED"  # DELIVERED | FAILED
    failedReason: str = ""


# -- MeetingRoom / MeetingSession (§34) --------------------------------------


@dataclass(frozen=True)
class OpenMeetingRoomCommand(Command):
    meetingId: str
    capacity: int = 0


@dataclass(frozen=True)
class StartMeetingSessionCommand(Command):
    meetingId: str


@dataclass(frozen=True)
class EndMeetingSessionCommand(Command):
    sessionId: str


# -- Screen share (§35) ------------------------------------------------------


@dataclass(frozen=True)
class StartScreenShareCommand(Command):
    meetingId: str
    shareKind: str = "SCREEN"  # SCREEN | WINDOW | TAB
    sessionId: str = ""


@dataclass(frozen=True)
class StopScreenShareCommand(Command):
    shareId: str


# -- MeetingSummary (§38) ----------------------------------------------------


@dataclass(frozen=True)
class GenerateMeetingSummaryCommand(Command):
    meetingId: str
    transcriptId: str = ""
    summary: str = ""
    keyPoints: list = field(default_factory=list)
    decisions: list = field(default_factory=list)
    actionItems: list = field(default_factory=list)
    risks: list = field(default_factory=list)
    topics: list = field(default_factory=list)
    confidence: float = 0.0
    modelReference: str = "tekarai.ai.summary.v1"


@dataclass(frozen=True)
class ReviewMeetingSummaryCommand(Command):
    summaryId: str
    decision: str  # APPROVE | REJECT


# -- ActionItemCandidate (§39) -----------------------------------------------


@dataclass(frozen=True)
class ReviewActionItemCommand(Command):
    itemId: str
    decision: str  # APPROVE | REJECT
    note: str = ""


@dataclass(frozen=True)
class DispatchActionItemCommand(Command):
    itemId: str
    taskRef: str


# -- OfficialMessage (§40/§41) -----------------------------------------------


@dataclass(frozen=True)
class CreateOfficialMessageCommand(Command):
    kind: str  # ANNOUNCEMENT | DIRECTIVE | CIRCULAR | NOTICE
    subject: str
    body: str = ""
    recipientIds: list = field(default_factory=list)


@dataclass(frozen=True)
class TransitionOfficialMessageCommand(Command):
    officialId: str
    action: str  # review | approve | return | publish | deliver


@dataclass(frozen=True)
class AcknowledgeOfficialMessageCommand(Command):
    officialId: str


# -- MessageReport (§43/§44) -------------------------------------------------


@dataclass(frozen=True)
class ReportMessageCommand(Command):
    messageId: str
    reason: str  # SPAM | ABUSE | ...
    description: str = ""


@dataclass(frozen=True)
class ReviewMessageReportCommand(Command):
    reportId: str
    decision: str  # RESOLVE | DISMISS
    note: str = ""


# -- LegalHold (§69) ---------------------------------------------------------


@dataclass(frozen=True)
class PlaceLegalHoldCommand(Command):
    scope: str  # CONVERSATION | MEETING | RECORDING | TRANSCRIPT | USER
    targetId: str
    reason: str = ""


@dataclass(frozen=True)
class ReleaseLegalHoldCommand(Command):
    holdId: str
