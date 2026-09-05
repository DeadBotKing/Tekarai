"""Phase 13-M resilience integration tests (real transport, flaky server).

The Phase 13-D registry resolves real ``LocalProviderAdapter`` instances
whose HTTP calls hit a localhost ``ThreadingHTTPServer`` that replays
scripted failure sequences (503 twice, then 200; 429 then 200; permanent
400). These tests prove the domain executor's decisions over the wire:
transient errors are retried exactly as configured, fatal errors stop on
the first request, and fallback recovers on the secondary provider.
No external network or vendor credentials are involved.
"""

from __future__ import annotations

import json
import threading
import time
import unittest
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any

from apps.ai.domain.entities.aiRecords import AIProvider
from apps.ai.domain.exceptions import AIProviderUnavailable
from apps.ai.domain.ports import GenerationRequest
from apps.ai.domain.registries.providerRegistry import ProviderRegistry
from apps.ai.domain.services.providerResilience import (
    MonotonicClock,
    ResilientProviderExecutor,
    RetryPolicy,
    reportFromError,
)
from apps.ai.infrastructure.providers.localProvider import LocalProviderAdapter
from apps.sharedKernel.domain.errors import ValidationFailedError

TENANT_ID = uuid.uuid4()


class RecordingSleeper:
    """Records delays and actually sleeps (tiny values keep tests fast)."""

    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)
        if seconds > 0:
            time.sleep(min(seconds, 0.05))


class PrimaryAdapter(LocalProviderAdapter):
    providerCode = "PRIMARY"


class SecondaryAdapter(LocalProviderAdapter):
    providerCode = "SECONDARY"


class FlakyStubHandler(BaseHTTPRequestHandler):
    """Serves scripted failure sequences; counts requests per path."""

    requestCounts: dict[str, int] = {}
    countsLock = threading.Lock()

    def log_message(self, *args: Any) -> None:  # silence request logging
        pass

    def _count(self) -> int:
        with FlakyStubHandler.countsLock:
            count = FlakyStubHandler.requestCounts.get(self.path, 0) + 1
            FlakyStubHandler.requestCounts[self.path] = count
            return count

    def _sendJson(self, status: int, body: dict[str, Any]) -> None:
        payload = json.dumps(body).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def _sendLocalSuccess(self) -> None:
        self._sendJson(
            200,
            {
                "content": "recovered-reply",
                "structuredData": {},
                "inputTokens": 3,
                "outputTokens": 5,
                "finishReason": "STOP",
            },
        )

    def do_POST(self) -> None:  # noqa: N802 — http.server hook
        length = int(self.headers.get("Content-Length", "0"))
        if length:
            self.rfile.read(length)
        attempt = self._count()
        if self.path == "/flaky/unavailable":
            if attempt <= 2:
                self._sendJson(503, {"error": {"message": "service restarting"}})
            else:
                self._sendLocalSuccess()
            return
        if self.path == "/flaky/rate-limited":
            if attempt == 1:
                self._sendJson(429, {"error": {"message": "slow down"}})
            else:
                self._sendLocalSuccess()
            return
        if self.path == "/fatal/bad-request":
            self._sendJson(400, {"error": {"message": "malformed prompt"}})
            return
        if self.path == "/always/unavailable":
            self._sendJson(503, {"error": {"message": "permanently down"}})
            return
        if self.path == "/ok":
            self._sendLocalSuccess()
            return
        self._sendJson(404, {"error": {"message": "not found"}})


class Phase13ResilienceContractTests(unittest.TestCase):
    server: ThreadingHTTPServer
    serverThread: threading.Thread
    baseUrl: str

    @classmethod
    def setUpClass(cls) -> None:
        cls.server = ThreadingHTTPServer(("127.0.0.1", 0), FlakyStubHandler)
        cls.serverThread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.serverThread.start()
        cls.baseUrl = f"http://127.0.0.1:{cls.server.server_address[1]}"

    @classmethod
    def tearDownClass(cls) -> None:
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self) -> None:
        with FlakyStubHandler.countsLock:
            FlakyStubHandler.requestCounts.clear()
        self.registry = ProviderRegistry()
        self.sleeper = RecordingSleeper()

    def _register(self, adapter: LocalProviderAdapter) -> None:
        definition = AIProvider(
            tenantId=TENANT_ID,
            code=adapter.providerCode,
            name=f"Integration {adapter.providerCode}",
            providerType="LOCAL",
            configurationReference="secret-ref-only",
            metadata={"notForPersistence": True},
        )
        self.registry.registerProvider(definition, adapter)

    def _executor(self, maxAttempts: int) -> ResilientProviderExecutor:
        return ResilientProviderExecutor(
            self.registry,
            retryPolicy=RetryPolicy(maxAttempts=maxAttempts, initialBackoffSeconds=0.01),
            clock=MonotonicClock(),
            sleeper=self.sleeper,
            timeoutBudgetSeconds=30.0,
        )

    def _request(self) -> GenerationRequest:
        return GenerationRequest(prompt="ping", model="integration-model")

    def requestCount(self, path: str) -> int:
        with FlakyStubHandler.countsLock:
            return FlakyStubHandler.requestCounts.get(path, 0)

    def testTransient503IsRetriedUntilSuccessOverRealTransport(self) -> None:
        self._register(PrimaryAdapter(baseUrl=self.baseUrl, invocationPath="/flaky/unavailable"))
        outcome = self._executor(maxAttempts=3).execute(
            TENANT_ID, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(outcome.result.content, "recovered-reply")
        self.assertEqual(outcome.result.provider, "local")
        self.assertEqual(self.requestCount("/flaky/unavailable"), 3)
        self.assertEqual(outcome.report.attemptsCount, 3)
        self.assertEqual(len(self.sleeper.sleeps), 2)
        self.assertFalse(outcome.report.fallbackUsed)

    def testRateLimit429IsRetriedOverRealTransport(self) -> None:
        self._register(
            PrimaryAdapter(baseUrl=self.baseUrl, invocationPath="/flaky/rate-limited")
        )
        outcome = self._executor(maxAttempts=3).execute(
            TENANT_ID, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(self.requestCount("/flaky/rate-limited"), 2)
        self.assertEqual(outcome.report.attemptsCount, 2)

    def testFatalClientErrorIsNotRetriedAndStopsOnFirstRequest(self) -> None:
        self._register(PrimaryAdapter(baseUrl=self.baseUrl, invocationPath="/fatal/bad-request"))
        self._register(SecondaryAdapter(baseUrl=self.baseUrl, invocationPath="/ok"))
        with self.assertRaises(ValidationFailedError) as captured:
            self._executor(maxAttempts=3).execute(
                TENANT_ID,
                "PRIMARY",
                lambda adapter: adapter.generateRequest(self._request()),
                fallbackProviderCodes=("SECONDARY",),
            )
        self.assertEqual(self.requestCount("/fatal/bad-request"), 1)
        self.assertEqual(self.requestCount("/ok"), 0)
        report = reportFromError(captured.exception)
        assert report is not None
        self.assertFalse(report.success)
        self.assertEqual(report.attemptsCount, 1)
        self.assertFalse(report.fallbackUsed)

    def testFallbackRecoversOnSecondaryWhenPrimaryStaysDown(self) -> None:
        self._register(PrimaryAdapter(baseUrl=self.baseUrl, invocationPath="/always/unavailable"))
        self._register(SecondaryAdapter(baseUrl=self.baseUrl, invocationPath="/ok"))
        outcome = self._executor(maxAttempts=2).execute(
            TENANT_ID,
            "PRIMARY",
            lambda adapter: adapter.generateRequest(self._request()),
            fallbackProviderCodes=("SECONDARY",),
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(outcome.report.finalProviderCode, "SECONDARY")
        self.assertTrue(outcome.report.fallbackUsed)
        self.assertEqual(self.requestCount("/always/unavailable"), 2)
        self.assertEqual(self.requestCount("/ok"), 1)
        self.assertEqual(outcome.result.content, "recovered-reply")

    def testExhaustedChainOverRealTransportCarriesTheFinalReport(self) -> None:
        self._register(PrimaryAdapter(baseUrl=self.baseUrl, invocationPath="/always/unavailable"))
        with self.assertRaises(AIProviderUnavailable) as captured:
            self._executor(maxAttempts=2).execute(
                TENANT_ID, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
            )
        self.assertEqual(self.requestCount("/always/unavailable"), 2)
        report = reportFromError(captured.exception)
        assert report is not None
        self.assertFalse(report.success)
        self.assertEqual(report.finalErrorCode, "AI_PROVIDER_UNAVAILABLE")
        self.assertEqual(report.attemptsCount, 2)
        self.assertEqual(report.finalProviderCode, "PRIMARY")


if __name__ == "__main__":
    unittest.main()
