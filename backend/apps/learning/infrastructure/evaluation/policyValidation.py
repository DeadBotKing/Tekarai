"""Policy-driven Phase 16 validation-engine adapter."""

from __future__ import annotations

from typing import Any

from apps.learning.domain.valueObjects.learningTypes import compareMetrics


class PolicyValidationEngine:
    def validate(
        self,
        *,
        candidate: dict[str, float],
        baseline: dict[str, float],
        policy: dict,
        integrityValid: bool,
    ) -> tuple[bool, list[dict[str, Any]]]:
        passed, failures = compareMetrics(
            candidate,
            baseline,
            minimums=policy.get("minimums", {"accuracy": 0.5}),
            maximumRegression=policy.get("maximumRegression", {}),
        )
        if not integrityValid:
            passed = False
            failures.append({"rule": "artifact-integrity"})
        for metricName, maximum in policy.get("maximums", {}).items():
            actual = candidate.get(metricName)
            if actual is None or actual > float(maximum):
                passed = False
                failures.append(
                    {
                        "metric": metricName,
                        "rule": "maximum",
                        "expected": maximum,
                        "actual": actual,
                    }
                )
        for guardName in (
            "safetyPassed",
            "dataLeakagePassed",
            "compatibilityPassed",
            "resourceUsagePassed",
            "businessConstraintsPassed",
        ):
            if policy.get(guardName, True) is not True:
                passed = False
                failures.append({"rule": guardName})
        return passed, failures
