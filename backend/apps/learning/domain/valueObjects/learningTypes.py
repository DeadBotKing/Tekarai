"""Framework-independent Phase 16 value objects, states and integrity rules."""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from typing import Any

from apps.sharedKernel.domain.errors import ValidationFailedError

DATASET_STATUSES = (
    "DRAFT",
    "BUILDING",
    "READY",
    "VALIDATING",
    "APPROVED",
    "ARCHIVED",
    "FAILED",
)
EXPERIMENT_STATUSES = ("CREATED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
RUN_STATUSES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
ARTIFACT_TYPES = (
    "MODEL",
    "POLICY",
    "RULE_SET",
    "EMBEDDING",
    "KNOWLEDGE",
    "CONFIGURATION",
    "STRATEGY",
)
ARTIFACT_STATUSES = (
    "CREATED",
    "EVALUATED",
    "VALIDATED",
    "APPROVED",
    "REJECTED",
    "STAGED",
    "CANARY",
    "ACTIVE",
    "ROLLED_BACK",
    "FAILED",
    "ARCHIVED",
)
VALIDATION_DECISIONS = ("PASSED", "FAILED")
APPROVAL_DECISIONS = ("APPROVED", "REJECTED")
DEPLOYMENT_STATUSES = (
    "STAGED",
    "CANARY",
    "ACTIVE",
    "FAILED",
    "ROLLING_BACK",
    "ROLLED_BACK",
    "SUPERSEDED",
)
FEEDBACK_TYPES = ("POSITIVE", "NEGATIVE", "NEUTRAL", "HUMAN", "SYSTEM", "BUSINESS")
HUMAN_ACTIONS = ("APPROVE", "REJECT", "CORRECT", "LABEL", "RATE", "FLAG")
DRIFT_TYPES = ("DATA", "CONCEPT", "PREDICTION", "PERFORMANCE")
JOB_STATUSES = ("QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
CANARY_STAGES = (5, 25, 50, 100)
SEMVER = re.compile(r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?$")
_SECRET_KEYS = ("password", "secret", "token", "apikey", "api_key", "credential", "privatekey")


def requireChoice(value: str, allowed: tuple[str, ...], field: str) -> str:
    normalized = str(value).strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(
            f"{field} is invalid.", fieldErrors={field: f"must be one of {', '.join(allowed)}"}
        )
    return normalized


def requireSemVer(value: str) -> str:
    normalized = value.strip()
    if not SEMVER.fullmatch(normalized):
        raise ValidationFailedError(
            "Artifact version must use semantic versioning.",
            fieldErrors={"version": "expected MAJOR.MINOR.PATCH"},
        )
    return normalized


def canonicalJson(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, default=str)


def integrityHash(value: Any) -> str:
    return hashlib.sha256(canonicalJson(value).encode("utf-8")).hexdigest()


def safePayload(value: Mapping[str, Any] | None, *, maxBytes: int = 64_000) -> dict[str, Any]:
    """Copy bounded JSON metadata while rejecting secret-bearing keys."""
    payload = dict(value or {})

    def inspect(node: Any, path: str = "") -> None:
        if isinstance(node, Mapping):
            for key, child in node.items():
                normalized = str(key).lower().replace("-", "").replace("_", "")
                if any(secret.replace("_", "") in normalized for secret in _SECRET_KEYS):
                    raise ValidationFailedError(
                        "Learning payload contains secret-like data.",
                        fieldErrors={path + str(key): "secret material is forbidden"},
                    )
                inspect(child, path + str(key) + ".")
        elif isinstance(node, (list, tuple)):
            for index, child in enumerate(node):
                inspect(child, f"{path}{index}.")
        elif not isinstance(node, (str, int, float, bool, type(None))):
            raise ValidationFailedError("Learning payload must be JSON-compatible.")
        elif isinstance(node, float) and not math.isfinite(node):
            raise ValidationFailedError("Learning payload numbers must be finite.")

    inspect(payload)
    if len(canonicalJson(payload).encode("utf-8")) > maxBytes:
        raise ValidationFailedError("Learning payload exceeds the allowed size.")
    return payload


def normalizedMetrics(metrics: Mapping[str, Any]) -> dict[str, float]:
    result: dict[str, float] = {}
    for key, value in metrics.items():
        if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
            raise ValidationFailedError(f"Metric {key} must be a finite number.")
        result[str(key)] = float(value)
    return result


def nextCanaryStage(current: int) -> int:
    if current not in (0, *CANARY_STAGES):
        raise ValidationFailedError("Current canary stage is invalid.")
    for stage in CANARY_STAGES:
        if stage > current:
            return stage
    return 100


def compareMetrics(
    candidate: Mapping[str, float],
    baseline: Mapping[str, float],
    *,
    minimums: Mapping[str, float] | None = None,
    maximumRegression: Mapping[str, float] | None = None,
) -> tuple[bool, list[dict[str, Any]]]:
    """Validate absolute thresholds and directional regression.

    Latency/error/failure/resource metrics are lower-is-better; all others are
    higher-is-better. Missing mandatory metrics fail closed.
    """
    failures: list[dict[str, Any]] = []
    for name, minimum in (minimums or {}).items():
        actual = candidate.get(name)
        if actual is None or actual < float(minimum):
            failures.append(
                {"metric": name, "rule": "minimum", "expected": minimum, "actual": actual}
            )
    lowerIsBetter = ("latency", "error", "failure", "resource")
    for name, allowed in (maximumRegression or {}).items():
        actual = candidate.get(name)
        old = baseline.get(name)
        if actual is None or old is None:
            failures.append({"metric": name, "rule": "baseline-required", "actual": actual})
            continue
        regression = (
            (actual - old)
            if any(token in name.lower() for token in lowerIsBetter)
            else (old - actual)
        )
        if regression > float(allowed):
            failures.append(
                {
                    "metric": name,
                    "rule": "maximum-regression",
                    "allowed": allowed,
                    "actual": actual,
                    "baseline": old,
                    "regression": regression,
                }
            )
    return not failures, failures
