"""Document library domain entity (Phase 31)."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class Document:
    """One uploaded tenant file; the byte stream lives on media storage."""

    id: uuid.UUID
    tenantId: uuid.UUID
    name: str
    contentType: str
    sizeBytes: int
    category: str
    description: str
    uploadedByIdentifier: str
    uploadedAt: datetime
    storagePath: str
