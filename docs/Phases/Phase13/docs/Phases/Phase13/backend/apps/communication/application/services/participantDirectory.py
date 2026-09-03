"""Communication participant directory — public cross-context read contract.

Phase 09 notification-platform read-side integration: recipient specs
that reference conversations/meetings/calls/channels resolve to user ids
through these functions only (RULE E/F — application is the public
surface; the ORM stays private to communication).
"""

from __future__ import annotations

import uuid


def conversationMemberIds(conversationIds: list[uuid.UUID]) -> list[uuid.UUID]:
    from apps.communication.infrastructure.models import (
        ConversationParticipantModel,
    )

    if not conversationIds:
        return []
    rows = ConversationParticipantModel.objects.filter(
        conversationId__in=conversationIds
    ).values_list("userId", flat=True)
    return list(dict.fromkeys(rows))


def meetingInviteeIds(meetingIds: list[uuid.UUID]) -> list[uuid.UUID]:
    from apps.communication.infrastructure.models import MeetingParticipantModel

    if not meetingIds:
        return []
    rows = MeetingParticipantModel.objects.filter(meetingId__in=meetingIds).values_list(
        "userId", flat=True
    )
    return list(dict.fromkeys(rows))


def callParticipantIds(callIds: list[uuid.UUID]) -> list[uuid.UUID]:
    from apps.communication.infrastructure.models import CallParticipantModel

    if not callIds:
        return []
    rows = CallParticipantModel.objects.filter(callId__in=callIds).values_list(
        "userId", flat=True
    )
    return list(dict.fromkeys(rows))


def channelMemberIds(
    tenantId: uuid.UUID, conversationIds: list[uuid.UUID]
) -> list[uuid.UUID]:
    from apps.communication.infrastructure.models import ChannelMembershipModel

    if not conversationIds:
        return []
    rows = ChannelMembershipModel.objects.filter(
        tenantId=tenantId,
        conversationId__in=conversationIds,
        leftAt__isnull=True,
    ).values_list("userId", flat=True)
    return list(dict.fromkeys(rows))
