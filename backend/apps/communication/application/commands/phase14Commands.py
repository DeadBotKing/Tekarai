"""Commands introduced by the Phase 14 completion gate."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from apps.sharedKernel.application.messaging import Command


@dataclass(frozen=True)
class ForwardMessageCommand(Command):
    messageId: str
    targetConversationId: str
    clientRequestId: str
    comment: str = ""


@dataclass(frozen=True)
class AttachmentPreflightCommand(Command):
    fileName: str
    mimeType: str
    sizeBytes: int
    checksum: str
    scanStatus: str
    classification: str = "INTERNAL"


@dataclass(frozen=True)
class UnifiedSearchQuery(Command):
    query: str
    scopes: tuple[str, ...] = ()
    limit: int = 25


@dataclass(frozen=True)
class OfflineSyncCommand(Command):
    clientBatchId: str
    operations: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class RunRetentionCommand(Command):
    retentionDays: int | None = None
    dryRun: bool = True


__all__ = [
    "AttachmentPreflightCommand",
    "ForwardMessageCommand",
    "OfflineSyncCommand",
    "RunRetentionCommand",
    "UnifiedSearchQuery",
]
