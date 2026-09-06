"""Phase 14 REST contract and authentication coverage."""

from __future__ import annotations

import uuid

from tests.integration.testPhase11ApiContract import Phase11ApiBase

V1 = "/api/v1/communication"


class Phase14ApiContractTests(Phase11ApiBase):
    def makeConversation(self, name: str) -> str:
        response = self.client.post(
            f"{V1}/conversations",
            {"kind": "group", "name": name, "memberIds": []},
            format="json",
            **self.auth(),
        )
        self.assertEqual(response.status_code, 201, response.content)
        return response.json()["data"]["id"]

    def testPreflightClientUuidForwardSearchAndSync(self) -> None:
        source = self.makeConversation("Phase 14 source")
        target = self.makeConversation("Phase 14 target")
        preflight = self.client.post(
            f"{V1}/attachments/preflight",
            {
                "fileName": "proof.txt",
                "mimeType": "text/plain",
                "sizeBytes": 12,
                "checksum": "c" * 64,
                "scanStatus": "CLEAN",
                "classification": "CONFIDENTIAL",
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(preflight.status_code, 200, preflight.content)
        attachment = preflight.json()["data"]
        clientMessageId = str(uuid.uuid4())
        sent = self.client.post(
            f"{V1}/conversations/{source}/messages",
            {
                "body": "phase fourteen searchable",
                "messageType": "FILE",
                "clientMessageId": clientMessageId,
                "attachments": [attachment],
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(sent.status_code, 201, sent.content)
        self.assertEqual(sent.json()["data"]["id"], clientMessageId)
        forwarded = self.client.post(
            f"{V1}/messages/{clientMessageId}/forward",
            {"targetConversationId": target, "clientRequestId": "api-forward-1"},
            format="json",
            **self.auth(),
        )
        self.assertEqual(forwarded.status_code, 201, forwarded.content)
        self.assertEqual(forwarded.json()["data"]["forwardedFromId"], clientMessageId)
        search = self.client.get(f"{V1}/search?q=searchable&scope=MESSAGES", **self.auth())
        self.assertEqual(search.status_code, 200, search.content)
        self.assertGreaterEqual(search.json()["data"]["count"], 1)
        sync = self.client.post(
            f"{V1}/sync",
            {
                "clientBatchId": "api-batch-1",
                "operations": [
                    {
                        "operationId": "api-op-1",
                        "kind": "SEND_MESSAGE",
                        "payload": {"conversationId": source, "body": "synced"},
                    }
                ],
            },
            format="json",
            **self.auth(),
        )
        self.assertEqual(sync.status_code, 200, sync.content)
        self.assertEqual(sync.json()["data"]["applied"], 1)

    def testEveryPhase14EndpointRequiresAuthentication(self) -> None:
        messageId = str(uuid.uuid4())
        endpoints = (
            ("get", f"{V1}/search?q=xx", None),
            ("post", f"{V1}/attachments/preflight", {}),
            ("post", f"{V1}/messages/{messageId}/forward", {}),
            ("post", f"{V1}/sync", {}),
            ("post", f"{V1}/retention/runs", {}),
        )
        for method, path, body in endpoints:
            response = getattr(self.client, method)(path, body or {}, format="json")
            self.assertEqual(response.status_code, 401, (method, path, response.content))

    def testUnsafeAttachmentIsRejectedAtTransportBoundary(self) -> None:
        response = self.client.post(
            f"{V1}/attachments/preflight",
            {
                "fileName": "virus.exe",
                "mimeType": "application/octet-stream",
                "sizeBytes": 1,
                "checksum": "d" * 64,
                "scanStatus": "INFECTED",
            },
            format="json",
            **self.auth(),
        )
        self.assertIn(response.status_code, (400, 422))
