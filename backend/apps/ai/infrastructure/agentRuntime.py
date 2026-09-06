"""Release wiring adapters for the Phase 13 agent runtime (sub-phase Z).

The application/domain layers remain unaware of Django, HTTP and provider SDKs.
This module is the only bridge from the release composition root to configured
provider adapters and the platform permission gate.
"""

from __future__ import annotations

import json
from typing import Any

from django.conf import settings as djangoSettings

from apps.ai.domain.exceptions import AIConfigurationError
from apps.ai.domain.ports import DeterministicAIProvider, ProviderRequestContext
from apps.ai.domain.services.agentEngine import AgentModelReply, AgentToolOutcome
from apps.ai.domain.services.toolEngine import ToolProposal
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider


class SharedGateAgentPermissionChecker:
    """Re-check an agent permission against Identity at execution time.

    Async jobs therefore do not trust an authorization snapshot captured when
    they were submitted: revoked access is observed by the worker.
    """

    def can(self, principal: Any, action: str, resource: Any) -> bool:
        if principal is None or not bool(getattr(principal, "isActive", False)):
            return False
        if getattr(principal, "tenantId", None) != getattr(resource, "tenantId", None):
            return False
        subjectId = getattr(principal, "subjectId", None)
        if subjectId is None:
            return False
        permission = _identityPermission(action)
        try:
            gate = sharedKernelProvider("permissionGate")()
            return bool(gate.hasPermission(subjectId, permission, tenantId=resource.tenantId))
        except Exception:  # fail closed at the authorization boundary
            return False


class SharedGateToolPermissionChecker:
    """Phase X permission-port adapter using the same live Identity gate."""

    def can(self, principal: Any, action: str, resource: Any) -> bool:
        return SharedGateAgentPermissionChecker().can(principal, action, resource)


class ConfiguredAgentModelCaller:
    """Translate an Agent model request to a configured provider-neutral port.

    Provider and model selection are configuration/model-policy driven.  The
    deterministic provider is available only when explicitly enabled (testing
    does so in ``config.settings.testing``); production never silently falls
    back to a fake provider.
    """

    def __init__(self, adapters: dict[str, Any] | None = None) -> None:
        if adapters is None:
            from apps.ai.infrastructure.providers.providerWiring import (
                buildConfiguredProviderAdapters,
            )

            adapters = buildConfiguredProviderAdapters()
        self._adapters = {str(key).upper(): value for key, value in adapters.items()}
        if bool(getattr(djangoSettings, "AI_AGENT_ALLOW_DETERMINISTIC_PROVIDER", False)):
            self._adapters.setdefault("DETERMINISTIC", DeterministicAIProvider())

    def call(self, tenantId: Any, request: Any) -> AgentModelReply:
        policy = dict(getattr(request, "modelPolicy", {}) or {})
        providerCode = (
            str(
                policy.get("provider")
                or getattr(djangoSettings, "AI_AGENT_DEFAULT_PROVIDER", "")
                or ""
            )
            .strip()
            .upper()
        )
        modelCode = str(
            policy.get("model") or getattr(djangoSettings, "AI_AGENT_DEFAULT_MODEL", "") or ""
        ).strip()
        if not providerCode or not modelCode:
            raise AIConfigurationError("Agent provider and model must be configured.")
        provider = self._adapters.get(providerCode)
        if provider is None:
            raise AIConfigurationError(f"Agent provider {providerCode} is not configured.")

        prompt = _agentPrompt(request)
        schema = dict(getattr(request, "outputSchema", {}) or {})
        result = provider.generate(
            prompt=prompt,
            systemInstruction=str(getattr(request, "instructions", "")),
            model=modelCode,
            temperature=float(policy.get("temperature", 0.0)),
            maxTokens=policy.get("maxTokens"),
            responseFormat="JSON" if schema else "TEXT",
            jsonSchema=schema,
            context=ProviderRequestContext(tenantId=tenantId),
        )
        structured = dict(result.structuredData) if schema else None
        answer = result.content if result.content else json.dumps(structured or {}, sort_keys=True)
        return AgentModelReply(
            answer=answer,
            structured=structured,
            inputTokens=result.inputTokens,
            outputTokens=result.outputTokens,
        )


class FailClosedToolRunner:
    """A runner used when no domain tool handlers were registered.

    Definitions can still be resolved and shown to the model, but execution
    cannot escape through an unregistered callable.
    """

    def supports(self, toolCode: str) -> bool:
        return False

    def run(self, tenantId: Any, ticket: Any) -> dict[str, Any]:
        raise AIConfigurationError("No release tool runner is registered for this tool.")


class NoToolExecutor:
    """Safe fallback satisfying the planner port for agents without tools."""

    def declarationsFor(self, tenantId: Any, toolCodes: tuple[str, ...]) -> tuple[Any, ...]:
        return ()

    def execute(
        self, tenantId: Any, proposal: ToolProposal, *, principal: Any = None
    ) -> AgentToolOutcome:
        return AgentToolOutcome(
            status="DENIED",
            errorCode="AI_AGENT_TOOL_NOT_DECLARED",
            reason="No registered tool execution boundary is configured.",
        )


def _identityPermission(action: str) -> str:
    normalized = str(action or "").strip()
    aliases = {
        "AI_AGENT_RUN": "ai.agent.run",
        "AI_TOOL_INVOKE": "ai.tool.invoke",
    }
    return aliases.get(normalized.upper(), normalized.lower().replace("_", "."))


def _agentPrompt(request: Any) -> str:
    payload = {
        "context": str(getattr(request, "contextText", "")),
        "input": dict(getattr(request, "input", {}) or {}),
        "history": [
            {
                "ordinal": step.ordinal,
                "kind": step.kind,
                "status": step.status,
                "toolCode": step.toolCode,
                "result": dict(step.result),
                "errorCode": step.errorCode,
            }
            for step in tuple(getattr(request, "history", ()) or ())
        ],
    }
    return json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


__all__ = [
    "ConfiguredAgentModelCaller",
    "FailClosedToolRunner",
    "NoToolExecutor",
    "SharedGateAgentPermissionChecker",
    "SharedGateToolPermissionChecker",
]
