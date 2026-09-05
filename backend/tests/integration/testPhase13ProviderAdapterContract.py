"""Phase 13-L provider adapter integration tests (real local HTTP server).

These tests run the standard-library transport against an actual
``http.server`` on localhost: payload delivery, SSE/NDJSON streaming,
error mapping over the wire, timeout classification, secret redaction, and
health probes. No external network or vendor credentials are involved.
"""

from __future__ import annotations

import json
import threading
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from apps.ai.domain.exceptions import (
    AIProviderRateLimited,
    AIProviderUnavailable,
    AIRequestTimeout,
)
from apps.ai.domain.ports import ProviderRequestContext
from apps.ai.infrastructure.providers import (
    LocalProviderAdapter,
    OllamaProviderAdapter,
    OpenAiProviderAdapter,
)

TENANT_ID = uuid.uuid4()
SECRET_KEY = "sk-integration-secret-999"


class ProviderStubHandler(BaseHTTPRequestHandler):
    """Routes requests to canned vendor-shaped responses on localhost."""

    def log_message(self, *args: Any) -> None:  # silence request logging
        pass

    def _sendJson(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _sendSse(self, events: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        for event in events:
            self.wfile.write(f"data: {event}\n\n".encode())
            self.wfile.flush()

    def _sendNdjson(self, events: list[str]) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "application/x-ndjson")
        self.end_headers()
        for event in events:
            self.wfile.write(f"{event}\n".encode())
            self.wfile.flush()

    def do_POST(self) -> None:  # noqa: N802 — http.server hook
        length = int(self.headers.get("Content-Length", "0"))
        body = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
        if self.path == "/v1/chat/completions":
            if body.get("stream"):
                self._sendSse(
                    [
                        json.dumps({"choices": [{"delta": {"content": "Re"}}]}),
                        json.dumps(
                            {"choices": [{"delta": {"content": "al"}, "finish_reason": "stop"}]}
                        ),
                        "[DONE]",
                    ]
                )
                return
            self._sendJson(
                200,
                {
                    "choices": [{"message": {"content": "real-reply"}, "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 2, "completion_tokens": 4},
                },
            )
            return
        if self.path == "/v1/embeddings":
            self._sendJson(
                200,
                {"data": [{"embedding": [0.5, -0.5]}], "usage": {"prompt_tokens": 1}},
            )
            return
        if self.path == "/api/chat":
            self._sendNdjson(
                [
                    json.dumps({"message": {"content": "Lo"}}),
                    json.dumps(
                        {"message": {"content": "cal"}, "done": True, "done_reason": "stop"}
                    ),
                ]
            )
            return
        if self.path == "/err/rate-limited":
            self._sendJson(429, {"error": {"message": "too many requests"}})
            return
        if self.path == "/err/credential":
            # Simulates a vendor echoing credentials in an error body — the
            # adapter must redact the secret before the error surfaces.
            self._sendJson(401, {"error": {"message": f"invalid key {SECRET_KEY}"}})
            return
        if self.path == "/err/slow":
            threading.Event().wait(2.0)
            self._sendJson(200, {})
            return
        self._sendJson(404, {"error": {"message": "not found"}})

    def do_GET(self) -> None:  # noqa: N802 — http.server hook
        if self.path == "/v1/models":
            self._sendJson(200, {"data": []})
            return
        self._sendJson(404, {"error": {"message": "not found"}})


class Phase13ProviderAdapterContractTests(unittest.TestCase):
    server: ThreadingHTTPServer
    serverThread: threading.Thread

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderStubHandler)
        cls.serverThread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.serverThread.start()
        cls.baseUrl = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def makeAdapter(self, timeoutSeconds: float = 5.0) -> OpenAiProviderAdapter:
        return OpenAiProviderAdapter(
            baseUrl=f"{self.baseUrl}/v1",
            apiKey=SECRET_KEY,
            timeoutSeconds=timeoutSeconds,
        )

    def testGenerationRoundTripOverRealTransport(self) -> None:
        context = ProviderRequestContext(tenantId=TENANT_ID, requestId=uuid.uuid4())
        result = self.makeAdapter().generate(
            prompt="Hello", model="gpt-test", temperature=0.1, context=context
        )
        self.assertEqual(result.content, "real-reply")
        self.assertEqual(result.inputTokens, 2)
        self.assertEqual(result.outputTokens, 4)
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.correlationId, context.correlationId)

    def testServerSentEventStreamingOverRealTransport(self) -> None:
        chunks = list(self.makeAdapter().stream(prompt="Stream", model="gpt-test"))
        self.assertEqual([chunk.content for chunk in chunks], ["Re", "al", ""])
        self.assertTrue(chunks[-1].isFinal)
        self.assertEqual(chunks[-1].finishReason, "STOP")

    def testNdjsonStreamingWithOllamaContract(self) -> None:
        adapter = OllamaProviderAdapter(baseUrl=self.baseUrl)
        chunks = list(adapter.stream(prompt="Local", model="llama-test"))
        self.assertEqual([chunk.content for chunk in chunks], ["Lo", "cal", ""])
        self.assertTrue(chunks[-1].isFinal)
        self.assertEqual(chunks[-1].finishReason, "STOP")

    def testEmbeddingRoundTripOverRealTransport(self) -> None:
        vector = self.makeAdapter().embed(text="hello", model="embed-test")
        self.assertEqual(vector, [0.5, -0.5])

    def makeLocalAdapter(
        self, invocationPath: str, timeoutSeconds: float = 5.0
    ) -> LocalProviderAdapter:
        return LocalProviderAdapter(
            baseUrl=self.baseUrl,
            invocationPath=invocationPath,
            timeoutSeconds=timeoutSeconds,
        )

    def testRateLimitOverTheWireMapsToDomainError(self) -> None:
        with self.assertRaises(AIProviderRateLimited):
            self.makeLocalAdapter("/err/rate-limited").generate(prompt="x", model="m")

    def testCredentialErrorRedactsTheSecret(self) -> None:
        adapter = LocalProviderAdapter(
            baseUrl=self.baseUrl, invocationPath="/err/credential", apiKey=SECRET_KEY
        )
        with self.assertRaises(AIProviderUnavailable) as captured:
            adapter.generate(prompt="x", model="m")
        self.assertNotIn(SECRET_KEY, str(captured.exception))

    def testSlowEndpointClassifiesAsTimeout(self) -> None:
        with self.assertRaises(AIRequestTimeout):
            self.makeLocalAdapter("/err/slow", timeoutSeconds=0.5).generate(prompt="x", model="m")

    def testRefusedConnectionMapsToProviderUnavailable(self) -> None:
        adapter = OpenAiProviderAdapter(
            baseUrl="http://127.0.0.1:1/v1", apiKey=SECRET_KEY, timeoutSeconds=2.0
        )
        with self.assertRaises(AIProviderUnavailable):
            adapter.generate(prompt="x", model="gpt-test")
        health = adapter.healthCheck()
        self.assertEqual(health.status, "UNAVAILABLE")
        self.assertNotIn(SECRET_KEY, health.detail)

    def testHealthProbeAgainstLiveEndpoint(self) -> None:
        health = self.makeAdapter().healthCheck()
        self.assertEqual(health.status, "HEALTHY")
        self.assertGreaterEqual(health.latencyMs or 0, 0)


if __name__ == "__main__":
    unittest.main()
