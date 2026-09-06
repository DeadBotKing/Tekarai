"""Ports required by the Phase 14 completion services."""

from __future__ import annotations

import uuid
from datetime import datetime
from typing import Any, Protocol


class UnifiedCommunicationSearch(Protocol):
    def search(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        query: str,
        scopes: tuple[str, ...],
        limit: int,
    ) -> tuple[dict[str, Any], ...]: ...


class OfflineSyncReceiptStore(Protocol):
    def find(
        self, tenantId: uuid.UUID, userId: uuid.UUID, clientBatchId: str
    ) -> tuple[str, dict[str, Any]] | None: ...

    def save(
        self,
        tenantId: uuid.UUID,
        userId: uuid.UUID,
        clientBatchId: str,
        requestHash: str,
        result: dict[str, Any],
    ) -> dict[str, Any]: ...


class CommunicationRetentionStore(Protocol):
    def sweep(
        self,
        tenantId: uuid.UUID,
        cutoff: datetime,
        requestedById: uuid.UUID,
        *,
        dryRun: bool,
    ) -> dict[str, int]: ...


__all__ = [
    "CommunicationRetentionStore",
    "OfflineSyncReceiptStore",
    "UnifiedCommunicationSearch",
]
