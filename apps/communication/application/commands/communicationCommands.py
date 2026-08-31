"""Communication commands (Phase 08 §35 service inventory)."""

from __future__ import annotations

from dataclasses import dataclass, field

from apps.sharedKernel.application.messaging import Command


# -- conversations (§3.1/§4/§5/§6) ----------------------------------------------


@dataclass(frozen=True)
class CreateDirectConversationCommand(Command):
    peerUserId: str


@dataclass(frozen=True)
class CreateGroupConversationCommand(Command):
    name: str
    memberIds: list[str] = field(default_factory=list)
    description: str = ""


@dataclass(frozen=True)
class CreateChannelCommand(Command):
    name: str
    code: str = ""
    description: str = ""
    topic: str = ""
    visibility: str = "PUBLIC"  # PUBLIC | PRIVATE | RESTRICTED (§4)
    isArchived: bool = False


@dataclass(frozen=True)
class UpdateConversationCommand(Command):
    conversationId: str
    name: str = ""
    description: str = ""
    topic: str = ""


@dataclass(frozen=True)
class ArchiveConversationCommand(Command):
    conversationId: str


@dataclass(frozen=True)
class AddParticipantCommand(Command):
    conversationId: str
    userId: str
    role: str = "MEMBER"


@dataclass(frozen=True)
class RemoveParticipantCommand(Command):
    conversationId: str
    userId: str


@dataclass(frozen=True)
class UpdateParticipantPreferencesCommand(Command):
    conversationId: str
    isMuted: bool | None = None
    notificationLevel: str = ""


@dataclass(frozen=True)
class JoinChannelCommand(Command):
    conversationId: str


@dataclass(frozen=True)
class LeaveConversationCommand(Command):
    conversationId: str


@dataclass(frozen=True)
class ChangeParticipantRoleCommand(Command):
    conversationId: str
    userId: str
    role: str


# -- messages (§3.3–§3.8, §23/§24, §33/§34) ----------------------------------------


@dataclass(frozen=True)
class SendMessageCommand(Command):
    conversationId: str
    body: str
    messageType: str = "TEXT"
    replyToId: str = ""
    clientRequestId: str = ""  # §24 idempotency for offline retries
    attachments: list[dict] = field(default_factory=list)  # §3.4 metadata refs


@dataclass(frozen=True)
class EditMessageCommand(Command):
    messageId: str
    body: str


@dataclass(frozen=True)
class DeleteMessageCommand(Command):
    messageId: str


@dataclass(frozen=True)
class ReactToMessageCommand(Command):
    messageId: str
    reaction: str


@dataclass(frozen=True)
class RemoveReactionCommand(Command):
    messageId: str
    reaction: str


@dataclass(frozen=True)
class MarkConversationReadCommand(Command):
    conversationId: str
    uptoMessageId: str


@dataclass(frozen=True)
class PinMessageCommand(Command):
    conversationId: str
    messageId: str


@dataclass(frozen=True)
class UnpinMessageCommand(Command):
    conversationId: str
    messageId: str


# -- calls (§10/§11) -----------------------------------------------------------------


@dataclass(frozen=True)
class StartCallCommand(Command):
    mediaType: str  # AUDIO | VIDEO | SCREEN_SHARE (§14)
    conversationId: str = ""
    meetingId: str = ""
    clientRequestId: str = ""  # §24


@dataclass(frozen=True)
class AcceptCallCommand(Command):
    callId: str


@dataclass(frozen=True)
class RejectCallCommand(Command):
    callId: str


@dataclass(frozen=True)
class EndCallCommand(Command):
    callId: str


@dataclass(frozen=True)
class RelaySignalCommand(Command):
    """§11 — versioned signaling relay (communication.signal.v1)."""

    envelope: dict  # validated envelope {version, kind, callId, payload}
    targetUserId: str = ""  # empty → broadcast to the call group


# -- meetings (§13) --------------------------------------------------------------------


@dataclass(frozen=True)
class CreateMeetingCommand(Command):
    title: str
    conversationId: str
    description: str = ""
    scheduledStart: str = ""
    scheduledEnd: str = ""
    inviteeIds: list[str] = field(default_factory=list)
    clientRequestId: str = ""  # §24


@dataclass(frozen=True)
class RsvpMeetingCommand(Command):
    meetingId: str
    accepted: bool


@dataclass(frozen=True)
class StartMeetingCommand(Command):
    meetingId: str


@dataclass(frozen=True)
class JoinMeetingCommand(Command):
    meetingId: str


@dataclass(frozen=True)
class LeaveMeetingCommand(Command):
    meetingId: str


@dataclass(frozen=True)
class EndMeetingCommand(Command):
    meetingId: str


@dataclass(frozen=True)
class CancelMeetingCommand(Command):
    meetingId: str


# -- recordings (§15) --------------------------------------------------------------------


@dataclass(frozen=True)
class StartRecordingCommand(Command):
    meetingId: str


@dataclass(frozen=True)
class StopRecordingCommand(Command):
    recordingId: str


@dataclass(frozen=True)
class PublishRecordingCommand(Command):
    """PROCESSING → AVAILABLE (or FAILED) — called by the media pipeline."""

    recordingId: str
    storageRef: str = ""
    failed: bool = False
    reason: str = ""


# -- official letters (§16) -----------------------------------------------------------------


@dataclass(frozen=True)
class CreateLetterCommand(Command):
    recipientId: str
    subject: str
    body: str = ""
    recipientOrganization: str = ""
    recipientUnit: str = ""


@dataclass(frozen=True)
class SubmitLetterCommand(Command):
    letterId: str
    action: str = "submit"


@dataclass(frozen=True)
class ApproveLetterCommand(Command):
    letterId: str
    action: str = "approve"


@dataclass(frozen=True)
class SignLetterCommand(Command):
    letterId: str
    action: str = "sign"


@dataclass(frozen=True)
class DispatchLetterCommand(Command):
    letterId: str
    action: str = "dispatch"


@dataclass(frozen=True)
class ReceiveLetterCommand(Command):
    letterId: str
    action: str = "receive"


# -- presence (§7) ----------------------------------------------------------------------------


@dataclass(frozen=True)
class UpdatePresenceCommand(Command):
    status: str
