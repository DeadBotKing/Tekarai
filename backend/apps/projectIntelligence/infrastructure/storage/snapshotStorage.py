"""Immutable, tenant-partitioned snapshot artifact storage."""

from __future__ import annotations

import hashlib
import json
import os
import uuid
from pathlib import Path

from django.conf import settings

from apps.sharedKernel.domain.errors import ConflictError


class ImmutableSnapshotStorage:
    def __init__(self, root: Path | None = None):
        self.root = Path(root or settings.PROJECT_INTELLIGENCE_ARTIFACT_ROOT).resolve()

    def put(
        self, tenantId: uuid.UUID, projectId: uuid.UUID, snapshotId: uuid.UUID, payload: dict
    ) -> tuple[str, str]:
        content = json.dumps(
            payload, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str
        ).encode()
        checksum = hashlib.sha256(content).hexdigest()
        target = self.root / str(tenantId) / str(projectId) / f"{snapshotId}-{checksum}.json"
        target.parent.mkdir(parents=True, exist_ok=True)
        if target.exists() and target.read_bytes() != content:
            raise ConflictError("Immutable snapshot collision.")
        if not target.exists():
            temporary = target.with_suffix(".tmp")
            temporary.write_bytes(content)
            os.replace(temporary, target)
            target.chmod(0o440)
        return target.as_uri(), checksum

    def verify(self, uri: str, checksum: str) -> bool:
        try:
            path = Path(uri.removeprefix("file://")).resolve()
            path.relative_to(self.root)
            return hashlib.sha256(path.read_bytes()).hexdigest() == checksum
        except (OSError, ValueError):
            return False

    def load(self, uri: str) -> dict:
        path = Path(uri.removeprefix("file://")).resolve()
        path.relative_to(self.root)
        return json.loads(path.read_text())
