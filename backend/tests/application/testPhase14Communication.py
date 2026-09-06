"""Phase 14 communication gap-closure tests."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.utils import timezone

from apps.communication.application.commands.communicationCommands import (
    CreateGroupConversationCommand,
    SendMessageCommand,
)
from apps.communication.application.commands.phase14Commands import (
    AttachmentPreflightCommand,
    ForwardMessageCommand,
    OfflineSyncCommand,
    RunRetentionCommand,
    UnifiedSearchQuery,
)
from apps.communication.application.queries.communicationQueries import ListMessagesQuery
from apps.communication.domain.entities.recording import Recording
from apps.communication.domain.valueObjects.phase14Types import AttachmentPolicy, syncRequestHash
from apps.communication.infrastructure import container
from apps.communication.infrastructure.models import (
    CommunicationRetentionRunModel,
    CommunicationSyncReceiptModel,
    LegalHoldModel,
    MessageModel,
)
from apps.sharedKernel.domain.errors import (
    ConflictError,
    PermissionDeniedError,
    ValidationFailedError,
)
from tests.support.phase8Helpers import asUser, ensureTenant, ensureUser, grantCommAdmin


class Phase14CommunicationTests(TestCase):
    def setUp(self) -> None:
        self.tenant = ensureTenant("phase14-tenant")
        self.foreignTenant = ensureTenant("phase14-foreign")
        self.admin = ensureUser(self.tenant, "p14-admin")
        self.member = ensureUser(self.tenant, "p14-member")
        self.outsider = ensureUser(self.tenant, "p14-outsider")
        self.foreign = ensureUser(self.foreignTenant, "p14-foreign")
        grantCommAdmin(self.tenant, self.admin)
        grantCommAdmin(self.foreignTenant, self.foreign)
        with asUser(self.tenant.id, self.admin.id):
            self.source = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(name="source", memberIds=[str(self.member.id)])
            )
            self.target = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(name="target", memberIds=[str(self.member.id)])
            )
            self.message = container.sendMessageUseCase().execute(
                SendMessageCommand(conversationId=self.source.id, body="quarterly needle report")
            )

    def testForwardPreservesOriginalReferenceAndIsIdempotent(self) -> None:
        command = ForwardMessageCommand(
            messageId=self.message.id,
            targetConversationId=self.target.id,
            clientRequestId="forward-1",
        )
        with asUser(self.tenant.id, self.member.id):
            first = container.forwardMessageUseCase().execute(command)
            second = container.forwardMessageUseCase().execute(command)
        self.assertEqual(first.id, second.id)
        row = MessageModel.objects.get(id=first.id)
        self.assertEqual(str(row.forwardedFromId), self.message.id)
        self.assertEqual(str(row.forwardedById), str(self.member.id))
        self.assertEqual(row.forwardSnapshot["originalMessageId"], self.message.id)
        self.assertEqual(MessageModel.objects.filter(forwardedFromId=self.message.id).count(), 1)

    def testForwardRequiresMembershipInBothConversations(self) -> None:
        with asUser(self.tenant.id, self.outsider.id), self.assertRaises(PermissionDeniedError):
            container.forwardMessageUseCase().execute(
                ForwardMessageCommand(
                    messageId=self.message.id,
                    targetConversationId=self.target.id,
                    clientRequestId="denied",
                )
            )

    def testAttachmentPolicyRejectsUnsafeAndUnscannedInput(self) -> None:
        policy = AttachmentPolicy(maxSizeBytes=100, allowedMimeTypes=("text/plain",))
        with self.assertRaises(ValidationFailedError):
            policy.validate(
                fileName="../secret.txt",
                mimeType="text/plain",
                sizeBytes=5,
                checksum="a" * 64,
                scanStatus="CLEAN",
                classification="INTERNAL",
            )
        with self.assertRaises(ValidationFailedError):
            policy.validate(
                fileName="safe.txt",
                mimeType="text/plain",
                sizeBytes=5,
                checksum="a" * 64,
                scanStatus="PENDING",
                classification="INTERNAL",
            )

    def testPreflightAndSendPersistSecurityMetadata(self) -> None:
        with asUser(self.tenant.id, self.member.id):
            preflight = container.attachmentPreflightUseCase().execute(
                AttachmentPreflightCommand(
                    fileName="evidence.txt",
                    mimeType="text/plain",
                    sizeBytes=5,
                    checksum="b" * 64,
                    scanStatus="CLEAN",
                    classification="CONFIDENTIAL",
                )
            )
            sent = container.sendMessageUseCase().execute(
                SendMessageCommand(
                    conversationId=self.source.id,
                    body="secure file",
                    messageType="FILE",
                    attachments=[preflight],
                )
            )
        self.assertEqual(sent.attachments[0].checksum, "b" * 64)
        self.assertTrue(
            sent.attachments[0].storageKey.startswith(f"communication/{self.tenant.id}/")
        )

    def testUnifiedSearchIsScopedToMembershipAndTenant(self) -> None:
        with asUser(self.foreignTenant.id, self.foreign.id):
            foreignConversation = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(name="foreign needle")
            )
            container.sendMessageUseCase().execute(
                SendMessageCommand(conversationId=foreignConversation.id, body="foreign needle")
            )
        with asUser(self.tenant.id, self.member.id):
            results = container.unifiedSearchUseCase().execute(
                UnifiedSearchQuery(query="needle", scopes=("MESSAGES", "CONVERSATIONS"))
            )
        ids = {item["id"] for item in results}
        self.assertIn(self.message.id, ids)
        self.assertNotIn(foreignConversation.id, ids)
        self.assertTrue(all("foreign" not in item["title"] for item in results))

    def testClientGeneratedMessageUuidIsIdempotent(self) -> None:
        clientId = uuid.uuid4()
        command = SendMessageCommand(
            conversationId=self.source.id,
            body="client allocated",
            clientMessageId=str(clientId),
        )
        with asUser(self.tenant.id, self.member.id):
            first = container.sendMessageUseCase().execute(command)
            second = container.sendMessageUseCase().execute(command)
        self.assertEqual(first.id, str(clientId))
        self.assertEqual(first.id, second.id)
        self.assertEqual(MessageModel.objects.filter(id=clientId).count(), 1)

    def testOfflineSyncIsExactlyReplayableAndDetectsBatchReuse(self) -> None:
        operation = {
            "operationId": "op-1",
            "kind": "SEND_MESSAGE",
            "payload": {"conversationId": self.source.id, "body": "offline"},
        }
        command = OfflineSyncCommand(clientBatchId="batch-1", operations=[operation])
        with asUser(self.tenant.id, self.member.id):
            first = container.offlineSyncUseCase().execute(command)
            second = container.offlineSyncUseCase().execute(command)
            with self.assertRaises(ConflictError):
                container.offlineSyncUseCase().execute(
                    OfflineSyncCommand(
                        clientBatchId="batch-1",
                        operations=[
                            {**operation, "payload": {**operation["payload"], "body": "changed"}}
                        ],
                    )
                )
        self.assertEqual(first, second)
        self.assertEqual(first["applied"], 1)
        self.assertEqual(CommunicationSyncReceiptModel.objects.count(), 1)
        self.assertEqual(
            MessageModel.objects.filter(tenantId=self.tenant.id, body="offline").count(), 1
        )

    def testRetentionPreviewExecutionAndLegalHoldExclusion(self) -> None:
        with asUser(self.tenant.id, self.admin.id):
            heldConversation = container.createGroupUseCase().execute(
                CreateGroupConversationCommand(name="held")
            )
            heldMessage = container.sendMessageUseCase().execute(
                SendMessageCommand(conversationId=heldConversation.id, body="held old")
            )
        old = timezone.now() - timedelta(days=30)
        MessageModel.objects.filter(id=self.message.id).update(deletedAt=old)
        MessageModel.objects.filter(id=heldMessage.id).update(deletedAt=old)
        LegalHoldModel.objects.create(
            tenantId=self.tenant.id,
            holdScope="CONVERSATION",
            targetId=heldConversation.id,
            reason="litigation",
            createdById=self.admin.id,
        )
        with asUser(self.tenant.id, self.admin.id):
            preview = container.runRetentionUseCase().execute(
                RunRetentionCommand(retentionDays=7, dryRun=True)
            )
            self.assertEqual(preview["counts"]["messages"], 1)
            self.assertTrue(MessageModel.objects.filter(id=self.message.id).exists())
            executed = container.runRetentionUseCase().execute(
                RunRetentionCommand(retentionDays=7, dryRun=False)
            )
        self.assertEqual(executed["counts"]["messages"], 1)
        self.assertFalse(MessageModel.objects.filter(id=self.message.id).exists())
        self.assertTrue(MessageModel.objects.filter(id=heldMessage.id).exists())
        self.assertEqual(CommunicationRetentionRunModel.objects.count(), 2)

    def testRecordingIntegrityMetadataIsValidatedAndExposed(self) -> None:
        recording = Recording.request(
            self.tenant.id, uuid.uuid4(), self.admin.id, datetime.now(tz=UTC)
        )
        recording.attachStorageRef(
            "document://recording",
            storageKey=f"communication/{self.tenant.id}/recording.webm",
            fileSizeBytes=4096,
            checksum="e" * 64,
        )
        snapshot = recording.snapshot()
        self.assertEqual(snapshot["fileSizeBytes"], 4096)
        self.assertEqual(snapshot["checksum"], "e" * 64)
        with self.assertRaises(ValidationFailedError):
            recording.attachStorageRef("bad", checksum="not-sha256")

    def testMessageListingHasConstantQueryCount(self) -> None:
        with asUser(self.tenant.id, self.member.id):
            for index in range(12):
                container.sendMessageUseCase().execute(
                    SendMessageCommand(conversationId=self.source.id, body=f"message {index}")
                )
            # Warm permission/cache paths so this measures list-size behavior.
            container.listMessagesUseCase().execute(
                ListMessagesQuery(conversationId=self.source.id, limit=1)
            )
            with CaptureQueriesContext(connection) as one:
                container.listMessagesUseCase().execute(
                    ListMessagesQuery(conversationId=self.source.id, limit=1)
                )
            with CaptureQueriesContext(connection) as many:
                container.listMessagesUseCase().execute(
                    ListMessagesQuery(conversationId=self.source.id, limit=50)
                )
        self.assertLessEqual(len(many), len(one) + 1, (len(one), len(many)))

    def testSyncHashIsCanonicalAndRejectsDuplicateOperationIds(self) -> None:
        operation = {"operationId": "x", "kind": "DELETE_MESSAGE", "payload": {"messageId": "1"}}
        self.assertEqual(syncRequestHash([operation]), syncRequestHash([dict(operation)]))
        with self.assertRaises(ValidationFailedError):
            syncRequestHash([operation, operation])
