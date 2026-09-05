"""Phase 13-L provider adapter unit tests (pure, offline, no vendor SDK).

Adapters are exercised through an injected fake transport, so these tests
verify payload construction, response normalization, capability gating,
error mapping, secret redaction, registry integration, and configuration
wiring without any network access.
"""

from __future__ import annotations

import json
import unittest
import uuid
from collections.abc import Iterator
from types import SimpleNamespace
from typing import Any

from apps.ai.domain.entities.aiRecords import AIProvider
from apps.ai.domain.exceptions import (
    AIModelUnavailable,
    AIOutputValidationFailed,
    AIProviderRateLimited,
    AIProviderRegistrationInvalid,
    AIProviderUnavailable,
    AIRequestTimeout,
)
from apps.ai.domain.ports import (
    AIProviderPort,
    DeterministicAIProvider,
    ProviderRequestContext,
)
from apps.ai.domain.registries.providerRegistry import ProviderRegistry
from apps.ai.infrastructure.providers import (
    AnthropicProviderAdapter,
    AzureOpenAiProviderAdapter,
    LocalProviderAdapter,
    OllamaProviderAdapter,
    OpenAiProviderAdapter,
    ProviderAdapterConfig,
    adapterIsConfigured,
    buildProviderAdapter,
)
from apps.ai.infrastructure.providers.providerErrors import (
    TransportConnectionFailed,
    TransportTimeout,
)
from apps.ai.infrastructure.providers.providerHttp import HttpResponse
from apps.ai.infrastructure.providers.providerWiring import (
    buildConfiguredProviderAdapters,
    providerConfigFromSettings,
    readProviderAdapterSettings,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

TENANT_ID = uuid.uuid4()
SECRET_KEY = "sk-super-secret-value-123"


class FakeTransport:
    """Scripted transport double; records requests, returns canned responses."""

    def __init__(self) -> None:
        self.requests: list[dict[str, Any]] = []
        self.responseQueue: list[Any] = []
        self.streamQueue: list[list[str]] = []

    def enqueue(self, response: Any) -> None:
        self.responseQueue.append(response)

    def enqueueStream(self, lines: list[str]) -> None:
        self.streamQueue.append(lines)

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeoutSeconds: float | None = None,
    ) -> HttpResponse:
        self.requests.append(
            {
                "method": method,
                "url": url,
                "payload": payload,
                "headers": headers or {},
                "timeoutSeconds": timeoutSeconds,
            }
        )
        if not self.responseQueue:
            raise AssertionError("FakeTransport has no queued response.")
        item = self.responseQueue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    def streamLines(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeoutSeconds: float | None = None,
    ) -> Iterator[str]:
        self.requests.append(
            {"method": method, "url": url, "payload": payload, "headers": headers or {}}
        )
        if not self.streamQueue:
            raise AssertionError("FakeTransport has no queued stream.")
        lines = self.streamQueue.pop(0)
        if isinstance(lines, Exception):
            raise lines
        return iter(lines)


def jsonResponse(status: int, body: dict[str, Any]) -> HttpResponse:
    return HttpResponse(status=status, body=json.dumps(body).encode("utf-8"))


def openAiChatBody(content: str = "hello back") -> dict[str, Any]:
    return {
        "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
        "usage": {"prompt_tokens": 3, "completion_tokens": 5},
    }


def makeOpenAi(transport: FakeTransport) -> OpenAiProviderAdapter:
    return OpenAiProviderAdapter(
        baseUrl="https://provider.test/v1",
        apiKey=SECRET_KEY,
        transport=transport,
    )


class ProviderFactoryTests(unittest.TestCase):
    def testFactoryBuildsEveryDocumentedAdapterType(self) -> None:
        deterministic = buildProviderAdapter(ProviderAdapterConfig(providerType="deterministic"))
        self.assertIsInstance(deterministic, DeterministicAIProvider)
        ollama = buildProviderAdapter(ProviderAdapterConfig(providerType="ollama"))
        self.assertIsInstance(ollama, OllamaProviderAdapter)
        local = buildProviderAdapter(
            ProviderAdapterConfig(providerType="local", baseUrl="http://local.test")
        )
        self.assertIsInstance(local, LocalProviderAdapter)
        openAi = buildProviderAdapter(
            ProviderAdapterConfig(providerType="openai", apiKey=SECRET_KEY)
        )
        self.assertIsInstance(openAi, OpenAiProviderAdapter)
        azure = buildProviderAdapter(
            ProviderAdapterConfig(
                providerType="azure_openai",
                baseUrl="https://azure.test",
                apiKey=SECRET_KEY,
                apiVersion="2024-10-21",
            )
        )
        self.assertIsInstance(azure, AzureOpenAiProviderAdapter)
        anthropic = buildProviderAdapter(
            ProviderAdapterConfig(providerType="anthropic", apiKey=SECRET_KEY)
        )
        self.assertIsInstance(anthropic, AnthropicProviderAdapter)

    def testFactoryRejectsUnknownTypesAndIncompleteConfiguration(self) -> None:
        with self.assertRaises(ValidationFailedError):
            buildProviderAdapter(ProviderAdapterConfig(providerType="NOPE"))
        with self.assertRaises(AIProviderUnavailable):
            buildProviderAdapter(ProviderAdapterConfig(providerType="openai"))
        with self.assertRaises(AIProviderUnavailable):
            buildProviderAdapter(
                ProviderAdapterConfig(providerType="azure_openai", apiKey=SECRET_KEY)
            )
        with self.assertRaises(AIProviderUnavailable):
            buildProviderAdapter(ProviderAdapterConfig(providerType="local"))

    def testConfiguredPredicateMatchesPerTypeRequirements(self) -> None:
        self.assertTrue(
            adapterIsConfigured(ProviderAdapterConfig(providerType="openai", apiKey="k"))
        )
        self.assertFalse(adapterIsConfigured(ProviderAdapterConfig(providerType="openai")))
        self.assertTrue(adapterIsConfigured(ProviderAdapterConfig(providerType="ollama")))
        self.assertTrue(adapterIsConfigured(ProviderAdapterConfig(providerType="deterministic")))
        self.assertFalse(
            adapterIsConfigured(ProviderAdapterConfig(providerType="azure_openai", apiKey="k"))
        )
        self.assertTrue(
            adapterIsConfigured(
                ProviderAdapterConfig(
                    providerType="azure_openai", apiKey="k", baseUrl="https://azure.test"
                )
            )
        )

    def testEveryAdapterSatisfiesThePortProtocolAndCodeHandshake(self) -> None:
        transport = FakeTransport()
        adapters = [
            makeOpenAi(transport),
            AzureOpenAiProviderAdapter(
                baseUrl="https://azure.test", apiKey=SECRET_KEY, transport=transport
            ),
            OllamaProviderAdapter(transport=transport),
            AnthropicProviderAdapter(apiKey=SECRET_KEY, transport=transport),
            LocalProviderAdapter(baseUrl="http://local.test", transport=transport),
            DeterministicAIProvider(),
        ]
        expectedCodes = {"OPENAI", "AZURE_OPENAI", "OLLAMA", "ANTHROPIC", "LOCAL", "DETERMINISTIC"}
        for adapter in adapters:
            with self.subTest(code=adapter.providerCode):
                self.assertIsInstance(adapter, AIProviderPort)
                self.assertIn(adapter.providerCode, expectedCodes)
                self.assertEqual(adapter.capabilities.providerCode, adapter.providerCode)
                self.assertTrue(adapter.capabilities.supports("GENERATION"))


class OpenAiAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = makeOpenAi(self.transport)
        self.context = ProviderRequestContext(
            tenantId=TENANT_ID, requestId=uuid.uuid4(), idempotencyKey="idem-1"
        )

    def testGenerateBuildsChatPayloadAndNormalizesResult(self) -> None:
        self.transport.enqueue(jsonResponse(200, openAiChatBody()))
        result = self.adapter.generate(
            prompt="Hello",
            systemInstruction="Be brief",
            model="gpt-test",
            temperature=0.25,
            maxTokens=64,
            context=self.context,
        )
        sent = self.transport.requests[0]
        self.assertEqual(sent["url"], "https://provider.test/v1/chat/completions")
        self.assertEqual(sent["payload"]["model"], "gpt-test")
        self.assertEqual(sent["payload"]["messages"][0], {"role": "system", "content": "Be brief"})
        self.assertEqual(sent["payload"]["messages"][1], {"role": "user", "content": "Hello"})
        self.assertEqual(sent["payload"]["max_tokens"], 64)
        self.assertNotIn("response_format", sent["payload"])
        self.assertEqual(sent["headers"]["Authorization"], f"Bearer {SECRET_KEY}")
        self.assertEqual(sent["headers"]["X-Correlation-Id"], self.context.correlationId)
        self.assertEqual(sent["headers"]["X-Trace-Id"], self.context.traceId)
        self.assertEqual(result.content, "hello back")
        self.assertEqual(result.inputTokens, 3)
        self.assertEqual(result.outputTokens, 5)
        self.assertEqual(result.totalTokens, 8)
        self.assertEqual(result.finishReason, "STOP")
        self.assertEqual(result.provider, "openai")
        self.assertEqual(result.model, "gpt-test")
        self.assertEqual(result.requestId, self.context.requestId)
        self.assertEqual(result.correlationId, self.context.correlationId)

    def testStructuredGenerationSendsJsonSchemaAndParsesStructuredOutput(self) -> None:
        schema = {
            "type": "object",
            "properties": {"summary": {"type": "string"}},
            "required": ["summary"],
        }
        self.transport.enqueue(jsonResponse(200, openAiChatBody(content='{"summary": "done"}')))
        result = self.adapter.generateStructured(
            prompt="Summarize", model="gpt-test", jsonSchema=schema, context=self.context
        )
        sent = self.transport.requests[0]
        responseFormat = sent["payload"]["response_format"]
        self.assertEqual(responseFormat["type"], "json_schema")
        self.assertEqual(responseFormat["json_schema"]["schema"], schema)
        self.assertEqual(result.structuredData, {"summary": "done"})
        self.assertEqual(result.content, "")

    def testJsonResponseWithoutSchemaUsesJsonObjectMode(self) -> None:
        self.transport.enqueue(jsonResponse(200, openAiChatBody(content='{"ok": true}')))
        result = self.adapter.generate(
            prompt="Give JSON", model="gpt-test", responseFormat="json", context=self.context
        )
        self.assertEqual(
            self.transport.requests[0]["payload"]["response_format"], {"type": "json_object"}
        )
        self.assertEqual(result.structuredData, {"ok": True})

    def testStructuredOutputThatIsNotValidJsonFailsValidation(self) -> None:
        self.transport.enqueue(jsonResponse(200, openAiChatBody(content="not-json")))
        with self.assertRaises(AIOutputValidationFailed):
            self.adapter.generateStructured(
                prompt="Summarize", model="gpt-test", jsonSchema={"type": "object"}
            )

    def testStreamParsesServerSentEventsAndEmitsFinalChunk(self) -> None:
        self.transport.enqueueStream(
            [
                'data: {"choices": [{"delta": {"content": "Hel"}}]}',
                'data: {"choices": [{"delta": {"content": "lo"}, "finish_reason": "stop"}]}',
                "data: [DONE]",
            ]
        )
        chunks = list(self.adapter.stream(prompt="Hi", model="gpt-test", context=self.context))
        self.assertEqual([chunk.content for chunk in chunks], ["Hel", "lo", ""])
        self.assertFalse(chunks[0].isFinal)
        self.assertTrue(chunks[-1].isFinal)
        self.assertEqual(chunks[-1].finishReason, "STOP")
        self.assertEqual(chunks[0].provider, "openai")
        self.assertEqual(chunks[0].correlationId, self.context.correlationId)
        self.assertEqual(self.transport.requests[0]["payload"]["stream"], True)

    def testEmbedAndEmbedBatchNormalizeVectorsAndDetectMismatch(self) -> None:
        self.transport.enqueue(
            jsonResponse(
                200,
                {
                    "data": [{"embedding": [0.1, 0.2, 0.3]}],
                    "usage": {"prompt_tokens": 2},
                },
            )
        )
        vector = self.adapter.embed(text="hello", model="embed-test", context=self.context)
        self.assertEqual(vector, [0.1, 0.2, 0.3])
        sent = self.transport.requests[0]
        self.assertEqual(sent["url"], "https://provider.test/v1/embeddings")
        self.assertEqual(sent["payload"], {"model": "embed-test", "input": ["hello"]})

        self.transport.enqueue(
            jsonResponse(200, {"data": [{"embedding": [0.5]}], "usage": {"prompt_tokens": 1}})
        )
        with self.assertRaises(AIOutputValidationFailed):
            self.adapter.embedBatch(texts=["a", "b"], model="embed-test")

    def testTokenCountingIsDeterministicOfflineEstimate(self) -> None:
        first = self.adapter.countTokens(text="count these words", model="gpt-test")
        second = self.adapter.countTokens(text="count these words", model="gpt-test")
        self.assertEqual(first, second)
        self.assertGreater(first, 0)
        self.assertEqual(self.adapter.countTokens(text="   ", model="gpt-test"), 0)

    def testHealthCheckReportsHealthyWithoutLeakingSecrets(self) -> None:
        self.transport.enqueue(jsonResponse(200, {"data": []}))
        health = self.adapter.healthCheck()
        self.assertEqual(health.status, "HEALTHY")
        self.assertNotIn(SECRET_KEY, health.detail)
        self.assertEqual(self.transport.requests[0]["url"], "https://provider.test/v1/models")

    def testHealthCheckReportsUnavailableInsteadOfRaising(self) -> None:
        self.transport.enqueue(TransportConnectionFailed("no route"))
        health = self.adapter.healthCheck()
        self.assertEqual(health.status, "UNAVAILABLE")
        self.assertNotIn(SECRET_KEY, health.detail)


class OpenAiErrorMappingTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = makeOpenAi(self.transport)

    def generate(self) -> None:
        self.adapter.generate(prompt="x", model="gpt-test")

    def testRateLimitStatusMapsToDomainError(self) -> None:
        self.transport.enqueue(jsonResponse(429, {"error": {"message": "slow down"}}))
        with self.assertRaises(AIProviderRateLimited):
            self.generate()

    def testMissingModelMapsToModelUnavailable(self) -> None:
        self.transport.enqueue(
            jsonResponse(404, {"error": {"message": f"model gone {SECRET_KEY}"}})
        )
        with self.assertRaises(AIModelUnavailable) as captured:
            self.generate()
        self.assertNotIn(SECRET_KEY, str(captured.exception))

    def testCredentialRejectionMapsToProviderUnavailableWithoutSecret(self) -> None:
        self.transport.enqueue(jsonResponse(401, {"error": {"message": f"bad key {SECRET_KEY}"}}))
        with self.assertRaises(AIProviderUnavailable) as captured:
            self.generate()
        self.assertNotIn(SECRET_KEY, str(captured.exception))

    def testInvalidRequestIsNotRetryableValidation(self) -> None:
        self.transport.enqueue(jsonResponse(400, {"error": {"message": "bad prompt"}}))
        with self.assertRaises(ValidationFailedError):
            self.generate()

    def testServerErrorMapsToProviderUnavailable(self) -> None:
        self.transport.enqueue(jsonResponse(503, {"error": {"message": "overloaded"}}))
        with self.assertRaises(AIProviderUnavailable):
            self.generate()

    def testTimeoutMapsToRequestTimeout(self) -> None:
        self.transport.enqueue(TransportTimeout("slow"))
        with self.assertRaises(AIRequestTimeout):
            self.generate()

    def testConnectionFailureMapsToProviderUnavailable(self) -> None:
        self.transport.enqueue(TransportConnectionFailed("refused"))
        with self.assertRaises(AIProviderUnavailable):
            self.generate()

    def testNonJsonSuccessBodyMapsToOutputValidation(self) -> None:
        self.transport.enqueue(HttpResponse(status=200, body=b"<html>gateway</html>"))
        with self.assertRaises(AIOutputValidationFailed):
            self.generate()

    def testUnexpectedPayloadShapeMapsToOutputValidation(self) -> None:
        self.transport.enqueue(jsonResponse(200, {"unexpected": True}))
        with self.assertRaises(AIOutputValidationFailed):
            self.generate()


class OllamaAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = OllamaProviderAdapter(baseUrl="http://ollama.test", transport=self.transport)

    def testGenerateUsesApiChatWithOptionsAndJsonFormat(self) -> None:
        self.transport.enqueue(
            jsonResponse(
                200,
                {
                    "message": {"content": '{"ok": 1}'},
                    "done": True,
                    "done_reason": "stop",
                    "prompt_eval_count": 4,
                    "eval_count": 6,
                },
            )
        )
        result = self.adapter.generate(
            prompt="Hi",
            model="llama-test",
            temperature=0.5,
            maxTokens=32,
            responseFormat="JSON",
        )
        sent = self.transport.requests[0]
        self.assertEqual(sent["url"], "http://ollama.test/api/chat")
        self.assertEqual(sent["payload"]["format"], "json")
        self.assertEqual(sent["payload"]["options"], {"temperature": 0.5, "num_predict": 32})
        self.assertFalse(sent["payload"]["stream"])
        self.assertEqual(sent["headers"].get("Authorization"), None)
        self.assertEqual(result.structuredData, {"ok": 1})
        self.assertEqual(result.inputTokens, 4)
        self.assertEqual(result.outputTokens, 6)
        self.assertEqual(result.provider, "ollama")

    def testStreamParsesNdjsonUntilDone(self) -> None:
        self.transport.enqueueStream(
            [
                json.dumps({"message": {"content": "He"}}),
                json.dumps({"message": {"content": "llo"}, "done": True, "done_reason": "stop"}),
            ]
        )
        chunks = list(self.adapter.stream(prompt="Hi", model="llama-test"))
        self.assertEqual([chunk.content for chunk in chunks], ["He", "llo", ""])
        self.assertTrue(chunks[-1].isFinal)
        self.assertEqual(chunks[-1].finishReason, "STOP")

    def testEmbeddingsUseApiEmbedContract(self) -> None:
        self.transport.enqueue(jsonResponse(200, {"embeddings": [[0.25, 0.75]]}))
        vector = self.adapter.embed(text="hello", model="embed-model")
        self.assertEqual(vector, [0.25, 0.75])
        sent = self.transport.requests[0]
        self.assertEqual(sent["url"], "http://ollama.test/api/embed")
        self.assertEqual(sent["payload"], {"model": "embed-model", "input": ["hello"]})

    def testHealthProbesTagsEndpoint(self) -> None:
        self.transport.enqueue(jsonResponse(200, {"models": []}))
        health = self.adapter.healthCheck()
        self.assertEqual(health.status, "HEALTHY")
        self.assertEqual(self.transport.requests[0]["url"], "http://ollama.test/api/tags")


class AnthropicAdapterTests(unittest.TestCase):
    def setUp(self) -> None:
        self.transport = FakeTransport()
        self.adapter = AnthropicProviderAdapter(
            baseUrl="https://anthropic.test", apiKey=SECRET_KEY, transport=self.transport
        )

    def testGenerateBuildsMessagesPayloadWithApiKeyHeader(self) -> None:
        self.transport.enqueue(
            jsonResponse(
                200,
                {
                    "content": [{"type": "text", "text": "hi"}],
                    "stop_reason": "end_turn",
                    "usage": {"input_tokens": 2, "output_tokens": 3},
                },
            )
        )
        result = self.adapter.generate(prompt="Hello", systemInstruction="Sys", model="claude-test")
        sent = self.transport.requests[0]
        self.assertEqual(sent["url"], "https://anthropic.test/v1/messages")
        self.assertEqual(sent["headers"]["x-api-key"], SECRET_KEY)
        self.assertEqual(sent["headers"]["anthropic-version"], "2023-06-01")
        self.assertEqual(sent["payload"]["system"], "Sys")
        self.assertEqual(sent["payload"]["max_tokens"], 1024)
        self.assertEqual(result.content, "hi")
        self.assertEqual(result.finishReason, "STOP")
        self.assertEqual(result.provider, "anthropic")

    def testEmbeddingAndStructuredAreRejectedByCapabilityGate(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.adapter.embed(text="hello", model="none")
        with self.assertRaises(ValidationFailedError):
            self.adapter.generateStructured(
                prompt="x", model="claude-test", jsonSchema={"type": "object"}
            )

    def testStreamParsesContentBlockDeltasAndStopReason(self) -> None:
        self.transport.enqueueStream(
            [
                'data: {"type": "content_block_delta", "delta": {"text": "He"}}',
                'data: {"type": "content_block_delta", "delta": {"text": "llo"}}',
                'data: {"type": "message_delta", "delta": {"stop_reason": "end_turn"}}',
                'data: {"type": "message_stop"}',
            ]
        )
        chunks = list(self.adapter.stream(prompt="Hi", model="claude-test"))
        self.assertEqual([chunk.content for chunk in chunks], ["He", "llo", ""])
        self.assertEqual(chunks[-1].finishReason, "STOP")
        self.assertTrue(chunks[-1].isFinal)


class AzureAndLocalAdapterTests(unittest.TestCase):
    def testAzureUsesDeploymentUrlsAndApiKeyHeader(self) -> None:
        transport = FakeTransport()
        adapter = AzureOpenAiProviderAdapter(
            baseUrl="https://azure.test",
            apiKey=SECRET_KEY,
            apiVersion="2024-10-21",
            transport=transport,
        )
        transport.enqueue(jsonResponse(200, openAiChatBody()))
        adapter.generate(prompt="Hi", model="deploy-1")
        sent = transport.requests[0]
        self.assertEqual(
            sent["url"],
            "https://azure.test/openai/deployments/deploy-1/chat/completions"
            "?api-version=2024-10-21",
        )
        self.assertEqual(sent["headers"]["api-key"], SECRET_KEY)
        self.assertNotIn("Authorization", sent["headers"])
        self.assertEqual(adapter.providerCode, "AZURE_OPENAI")
        self.assertEqual(adapter.capabilities.providerCode, "AZURE_OPENAI")
        self.assertEqual(
            adapter.embeddingUrl("deploy-1"),
            "https://azure.test/openai/deployments/deploy-1/embeddings?api-version=2024-10-21",
        )
        self.assertEqual(
            adapter.healthUrl(), "https://azure.test/openai/models?api-version=2024-10-21"
        )

    def testAzureRequiresApiVersion(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AzureOpenAiProviderAdapter(baseUrl="https://azure.test", apiKey="k", apiVersion=" ")

    def testLocalAdapterUsesProviderNeutralContract(self) -> None:
        transport = FakeTransport()
        adapter = LocalProviderAdapter(
            baseUrl="http://local.test",
            supportsEmbedding=True,
            transport=transport,
        )
        transport.enqueue(
            jsonResponse(
                200,
                {
                    "content": "",
                    "structuredData": {"verdict": "ok"},
                    "inputTokens": 2,
                    "outputTokens": 4,
                    "finishReason": "STOP",
                },
            )
        )
        result = adapter.generateStructured(
            prompt="Check", model="enterprise-model", jsonSchema={"type": "object"}
        )
        sent = transport.requests[0]
        self.assertEqual(sent["url"], "http://local.test/invocations")
        self.assertEqual(sent["payload"]["model"], "enterprise-model")
        self.assertEqual(sent["payload"]["responseFormat"], "JSON")
        self.assertEqual(result.structuredData, {"verdict": "ok"})
        self.assertEqual(result.provider, "local")

        transport.enqueue(jsonResponse(200, {"vectors": [[0.1, 0.9]]}))
        vector = adapter.embed(text="hello", model="enterprise-embed")
        self.assertEqual(vector, [0.1, 0.9])

    def testLocalAdapterWithoutEmbeddingGatesTheFeature(self) -> None:
        adapter = LocalProviderAdapter(baseUrl="http://local.test", transport=FakeTransport())
        with self.assertRaises(ValidationFailedError):
            adapter.embed(text="hello", model="m")

    def testAdaptersRequireBaseUrlOrKeyAtConstruction(self) -> None:
        with self.assertRaises(AIProviderUnavailable):
            OpenAiProviderAdapter(baseUrl="", apiKey=SECRET_KEY)
        with self.assertRaises(AIProviderUnavailable):
            OpenAiProviderAdapter(baseUrl="https://x.test", apiKey="")
        with self.assertRaises(AIProviderUnavailable):
            AnthropicProviderAdapter(baseUrl="https://x.test", apiKey="")
        with self.assertRaises(AIProviderUnavailable):
            LocalProviderAdapter(baseUrl="")
        with self.assertRaises(ValidationFailedError):
            OllamaProviderAdapter(baseUrl="http://x.test", timeoutSeconds=0)


class ProviderWiringAndRegistryTests(unittest.TestCase):
    def testWiringBuildsOnlyConfiguredAdaptersAndSkipsIncompleteOnes(self) -> None:
        stubSettings = SimpleNamespace(
            AI_PROVIDER_ADAPTERS={
                "OPENAI": {"apiKey": ""},
                "OLLAMA": {"baseUrl": "http://ollama.test"},
                "LOCAL": {"baseUrl": "http://local.test"},
                "AZURE_OPENAI": {"baseUrl": "", "apiKey": ""},
            }
        )
        adapters = buildConfiguredProviderAdapters(stubSettings)
        self.assertEqual(sorted(adapters), ["LOCAL", "OLLAMA"])
        self.assertIsInstance(adapters["OLLAMA"], OllamaProviderAdapter)
        self.assertIsInstance(adapters["LOCAL"], LocalProviderAdapter)

    def testWiringReadsSettingsMappingSafely(self) -> None:
        stubSettings = SimpleNamespace(AI_PROVIDER_ADAPTERS={"OPENAI": {"apiKey": "k"}})
        mapping = readProviderAdapterSettings(stubSettings)
        self.assertEqual(mapping["OPENAI"], {"apiKey": "k"})
        self.assertEqual(readProviderAdapterSettings(SimpleNamespace()), {})
        config = providerConfigFromSettings("OPENAI", {"apiKey": "k", "timeoutSeconds": "12"})
        self.assertEqual(config.apiKey, "k")
        self.assertEqual(config.timeoutSeconds, 12.0)

    def testAdaptersRegisterIntoThePhase13DRegistry(self) -> None:
        transport = FakeTransport()
        adapter = makeOpenAi(transport)
        provider = AIProvider(
            tenantId=TENANT_ID,
            code="OPENAI",
            name="OpenAI",
            providerType="CLOUD_LLM",
        )
        registry = ProviderRegistry()
        registry.registerProvider(provider, adapter)
        resolved = registry.resolveProvider(TENANT_ID, "OPENAI")
        self.assertIs(resolved, adapter)
        descriptor = registry.describeProvider(TENANT_ID, "OPENAI")
        self.assertEqual(descriptor.code, "OPENAI")
        self.assertTrue(descriptor.capabilities.supports("EMBEDDING"))

        transport.enqueue(jsonResponse(200, openAiChatBody()))
        result = resolved.generate(prompt="Hi", model="gpt-test")
        self.assertEqual(result.content, "hello back")

    def testRegistryRejectsMismatchedAdapterCode(self) -> None:
        transport = FakeTransport()
        adapter = makeOpenAi(transport)
        provider = AIProvider(
            tenantId=TENANT_ID,
            code="OLLAMA",
            name="Wrong",
            providerType="LOCAL_LLM",
        )
        registry = ProviderRegistry()
        with self.assertRaises(AIProviderRegistrationInvalid) as captured:
            registry.registerProvider(provider, adapter)
        self.assertIn("codes must match", str(captured.exception))


if __name__ == "__main__":
    unittest.main()
