"""Immutable filesystem artifact storage; object stores implement the same port."""

from __future__ import annotations

import hashlib
import os
import uuid
from pathlib import Path

from django.conf import settings


class ImmutableArtifactStorage:
    def __init__(self, root: str | None = None) -> None:
        self.root = Path(
            root
            or getattr(
                settings, "LEARNING_ARTIFACT_ROOT", settings.BASE_DIR / "var" / "learningArtifacts"
            )
        )

    def putImmutable(
        self, tenantId: uuid.UUID, name: str, version: str, content: bytes
    ) -> tuple[str, str]:
        checksum = hashlib.sha256(content).hexdigest()
        safeName = "".join(
            character for character in name if character.isalnum() or character in "-_"
        )
        target = self.root / str(tenantId) / safeName / version / f"{checksum}.artifact"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists():
            if target.read_bytes() != content:
                raise ValueError("Immutable artifact checksum collision.")
        else:
            temporary = target.with_suffix(f".{os.getpid()}.tmp")
            temporary.write_bytes(content)
            os.replace(temporary, target)
        return target.as_uri(), checksum

    def putDataset(
        self, tenantId: uuid.UUID, datasetId: uuid.UUID, version: str, content: bytes
    ) -> tuple[str, str]:
        return self.putImmutable(tenantId, f"dataset-{datasetId}", version, content)

    def verify(self, uri: str, checksum: str) -> bool:
        path = Path(uri.removeprefix("file://"))
        return path.is_file() and hashlib.sha256(path.read_bytes()).hexdigest() == checksum

    def read(self, uri: str) -> bytes:
        return Path(uri.removeprefix("file://")).read_bytes()
