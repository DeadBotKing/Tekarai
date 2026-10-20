"""Optional, provider-neutral AI interpretation of lifecycle aggregates.

The advisor receives derived, tenant-scoped metrics only (no equipment ID,
operator identity, or raw work-order narrative). Its text is displayed beside
and never replaces the rule-based counts, cohort estimate, condition, or
human-controlled asset status.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

logger = logging.getLogger(__name__)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "summary": {"type": "string", "minLength": 1, "maxLength": 1200},
        "recommendations": {
            "type": "array",
            "items": {"type": "string", "minLength": 1, "maxLength": 400},
            "maxItems": 3,
        },
    },
    "required": ["summary", "recommendations"],
    "additionalProperties": False,
}

_INSTRUCTIONS = """You are an advisory maintenance analyst. Interpret only the supplied aggregate maintenance metrics and evidence limitations. Do not invent measurements, thresholds, causes, dates, peer counts, remaining years, or a numeric life estimate. Preserve the supplied statistical peer estimate exactly; it is remaining major-repair events, not calendar life. If evidence is insufficient, state that clearly. Offer at most three practical verification or maintenance-review steps. Never direct an automatic shutdown, status change, or retirement; any such decision requires an authorized human. Reply in the requested language (fa=Persian, en=English, de=German). Return the requested JSON only."""


class ConfiguredEquipmentLifecycleAIAdvisor:
    """Generate a short interpretation through Tekarai's configured AI runtime."""

    def __init__(
        self,
        *,
        caller: Any = None,
        providerCode: str | None = None,
        modelCode: str | None = None,
    ) -> None:
        self._caller = caller
        self._providerCode = providerCode
        self._modelCode = modelCode

    def advise(
        self,
        *,
        tenantId: Any,
        language: str,
        analysis: dict[str, Any],
    ) -> dict[str, Any] | None:
        configuration = self._configuration()
        if configuration is None:
            return None
        providerCode, modelCode = configuration
        try:
            caller = self._caller or self._configuredCaller()
            request = SimpleNamespace(
                modelPolicy={
                    "provider": providerCode,
                    "model": modelCode,
                    "temperature": 0.1,
                    "maxTokens": 900,
                },
                contextText="Explain the computed lifecycle evidence without replacing its measurements or estimate.",
                input={
                    "language": language if language in {"fa", "en", "de"} else "fa",
                    "analysis": self._safeAnalysis(analysis),
                },
                history=(),
                instructions=_INSTRUCTIONS,
                outputSchema=_OUTPUT_SCHEMA,
            )
            reply = caller.call(tenantId, request)
            structured = self._structuredReply(reply)
            if structured is None:
                return None
            summary = structured.get("summary")
            recommendations = structured.get("recommendations")
            if not isinstance(summary, str) or not summary.strip():
                return None
            if not isinstance(recommendations, (list, tuple)):
                return None
            safeRecommendations = [
                item.strip()[:400]
                for item in recommendations[:3]
                if isinstance(item, str) and item.strip()
            ]
            return {
                "summary": summary.strip()[:1200],
                "recommendations": safeRecommendations,
            }
        except Exception as error:  # Provider outages must not block lifecycle analysis.
            logger.warning(
                "Configured lifecycle AI advisor failed; retaining rule-based analysis (%s).",
                type(error).__name__,
            )
            return None

    def _configuration(self) -> tuple[str, str] | None:
        providerCode = str(self._providerCode or "").strip().upper()
        modelCode = str(self._modelCode or "").strip()
        if self._providerCode is None or self._modelCode is None:
            try:
                from django.conf import settings

                if not bool(getattr(settings, "AI_AGENT_ENABLED", True)):
                    return None
                providerCode = str(
                    self._providerCode
                    or getattr(settings, "AI_AGENT_DEFAULT_PROVIDER", "")
                    or ""
                ).strip().upper()
                modelCode = str(
                    self._modelCode or getattr(settings, "AI_AGENT_DEFAULT_MODEL", "") or ""
                ).strip()
            except ImportError:
                return None
        if not providerCode or not modelCode:
            return None
        return providerCode, modelCode

    def _configuredCaller(self) -> Any:
        from apps.ai.infrastructure.agentRuntime import ConfiguredAgentModelCaller

        return ConfiguredAgentModelCaller()

    @staticmethod
    def _safeAnalysis(analysis: dict[str, Any]) -> dict[str, Any]:
        """Whitelist the computed, aggregate fields sent to an AI provider."""
        performance = analysis.get("performance") or {}
        rawSignals = performance.get("signals") or ()
        signals = [
            {
                "name": str(signal.get("name", ""))[:120],
                "unit": str(signal.get("unit", ""))[:32],
                "role": str(signal.get("role", "")),
                "readingCount": signal.get("readingCount"),
                "retentionPercent": signal.get("retentionPercent"),
                "changePercent": signal.get("changePercent"),
                "trend": signal.get("trend"),
            }
            for signal in tuple(rawSignals)[:12]
            if isinstance(signal, dict)
        ]
        life = analysis.get("lifeEstimate") or {}
        reliability = analysis.get("reliability") or {}
        return {
            "condition": analysis.get("condition"),
            "confidence": analysis.get("confidence"),
            "confidenceReason": str(analysis.get("confidenceReason", ""))[:500],
            "events": dict(analysis.get("events") or {}),
            "reliability": {
                key: reliability.get(key)
                for key in (
                    "recentCorrectiveCount",
                    "previousCorrectiveCount",
                    "failureFrequencyTrend",
                    "recentMajorRepairCount",
                    "previousMajorRepairCount",
                    "majorRepairFrequencyTrend",
                    "recentAvailabilityPercent",
                    "previousAvailabilityPercent",
                    "availabilityChangePercentagePoints",
                    "availabilityTrend",
                    "recentDowntimeHours",
                    "previousDowntimeHours",
                    "repeatFailureCount",
                )
            },
            "performance": {
                "trend": performance.get("trend"),
                "overallRetentionPercent": performance.get("overallRetentionPercent"),
                "validReadingCount": performance.get("validReadingCount"),
                "configuredSignalCount": performance.get("configuredSignalCount"),
                "signals": signals,
            },
            "lifeEstimate": {
                key: life.get(key)
                for key in (
                    "status",
                    "cohortType",
                    "peerCount",
                    "typicalMajorRepairsAtRetirement",
                    "estimatedRemainingMajorRepairs",
                    "currentMajorRepairCount",
                    "reason",
                )
            },
            "limitations": [str(item)[:500] for item in tuple(analysis.get("limitations") or ())[:8]],
        }

    @staticmethod
    def _structuredReply(reply: Any) -> dict[str, Any] | None:
        if isinstance(reply, dict):
            structured = reply.get("structured") or reply.get("structuredData")
            answer = reply.get("answer", reply.get("content", ""))
        else:
            structured = getattr(reply, "structured", None)
            answer = getattr(reply, "answer", getattr(reply, "content", ""))
        if isinstance(structured, dict) and structured:
            return structured
        if not isinstance(answer, str) or not answer.strip():
            return None
        try:
            parsed = json.loads(answer)
        except (TypeError, ValueError):
            return None
        return parsed if isinstance(parsed, dict) else None
