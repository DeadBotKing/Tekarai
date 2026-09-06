"""Phase 13-Z queue bridge for asynchronous agent execution."""

from __future__ import annotations

import uuid
from typing import Any

from apps.ai.application.services.agentService import RunAgentCommand
from apps.ai.domain.entities.jobRecords import AIJob
from apps.ai.domain.services.authorizationService import AuthorizationPrincipal
from apps.ai.domain.services.jobQueue import JobOutcome


class AgentRunJobHandler:
    """Execute an ``AGENT_RUN`` job through the exact same Y application service.

    The job stores only IDs and the already-redacted execution input. Authority
    is reconstructed as a principal identity and re-evaluated by the live
    permission adapter when the worker executes it.
    """

    def __init__(self, agentService: Any) -> None:
        self._agents = agentService

    def kind(self) -> str:
        return "AGENT_RUN"

    def execute(self, job: AIJob) -> JobOutcome:
        payload = dict(job.payload or {})
        actorId = uuid.UUID(str(payload["actorId"]))
        principal = AuthorizationPrincipal(
            tenantId=job.tenantId,
            subjectId=actorId,
            subjectType=str(payload.get("subjectType", "USER")),
        )
        approvalValue = payload.get("approvalId")
        result = self._agents.runAgent(
            job.tenantId,
            RunAgentCommand(
                agentCode=str(payload["agentCode"]),
                version=payload.get("version"),
                input=dict(payload.get("input") or {}),
                principal=principal,
                actorId=actorId,
                reason=str(payload.get("reason", "")),
                approvalId=uuid.UUID(str(approvalValue)) if approvalValue else None,
            ),
        )
        summary = {
            "runId": str(result.run.runId),
            "runStatus": result.run.status,
            "approvalId": str(result.run.approvalId) if result.run.approvalId else None,
            "awaitingApproval": result.awaitingApproval,
            "executed": result.executed,
            "errorCode": result.run.errorCode,
        }
        # A denied or approval-pending run is a valid business result. Retrying
        # it at transport level would duplicate run rows and approval prompts.
        return JobOutcome(outcome="SUCCEEDED", retryable=False, summary=summary)


__all__ = ["AgentRunJobHandler"]
