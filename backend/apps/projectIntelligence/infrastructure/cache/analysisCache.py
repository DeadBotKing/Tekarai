"""Tenant-safe persistent analyzer cache."""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.utils import timezone

from apps.projectIntelligence.infrastructure.persistence.models import AnalysisCacheModel


class DjangoAnalysisCache:
    def __init__(self, tenantId: uuid.UUID, ttlSeconds: int = 86400):
        self.tenantId = tenantId
        self.ttl = ttlSeconds

    def get(self, key: str) -> dict | None:
        obj = AnalysisCacheModel.objects.filter(tenantId=self.tenantId, cacheKey=key).first()
        if not obj or (obj.expiresAt and obj.expiresAt <= timezone.now()):
            return None
        return obj.value

    def put(self, key: str, value: dict) -> None:
        AnalysisCacheModel.objects.update_or_create(
            tenantId=self.tenantId,
            cacheKey=key,
            defaults={"value": value, "expiresAt": timezone.now() + timedelta(seconds=self.ttl)},
        )
