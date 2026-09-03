"""Domain services (Phase 08 §3.5, §3.8, §5, §11, §23, §33, §34).

- ``directChat``: deterministic dedup key for direct conversations (§5).
- ``mentionParser``: @username extraction (§3.7) — resolution to user ids
  happens in the application layer (identity lives in another context).
- ``editPolicy``: explicit edit rules — own message, configurable window,
  moderator elevation, editedAt + audit (§33).
- ``signalingProtocol``: the versioned ``communication.signal.v1``
  envelope builder/validator (§11) — no signaling assumptions hard-coded
  elsewhere.
"""

from __future__ import annotations

import re
import uuid
from typing import Any

from apps.communication.domain.valueObjects.communicationTypes import (
    DEFAULT_EDIT_WINDOW_MINUTES,
    REALTIME_PROTOCOL_VERSION,
    SIGNAL_KINDS,
    SIGNALING_PROTOCOL_VERSION,
)

# §3.7 — @username must not be preceded by word chars (emails stay untouched).
MENTION_PATTERN = re.compile(r"(?<![\w.@])@([a-z0-9][a-z0-9._-]{1,63})", re.IGNORECASE)


def directKeyOf(userA: uuid.UUID, userB: uuid.UUID) -> str:
    """§5 — stable key for the unordered user pair, tenant-scoped unique."""
    low, high = sorted((str(userA), str(userB)))
    return f"{low}:{high}"


def mentionedUsernames(body: str) -> tuple[str, ...]:
    """§3.7 — @username tokens found in the body (lowercased, deduped)."""
    seen: dict[str, None] = {}
    for match in MENTION_PATTERN.finditer(body or ""):
        seen[match.group(1).lower()] = None
    return tuple(seen)


def canEditMessage(
    *,
    senderId: uuid.UUID,
    actorId: uuid.UUID,
    createdAt: Any,
    now: Any,
    isModerator: bool,
    editWindowMinutes: int = DEFAULT_EDIT_WINDOW_MINUTES,
) -> tuple[bool, str]:
    """§33 — sender-only within the window; moderators elevated."""
    if isModerator:
        return True, "moderator"
    if senderId != actorId:
        return False, "not_sender"
    elapsed = (now - createdAt).total_seconds()
    if elapsed > editWindowMinutes * 60:
        return False, "window_expired"
    return True, "sender"


def canDeleteMessage(
    *,
    senderId: uuid.UUID,
    actorId: uuid.UUID,
    isModerator: bool,
) -> bool:
    """§34 — sender deletes own; moderators manage anyone's."""
    return isModerator or senderId == actorId


def validateThread(
    *,
    replyToId: uuid.UUID | None,
    rootFound: bool,
    rootSameConversation: bool,
) -> None:
    """§3.8 — a reply must reference an existing message in the SAME
    conversation (thread root)."""
    if replyToId is None:
        return
    if not rootFound:
        from apps.sharedKernel.domain.errors import EntityNotFoundError

        raise EntityNotFoundError("Message", str(replyToId))
    if not rootSameConversation:
        from apps.sharedKernel.domain.errors import ValidationFailedError

        raise ValidationFailedError(
            "Reply root belongs to a different conversation.",
            fieldErrors={"replyToId": "cross-conversation thread"},
        )


class SignalingProtocol:
    """§11 — versioned signaling envelopes (communication.signal.v1)."""

    VERSION = SIGNALING_PROTOCOL_VERSION

    @staticmethod
    def envelope(kind: str, *, callId: str, fromUser: str, payload: dict) -> dict:
        if kind not in SIGNAL_KINDS:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown signaling kind.", fieldErrors={"kind": kind}
            )
        return {
            "version": SignalingProtocol.VERSION,
            "kind": kind,
            "callId": callId,
            "from": fromUser,
            "payload": payload,
        }

    @staticmethod
    def validate(envelope: dict) -> tuple[str, str, dict]:
        """Returns (kind, callId, payload) or raises."""
        version = envelope.get("version")
        if version != SignalingProtocol.VERSION:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unsupported signaling protocol version.",
                fieldErrors={"version": str(version)},
            )
        kind = str(envelope.get("kind", ""))
        if kind not in SIGNAL_KINDS:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unknown signaling kind.", fieldErrors={"kind": kind}
            )
        callId = str(envelope.get("callId", ""))
        if not callId:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Signaling envelopes need a callId.", fieldErrors={"callId": "empty"}
            )
        payload = envelope.get("payload") or {}
        if not isinstance(payload, dict):
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Signaling payload must be an object.",
                fieldErrors={"payload": "not_object"},
            )
        return kind, callId, payload


class RealtimeProtocol:
    """Versioned realtime client→server envelope (communication.rt.v1)."""

    VERSION = REALTIME_PROTOCOL_VERSION

    @staticmethod
    def validate(envelope: dict) -> tuple[str, dict, str]:
        """Returns (type, payload, requestId) or raises."""
        version = envelope.get("version")
        if version not in (RealtimeProtocol.VERSION, SignalingProtocol.VERSION):
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Unsupported realtime protocol version.",
                fieldErrors={"version": str(version)},
            )
        messageType = str(envelope.get("type", ""))
        if not messageType:
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Realtime envelopes need a type.", fieldErrors={"type": "empty"}
            )
        payload = envelope.get("payload") or {}
        if not isinstance(payload, dict):
            from apps.sharedKernel.domain.errors import ValidationFailedError

            raise ValidationFailedError(
                "Realtime payload must be an object.",
                fieldErrors={"payload": "not_object"},
            )
        return messageType, payload, str(envelope.get("requestId", ""))
