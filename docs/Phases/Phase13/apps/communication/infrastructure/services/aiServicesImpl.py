"""AI-side adapters (Phase 08 §21) — provider-neutral by design.

``LocalMeetingAiAssistant`` is a deterministic local implementation so the
platform works without any external AI vendor; swapping in a hosted model
means implementing the same two methods. The AI NEVER writes domain state
directly — results flow back through application services (§21).
"""

from __future__ import annotations

import uuid


class TranscriptReaderDjango:
    """Reads meeting-visible messages from the conversation transcript."""

    def linesOf(self, conversationId: uuid.UUID) -> list[str]:
        from apps.communication.infrastructure.models import MessageModel

        rows = (
            MessageModel.objects.filter(
                conversationId=conversationId, deletedAt__isnull=True
            )
            .exclude(body="")
            .order_by("createdAt")
            .values_list("senderId", "body")
        )
        return [f"{sender}: {body}" for sender, body in rows]


class LocalMeetingAiAssistant:
    """Extractive summarizer — no external calls, fully testable."""

    def summarize(self, transcript: list[str]) -> str:
        if not transcript:
            return ""
        speakers = {line.split(":", 1)[0] for line in transcript if ":" in line}
        first = transcript[0].split(":", 1)[-1].strip()
        last = transcript[-1].split(":", 1)[-1].strip()
        return (
            f"Meeting had {len(transcript)} contributions from "
            f"{len(speakers)} participants. It opened with “{first[:120]}” "
            f"and closed with “{last[:120]}”."
        )

    def extractActionItems(self, transcript: list[str]) -> list[str]:
        markers = ("باید", "will ", "need to", "action", "follow up", "تا ", "اجرا")
        items = [
            line.split(":", 1)[-1].strip()
            for line in transcript
            if any(marker in line.lower() for marker in markers)
        ]
        return items[:10]
