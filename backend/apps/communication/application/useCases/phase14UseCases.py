"""Phase 14 completion use cases.

These services close the gaps not already delivered by Phases 8/10/11:
reference-preserving forwarding, secure attachment preflight, unified scoped
search, idempotent offline synchronization and legal-hold-aware retention.
"""

from __future__ import annotations

import dataclasses
import uuid
from datetime import timedelta
from typing import Any

from apps.communication.application.commands.communicationCommands import (
    DeleteMessageCommand,
    EditMessageCommand,
    SendMessageCommand,
)
from apps.communication.application.commands.phase14Commands import (
    AttachmentPreflightCommand,
    ForwardMessageCommand,
    OfflineSyncCommand,
    RunRetentionCommand,
    UnifiedSearchQuery,
)
from apps.communication.application.dto.communicationDtos import messageDtoFromDomain
from apps.communication.application.services.communicationSupport import CommunicationUseCase
from apps.communication.application.useCases.conversationUseCases import actorOf
from apps.communication.domain.entities.message import Message
from apps.communication.domain.repositories.communicationRepositories import (
    MessageRepository,
    ParticipantRepository,
)
from apps.communication.domain.repositories.phase14Repositories import (
    CommunicationRetentionStore,
    OfflineSyncReceiptStore,
    UnifiedCommunicationSearch,
)
from apps.communication.domain.valueObjects.phase14Types import (
    AttachmentPolicy,
    normalizeSearchScopes,
    syncRequestHash,
)
from apps.sharedKernel.domain.errors import (
    ConflictError,
    EntityNotFoundError,
    PermissionDeniedError,
    TekaraiError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.valueObjects import asUuid


class ForwardMessageUseCase(CommunicationUseCase[ForwardMessageCommand, Any]):
    """Forward by reference plus snapshot; never clone the original identity."""

    requiredAction = ""

    def __init__(
        self,
        messageRepository: MessageRepository,
        participantRepository: ParticipantRepository,
        **kernel: Any,
    ) -> None:
        super().__init__(**kernel)
        self.messageRepository = messageRepository
        self.participantRepository = participantRepository

    def perform(self, command: ForwardMessageCommand) -> Any:
        actorId, tenantId = actorOf()
        targetId = asUuid(command.targetConversationId)
        original = self.messageRepository.getById(asUuid(command.messageId), tenantId)
        if original is None:
            raise EntityNotFoundError("Message", command.messageId)
        if original.deletedAt is not None:
            raise ConflictError("Deleted messages cannot be forwarded.")
        for conversationId in (original.conversationId, targetId):
            member = self.participantRepository.get(conversationId, actorId)
            if member is None or not member.isActive():
                raise PermissionDeniedError(action="message.forward")
        key = str(command.clientRequestId or "").strip()
        if not key:
            raise ValidationFailedError("Forwarding requires clientRequestId.")
        existing = self.messageRepository.findByIdempotencyKey(tenantId, targetId, actorId, key)
        if existing is not None:
            return messageDtoFromDomain(existing)
        now = self.clock.nowUtc()
        snapshot = {
            "originalMessageId": str(original.id),
            "originalConversationId": str(original.conversationId),
            "originalSenderId": str(original.senderId),
            "messageType": original.messageType,
            "body": original.body[:8000],
            "createdAt": original.createdAt.isoformat(),
        }
        body = str(command.comment or "").strip() or original.body
        forwarded = Message.send(
            tenantId,
            targetId,
            actorId,
            body,
            now,
            messageType=original.messageType,
            clientRequestId=key,
            forwardedFromId=original.id,
            forwardedById=actorId,
            forwardSnapshot=snapshot,
        )
        self.messageRepository.create(forwarded)
        self.collectEventsFrom(forwarded)
        self.emitIntegrationEvent(
            tenantId,
            "MessageForwarded",
            {
                "messageId": str(forwarded.id),
                "originalMessageId": str(original.id),
                "targetConversationId": str(targetId),
            },
        )
        self.broadcastConversation(
            targetId, {"type": "message.forwarded", "messageId": str(forwarded.id)}
        )
        self.audit(
            "CREATE",
            resourceType="MessageForward",
            resourceId=str(forwarded.id),
            tenantId=tenantId,
            after={"originalMessageId": str(original.id), "targetConversationId": str(targetId)},
        )
        return messageDtoFromDomain(forwarded)


class AttachmentPreflightUseCase:
    """Validate metadata and issue a server-generated object-storage key."""

    def __init__(self, policy: AttachmentPolicy) -> None:
        self.policy = policy

    def execute(self, command: AttachmentPreflightCommand) -> dict[str, Any]:
        _actor, tenantId = actorOf()
        self.policy.validate(
            fileName=command.fileName,
            mimeType=command.mimeType,
            sizeBytes=command.sizeBytes,
            checksum=command.checksum,
            scanStatus=command.scanStatus,
            classification=command.classification,
        )
        identifier = uuid.uuid4()
        return {
            "attachmentId": str(identifier),
            "storageKey": self.policy.storageKey(tenantId, command.fileName, identifier),
            "fileName": command.fileName,
            "mimeType": command.mimeType.lower(),
            "sizeBytes": command.sizeBytes,
            "checksum": command.checksum.lower(),
            "scanStatus": command.scanStatus.upper(),
            "classification": command.classification.upper(),
        }


class UnifiedSearchUseCase:
    def __init__(self, searchPort: UnifiedCommunicationSearch) -> None:
        self.searchPort = searchPort

    def execute(self, query: UnifiedSearchQuery) -> tuple[dict[str, Any], ...]:
        actorId, tenantId = actorOf()
        text = str(query.query or "").strip()
        if len(text) < 2 or len(text) > 200:
            raise ValidationFailedError("Search query length must be between 2 and 200.")
        if query.limit < 1 or query.limit > 100:
            raise ValidationFailedError("Search limit must be between 1 and 100.")
        scopes = normalizeSearchScopes(query.scopes)
        return self.searchPort.search(tenantId, actorId, text, scopes, query.limit)


class OfflineSyncUseCase:
    """Replay bounded offline operations once and persist the exact result."""

    def __init__(
        self,
        receiptStore: OfflineSyncReceiptStore,
        sendMessage: Any,
        editMessage: Any,
        deleteMessage: Any,
    ) -> None:
        self.receiptStore = receiptStore
        self.sendMessage = sendMessage
        self.editMessage = editMessage
        self.deleteMessage = deleteMessage

    def execute(self, command: OfflineSyncCommand) -> dict[str, Any]:
        actorId, tenantId = actorOf()
        batchId = str(command.clientBatchId or "").strip()
        if not batchId or len(batchId) > 100:
            raise ValidationFailedError("clientBatchId is required and must be at most 100 chars.")
        fingerprint = syncRequestHash(command.operations)
        existing = self.receiptStore.find(tenantId, actorId, batchId)
        if existing is not None:
            existingHash, result = existing
            if existingHash != fingerprint:
                raise ConflictError(
                    "The offline batch id is already bound to different operations."
                )
            return result
        results: list[dict[str, Any]] = []
        for operation in command.operations:
            operationId = str(operation["operationId"])
            kind = str(operation["kind"]).upper()
            payload = dict(operation.get("payload") or {})
            try:
                value = self._executeOne(kind, payload, operationId)
                results.append({"operationId": operationId, "status": "APPLIED", "data": value})
            except TekaraiError as exc:
                results.append(
                    {
                        "operationId": operationId,
                        "status": "CONFLICT" if exc.httpStatus == 409 else "REJECTED",
                        "error": {"code": exc.code, "message": exc.message},
                    }
                )
            except (KeyError, TypeError, ValueError) as exc:
                results.append(
                    {
                        "operationId": operationId,
                        "status": "REJECTED",
                        "error": {"code": "VALIDATION_ERROR", "message": str(exc)},
                    }
                )
        applied = sum(item["status"] == "APPLIED" for item in results)
        result = {
            "clientBatchId": batchId,
            "requestHash": fingerprint,
            "applied": applied,
            "rejected": len(results) - applied,
            "operations": results,
        }
        return self.receiptStore.save(tenantId, actorId, batchId, fingerprint, result)

    def _executeOne(self, kind: str, payload: dict[str, Any], operationId: str) -> Any:
        if kind == "SEND_MESSAGE":
            value = self.sendMessage.execute(
                SendMessageCommand(
                    conversationId=str(payload["conversationId"]),
                    body=str(payload.get("body", "")),
                    messageType=str(payload.get("messageType", "TEXT")),
                    replyToId=str(payload.get("replyToId", "")),
                    clientRequestId=str(payload.get("clientRequestId") or operationId),
                    clientMessageId=str(payload.get("clientMessageId") or ""),
                    attachments=list(payload.get("attachments") or []),
                )
            )
        elif kind == "EDIT_MESSAGE":
            value = self.editMessage.execute(
                EditMessageCommand(messageId=str(payload["messageId"]), body=str(payload["body"]))
            )
        else:
            value = self.deleteMessage.execute(
                DeleteMessageCommand(messageId=str(payload["messageId"]))
            )
        if dataclasses.is_dataclass(value) and not isinstance(value, type):
            return dataclasses.asdict(value)
        return value


class RunRetentionUseCase(CommunicationUseCase[RunRetentionCommand, dict[str, Any]]):
    # Existing tenant communication administrators hold this catalogued action.
    requiredAction = "conversation.moderate"

    def __init__(
        self,
        retentionStore: CommunicationRetentionStore,
        *,
        defaultRetentionDays: int = 2555,
        **kernel: Any,
    ) -> None:
        super().__init__(**kernel)
        self.retentionStore = retentionStore
        self.defaultRetentionDays = defaultRetentionDays

    def perform(self, command: RunRetentionCommand) -> dict[str, Any]:
        actorId, tenantId = actorOf()
        days = command.retentionDays
        if days is None:
            days = self.defaultRetentionDays
        if days < 1 or days > 36500:
            raise ValidationFailedError("Retention days must be between 1 and 36500.")
        cutoff = self.clock.nowUtc() - timedelta(days=days)
        counts = self.retentionStore.sweep(tenantId, cutoff, actorId, dryRun=bool(command.dryRun))
        self.audit(
            "RETENTION_PREVIEW" if command.dryRun else "RETENTION_PURGE",
            resourceType="CommunicationRetention",
            resourceId=str(tenantId),
            tenantId=tenantId,
            after={"retentionDays": days, "counts": counts, "dryRun": command.dryRun},
        )
        return {
            "dryRun": bool(command.dryRun),
            "retentionDays": days,
            "cutoff": cutoff.isoformat(),
            "counts": counts,
        }


__all__ = [
    "AttachmentPreflightUseCase",
    "ForwardMessageUseCase",
    "OfflineSyncUseCase",
    "RunRetentionUseCase",
    "UnifiedSearchUseCase",
]
