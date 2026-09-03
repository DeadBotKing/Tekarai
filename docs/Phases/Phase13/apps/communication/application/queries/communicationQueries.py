"""Communication queries (Phase 08 §30 REST responsibilities)."""

from __future__ import annotations

from dataclasses import dataclass

from apps.sharedKernel.application.messaging import Query


@dataclass(frozen=True)
class ListConversationsQuery(Query):
    includeArchived: bool = False


@dataclass(frozen=True)
class GetConversationQuery(Query):
    conversationId: str


@dataclass(frozen=True)
class ListParticipantsQuery(Query):
    conversationId: str


@dataclass(frozen=True)
class ListMessagesQuery(Query):
    conversationId: str
    beforeId: str = ""
    limit: int = 50
    threadRootId: str = ""


@dataclass(frozen=True)
class SearchMessagesQuery(Query):
    query: str
    limit: int = 25


@dataclass(frozen=True)
class ListPinsQuery(Query):
    conversationId: str


@dataclass(frozen=True)
class ListMeetingsQuery(Query):
    conversationId: str = ""


@dataclass(frozen=True)
class GetMeetingQuery(Query):
    meetingId: str


@dataclass(frozen=True)
class GetCallQuery(Query):
    callId: str


@dataclass(frozen=True)
class ListRecordingsQuery(Query):
    meetingId: str


@dataclass(frozen=True)
class ListLettersQuery(Query):
    status: str = ""
    limit: int = 50


@dataclass(frozen=True)
class PresenceQuery(Query):
    userIds: str = ""  # comma-separated


@dataclass(frozen=True)
class GenerateMeetingSummaryQuery(Query):
    """§21 — ask the AI assistant (through ports) for a meeting summary."""

    meetingId: str
