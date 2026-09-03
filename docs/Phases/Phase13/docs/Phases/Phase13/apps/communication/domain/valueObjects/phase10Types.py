"""Communication domain constants added by Phase 10.

Phase 10 (``docs/Phases/Phase10.md``) deepens the Communication platform
that Phase 08 established. These vocabularies are NEW for Phase 10 and live
in a separate module so the Phase 08 set stays untouched and every existing
test stays green:

- meeting granular capabilities / meeting-participant roles (§29/§30);
- transcript + transcript-segment lifecycle (§34/§35);
- message-revision history (§11) and screen-share kinds (§31);
- user blocking for abuse protection (§70);
- communication rate-limit scopes (§68) and search provider kinds (§54).

Plain string constants + validated value objects, framework-free — the
domain must stay independent of Channels/Redis/WebRTC/SQL (§62/§74).
"""

from __future__ import annotations

from apps.sharedKernel.domain.errors import ValidationFailedError
from apps.sharedKernel.domain.valueObjects import ValueObject

# ---------------------------------------------------------------------------
# §29 — meeting participant roles (distinct from conversation roles)
# ---------------------------------------------------------------------------
MEETING_ROLE_HOST = "HOST"
MEETING_ROLE_CO_HOST = "CO_HOST"
MEETING_ROLE_PARTICIPANT = "PARTICIPANT"
MEETING_ROLE_GUEST = "GUEST"
MEETING_PARTICIPANT_ROLES = (
    MEETING_ROLE_HOST,
    MEETING_ROLE_CO_HOST,
    MEETING_ROLE_PARTICIPANT,
    MEETING_ROLE_GUEST,
)

# ---------------------------------------------------------------------------
# §30 — granular meeting capabilities (permission matrix)
# ---------------------------------------------------------------------------
CAP_JOIN = "CAN_JOIN"
CAP_SPEAK = "CAN_SPEAK"
CAP_VIDEO = "CAN_VIDEO"
CAP_SHARE_SCREEN = "CAN_SHARE_SCREEN"
CAP_RECORD = "CAN_RECORD"
CAP_CHAT = "CAN_CHAT"
CAP_INVITE = "CAN_INVITE"
CAP_REMOVE_PARTICIPANT = "CAN_REMOVE_PARTICIPANT"
CAP_END_MEETING = "CAN_END_MEETING"
MEETING_CAPABILITIES = (
    CAP_JOIN,
    CAP_SPEAK,
    CAP_VIDEO,
    CAP_SHARE_SCREEN,
    CAP_RECORD,
    CAP_CHAT,
    CAP_INVITE,
    CAP_REMOVE_PARTICIPANT,
    CAP_END_MEETING,
)

#: Default capability grants per meeting role (§30 matrix). HOST holds every
#: capability; CO_HOST mirrors HOST except ending the meeting; PARTICIPANT is
#: a speaking/chatting attendee; GUEST is a restricted observer.
DEFAULT_MEETING_CAPABILITIES: dict[str, frozenset[str]] = {
    MEETING_ROLE_HOST: frozenset(MEETING_CAPABILITIES),
    MEETING_ROLE_CO_HOST: frozenset(
        cap for cap in MEETING_CAPABILITIES if cap != CAP_END_MEETING
    ),
    MEETING_ROLE_PARTICIPANT: frozenset(
        {
            CAP_JOIN,
            CAP_SPEAK,
            CAP_VIDEO,
            CAP_SHARE_SCREEN,
            CAP_CHAT,
        }
    ),
    MEETING_ROLE_GUEST: frozenset({CAP_JOIN, CAP_CHAT}),
}

# ---------------------------------------------------------------------------
# §31 — screen sharing kinds
# ---------------------------------------------------------------------------
SCREEN_SHARE_SCREEN = "SCREEN"
SCREEN_SHARE_WINDOW = "WINDOW"
SCREEN_SHARE_TAB = "TAB"
SCREEN_SHARE_KINDS = (
    SCREEN_SHARE_SCREEN,
    SCREEN_SHARE_WINDOW,
    SCREEN_SHARE_TAB,
)

# ---------------------------------------------------------------------------
# §34 — transcript lifecycle
# ---------------------------------------------------------------------------
TRANSCRIPT_PENDING = "PENDING"
TRANSCRIPT_PROCESSING = "PROCESSING"
TRANSCRIPT_READY = "READY"
TRANSCRIPT_FAILED = "FAILED"
TRANSCRIPT_STATES = (
    TRANSCRIPT_PENDING,
    TRANSCRIPT_PROCESSING,
    TRANSCRIPT_READY,
    TRANSCRIPT_FAILED,
)
TRANSCRIPT_TRANSITIONS: dict[str, tuple[str, ...]] = {
    TRANSCRIPT_PENDING: (TRANSCRIPT_PROCESSING, TRANSCRIPT_FAILED),
    TRANSCRIPT_PROCESSING: (TRANSCRIPT_READY, TRANSCRIPT_FAILED),
    TRANSCRIPT_READY: (),
    TRANSCRIPT_FAILED: (),
}

#: Confidence floor for a transcript segment (0..1).
MIN_SEGMENT_CONFIDENCE = 0.0
MAX_SEGMENT_CONFIDENCE = 1.0

# ---------------------------------------------------------------------------
# §70 — user blocks (abuse protection)
# ---------------------------------------------------------------------------
BLOCK_DIRECT_MESSAGE = "DIRECT_MESSAGE"
BLOCK_CALL = "CALL"
BLOCK_MEETING_INVITATION = "MEETING_INVITATION"
BLOCK_SCOPES = (
    BLOCK_DIRECT_MESSAGE,
    BLOCK_CALL,
    BLOCK_MEETING_INVITATION,
)
BLOCK_ACTIVE = "ACTIVE"
BLOCK_REMOVED = "REMOVED"

# ---------------------------------------------------------------------------
# §68 — communication rate-limit scopes (extension of the kernel limiter)
# ---------------------------------------------------------------------------
RL_SEND_MESSAGE = "communication:sendMessage"
RL_CREATE_CONVERSATION = "communication:createConversation"
RL_CALL_START = "communication:callStart"
RL_MEETING_CREATE = "communication:meetingCreate"
RL_WS_CONNECTION = "communication:wsConnection"
RL_PRESENCE_UPDATE = "communication:presenceUpdate"
COMMUNICATION_RATE_LIMIT_SCOPES = (
    RL_SEND_MESSAGE,
    RL_CREATE_CONVERSATION,
    RL_CALL_START,
    RL_MEETING_CREATE,
    RL_WS_CONNECTION,
    RL_PRESENCE_UPDATE,
)
#: Default fixed-window ceilings (requests per window); overridable via
#: settings.COMMUNICATION_RATE_LIMITS. Presence is intentionally generous —
#: heartbeats are frequent (§68).
DEFAULT_RATE_LIMITS: dict[str, tuple[int, int]] = {
    RL_SEND_MESSAGE: (30, 60),         # 30 messages / 60 s
    RL_CREATE_CONVERSATION: (20, 300),  # 20 conversations / 5 min
    RL_CALL_START: (10, 60),
    RL_MEETING_CREATE: (20, 300),
    RL_WS_CONNECTION: (30, 60),
    RL_PRESENCE_UPDATE: (120, 60),
}

# ---------------------------------------------------------------------------
# §54 — search provider kinds (port is provider-agnostic; SQL ships now)
# ---------------------------------------------------------------------------
SEARCH_PROVIDER_SQL = "SQL"
SEARCH_PROVIDER_FULLTEXT = "FULLTEXT"
SEARCH_PROVIDER_ELASTICSEARCH = "ELASTICSEARCH"
SEARCH_PROVIDER_OPENSEARCH = "OPENSEARCH"
SEARCH_PROVIDERS = (
    SEARCH_PROVIDER_SQL,
    SEARCH_PROVIDER_FULLTEXT,
    SEARCH_PROVIDER_ELASTICSEARCH,
    SEARCH_PROVIDER_OPENSEARCH,
)


class MeetingParticipantRole(ValueObject):
    """Validated meeting-participant role (§29)."""

    def __init__(self, value: str) -> None:
        if value not in MEETING_PARTICIPANT_ROLES:
            raise ValidationFailedError(
                "Unknown meeting participant role.",
                fieldErrors={"meetingRole": value},
            )
        self.value = value

    def __str__(self) -> str:
        return self.value


class MeetingCapability(ValueObject):
    """Validated granular meeting capability (§30)."""

    def __init__(self, value: str) -> None:
        if value not in MEETING_CAPABILITIES:
            raise ValidationFailedError(
                "Unknown meeting capability.",
                fieldErrors={"capability": value},
            )
        self.value = value

    def __str__(self) -> str:
        return self.value


class TranscriptStatus(ValueObject):
    """Validated transcript lifecycle state (§34)."""

    def __init__(self, value: str) -> None:
        if value not in TRANSCRIPT_STATES:
            raise ValidationFailedError(
                "Unknown transcript status.",
                fieldErrors={"transcriptStatus": value},
            )
        self.value = value

    def __str__(self) -> str:
        return self.value


class ScreenShareKind(ValueObject):
    """Validated screen-share content kind (§31)."""

    def __init__(self, value: str) -> None:
        if value not in SCREEN_SHARE_KINDS:
            raise ValidationFailedError(
                "Unknown screen share kind.",
                fieldErrors={"screenShareKind": value},
            )
        self.value = value

    def __str__(self) -> str:
        return self.value


class BlockScope(ValueObject):
    """Validated user-block scope (§70)."""

    def __init__(self, value: str) -> None:
        if value not in BLOCK_SCOPES:
            raise ValidationFailedError(
                "Unknown block scope.", fieldErrors={"scope": value}
            )
        self.value = value

    def __str__(self) -> str:
        return self.value
