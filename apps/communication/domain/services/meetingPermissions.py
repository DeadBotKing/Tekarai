"""Meeting permission domain service (Phase 10 §29/§30).

A pure, framework-free policy that maps a meeting-participant role to the set
of granular capabilities (CAN_JOIN, CAN_SPEAK, …, CAN_END_MEETING) and answers
authorization questions. Meeting organizers always hold HOST-equivalent rights
even before a participant row exists (the inviter/scheduler).

This deliberately lives in the DOMAIN layer (§46 ConversationPermissionService
/ MeetingPermissionService): no Django, no HTTP, no ORM — just rules.
"""

from __future__ import annotations

import uuid

from apps.communication.domain.valueObjects.phase10Types import (
    CAP_END_MEETING,
    CAP_RECORD,
    CAP_REMOVE_PARTICIPANT,
    DEFAULT_MEETING_CAPABILITIES,
    MEETING_CAPABILITIES,
    MEETING_PARTICIPANT_ROLES,
    MEETING_ROLE_CO_HOST,
    MEETING_ROLE_GUEST,
    MEETING_ROLE_HOST,
    MEETING_ROLE_PARTICIPANT,
)
from apps.sharedKernel.domain.errors import BusinessRuleViolationError


def capabilitiesForRole(role: str) -> frozenset[str]:
    """Return the immutable capability set granted to a meeting role (§30)."""
    if role not in MEETING_PARTICIPANT_ROLES:
        return frozenset()
    return DEFAULT_MEETING_CAPABILITIES[role]


def roleForUser(
    userId: uuid.UUID,
    organizerId: uuid.UUID,
    *,
    participantRole: str = "",
    isInvited: bool = False,
) -> str:
    """Resolve a user's effective meeting role.

    The organizer is always HOST. An invited/joined participant uses the role
    recorded on their participant row. Anyone else who is admitted defaults to
    GUEST (most restricted).
    """
    if userId == organizerId:
        return MEETING_ROLE_HOST
    if participantRole in MEETING_PARTICIPANT_ROLES:
        return participantRole
    if isInvited:
        return MEETING_ROLE_PARTICIPANT
    return MEETING_ROLE_GUEST


def can(
    capability: str,
    *,
    userId: uuid.UUID,
    organizerId: uuid.UUID,
    participantRole: str = "",
    isInvited: bool = False,
    meetingIsLive: bool = False,
) -> bool:
    """Authorize one granular capability for a user (§30).

    Extra invariants beyond the static role matrix:
    - CAN_JOIN is always granted to a known participant/host (the join
      use-case additionally enforces invitation/lobby policy).
    - Recording/removing/ending require the meeting to actually be live.
    """
    if capability not in MEETING_CAPABILITIES:
        return False
    role = roleForUser(
        userId,
        organizerId,
        participantRole=participantRole,
        isInvited=isInvited,
    )
    granted = capability in capabilitiesForRole(role)
    if not granted:
        return False
    if capability in (CAP_RECORD, CAP_REMOVE_PARTICIPANT, CAP_END_MEETING) and not meetingIsLive:
        # These operate on a running meeting; ending a not-started meeting is
        # handled as cancellation (a separate, organizer-only operation).
        return capability == CAP_END_MEETING and role == MEETING_ROLE_HOST
    return True


def assertCan(
    capability: str,
    *,
    userId: uuid.UUID,
    organizerId: uuid.UUID,
    participantRole: str = "",
    isInvited: bool = False,
    meetingIsLive: bool = False,
) -> None:
    """Raise a business-rule violation when the capability is not granted."""
    if not can(
        capability,
        userId=userId,
        organizerId=organizerId,
        participantRole=participantRole,
        isInvited=isInvited,
        meetingIsLive=meetingIsLive,
    ):
        raise BusinessRuleViolationError(
            f"Meeting capability {capability} is not permitted for this role.",
            ruleId=f"PHASE10-MEETING_{capability}",
        )


def isPrivilegedRole(role: str) -> bool:
    """HOST / CO_HOST can moderate participants (§29)."""
    return role in (MEETING_ROLE_HOST, MEETING_ROLE_CO_HOST)
