"""Framework-free Phase 14 completion policies.

Security-sensitive attachment validation, offline request hashing and the closed
search vocabulary live in the domain; HTTP, ORM, storage and malware engines do
not.
"""

from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import PurePath
from typing import Any

from apps.sharedKernel.domain.errors import ValidationFailedError

SEARCH_SCOPES = (
    "MESSAGES",
    "CONVERSATIONS",
    "CHANNELS",
    "ATTACHMENTS",
    "MEETINGS",
    "TRANSCRIPTS",
)
ATTACHMENT_SCAN_STATUSES = ("PENDING", "CLEAN", "INFECTED", "FAILED")
DATA_CLASSIFICATIONS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED")
SYNC_OPERATIONS = ("SEND_MESSAGE", "EDIT_MESSAGE", "DELETE_MESSAGE")
_SHA256 = re.compile(r"^[0-9a-f]{64}$")
_MIME_EXTENSIONS = {
    "application/pdf": (".pdf",),
    "image/jpeg": (".jpg", ".jpeg"),
    "image/png": (".png",),
    "text/plain": (".txt",),
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": (".docx",),
}


@dataclass(frozen=True)
class AttachmentPolicy:
    maxSizeBytes: int = 25 * 1024 * 1024
    allowedMimeTypes: tuple[str, ...] = (
        "application/pdf",
        "image/jpeg",
        "image/png",
        "text/plain",
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    )
    requireCleanScan: bool = True

    def __post_init__(self) -> None:
        if self.maxSizeBytes < 1:
            raise ValidationFailedError("Attachment size policy must be positive.")
        object.__setattr__(
            self,
            "allowedMimeTypes",
            tuple(sorted({str(value).strip().lower() for value in self.allowedMimeTypes if value})),
        )

    def validate(
        self,
        *,
        fileName: str,
        mimeType: str,
        sizeBytes: int,
        checksum: str,
        scanStatus: str,
        classification: str,
    ) -> None:
        name = str(fileName or "").strip()
        if (
            not name
            or name != PurePath(name).name
            or any(value in name for value in ("/", "\\", ".."))
        ):
            raise ValidationFailedError("Attachment file name must not contain a path.")
        if (
            not isinstance(sizeBytes, int)
            or isinstance(sizeBytes, bool)
            or not 0 < sizeBytes <= self.maxSizeBytes
        ):
            raise ValidationFailedError("Attachment size is outside the configured limit.")
        normalizedMime = str(mimeType or "").strip().lower()
        if normalizedMime not in self.allowedMimeTypes:
            raise ValidationFailedError("Attachment MIME type is not allowed.")
        suffix = PurePath(name).suffix.lower()
        acceptedExtensions = _MIME_EXTENSIONS.get(normalizedMime, ())
        if not acceptedExtensions or suffix not in acceptedExtensions:
            raise ValidationFailedError("Attachment extension does not match its MIME type.")
        if not _SHA256.fullmatch(str(checksum or "").strip().lower()):
            raise ValidationFailedError("Attachment checksum must be a SHA-256 hex digest.")
        normalizedScan = str(scanStatus or "").strip().upper()
        if normalizedScan not in ATTACHMENT_SCAN_STATUSES:
            raise ValidationFailedError("Attachment scan status is invalid.")
        if self.requireCleanScan and normalizedScan != "CLEAN":
            raise ValidationFailedError("Attachment must pass malware scanning before use.")
        if str(classification or "").strip().upper() not in DATA_CLASSIFICATIONS:
            raise ValidationFailedError("Attachment classification is invalid.")

    def storageKey(
        self, tenantId: uuid.UUID, fileName: str, identifier: uuid.UUID | None = None
    ) -> str:
        suffix = PurePath(fileName).suffix.lower()[:16]
        return f"communication/{tenantId}/{identifier or uuid.uuid4()}{suffix}"


def normalizeSearchScopes(values: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    requested = tuple(str(value).strip().upper() for value in (values or SEARCH_SCOPES))
    if not requested or any(value not in SEARCH_SCOPES for value in requested):
        raise ValidationFailedError("Search scope is invalid.")
    return tuple(dict.fromkeys(requested))


def syncRequestHash(operations: list[dict[str, Any]]) -> str:
    if not isinstance(operations, list) or not operations:
        raise ValidationFailedError("Offline sync requires at least one operation.")
    if len(operations) > 100:
        raise ValidationFailedError("Offline sync accepts at most 100 operations.")
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in operations:
        if not isinstance(item, dict):
            raise ValidationFailedError("Offline sync operations must be objects.")
        operationId = str(item.get("operationId", "")).strip()
        kind = str(item.get("kind", "")).strip().upper()
        if not operationId or operationId in seen:
            raise ValidationFailedError("Offline operation IDs must be non-empty and unique.")
        if kind not in SYNC_OPERATIONS:
            raise ValidationFailedError("Offline operation kind is invalid.")
        seen.add(operationId)
        normalized.append(
            {"operationId": operationId, "kind": kind, "payload": item.get("payload", {})}
        )
    canonical = json.dumps(normalized, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


__all__ = [
    "ATTACHMENT_SCAN_STATUSES",
    "AttachmentPolicy",
    "DATA_CLASSIFICATIONS",
    "SEARCH_SCOPES",
    "SYNC_OPERATIONS",
    "normalizeSearchScopes",
    "syncRequestHash",
]
