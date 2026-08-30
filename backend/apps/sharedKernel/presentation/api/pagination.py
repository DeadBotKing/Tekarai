"""Standard pagination (Phase 06 §21).

- ``TekaraiPagePagination`` — regular lists: ``?page=1&pageSize=50`` with a
  ``meta.pagination`` block (totalCount / page / pageSize / hasNext …).
- ``TekaraiCursorPagination`` — large append-only streams (messages,
  telemetry, audit): opaque cursor over (createdAt, id); offset pagination
  is forbidden for those (BR-PERF-002).
"""

from __future__ import annotations

import base64
import hashlib
from typing import Any

from rest_framework.pagination import CursorPagination, PageNumberPagination
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.sharedKernel.presentation.api.response import successEnvelope


class TekaraiPagePagination(PageNumberPagination):
    page_size = 50
    page_size_query_param = "pageSize"
    max_page_size = 100
    page_query_param = "page"

    def get_paginated_response(self, data: list[Any]) -> Response:
        return Response(
            successEnvelope(
                data,
                meta={
                    "pagination": {
                        "totalCount": self.page.paginator.count,
                        "page": self.page.number,
                        "pageSize": self.get_page_size(self.request),
                        "totalPages": self.page.paginator.num_pages,
                        "hasNext": self.page.has_next(),
                        "hasPrevious": self.page.has_previous(),
                    }
                },
            )
        )


class TekaraiCursorPagination(CursorPagination):
    """Cursor pagination with the standard envelope (§21, BR-PERF-002)."""

    page_size = 50
    page_size_query_param = "pageSize"
    max_page_size = 200
    cursor_query_param = "cursor"
    ordering = "-occurredAt"

    def get_paginated_response(self, data: list[Any]) -> Response:
        nextLink = self.get_next_link()
        return Response(
            successEnvelope(
                data,
                meta={
                    "pagination": {
                        "pageSize": self.page_size,
                        "nextCursor": extractCursor(nextLink, self.cursor_query_param),
                        "hasNext": bool(nextLink),
                    }
                },
            )
        )


def extractCursor(link: str | None, cursorParam: str) -> str:
    """Reduce a next-page URL to its opaque cursor token."""
    if not link:
        return ""
    from urllib.parse import parse_qs, urlparse

    parsed = parse_qs(urlparse(link).query)
    values = parsed.get(cursorParam)
    return values[0] if values else ""


def stableCursor(*parts: str) -> str:
    """Deterministic opaque cursor (no client-crafted offsets)."""
    digest = hashlib.sha256("|".join(parts).encode("utf-8")).digest()[:10]
    return base64.urlsafe_b64encode(digest).decode("ascii").rstrip("=")


class PaginatedViewMixin(APIView):
    """Views that serve lists must declare a pagination class (§21)."""

    pagination_class = TekaraiPagePagination
