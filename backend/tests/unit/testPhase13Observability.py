"""Phase 13-W unit tests — metrics, alerting, health. Fully offline.

Covers the closed metric registry and its types/units, label sanitation
(the §47 guard that keeps free-form text out of a monitoring platform),
the percentile and ratio math, ``AlertRule`` comparisons, the Prometheus
exposition text, the two entities with their lifecycles, the collector
(merge, duplicate refusal, derived metrics), the alert evaluator with its
de-duplication, and the health evaluator's per-component verdicts.

No Django, database, network, provider, or clock dependency.
"""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta

from apps.ai.domain.entities.observabilityRecords import (
    AIAlertEvent,
    AIMetricSnapshot,
    ComponentHealth,
    HealthReport,
    ensureRuleCode,
)
from apps.ai.domain.exceptions import (
    AIAlertRuleInvalid,
    AIMetricInvalid,
    AIObservabilityWindowInvalid,
)
from apps.ai.domain.services.observabilityEngine import (
    AlertEvaluator,
    HealthEvaluator,
    MetricCollector,
    MetricWindow,
    SnapshotBuilder,
)
from apps.ai.domain.valueObjects.observabilityTypes import (
    ALERT_SEVERITIES,
    ALLOWED_LABEL_KEYS,
    HEALTH_STATUSES,
    METRIC_NAMES,
    AlertRule,
    MetricSample,
    average,
    coerceValue,
    defaultAlertRules,
    ensureAlertSeverity,
    ensureMetricName,
    metricDescription,
    metricType,
    metricUnit,
    percentile,
    ratio,
    renderPrometheus,
    sanitizeLabels,
)
from apps.sharedKernel.domain.errors import ValidationFailedError

CLOCK = datetime(2026, 9, 5, 12, 0, 0, tzinfo=UTC)
TENANT = uuid.UUID("f0f0f0f0-f0f0-4f0f-8f0f-f0f0f0f0f0f0")


def window(minutes: int = 60) -> MetricWindow:
    return MetricWindow(start=CLOCK - timedelta(minutes=minutes), end=CLOCK)


def samples(**values: float) -> tuple[MetricSample, ...]:
    return tuple(MetricSample(name=name, value=value, at=CLOCK) for name, value in values.items())


class RegistryTests(unittest.TestCase):
    def testTheSection34MetricsAreAllRegistered(self) -> None:
        for name in (
            "aiRequestsTotal",
            "aiRequestsFailed",
            "aiTokensTotal",
            "aiCostTotal",
            "aiLatencyAverage",
            "aiLatencyP95",
            "aiProviderFailures",
            "aiModelFailures",
            "aiFallbackCount",
            "aiFeedbackScore",
        ):
            self.assertIn(name, METRIC_NAMES)

    def testEveryMetricDeclaresATypeUnitAndDescription(self) -> None:
        for name in METRIC_NAMES:
            self.assertIn(metricType(name), ("COUNTER", "GAUGE", "HISTOGRAM"))
            self.assertTrue(metricUnit(name))
            self.assertTrue(metricDescription(name).endswith("."))

    def testUnknownMetricsAreRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ensureMetricName("aiVibesTotal")
        with self.assertRaises(ValidationFailedError):
            ensureMetricName("")

    def testVocabulariesAreStable(self) -> None:
        self.assertEqual(ALERT_SEVERITIES, ("INFO", "WARNING", "CRITICAL"))
        self.assertEqual(HEALTH_STATUSES, ("HEALTHY", "DEGRADED", "UNHEALTHY", "UNKNOWN"))
        self.assertEqual(ensureAlertSeverity(" critical "), "CRITICAL")


class LabelSafetyTests(unittest.TestCase):
    """§47: metrics leave the tenant boundary, so labels are allow-listed."""

    def testOnlyAllowListedKeysSurvive(self) -> None:
        cleaned = sanitizeLabels(
            {"provider": "OPENAI", "userEmail": "person@example.com", "prompt": "secret"}
        )
        self.assertEqual(cleaned, {"provider": "OPENAI"})
        for key in cleaned:
            self.assertIn(key, ALLOWED_LABEL_KEYS)

    def testValuesAreCharacterSafeAndBounded(self) -> None:
        cleaned = sanitizeLabels({"model": "gpt 4o\n(preview)", "kind": "x" * 200})
        self.assertEqual(cleaned["model"], "gpt_4o_preview_")
        self.assertEqual(len(cleaned["kind"]), 64)

    def testEmptyAndForeignInput(self) -> None:
        self.assertEqual(sanitizeLabels(None), {})
        self.assertEqual(sanitizeLabels({"provider": "  "}), {})
        with self.assertRaises(ValidationFailedError):
            sanitizeLabels(["provider"])  # type: ignore[arg-type]

    def testASampleSanitizesOnConstruction(self) -> None:
        sample = MetricSample(
            name="aiRequestsTotal", value=3, labels={"provider": "openai", "secret": "x"}
        )
        self.assertEqual(sample.labels, {"provider": "openai"})
        self.assertEqual(sample.key, "aiRequestsTotal{provider=openai}")


class MetricMathTests(unittest.TestCase):
    def testValuesMustBeFiniteNumbers(self) -> None:
        self.assertEqual(coerceValue("3.5"), 3.5)
        with self.assertRaises(ValidationFailedError):
            coerceValue(float("inf"))
        with self.assertRaises(ValidationFailedError):
            coerceValue("many")

    def testPercentileUsesNearestRank(self) -> None:
        values = [10, 20, 30, 40, 50, 60, 70, 80, 90, 100]
        self.assertEqual(percentile(values, 0.95), 100)
        self.assertEqual(percentile(values, 0.5), 50)
        self.assertEqual(percentile([42], 0.95), 42)
        self.assertEqual(percentile([], 0.95), 0.0)

    def testPercentileAlwaysReturnsAnObservedValue(self) -> None:
        values = [1.0, 2.0, 3.0]
        self.assertIn(percentile(values, 0.9), values)

    def testPercentileFractionIsValidated(self) -> None:
        with self.assertRaises(ValidationFailedError):
            percentile([1, 2], 0.0)
        with self.assertRaises(ValidationFailedError):
            percentile([1, 2], 1.5)

    def testAverageAndRatioAreSafe(self) -> None:
        self.assertEqual(average([2, 4]), 3.0)
        self.assertEqual(average([]), 0.0)
        self.assertEqual(ratio(1, 4), 0.25)
        self.assertEqual(ratio(5, 0), 0.0)
        self.assertEqual(ratio(9, 4), 1.0)


class AlertRuleTests(unittest.TestCase):
    def testComparisonsBehaveAsNamed(self) -> None:
        above = AlertRule(code="R", metric="aiErrorRatio", comparison="ABOVE", threshold=0.1)
        self.assertTrue(above.isBreached(0.2))
        self.assertFalse(above.isBreached(0.1))
        below = AlertRule(code="R", metric="aiFeedbackScore", comparison="BELOW", threshold=0.5)
        self.assertTrue(below.isBreached(0.4))
        self.assertFalse(below.isBreached(0.5))
        equal = AlertRule(
            code="R", metric="aiQueueDepth", comparison="ABOVE_OR_EQUAL", threshold=10
        )
        self.assertTrue(equal.isBreached(10))

    def testRuleCodesAreNormalizedNotRejectedForCase(self) -> None:
        self.assertEqual(AlertRule(code=" error ratio ", metric="aiErrorRatio").code, "ERROR_RATIO")

    def testRuleValidatesItsOwnShape(self) -> None:
        for badCode in ("", "1BAD", "!!"):
            with self.assertRaises(ValidationFailedError):
                AlertRule(code=badCode, metric="aiErrorRatio")
        with self.assertRaises(ValidationFailedError):
            AlertRule(code="R", metric="aiUnknown")
        with self.assertRaises(ValidationFailedError):
            AlertRule(code="R", metric="aiErrorRatio", comparison="NEAR")
        with self.assertRaises(ValidationFailedError):
            AlertRule(code="R", metric="aiErrorRatio", minimumSamples=-1)

    def testMessageAndSignatureAreInformative(self) -> None:
        rule = AlertRule(code="R_HIGH", metric="aiErrorRatio", threshold=0.1)
        self.assertIn("aiErrorRatio", rule.message(0.4))
        self.assertIn("0.4", rule.message(0.4))
        self.assertIn("R_HIGH", rule.signature())

    def testTheShippedRulesCoverTheFailuresThatHurt(self) -> None:
        codes = {rule.code for rule in defaultAlertRules()}
        self.assertEqual(
            codes,
            {
                "AI_ERROR_RATIO_HIGH",
                "AI_LATENCY_P95_HIGH",
                "AI_QUEUE_BACKLOG",
                "AI_FEEDBACK_LOW",
                "AI_EVALUATION_LOW",
            },
        )


class PrometheusRenderingTests(unittest.TestCase):
    def testExpositionCarriesHelpTypeAndValue(self) -> None:
        text = renderPrometheus(samples(aiRequestsTotal=12, aiErrorRatio=0.25))
        self.assertIn("# HELP aiRequestsTotal", text)
        self.assertIn("# TYPE aiRequestsTotal counter", text)
        self.assertIn("aiRequestsTotal 12.0", text)
        self.assertIn("# TYPE aiErrorRatio gauge", text)
        self.assertTrue(text.endswith("\n"))

    def testLabelledSeriesRenderWithQuotedLabels(self) -> None:
        text = renderPrometheus(
            [MetricSample(name="aiProviderFailures", value=2, labels={"provider": "openai"})]
        )
        self.assertIn('aiProviderFailures{provider="openai"} 2.0', text)

    def testSeriesAreGroupedAndSortedDeterministically(self) -> None:
        text = renderPrometheus(
            [
                MetricSample(name="aiProviderFailures", value=1, labels={"provider": "zulu"}),
                MetricSample(name="aiProviderFailures", value=2, labels={"provider": "alpha"}),
            ]
        )
        self.assertEqual(text.count("# TYPE aiProviderFailures"), 1)
        self.assertLess(text.index('provider="alpha"'), text.index('provider="zulu"'))

    def testEmptyInputRendersEmptyText(self) -> None:
        self.assertEqual(renderPrometheus([]), "")

    def testForeignInputIsRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            renderPrometheus(["aiRequestsTotal 1"])  # type: ignore[list-item]


class SnapshotEntityTests(unittest.TestCase):
    def testSnapshotValidatesItsWindowAndMetrics(self) -> None:
        snapshot = AIMetricSnapshot(
            tenantId=TENANT,
            windowStart=CLOCK - timedelta(hours=1),
            windowEnd=CLOCK,
            metrics={"aiRequestsTotal": 10},
            labels={"tenant": "acme", "secret": "x"},
        )
        self.assertEqual(snapshot.durationSeconds, 3600.0)
        self.assertEqual(snapshot.valueFor("aiRequestsTotal"), 10.0)
        self.assertEqual(snapshot.valueFor("aiCostTotal"), 0.0)
        self.assertEqual(snapshot.labels, {"tenant": "acme"})

    def testInvertedWindowAndUnknownMetricAreRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            AIMetricSnapshot(tenantId=TENANT, windowStart=CLOCK, windowEnd=CLOCK)
        with self.assertRaises(ValidationFailedError):
            AIMetricSnapshot(
                tenantId=TENANT,
                windowStart=CLOCK - timedelta(hours=1),
                windowEnd=CLOCK,
                metrics={"aiVibes": 1},
            )

    def testSnapshotProjectsBackToSamples(self) -> None:
        snapshot = AIMetricSnapshot(
            tenantId=TENANT,
            windowStart=CLOCK - timedelta(hours=1),
            windowEnd=CLOCK,
            metrics={"aiRequestsTotal": 4, "aiErrorRatio": 0.5},
        )
        produced = snapshot.toSamples()
        self.assertEqual([item.name for item in produced], ["aiErrorRatio", "aiRequestsTotal"])
        self.assertEqual(produced[0].at, CLOCK)


class AlertEntityTests(unittest.TestCase):
    def alert(self, **overrides: object) -> AIAlertEvent:
        params: dict = {
            "tenantId": TENANT,
            "ruleCode": "AI_ERROR_RATIO_HIGH",
            "metric": "aiErrorRatio",
            "severity": "CRITICAL",
            "observedValue": 0.4,
            "threshold": 0.1,
            "firedAt": CLOCK,
            "createdAt": CLOCK,
        }
        params.update(overrides)
        return AIAlertEvent(**params)

    def testAlertStartsFiringAndIsActive(self) -> None:
        alert = self.alert()
        self.assertTrue(alert.isActive)
        self.assertFalse(alert.isTerminal)

    def testAcknowledgeThenResolve(self) -> None:
        alert = self.alert()
        alert.acknowledge(actorId=TENANT, now=CLOCK + timedelta(minutes=1))
        self.assertEqual(alert.state, "ACKNOWLEDGED")
        self.assertTrue(alert.isActive)
        alert.resolve(now=CLOCK + timedelta(minutes=5))
        self.assertEqual(alert.state, "RESOLVED")
        self.assertTrue(alert.isTerminal)
        self.assertEqual(alert.durationSeconds(), 300.0)

    def testAResolvedAlertIsFrozen(self) -> None:
        alert = self.alert()
        alert.resolve(now=CLOCK)
        with self.assertRaises(ValidationFailedError):
            alert.acknowledge(now=CLOCK)

    def testRuleCodeAndMetricAreValidated(self) -> None:
        with self.assertRaises(ValidationFailedError):
            self.alert(ruleCode="1BAD")
        with self.assertRaises(ValidationFailedError):
            self.alert(metric="aiUnknown")
        self.assertEqual(ensureRuleCode(" ai error ratio "), "AI_ERROR_RATIO")

    def testDurationUsesNowWhileStillFiring(self) -> None:
        alert = self.alert()
        self.assertEqual(alert.durationSeconds(now=CLOCK + timedelta(seconds=30)), 30.0)


class CollectorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.collector = MetricCollector()

    def testGroupsAreMergedAndSorted(self) -> None:
        merged = self.collector.merge([samples(aiRequestsTotal=5), samples(aiTokensTotal=100)])
        self.assertEqual([item.name for item in merged], ["aiRequestsTotal", "aiTokensTotal"])

    def testDuplicateSeriesFromTwoContributorsIsAWiringBug(self) -> None:
        with self.assertRaises(AIMetricInvalid):
            self.collector.merge([samples(aiRequestsTotal=5), samples(aiRequestsTotal=7)])

    def testTheSameMetricWithDifferentLabelsIsNotADuplicate(self) -> None:
        merged = self.collector.merge(
            [
                [MetricSample(name="aiProviderFailures", value=1, labels={"provider": "a"})],
                [MetricSample(name="aiProviderFailures", value=2, labels={"provider": "b"})],
            ]
        )
        self.assertEqual(len(merged), 2)

    def testErrorRatioIsDerivedWhenNotSupplied(self) -> None:
        collected = self.collector.collect(
            [samples(aiRequestsTotal=10, aiRequestsFailed=2)], at=CLOCK
        )
        byName = {item.name: item.value for item in collected}
        self.assertEqual(byName["aiErrorRatio"], 0.2)

    def testASuppliedErrorRatioIsNotOverwritten(self) -> None:
        collected = self.collector.collect(
            [samples(aiRequestsTotal=10, aiRequestsFailed=2, aiErrorRatio=0.9)], at=CLOCK
        )
        byName = {item.name: item.value for item in collected}
        self.assertEqual(byName["aiErrorRatio"], 0.9)

    def testLatencyMetricsAreDerivedFromRawSamples(self) -> None:
        collected = self.collector.collect(
            [samples(aiRequestsTotal=3)], latencies=[100, 200, 900], at=CLOCK
        )
        byName = {item.name: item.value for item in collected}
        self.assertEqual(byName["aiLatencyAverage"], 400.0)
        self.assertEqual(byName["aiLatencyP95"], 900.0)

    def testForeignSamplesAreRejected(self) -> None:
        with self.assertRaises(AIMetricInvalid):
            self.collector.merge([["aiRequestsTotal"]])  # type: ignore[list-item]


class WindowAndSnapshotBuilderTests(unittest.TestCase):
    def testWindowValidatesItsBounds(self) -> None:
        self.assertEqual(window(60).durationSeconds, 3600.0)
        with self.assertRaises(AIObservabilityWindowInvalid):
            MetricWindow(start=CLOCK, end=CLOCK)
        with self.assertRaises(AIObservabilityWindowInvalid):
            MetricWindow(start=CLOCK, end=CLOCK - timedelta(hours=1))

    def testWindowMembershipIsHalfOpen(self) -> None:
        current = window(60)
        self.assertTrue(current.contains(CLOCK - timedelta(minutes=30)))
        self.assertFalse(current.contains(CLOCK))

    def testBuilderFreezesUnlabelledSeriesOnly(self) -> None:
        builder = SnapshotBuilder()
        snapshot = builder.build(
            TENANT,
            window(60),
            samples(aiRequestsTotal=4)
            + (MetricSample(name="aiProviderFailures", value=1, labels={"provider": "a"}),),
        )
        self.assertEqual(list(snapshot.metrics), ["aiRequestsTotal"])
        self.assertEqual(snapshot.sampleCount, 2)

    def testBuilderRequiresARealWindow(self) -> None:
        with self.assertRaises(AIObservabilityWindowInvalid):
            SnapshotBuilder().build(TENANT, "window", ())  # type: ignore[arg-type]


class AlertEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = AlertEvaluator()
        self.rule = AlertRule(
            code="AI_ERROR_RATIO_HIGH",
            metric="aiErrorRatio",
            comparison="ABOVE",
            threshold=0.1,
            severity="CRITICAL",
        )

    def testABreachOpensOneAlert(self) -> None:
        evaluation = self.evaluator.evaluate(
            [self.rule], samples(aiErrorRatio=0.4), tenantId=TENANT, now=CLOCK
        )
        self.assertEqual(len(evaluation.opened), 1)
        alert = evaluation.opened[0]
        self.assertEqual(alert.ruleCode, "AI_ERROR_RATIO_HIGH")
        self.assertEqual(alert.severity, "CRITICAL")
        self.assertEqual(alert.observedValue, 0.4)

    def testASustainedBreachDoesNotOpenASecondAlert(self) -> None:
        first = self.evaluator.evaluate(
            [self.rule], samples(aiErrorRatio=0.4), tenantId=TENANT, now=CLOCK
        ).opened[0]
        second = self.evaluator.evaluate(
            [self.rule], samples(aiErrorRatio=0.5), [first], tenantId=TENANT, now=CLOCK
        )
        self.assertEqual(second.opened, ())
        self.assertEqual(len(second.sustained), 1)

    def testRecoveryResolvesTheOpenAlert(self) -> None:
        firing = self.evaluator.evaluate(
            [self.rule], samples(aiErrorRatio=0.4), tenantId=TENANT, now=CLOCK
        ).opened[0]
        recovered = self.evaluator.evaluate(
            [self.rule],
            samples(aiErrorRatio=0.01),
            [firing],
            tenantId=TENANT,
            now=CLOCK + timedelta(minutes=5),
        )
        self.assertEqual(len(recovered.resolved), 1)
        self.assertEqual(recovered.resolved[0].state, "RESOLVED")

    def testAHealthyMetricWithNoOpenAlertDoesNothing(self) -> None:
        evaluation = self.evaluator.evaluate(
            [self.rule], samples(aiErrorRatio=0.01), tenantId=TENANT, now=CLOCK
        )
        self.assertEqual(evaluation.opened, ())
        self.assertEqual(evaluation.resolved, ())
        self.assertEqual(evaluation.decisions[0].action, "NONE")

    def testAMissingMetricSkipsTheRuleInsteadOfFiring(self) -> None:
        evaluation = self.evaluator.evaluate(
            [self.rule], samples(aiRequestsTotal=1), tenantId=TENANT, now=CLOCK
        )
        self.assertEqual(evaluation.decisions[0].action, "SKIPPED")
        self.assertIn("not collected", evaluation.decisions[0].reason)

    def testASmallSampleSkipsANoisyRule(self) -> None:
        noisy = AlertRule(
            code="AI_ERROR_RATIO_HIGH",
            metric="aiErrorRatio",
            threshold=0.1,
            minimumSamples=10,
        )
        evaluation = self.evaluator.evaluate(
            [noisy], samples(aiErrorRatio=1.0), tenantId=TENANT, sampleCount=3, now=CLOCK
        )
        self.assertEqual(evaluation.decisions[0].action, "SKIPPED")
        self.assertIn("needs 10", evaluation.decisions[0].reason)

    def testLabelledSeriesDoNotDriveRules(self) -> None:
        evaluation = self.evaluator.evaluate(
            [self.rule],
            [MetricSample(name="aiErrorRatio", value=0.9, labels={"provider": "a"})],
            tenantId=TENANT,
            now=CLOCK,
        )
        self.assertEqual(evaluation.decisions[0].action, "SKIPPED")

    def testForeignRulesAreRejected(self) -> None:
        with self.assertRaises(AIAlertRuleInvalid):
            self.evaluator.evaluate(["rule"], samples(), tenantId=TENANT)  # type: ignore[list-item]


class HealthEvaluatorTests(unittest.TestCase):
    def setUp(self) -> None:
        self.evaluator = HealthEvaluator()

    def testAQuietPlatformIsUnknownNotHealthy(self) -> None:
        report = self.evaluator.evaluate(TENANT, (), now=CLOCK)
        self.assertEqual(report.status, "UNKNOWN")
        self.assertEqual(len(report.components), 5)

    def testAWorkingPlatformIsHealthy(self) -> None:
        report = self.evaluator.evaluate(
            TENANT,
            samples(
                aiRequestsTotal=100,
                aiErrorRatio=0.01,
                aiQueueDepth=2,
                aiRetrievalDenied=0,
                aiEvaluationScore=0.9,
                aiFeedbackScore=0.8,
            ),
            now=CLOCK,
        )
        self.assertEqual(report.status, "HEALTHY")
        self.assertTrue(report.isHealthy)
        self.assertEqual(report.degradedComponents(), ())

    def testAHighErrorRatioMakesTheProviderUnhealthy(self) -> None:
        report = self.evaluator.evaluate(
            TENANT, samples(aiRequestsTotal=100, aiErrorRatio=0.3), now=CLOCK
        )
        provider = report.componentFor("PROVIDER")
        assert provider is not None
        self.assertEqual(provider.status, "UNHEALTHY")
        self.assertEqual(report.status, "UNHEALTHY")

    def testABacklogDegradesTheQueue(self) -> None:
        report = self.evaluator.evaluate(
            TENANT, samples(aiRequestsTotal=10, aiErrorRatio=0.0, aiQueueDepth=80), now=CLOCK
        )
        queue = report.componentFor("QUEUE")
        assert queue is not None
        self.assertEqual(queue.status, "DEGRADED")
        self.assertEqual(report.status, "DEGRADED")

    def testFailingEvaluationCasesMakeEvaluationUnhealthy(self) -> None:
        report = self.evaluator.evaluate(
            TENANT, samples(aiEvaluationScore=0.9, aiEvaluationFailures=2), now=CLOCK
        )
        evaluation = report.componentFor("EVALUATION")
        assert evaluation is not None
        self.assertEqual(evaluation.status, "UNHEALTHY")

    def testLowSatisfactionDegradesFeedback(self) -> None:
        report = self.evaluator.evaluate(TENANT, samples(aiFeedbackScore=0.3), now=CLOCK)
        feedback = report.componentFor("FEEDBACK")
        assert feedback is not None
        self.assertEqual(feedback.status, "DEGRADED")

    def testDeniedRetrievalsDegradeRetrieval(self) -> None:
        report = self.evaluator.evaluate(TENANT, samples(aiRetrievalDenied=3), now=CLOCK)
        retrieval = report.componentFor("RETRIEVAL")
        assert retrieval is not None
        self.assertEqual(retrieval.status, "DEGRADED")
        self.assertIn("3", retrieval.reason)

    def testACriticalAlertAloneMakesThePlatformUnhealthy(self) -> None:
        alert = AIAlertEvent(
            tenantId=TENANT,
            ruleCode="AI_ERROR_RATIO_HIGH",
            metric="aiErrorRatio",
            severity="CRITICAL",
            firedAt=CLOCK,
        )
        report = self.evaluator.evaluate(
            TENANT,
            samples(aiRequestsTotal=10, aiErrorRatio=0.0, aiQueueDepth=1),
            [alert],
            now=CLOCK,
        )
        self.assertEqual(report.status, "UNHEALTHY")
        self.assertEqual(report.criticalAlerts, 1)

    def testComponentHealthValidatesItself(self) -> None:
        with self.assertRaises(ValidationFailedError):
            ComponentHealth(component="", status="HEALTHY")
        with self.assertRaises(ValidationFailedError):
            ComponentHealth(component="QUEUE", status="FINE")
        self.assertTrue(ComponentHealth(component="queue", status="HEALTHY").isHealthy)

    def testReportLookupsAreForgiving(self) -> None:
        report = HealthReport(tenantId=TENANT, status="HEALTHY")
        self.assertIsNone(report.componentFor("QUEUE"))
        self.assertEqual(report.degradedComponents(), ())


if __name__ == "__main__":  # pragma: no cover - manual execution helper
    unittest.main()
