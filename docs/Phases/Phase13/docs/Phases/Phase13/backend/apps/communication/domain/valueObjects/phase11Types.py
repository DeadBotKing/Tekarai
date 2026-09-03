"""Phase 11 value objects — the Enterprise Communication extension.

Phase 11 builds on the Phase 08/10 platform and adds the governance/moderation,
meeting-room/session, screen-share, AI-governed summary/action-item, official
communication and delivery/receipt vocabulary. Everything here is plain Python
(no Django / Redis / ORM) so the domain stays framework-free (§54/§79).
"""

from __future__ import annotations

from dataclasses import dataclass

from apps.communication.domain.valueObjects.phase10Types import (
    CAP_CHAT,
    CAP_JOIN,
    CAP_SHARE_SCREEN,
    CAP_SPEAK,
    CAP_VIDEO,
    MEETING_ROLE_CO_HOST,
    MEETING_ROLE_GUEST,
    MEETING_ROLE_HOST,
    MEETING_ROLE_PARTICIPANT,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

# ---------------------------------------------------------------------------
# §6 — conversation member role: READ_ONLY is the new restricted listener.
# (The existing OWNER/ADMIN/MODERATOR/MEMBER/GUEST live in communicationTypes;
# READ_ONLY is added here without mutating that tuple's ordering assumptions.)
# ---------------------------------------------------------------------------
PARTICIPANT_READ_ONLY = "READ_ONLY"
CONVERSATION_MEMBER_ROLES = (
    "OWNER",
    "ADMIN",
    "MODERATOR",
    "MEMBER",
    "READ_ONLY",
    "GUEST",
)

# ---------------------------------------------------------------------------
# §9 — channel kinds: ANNOUNCEMENT is a one-to-many official channel.
# ---------------------------------------------------------------------------
CHANNEL_ANNOUNCEMENT = "ANNOUNCEMENT"
CHANNEL_KINDS = ("PUBLIC", "PRIVATE", "RESTRICTED", CHANNEL_ANNOUNCEMENT)

# ---------------------------------------------------------------------------
# §11 — message kinds added in Phase 11: VOICE (audio note) joins the set.
# (DOCUMENT/CALL_EVENT/MEETING_EVENT were added in Phase 10.)
# ---------------------------------------------------------------------------
MESSAGE_VOICE = "VOICE"

# ---------------------------------------------------------------------------
# §19 — delivery receipt state machine.
# ---------------------------------------------------------------------------
DELIVERY_SENT = "SENT"
DELIVERY_DELIVERED = "DELIVERED"
DELIVERY_FAILED = "FAILED"
DELIVERY_STATES = (DELIVERY_SENT, DELIVERY_DELIVERED, DELIVERY_FAILED)
DELIVERY_TRANSITIONS: dict[str, tuple[str, ...]] = {
    DELIVERY_SENT: (DELIVERY_DELIVERED, DELIVERY_FAILED),
    DELIVERY_DELIVERED: (),
    DELIVERY_FAILED: (DELIVERY_SENT,),  # resend may re-queue
}

# ---------------------------------------------------------------------------
# §31 — meeting definition type.
# ---------------------------------------------------------------------------
MEETING_TYPE_INSTANT = "INSTANT"
MEETING_TYPE_SCHEDULED = "SCHEDULED"
MEETING_TYPE_RECURRING = "RECURRING"
MEETING_TYPES = (
    MEETING_TYPE_INSTANT,
    MEETING_TYPE_SCHEDULED,
    MEETING_TYPE_RECURRING,
)

# ---------------------------------------------------------------------------
# §32/§34 — meeting session (a live room instance) status.
# ---------------------------------------------------------------------------
SESSION_WAITING = "WAITING"
SESSION_LIVE = "LIVE"
SESSION_ENDED = "ENDED"
SESSION_FAILED = "FAILED"
MEETING_SESSION_STATES = (SESSION_WAITING, SESSION_LIVE, SESSION_ENDED, SESSION_FAILED)

# ---------------------------------------------------------------------------
# §33 — meeting participant roles: PRESENTER + OBSERVER join the Phase 10 set.
# ---------------------------------------------------------------------------
MEETING_ROLE_PRESENTER = "PRESENTER"
MEETING_ROLE_OBSERVER = "OBSERVER"
MEETING_PARTICIPANT_ROLES_V11 = (
    MEETING_ROLE_HOST,
    MEETING_ROLE_CO_HOST,
    MEETING_ROLE_PRESENTER,
    MEETING_ROLE_PARTICIPANT,
    MEETING_ROLE_OBSERVER,
    MEETING_ROLE_GUEST,
)

#: Attendance lifecycle (§33 attendanceStatus).
ATTENDANCE_INVITED = "INVITED"
ATTENDANCE_ACCEPTED = "ACCEPTED"
ATTENDANCE_DECLINED = "DECLINED"
ATTENDANCE_JOINED = "JOINED"
ATTENDANCE_LEFT = "LEFT"
ATTENDANCE_NO_SHOW = "NO_SHOW"
ATTENDANCE_STATES = (
    ATTENDANCE_INVITED,
    ATTENDANCE_ACCEPTED,
    ATTENDANCE_DECLINED,
    ATTENDANCE_JOINED,
    ATTENDANCE_LEFT,
    ATTENDANCE_NO_SHOW,
)

# ---------------------------------------------------------------------------
# §35 — screen share session state.
# ---------------------------------------------------------------------------
SCREEN_SHARE_ACTIVE = "ACTIVE"
SCREEN_SHARE_ENDED = "ENDED"
SCREEN_SHARE_STATES = (SCREEN_SHARE_ACTIVE, SCREEN_SHARE_ENDED)

# ---------------------------------------------------------------------------
# §40/§41 — official message lifecycle.
# ---------------------------------------------------------------------------
OFFICIAL_DRAFT = "DRAFT"
OFFICIAL_REVIEW = "REVIEW"
OFFICIAL_APPROVED = "APPROVED"
OFFICIAL_PUBLISHED = "PUBLISHED"
OFFICIAL_DELIVERED = "DELIVERED"
OFFICIAL_ACKNOWLEDGED = "ACKNOWLEDGED"
OFFICIAL_STATES = (
    OFFICIAL_DRAFT,
    OFFICIAL_REVIEW,
    OFFICIAL_APPROVED,
    OFFICIAL_PUBLISHED,
    OFFICIAL_DELIVERED,
    OFFICIAL_ACKNOWLEDGED,
)
OFFICIAL_TRANSITIONS: dict[str, tuple[str, ...]] = {
    OFFICIAL_DRAFT: (OFFICIAL_REVIEW,),
    OFFICIAL_REVIEW: (OFFICIAL_APPROVED, OFFICIAL_DRAFT),
    OFFICIAL_APPROVED: (OFFICIAL_PUBLISHED,),
    OFFICIAL_PUBLISHED: (OFFICIAL_DELIVERED,),
    OFFICIAL_DELIVERED: (OFFICIAL_ACKNOWLEDGED,),
    OFFICIAL_ACKNOWLEDGED: (),
}
#: kind of formal communication (§40).
OFFICIAL_KIND_ANNOUNCEMENT = "ANNOUNCEMENT"
OFFICIAL_KIND_DIRECTIVE = "DIRECTIVE"
OFFICIAL_KIND_CIRCULAR = "CIRCULAR"
OFFICIAL_KIND_NOTICE = "NOTICE"
OFFICIAL_KINDS = (
    OFFICIAL_KIND_ANNOUNCEMENT,
    OFFICIAL_KIND_DIRECTIVE,
    OFFICIAL_KIND_CIRCULAR,
    OFFICIAL_KIND_NOTICE,
)

# ---------------------------------------------------------------------------
# §44 — message report (moderation) status.
# ---------------------------------------------------------------------------
REPORT_OPEN = "OPEN"
REPORT_UNDER_REVIEW = "UNDER_REVIEW"
REPORT_RESOLVED = "RESOLVED"
REPORT_DISMISSED = "DISMISSED"
REPORT_STATES = (REPORT_OPEN, REPORT_UNDER_REVIEW, REPORT_RESOLVED, REPORT_DISMISSED)
REPORT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    REPORT_OPEN: (REPORT_UNDER_REVIEW, REPORT_DISMISSED),
    REPORT_UNDER_REVIEW: (REPORT_RESOLVED, REPORT_DISMISSED),
    REPORT_RESOLVED: (),
    REPORT_DISMISSED: (),
}
#: Standard report reasons (extensible — free text reason is also stored).
REPORT_REASONS = ("SPAM", "ABUSE", "HARASSMENT", "INAPPROPRIATE", "MISINFORMATION", "OTHER")

# ---------------------------------------------------------------------------
# §70 — CommunicationPolicy defaults. Never hard-code limits at call sites;
# these are the FALLBACKS used when a tenant has no policy row yet (§46/§79).
# ---------------------------------------------------------------------------
DEFAULT_MESSAGE_RETENTION_DAYS = 365 * 7  # 7 years
DEFAULT_RECORDING_RETENTION_DAYS = 365 * 2  # 2 years
DEFAULT_TRANSCRIPT_RETENTION_DAYS = 365 * 7
DEFAULT_PRESENCE_RETENTION_DAYS = 30
DEFAULT_MAX_ATTACHMENT_SIZE = 25 * 1024 * 1024  # 25 MB
DEFAULT_MAX_MESSAGE_LENGTH = 8000
DEFAULT_MAX_GROUP_MEMBERS = 5000
DEFAULT_MAX_MEETING_PARTICIPANTS = 500
DEFAULT_ALLOWED_FILE_TYPES = (
    "image/png",
    "image/jpeg",
    "application/pdf",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    "text/plain",
)
DEFAULT_AUDIT_RETENTION_DAYS = 365 * 10  # 10 years


@dataclass(frozen=True)
class PolicyDefaults:
    """Immutable tenant policy (§70). A ``CommunicationPolicy`` row maps to one
    of these; missing fields fall back to the module defaults."""

    messageRetentionDays: int = DEFAULT_MESSAGE_RETENTION_DAYS
    recordingRetentionDays: int = DEFAULT_RECORDING_RETENTION_DAYS
    transcriptRetentionDays: int = DEFAULT_TRANSCRIPT_RETENTION_DAYS
    presenceRetentionDays: int = DEFAULT_PRESENCE_RETENTION_DAYS
    auditRetentionDays: int = DEFAULT_AUDIT_RETENTION_DAYS
    maxAttachmentSize: int = DEFAULT_MAX_ATTACHMENT_SIZE
    maxMessageLength: int = DEFAULT_MAX_MESSAGE_LENGTH
    maxGroupMembers: int = DEFAULT_MAX_GROUP_MEMBERS
    maxMeetingParticipants: int = DEFAULT_MAX_MEETING_PARTICIPANTS
    allowedFileTypes: tuple[str, ...] = DEFAULT_ALLOWED_FILE_TYPES
    allowExternalUsers: bool = False
    allowRecording: bool = True
    allowScreenSharing: bool = True
    allowMessageEdit: bool = True
    allowMessageDelete: bool = True


# ---------------------------------------------------------------------------
# §76 — AI governance markers shared by MeetingSummary / action items.
# ---------------------------------------------------------------------------
AI_REVIEW_PENDING = "PENDING"
AI_REVIEW_APPROVED = "APPROVED"
AI_REVIEW_REJECTED = "REJECTED"
AI_REVIEW_STATES = (AI_REVIEW_PENDING, AI_REVIEW_APPROVED, AI_REVIEW_REJECTED)

#: Action item lifecycle (§39) — candidate → human approval → dispatched.
ACTION_CANDIDATE = "CANDIDATE"
ACTION_APPROVED = "APPROVED"
ACTION_REJECTED = "REJECTED"
ACTION_DISPATCHED = "DISPATCHED"
ACTION_STATES = (ACTION_CANDIDATE, ACTION_APPROVED, ACTION_REJECTED, ACTION_DISPATCHED)
ACTION_TRANSITIONS: dict[str, tuple[str, ...]] = {
    ACTION_CANDIDATE: (ACTION_APPROVED, ACTION_REJECTED),
    ACTION_APPROVED: (ACTION_DISPATCHED,),
    ACTION_REJECTED: (),
    ACTION_DISPATCHED: (),
}

# ---------------------------------------------------------------------------
# §69 — legal hold.
# ---------------------------------------------------------------------------
LEGAL_HOLD_ACTIVE = "ACTIVE"
LEGAL_HOLD_RELEASED = "RELEASED"
LEGAL_HOLD_STATES = (LEGAL_HOLD_ACTIVE, LEGAL_HOLD_RELEASED)


# ---------------------------------------------------------------------------
# capability matrix for the extended meeting roles (§33)
# ---------------------------------------------------------------------------
#: OBSERVER = read-only attendee (may watch/listen, may not speak/chat).
#: PRESENTER may present screen + speak/video/chat but cannot moderate.
EXTENDED_ROLE_CAPABILITIES: dict[str, frozenset[str]] = {
    MEETING_ROLE_OBSERVER: frozenset(
        {CAP_JOIN}
    ),
    MEETING_ROLE_PRESENTER: frozenset(
        {CAP_JOIN, CAP_SPEAK, CAP_VIDEO, CAP_SHARE_SCREEN, CAP_CHAT}
    ),
}


def roleCapabilitiesV11(role: str) -> frozenset[str]:
    """Return the capability set for a meeting role, including the Phase 11
    PRESENTER/OBSERVER roles; unknown roles get an empty set."""
    from apps.communication.domain.services.meetingPermissions import capabilitiesForRole

    extended = EXTENDED_ROLE_CAPABILITIES.get(role)
    if extended is not None:
        return extended
    base = capabilitiesForRole(role)
    return base


def validateOneOf(value: str, allowed: tuple[str, ...], *, field: str) -> str:
    """Small domain guard reused by Phase 11 entities (raises ValidationFailed)."""
    if value not in allowed:
        raise ValidationFailedError(
            f"Invalid {field}.", fieldErrors={field: value}
        )
    return value
