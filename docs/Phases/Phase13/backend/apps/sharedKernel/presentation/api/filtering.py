"""Safe filtering / sorting / searching (Phase 06 §22).

Whitelist-driven only: an endpoint declares which fields may filter, sort
and be searched. Anything else in the query string is ignored — never
reflected into SQL/ORM lookups. All lookups are parameterized ORM
expressions (SQL-injection safe by construction); ``search`` uses
``icontains`` on declared character fields only.
"""

from __future__ import annotations

from typing import Any

from django.db.models import QuerySet

from apps.sharedKernel.domain.errors import ValidationFailedError


class SafeQueryFilter:
    """Build filtered/ordered querysets from whitelisted query params (§22)."""

    def __init__(
        self,
        queryset: QuerySet[Any],
        params: dict[str, Any],
        *,
        filterableFields: dict[str, str],
        searchableFields: tuple[str, ...] = (),
        sortableFields: tuple[str, ...] = (),
        defaultOrdering: str = "-createdAt",
    ) -> None:
        self.queryset = queryset
        self.params = params
        self.filterableFields = filterableFields
        self.searchableFields = searchableFields
        self.sortableFields = sortableFields
        self.defaultOrdering = defaultOrdering

    def apply(self) -> QuerySet[Any]:
        queryset = self.applyFilters(self.queryset)
        queryset = self.applySearch(queryset)
        return self.applyOrdering(queryset)

    def applyFilters(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        for param, ormLookup in self.filterableFields.items():
            value = self.params.get(param)
            if value in (None, "", []):
                continue
            if isinstance(value, list):
                value = value[0]
            queryset = queryset.filter(**{ormLookup: value})
        return queryset

    def applySearch(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        term = str(self.params.get("search", "")).strip()
        if not term or not self.searchableFields:
            return queryset
        from django.db.models import Q

        query = Q()
        for field in self.searchableFields:
            query |= Q(**{f"{field}__icontains": term})
        return queryset.filter(query)

    def applyOrdering(self, queryset: QuerySet[Any]) -> QuerySet[Any]:
        requested = str(self.params.get("ordering", "")).strip()
        if not requested:
            return queryset.order_by(self.defaultOrdering)
        fields = [part.strip() for part in requested.split(",") if part.strip()]
        unknown = [field for field in fields if field.lstrip("-") not in self.sortableFields]
        if unknown:
            raise ValidationFailedError(
                "Field is not sortable.",
                fieldErrors={"ordering": ", ".join(unknown)},
            )
        return queryset.order_by(*fields)
