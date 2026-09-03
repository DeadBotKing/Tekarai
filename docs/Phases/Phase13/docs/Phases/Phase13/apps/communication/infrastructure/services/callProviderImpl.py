"""CallProvider adapter (Phase 10 §25/§26).

The domain/application layers talk only to the ``CallProvider`` port. This
default adapter is a **signaling-only WebRTC provider**: it mints opaque media
session references and never touches media itself — the SFU/media plane stays
external (ADR-023: Django relays signaling, media never flows through Django).

Future providers (Twilio, Agora, Jitsi, Microsoft Teams) implement the same
port and are selected by settings, with no domain/application change.
"""

from __future__ import annotations

import uuid
from typing import Any


class WebRtcCallProvider:
    """Vendor-neutral signaling session manager (§25).

    Sessions are tracked in an ephemeral in-memory map keyed by the opaque
    reference. This is NOT a source of truth — call/business state lives in
    the Call aggregate and the database; the map only supports provider-side
    session lifecycle during a running process (mirrors the presence fallback
    philosophy; a distributed deployment delegates to the SFU/provider API).
    """

    providerName = "webrtc"

    def __init__(self) -> None:
        self._sessions: dict[str, dict[str, Any]] = {}

    def createSession(
        self, *, callId: uuid.UUID, mediaType: str, tenantId: uuid.UUID
    ) -> dict[str, Any]:
        sessionRef = f"wrtc-{callId}"
        self._sessions[sessionRef] = {
            "callId": str(callId),
            "mediaType": mediaType,
            "tenantId": str(tenantId),
            "status": "INITIATED",
            "participants": [],
        }
        return {
            "provider": self.providerName,
            "sessionRef": sessionRef,
            "mediaType": mediaType,
            "transport": "webrtc-signaling",
        }

    def joinSession(self, *, sessionRef: str, userId: uuid.UUID) -> dict[str, Any]:
        session = self._sessions.get(sessionRef)
        if session is None:
            return {"provider": self.providerName, "joined": False, "reason": "unknown-session"}
        participant = str(userId)
        if participant not in session["participants"]:
            session["participants"].append(participant)
        session["status"] = "ACTIVE"
        return {
            "provider": self.providerName,
            "joined": True,
            "sessionRef": sessionRef,
            "peerCount": len(session["participants"]),
        }

    def leaveSession(self, *, sessionRef: str, userId: uuid.UUID) -> None:
        session = self._sessions.get(sessionRef)
        if session is None:
            return
        participant = str(userId)
        if participant in session["participants"]:
            session["participants"].remove(participant)
        if not session["participants"]:
            session["status"] = "ENDED"

    def endSession(self, *, sessionRef: str) -> None:
        session = self._sessions.pop(sessionRef, None)
        if session is not None:
            session["status"] = "ENDED"

    def getSessionStatus(self, *, sessionRef: str) -> str:
        session = self._sessions.get(sessionRef)
        return session["status"] if session else "UNKNOWN"
