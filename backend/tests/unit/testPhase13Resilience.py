"""Phase 13-M resilience tests: retry, fallback, timeout, error boundary.

Pure Python and offline. Time and sleeping are injected through deterministic
fakes, so every retry/backoff assertion is exact. Providers are scripted
test doubles registered through the Phase 13-D registry.
"""

from __future__ import annotations

import unittest
import uuid
from types import SimpleNamespace

from apps.ai.domain.entities.aiRecords import AIProvider
from apps.ai.domain.exceptions import (
    AIModelUnavailable,
    AIProviderNotRegistered,
    AIProviderRateLimited,
    AIProviderUnavailable,
    AIQuotaExceeded,
    AIRequestTimeout,
)
from apps.ai.domain.ports import (
    AIProviderPort,
    DeterministicAIProvider,
    GenerationRequest,
    GenerationResult,
    ProviderCapabilities,
)
from apps.ai.domain.registries.providerRegistry import ProviderRegistry
from apps.ai.domain.services.providerResilience import (
    OUTCOME_FATAL_ERROR,
    OUTCOME_RETRYABLE_ERROR,
    OUTCOME_SKIPPED,
    OUTCOME_SUCCESS,
    AttemptRecord,
    FallbackPolicy,
    ResilientProviderExecutor,
    RetryPolicy,
    reportFromError,
)
from apps.ai.infrastructure.providers.resilienceWiring import (
    buildFallbackPolicy,
    buildResilientExecutor,
    buildRetryPolicy,
    fallbackStepsFor,
    parseFallbackChain,
    readTimeoutBudgetSeconds,
)
from apps.sharedKernel.domain.errors import PermissionDeniedError, ValidationFailedError


class FakeClock:
    """Deterministic clock: explicit increments plus optional per-read step."""

    def __init__(self, startSeconds: float = 0.0, stepPerRead: float = 0.0) -> None:
        self.now = startSeconds
        self.stepPerRead = stepPerRead

    def monotonicSeconds(self) -> float:
        value = self.now
        self.now += self.stepPerRead
        return value

    def advance(self, seconds: float) -> None:
        self.now += seconds


class FakeSleeper:
    def __init__(self) -> None:
        self.sleeps: list[float] = []

    def sleep(self, seconds: float) -> None:
        self.sleeps.append(seconds)


class ScriptedProvider(DeterministicAIProvider):
    """Adapter whose generateRequest plays back a scripted list of outcomes."""

    def __init__(self, providerCode: str, script: list[object]) -> None:
        self.providerCode = providerCode
        self.capabilities = ProviderCapabilities(
            providerCode=providerCode,
            features=frozenset({"GENERATION", "STRUCTURED_GENERATION", "STREAMING"}),
            maxContextWindow=32_000,
            supportsJsonSchema=True,
            supportsBatchEmbedding=False,
        )
        self.script = list(script)
        self.calls = 0

    def generateRequest(self, request: GenerationRequest) -> GenerationResult:
        self.calls += 1
        if not self.script:
            raise AssertionError(f"Provider '{self.providerCode}' script exhausted.")
        entry = self.script.pop(0)
        if isinstance(entry, BaseException):
            raise entry
        return GenerationResult(
            content=f"[{self.providerCode}] {request.prompt}",
            model=request.model,
            provider=self.providerCode,
        )


def makeProviderDefinition(tenantId: uuid.UUID, code: str) -> AIProvider:
    return AIProvider(
        tenantId=tenantId,
        code=code,
        name=f"Provider {code}",
        providerType="LOCAL",
        configurationReference="secret-ref-only",
        metadata={"notForPersistence": True},
    )


def resilientSettings(**overrides: object) -> SimpleNamespace:
    values: dict[str, object] = {
        "aiRetryMaxAttempts": 3,
        "aiRetryInitialBackoffSeconds": 0.25,
        "aiRetryBackoffMultiplier": 2.0,
        "aiRetryMaxBackoffSeconds": 5.0,
        "aiProviderTimeoutBudgetSeconds": 60.0,
        "aiProviderFallbackChain": "",
    }
    values.update(overrides)
    return SimpleNamespace(AI_RESILIENCE=values)


class RetryPolicyTests(unittest.TestCase):
    def testValidationRejectsBadValues(self) -> None:
        with self.assertRaises(ValidationFailedError):
            RetryPolicy(maxAttempts=0)
        with self.assertRaises(ValidationFailedError):
            RetryPolicy(initialBackoffSeconds=-1.0)
        with self.assertRaises(ValidationFailedError):
            RetryPolicy(backoffMultiplier=0.5)
        with self.assertRaises(ValidationFailedError):
            RetryPolicy(initialBackoffSeconds=2.0, maxBackoffSeconds=1.0)
        with self.assertRaises(ValidationFailedError):
            RetryPolicy(retryableErrorCodes={"X"})  # type: ignore[arg-type]

    def testBackoffScheduleIsDeterministicAndCapped(self) -> None:
        policy = RetryPolicy()
        self.assertEqual(policy.backoffForAttempt(0), 0.25)
        self.assertEqual(policy.backoffForAttempt(1), 0.5)
        self.assertEqual(policy.backoffForAttempt(2), 1.0)
        self.assertEqual(policy.backoffForAttempt(3), 2.0)
        self.assertEqual(policy.backoffForAttempt(10), 5.0)
        with self.assertRaises(ValidationFailedError):
            policy.backoffForAttempt(-1)

    def testClassifierSeparatesTransientFromFatal(self) -> None:
        policy = RetryPolicy()
        self.assertTrue(policy.isTransient(AIRequestTimeout("slow")))
        self.assertTrue(policy.isTransient(AIProviderUnavailable("down")))
        self.assertTrue(policy.isTransient(AIProviderRateLimited("429")))
        self.assertFalse(policy.isTransient(AIModelUnavailable("no model")))
        self.assertFalse(policy.isTransient(AIQuotaExceeded("quota")))
        self.assertFalse(policy.isTransient(PermissionDeniedError(action="ai.generate")))
        self.assertFalse(policy.isTransient(RuntimeError("boom")))


class FallbackPolicyTests(unittest.TestCase):
    def testNormalizationOrderingAndDuplicates(self) -> None:
        policy = FallbackPolicy(providerCodes=(" openai ", "anthropic", "local"))
        self.assertEqual(policy.providerCodes, ("OPENAI", "ANTHROPIC", "LOCAL"))
        self.assertEqual(policy.primaryCode, "OPENAI")
        with self.assertRaises(ValidationFailedError):
            FallbackPolicy(providerCodes=("openai", " OpenAI "))
        with self.assertRaises(ValidationFailedError):
            FallbackPolicy(providerCodes=("openai", " "))
        with self.assertRaises(ValidationFailedError):
            self._primaryCodeOf(FallbackPolicy(providerCodes=()))

    def _primaryCodeOf(self, policy: FallbackPolicy) -> str:
        return policy.primaryCode

    def testStepsAfterKnownAndUnknownAnchor(self) -> None:
        policy = FallbackPolicy(providerCodes=("OPENAI", "ANTHROPIC", "LOCAL"))
        self.assertEqual(policy.stepsAfter("openai"), ("ANTHROPIC", "LOCAL"))
        self.assertEqual(policy.stepsAfter("LOCAL"), ())
        self.assertEqual(policy.stepsAfter("OLLAMA"), ("OPENAI", "ANTHROPIC", "LOCAL"))


class AttemptRecordTests(unittest.TestCase):
    def testValidationRejectsBadRecords(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AttemptRecord(providerCode=" ", attemptNumber=1, outcome=OUTCOME_SUCCESS)
        with self.assertRaises(ValidationFailedError):
            AttemptRecord(providerCode="X", attemptNumber=0, outcome=OUTCOME_SUCCESS)
        with self.assertRaises(ValidationFailedError):
            AttemptRecord(providerCode="X", attemptNumber=1, outcome="MAYBE")
        with self.assertRaises(ValidationFailedError):
            AttemptRecord(
                providerCode="X", attemptNumber=1, outcome=OUTCOME_SUCCESS, backoffSeconds=-0.1
            )


class ResilientExecutorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.registry = ProviderRegistry()
        self.clock = FakeClock()
        self.sleeper = FakeSleeper()

    def _register(self, code: str, adapter: AIProviderPort) -> None:
        self.registry.registerProvider(makeProviderDefinition(self.tenantId, code), adapter)

    def _executor(self, maxAttempts: int = 3, timeoutBudgetSeconds: float | None = None):
        return ResilientProviderExecutor(
            self.registry,
            retryPolicy=RetryPolicy(maxAttempts=maxAttempts),
            clock=self.clock,
            sleeper=self.sleeper,
            timeoutBudgetSeconds=timeoutBudgetSeconds,
        )

    def testSuccessOnFirstAttemptNeedsNoRetry(self) -> None:
        primary = ScriptedProvider("PRIMARY", ["ok"])
        self._register("PRIMARY", primary)
        outcome = self._executor().execute(
            self.tenantId, "primary", lambda adapter: adapter.generateRequest(self._request())
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(outcome.report.finalProviderCode, "PRIMARY")
        self.assertEqual(outcome.report.attemptsCount, 1)
        self.assertFalse(outcome.report.fallbackUsed)
        self.assertEqual(outcome.report.attempts[0].outcome, OUTCOME_SUCCESS)
        self.assertEqual(self.sleeper.sleeps, [])
        self.assertEqual(primary.calls, 1)

    def testRetryableErrorsAreRetriedUntilSuccess(self) -> None:
        script = [
            AIProviderUnavailable("down"),
            AIRequestTimeout("slow"),
            "ok",
        ]
        primary = ScriptedProvider("PRIMARY", script)
        self._register("PRIMARY", primary)
        outcome = self._executor(maxAttempts=3).execute(
            self.tenantId, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(primary.calls, 3)
        self.assertEqual(self.sleeper.sleeps, [0.25, 0.5])
        self.assertEqual(outcome.report.attempts[0].backoffSeconds, 0.25)
        self.assertEqual(outcome.report.attempts[1].backoffSeconds, 0.5)
        self.assertEqual(outcome.report.attempts[1].errorCode, "AI_REQUEST_TIMEOUT")
        self.assertEqual(outcome.report.attempts[2].outcome, OUTCOME_SUCCESS)
        self.assertEqual(outcome.report.totalBackoffSeconds, 0.75)

    def testFatalErrorStopsImmediatelyWithoutFallback(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIModelUnavailable("no model")])
        fallback = ScriptedProvider("FALLBACK", ["should never run"])
        self._register("PRIMARY", primary)
        self._register("FALLBACK", fallback)
        with self.assertRaises(AIModelUnavailable) as captured:
            self._executor().execute(
                self.tenantId,
                "PRIMARY",
                lambda adapter: adapter.generateRequest(self._request()),
                fallbackProviderCodes=("FALLBACK",),
            )
        self.assertEqual(primary.calls, 1)
        self.assertEqual(fallback.calls, 0)
        self.assertEqual(self.sleeper.sleeps, [])
        report = reportFromError(captured.exception)
        self.assertIsNotNone(report)
        assert report is not None
        self.assertFalse(report.success)
        self.assertEqual(report.finalErrorCode, "AI_MODEL_UNAVAILABLE")
        self.assertEqual(report.attempts[0].outcome, OUTCOME_FATAL_ERROR)
        self.assertFalse(report.fallbackUsed)

    def testChainExhaustedRaisesLastRetryableErrorWithReport(self) -> None:
        primary = ScriptedProvider(
            "PRIMARY",
            [AIProviderUnavailable("a"), AIProviderUnavailable("b")],
        )
        fallback = ScriptedProvider(
            "FALLBACK",
            [AIProviderRateLimited("x"), AIProviderRateLimited("y")],
        )
        self._register("PRIMARY", primary)
        self._register("FALLBACK", fallback)
        with self.assertRaises(AIProviderRateLimited) as captured:
            self._executor(maxAttempts=2).execute(
                self.tenantId,
                "PRIMARY",
                lambda adapter: adapter.generateRequest(self._request()),
                fallbackProviderCodes=("FALLBACK", "PRIMARY"),
            )
        report = reportFromError(captured.exception)
        assert report is not None
        self.assertFalse(report.success)
        self.assertEqual(report.attemptsCount, 4)
        self.assertTrue(report.fallbackUsed)
        self.assertEqual(report.finalErrorCode, "AI_PROVIDER_RATE_LIMITED")
        self.assertEqual(report.finalProviderCode, "FALLBACK")
        self.assertEqual(primary.calls, 2)
        self.assertEqual(fallback.calls, 2)
        self.assertEqual(self.sleeper.sleeps, [0.25, 0.25])

    def testTimeoutBudgetStopsTheChainBeforeTheNextAttempt(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIProviderUnavailable("down")] * 5)
        self._register("PRIMARY", primary)
        fastClock = FakeClock(stepPerRead=40.0)
        executor = ResilientProviderExecutor(
            self.registry,
            retryPolicy=RetryPolicy(maxAttempts=3),
            clock=fastClock,
            sleeper=self.sleeper,
            timeoutBudgetSeconds=60.0,
        )
        with self.assertRaises(AIRequestTimeout) as captured:
            executor.execute(
                self.tenantId, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
            )
        self.assertEqual(primary.calls, 1)
        report = reportFromError(captured.exception)
        assert report is not None
        self.assertFalse(report.success)
        self.assertEqual(report.finalErrorCode, "AI_REQUEST_TIMEOUT")
        self.assertEqual(report.attemptsCount, 1)

    def testFallbackWalksChainAndSucceedsOnSecondary(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIProviderUnavailable("down")] * 3)
        secondary = ScriptedProvider("SECONDARY", ["ok"])
        self._register("PRIMARY", primary)
        self._register("SECONDARY", secondary)
        outcome = self._executor().execute(
            self.tenantId,
            "PRIMARY",
            lambda adapter: adapter.generateRequest(self._request()),
            fallbackProviderCodes=("SECONDARY",),
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(outcome.report.finalProviderCode, "SECONDARY")
        self.assertTrue(outcome.report.fallbackUsed)
        self.assertEqual(outcome.report.attemptsCount, 4)
        self.assertEqual(secondary.calls, 1)

    def testUnresolvableFallbackStepIsSkippedNotFatal(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIProviderUnavailable("down")] * 3)
        tertiary = ScriptedProvider("TERTIARY", ["ok"])
        self._register("PRIMARY", primary)
        self._register("TERTIARY", tertiary)
        recorder: list[AttemptRecord] = []
        executor = ResilientProviderExecutor(
            self.registry,
            retryPolicy=RetryPolicy(maxAttempts=3),
            clock=self.clock,
            sleeper=self.sleeper,
            recorder=recorder.append,
        )
        outcome = executor.execute(
            self.tenantId,
            "PRIMARY",
            lambda adapter: adapter.generateRequest(self._request()),
            fallbackProviderCodes=("MISSING", "TERTIARY"),
        )
        self.assertTrue(outcome.report.success)
        skipped = [r for r in outcome.report.attempts if r.outcome == OUTCOME_SKIPPED]
        self.assertEqual(len(skipped), 1)
        self.assertEqual(skipped[0].providerCode, "MISSING")
        self.assertEqual(skipped[0].errorCode, "AI_PROVIDER_NOT_REGISTERED")
        self.assertEqual([r.outcome for r in recorder].count(OUTCOME_SKIPPED), 1)

    def testUnresolvablePrimaryRaisesConfigurationErrorImmediately(self) -> None:
        fallback = ScriptedProvider("FALLBACK", ["never"])
        self._register("FALLBACK", fallback)
        with self.assertRaises(AIProviderNotRegistered):
            self._executor().execute(
                self.tenantId,
                "GHOST",
                lambda adapter: adapter.generateRequest(self._request()),
                fallbackProviderCodes=("FALLBACK",),
            )
        self.assertEqual(fallback.calls, 0)

    def testErrorBoundaryWrapsNonDomainExceptionsAsFatal(self) -> None:
        def brokenOperation(adapter: object) -> object:
            raise RuntimeError("vendor internals exploded")

        primary = ScriptedProvider("PRIMARY", ["placeholder"])
        self._register("PRIMARY", primary)
        with self.assertRaises(AIProviderUnavailable) as captured:
            self._executor().execute(self.tenantId, "PRIMARY", brokenOperation)
        self.assertIsInstance(captured.exception.__cause__, RuntimeError)
        report = reportFromError(captured.exception)
        assert report is not None
        self.assertEqual(report.finalErrorCode, "AI_PROVIDER_UNAVAILABLE")
        self.assertEqual(report.attempts[0].outcome, OUTCOME_FATAL_ERROR)

    def testRecorderReceivesEveryRecord(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIProviderUnavailable("down"), "ok"])
        self._register("PRIMARY", primary)
        records: list[AttemptRecord] = []
        executor = ResilientProviderExecutor(
            self.registry,
            retryPolicy=RetryPolicy(maxAttempts=2),
            clock=self.clock,
            sleeper=self.sleeper,
            recorder=records.append,
        )
        executor.execute(
            self.tenantId, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
        )
        self.assertEqual([record.outcome for record in records],
                         [OUTCOME_RETRYABLE_ERROR, OUTCOME_SUCCESS])

    def testGenerateWithFallbackUsesConfiguredChain(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIProviderUnavailable("down")] * 3)
        local = ScriptedProvider("LOCAL", ["ok"])
        self._register("PRIMARY", primary)
        self._register("LOCAL", local)
        executor = self._executor()
        outcome = executor.generateWithFallback(
            self.tenantId,
            "PRIMARY",
            self._request(),
            fallbackProviderCodes=("LOCAL",),
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(outcome.report.finalProviderCode, "LOCAL")
        self.assertEqual(outcome.result.provider, "LOCAL")
        with self.assertRaises(ValidationFailedError):
            executor.generateWithFallback(self.tenantId, "PRIMARY", object())

    def testExecutorRejectsInvalidConstruction(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ResilientProviderExecutor(object())  # type: ignore[arg-type]
        with self.assertRaises(ValidationFailedError):
            ResilientProviderExecutor(self.registry, timeoutBudgetSeconds=0)
        with self.assertRaises(ValidationFailedError):
            self._executor().execute(self.tenantId, "  ", lambda adapter: None)

    def _request(self) -> GenerationRequest:
        return GenerationRequest(prompt="ping", model="test")


class ResilienceWiringTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.registry = ProviderRegistry()

    def _register(self, code: str, adapter: AIProviderPort) -> None:
        self.registry.registerProvider(makeProviderDefinition(self.tenantId, code), adapter)

    def testParseFallbackChainNormalizesAndIgnoresBlanks(self) -> None:
        self.assertEqual(parseFallbackChain(""), ())
        self.assertEqual(parseFallbackChain("   "), ())
        self.assertEqual(
            parseFallbackChain(" openai , anthropic ,, local "),
            ("OPENAI", "ANTHROPIC", "LOCAL"),
        )
        with self.assertRaises(ValidationFailedError):
            parseFallbackChain("openai,openai")

    def testWiringBuildsPoliciesFromSettings(self) -> None:
        settings = resilientSettings(
            aiRetryMaxAttempts=4,
            aiRetryInitialBackoffSeconds=0.1,
            aiProviderFallbackChain="OPENAI,ANTHROPIC,LOCAL",
        )
        policy = buildRetryPolicy(settings)
        self.assertEqual(policy.maxAttempts, 4)
        self.assertEqual(policy.initialBackoffSeconds, 0.1)
        chain = buildFallbackPolicy(settings)
        self.assertEqual(chain.providerCodes, ("OPENAI", "ANTHROPIC", "LOCAL"))
        self.assertEqual(readTimeoutBudgetSeconds(settings), 60.0)
        self.assertEqual(fallbackStepsFor("OPENAI", settings), ("ANTHROPIC", "LOCAL"))
        self.assertEqual(fallbackStepsFor("OLLAMA", settings), ("OPENAI", "ANTHROPIC", "LOCAL"))

    def testWiringRejectsNonPositiveBudget(self) -> None:
        with self.assertRaises(ValidationFailedError):
            readTimeoutBudgetSeconds(resilientSettings(aiProviderTimeoutBudgetSeconds=0))

    def testBuildResilientExecutorRunsEndToEnd(self) -> None:
        primary = ScriptedProvider("PRIMARY", [AIProviderUnavailable("down"), "ok"])
        self._register("PRIMARY", primary)
        settings = resilientSettings(
            aiRetryMaxAttempts=2,
            aiRetryInitialBackoffSeconds=0.0,
            aiProviderFallbackChain="LOCAL",
        )
        executor = buildResilientExecutor(
            self.registry,
            settingsModule=settings,
            clock=FakeClock(),
            sleeper=FakeSleeper(),
        )
        outcome = executor.execute(
            self.tenantId, "PRIMARY", lambda adapter: adapter.generateRequest(self._request())
        )
        self.assertTrue(outcome.report.success)
        self.assertEqual(primary.calls, 2)
        with self.assertRaises(ValidationFailedError):
            buildResilientExecutor(object())  # type: ignore[arg-type]

    def _request(self) -> GenerationRequest:
        return GenerationRequest(prompt="ping", model="test")


if __name__ == "__main__":
    unittest.main()
