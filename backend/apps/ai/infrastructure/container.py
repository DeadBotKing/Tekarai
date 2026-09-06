"""Phase 13-Z production composition root.

Presentation imports this module, never repositories or providers directly.
Factories intentionally return short-lived services: all durable state is in
Tenant-scoped stores, while provider adapters remain stateless.
"""

from __future__ import annotations

import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from typing import Any

_overrides: dict[str, Any] = {}


def auditService() -> Any:
    if "auditService" in _overrides:
        return _resolve(_overrides["auditService"])
    from apps.ai.application.services.auditService import AuditApplicationService
    from apps.ai.infrastructure.repositories.auditRepositories import (
        DjangoAuditRecordStore,
        DjangoGovernancePolicyStore,
        DjangoRetentionPurger,
    )

    return AuditApplicationService(
        DjangoAuditRecordStore(), DjangoGovernancePolicyStore(), DjangoRetentionPurger()
    )


def toolService() -> Any:
    if "toolService" in _overrides:
        return _resolve(_overrides["toolService"])
    from apps.ai.application.services.toolService import ToolApplicationService, ToolSettings
    from apps.ai.infrastructure.agentRuntime import SharedGateToolPermissionChecker
    from apps.ai.infrastructure.repositories.toolRepositories import (
        DjangoToolApprovalStore,
        DjangoToolDefinitionStore,
        DjangoToolInvocationStore,
    )

    return ToolApplicationService(
        DjangoToolDefinitionStore(),
        DjangoToolInvocationStore(),
        DjangoToolApprovalStore(),
        permissionChecker=SharedGateToolPermissionChecker(),
        settings=ToolSettings.fromDjangoSettings(),
        auditLogger=auditService(),
    )


def agentService() -> Any:
    if "agentService" in _overrides:
        return _resolve(_overrides["agentService"])
    from apps.ai.application.services.agentService import (
        AgentApplicationService,
        AgentSettings,
        ToolExecutorAdapter,
    )
    from apps.ai.infrastructure.agentRuntime import (
        ConfiguredAgentModelCaller,
        SharedGateAgentPermissionChecker,
    )
    from apps.ai.infrastructure.repositories.agentRepositories import (
        DjangoAgentApprovalStore,
        DjangoAgentDefinitionStore,
        DjangoAgentExecutionStore,
    )

    return AgentApplicationService(
        DjangoAgentDefinitionStore(),
        DjangoAgentApprovalStore(),
        DjangoAgentExecutionStore(),
        permissionChecker=SharedGateAgentPermissionChecker(),
        toolExecutor=ToolExecutorAdapter(toolService()),
        modelCaller=ConfiguredAgentModelCaller(),
        settings=AgentSettings.fromDjangoSettings(),
        auditLogger=auditService(),
    )


def queueService(*, withHandlers: bool = False) -> Any:
    if "queueService" in _overrides:
        service = _resolve(_overrides["queueService"])
    else:
        from django.conf import settings as djangoSettings

        from apps.ai.application.services.queueService import QueueApplicationService, QueueSettings
        from apps.ai.infrastructure.repositories.queueRepositories import DjangoJobStore

        queueSettings = QueueSettings.fromDjangoSettings(djangoSettings)
        service = QueueApplicationService(
            DjangoJobStore(),
            auditService=auditService(),
            queueSettings=queueSettings,
            workerId=f"{queueSettings.workerId}-{uuid.uuid4().hex[:8]}",
        )
    if withHandlers:
        from apps.ai.application.services.agentJobService import AgentRunJobHandler

        service.registerHandler(AgentRunJobHandler(agentService()))
    return service


def releaseReadiness() -> dict[str, Any]:
    """Non-secret operational readiness summary used by the release endpoint."""

    from django.conf import settings as djangoSettings
    from django.db import connection
    from django.db.migrations.executor import MigrationExecutor

    from apps.ai.infrastructure.providers.providerWiring import buildConfiguredProviderAdapters

    executor = MigrationExecutor(connection)
    pendingAi = [
        f"{migration.app_label}.{migration.name}"
        for migration, backwards in executor.migration_plan(executor.loader.graph.leaf_nodes())
        if migration.app_label == "ai" and not backwards
    ]
    providers = sorted(buildConfiguredProviderAdapters())
    if bool(getattr(djangoSettings, "AI_AGENT_ALLOW_DETERMINISTIC_PROVIDER", False)):
        providers.append("DETERMINISTIC")
    checks = {
        "agentEnabled": bool(getattr(djangoSettings, "AI_AGENT_ENABLED", True)),
        "queueEnabled": bool(getattr(djangoSettings, "AI_QUEUE_ENABLED", True)),
        "auditEnabled": bool(getattr(djangoSettings, "AI_AUDIT_ENABLED", True)),
        "pendingAiMigrations": pendingAi,
        "configuredProviders": sorted(set(providers)),
        "defaultProviderConfigured": bool(
            str(getattr(djangoSettings, "AI_AGENT_DEFAULT_PROVIDER", "") or "").strip()
        ),
        "defaultModelConfigured": bool(
            str(getattr(djangoSettings, "AI_AGENT_DEFAULT_MODEL", "") or "").strip()
        ),
    }
    ready = (
        checks["agentEnabled"]
        and checks["queueEnabled"]
        and checks["auditEnabled"]
        and not pendingAi
        and bool(checks["configuredProviders"])
        and checks["defaultProviderConfigured"]
        and checks["defaultModelConfigured"]
    )
    return {"phase": 13, "subPhase": "Z", "ready": ready, "checks": checks}


@contextmanager
def overrideServices(**services: Any) -> Iterator[None]:
    """Scoped test hook; production code has no mutable global service state."""

    previous = dict(_overrides)
    _overrides.update(services)
    try:
        yield
    finally:
        _overrides.clear()
        _overrides.update(previous)


def _resolve(value: Any) -> Any:
    return value() if callable(value) and not hasattr(value, "runAgent") else value


__all__ = [
    "agentService",
    "auditService",
    "overrideServices",
    "queueService",
    "releaseReadiness",
    "toolService",
]
