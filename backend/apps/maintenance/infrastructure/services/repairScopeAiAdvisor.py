"""Optional repair-scope advisor using Tekarai's configured AI provider port.

The configured model can only return a suggestion. The application use case
validates its scope and always requires technician confirmation; if provider
configuration or the response is unavailable/invalid, the explainable domain
rules remain the fallback.
"""

from __future__ import annotations

import json
import logging
from types import SimpleNamespace
from typing import Any

from apps.maintenance.domain.services.equipmentLifecycle import (
    REPAIR_SCOPES,
    RepairScopeSuggestion,
)

logger = logging.getLogger(__name__)

_OUTPUT_SCHEMA = {
    "type": "object",
    "properties": {
        "suggestedScope": {"type": "string", "enum": list(REPAIR_SCOPES)},
        "confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "reasons": {
            "type": "array",
            "items": {"type": "string"},
            "minItems": 1,
            "maxItems": 4,
        },
    },
    "required": ["suggestedScope", "confidence", "reasons"],
    "additionalProperties": False,
}

_SYSTEM_INSTRUCTION = """You are an advisory maintenance assistant. Classify the documented corrective-repair scope as unclassified, minor, major, or overhaul. Use only the supplied work-order text and part-impact labels. A bearing, filter, or other small/consumable part is not an overhaul. Never infer major repair from the number or quantity of parts. Prefer unclassified when evidence is ambiguous. Return concise reasons in the language used by the evidence. This is only a suggestion: a technician must confirm it; do not recommend automatic shutdown or retirement."""


class ConfiguredRepairScopeAIAdvisor:
    """Use the existing provider-neutral agent model caller when configured."""

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

    def suggest(self, *, tenantId: Any, evidence: dict[str, Any]) -> RepairScopeSuggestion | None:
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
                    "temperature": 0.0,
                    "maxTokens": 600,
                },
                contextText="Classify repair scope from the supplied maintenance evidence only.",
                input={"evidence": self._safeEvidence(evidence)},
                history=(),
                instructions=_SYSTEM_INSTRUCTION,
                outputSchema=_OUTPUT_SCHEMA,
            )
            reply = caller.call(tenantId, request)
            structured = self._structuredReply(reply)
            if structured is None:
                return None
            scope = str(structured.get("suggestedScope", "")).strip()
            confidence = str(structured.get("confidence", "")).strip()
            rawReasons = structured.get("reasons")
            if scope not in REPAIR_SCOPES or confidence not in {"low", "medium", "high"}:
                return None
            if not isinstance(rawReasons, (list, tuple)):
                return None
            reasons = tuple(
                str(reason).strip()[:400]
                for reason in rawReasons[:4]
                if isinstance(reason, str) and reason.strip()
            )
            if not reasons:
                return None
            return RepairScopeSuggestion(
                suggestedScope=scope,
                confidence=confidence,
                reasons=reasons,
                requiresHumanConfirmation=True,
            )
        except Exception as error:  # Provider failure must not block work-order closure.
            logger.warning(
                "Configured repair-scope AI advisor failed; using domain fallback (%s).",
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
    def _safeEvidence(evidence: dict[str, Any]) -> dict[str, Any]:
        textFields = ("title", "description", "failureSymptom", "rootCause", "actionTaken")
        safe: dict[str, Any] = {
            field: str(evidence.get(field, "") or "")[:6000] for field in textFields
        }
        rawParts = evidence.get("parts", ())
        safe["parts"] = [
            {
                "name": str(part.get("name", "") or "")[:160],
                "lifecycleImpact": str(part.get("lifecycleImpact", "unknown") or "unknown"),
            }
            for part in tuple(rawParts or ())[:20]
            if isinstance(part, dict)
        ]
        # Quantities are deliberately omitted: piece counts must never inflate
        # an AI suggestion from minor/consumable work to major repair.
        return safe

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
