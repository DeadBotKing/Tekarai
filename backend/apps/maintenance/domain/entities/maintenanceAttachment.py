"""Attachment metadata belonging to a maintenance device or work order."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True)
class MaintenanceAttachment:
    id: uuid.UUID
    tenantId: uuid.UUID
    targetType: str
    targetId: uuid.UUID
    category: str
    originalName: str
    mimeType: str
    sizeBytes: int
    storageName: str
    uploadedAt: datetime
