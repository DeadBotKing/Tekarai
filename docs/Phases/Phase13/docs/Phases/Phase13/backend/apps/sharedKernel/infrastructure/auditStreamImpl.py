"""Django keyset-cursor reader for the audit stream (§21, BR-PERF-002).

Cursor = opaque (occurredAt, id) pair; pages walk strictly backwards in
time without OFFSET. Presentation receives plain dicts only.
"""

from __future__ import annotations

import base64
import json
from typing import Any

from apps.sharedKernel.application.services.auditStream import AuditStreamPage
from apps.sharedKernel.infrastructure.models import AuditEventModel


class DjangoAuditStreamReader:
    def readPage(self, *, cursor: str = "", pageSize: int = 50) -> AuditStreamPage:
        size = min(200, max(1, pageSize))
        queryset = AuditEventModel.objects.order_by("-occurredAt", "-id")
        anchor = decodeCursor(cursor)
        if anchor is not None:
            occurredAt, recordId = anchor
            from django.db.models import Q

            queryset = queryset.filter(
                Q(occurredAt__lt=occurredAt) | Q(occurredAt=occurredAt, id__lt=recordId)
            )
        rows = list(queryset[: size + 1])
        hasNext = len(rows) > size
        page = rows[:size]
        nextCursor = ""
        if hasNext and page:
            last = page[-1]
            nextCursor = encodeCursor(last.occurredAt, str(last.id))
        return AuditStreamPage(
            items=[serializeEvent(event) for event in page],
            nextCursor=nextCursor,
            hasNext=hasNext,
        )


def serializeEvent(event: AuditEventModel) -> dict[str, Any]:
    return {
        "id": str(event.id),
        "occurredAt": event.occurredAt.isoformat(),
        "action": event.action,
        "resourceType": event.resourceType,
        "resourceId": event.resourceId,
        "tenantId": str(event.tenantId) if event.tenantId else None,
        "actorUserId": str(event.actorUserId) if event.actorUserId else None,
        "correlationId": event.correlationId,
        "ipAddress": event.ipAddress,
    }


def encodeCursor(occurredAt: object, recordId: str) -> str:
    from datetime import datetime

    stamp = occurredAt.isoformat() if isinstance(occurredAt, datetime) else str(occurredAt)
    payload = json.dumps({"o": stamp, "i": recordId}, separators=(",", ":"))
    return base64.urlsafe_b64encode(payload.encode("utf-8")).decode("ascii").rstrip("=")


def decodeCursor(cursor: str) -> tuple[Any, str] | None:
    if not cursor:
        return None
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        payload = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")))
        from datetime import datetime

        return datetime.fromisoformat(payload["o"]), str(payload["i"])
    except (ValueError, KeyError, TypeError) as exc:
        from apps.sharedKernel.domain.errors import ValidationFailedError

        raise ValidationFailedError("Invalid cursor.", fieldErrors={"cursor": "malformed"}) from exc
