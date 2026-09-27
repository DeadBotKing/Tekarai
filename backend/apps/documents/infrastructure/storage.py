"""Media-storage adapter for document byte streams (Phase 31)."""

from __future__ import annotations

import uuid
from pathlib import Path

from django.core.files.storage import default_storage


class DocumentStorage:
    """Wraps Django's configured MEDIA storage behind an intentful API."""

    def save(self, *, tenantId: uuid.UUID, fileName: str, stream) -> str:
        safeName = Path(fileName).name
        key = str(Path("documents") / str(tenantId) / f"{uuid.uuid4()}-{safeName}")
        return default_storage.save(key, stream)

    def open(self, storagePath: str):
        return default_storage.open(storagePath, "rb")

    def delete(self, storagePath: str) -> None:
        if storagePath and default_storage.exists(storagePath):
            default_storage.delete(storagePath)
