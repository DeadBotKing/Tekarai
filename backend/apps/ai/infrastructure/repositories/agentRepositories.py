"""Django persistence for the Phase 13-Y agent foundation.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped, and entities are rehydrated through the domain
records so an invalid stored row can never re-enter the domain.

``deleteSettledBefore`` spares runs that are still in flight: a run
waiting on a human approval (or its steps) must not vanish under
retention while somebody is still deciding (§Y.11).
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Q

from apps.ai.domain.entities.agentRecords import (
    AIAgentApproval,
    AIAgentDefinition,
    AIAgentRun,
    AIAgentStep,
)
from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.exceptions import AIAgentInvalid
from apps.ai.infrastructure.models import (
    AIAgentApprovalModel,
    AIAgentDefinitionModel,
    AIAgentRunModel,
    AIAgentStepModel,
)


def definitionToEntity(row: AIAgentDefinitionModel) -> AIAgentDefinition:
    return AIAgentDefinition(
        tenantId=row.tenantId,
        code=row.code,
        name=row.name,
        description=row.description or "",
        instructions=row.instructions,
        version=row.version,
        accessLevel=row.accessLevel,
        riskLevel=row.riskLevel,
        capabilityCodes=tuple(row.capabilityCodes or ()),
        toolCodes=tuple(row.toolCodes or ()),
        outputSchema=dict(row.outputSchema or {}),
        contextPolicy=dict(row.contextPolicy or {}),
        modelPolicy=dict(row.modelPolicy or {}),
        permissionPolicy=dict(row.permissionPolicy or {}),
        executionPolicy=dict(row.executionPolicy or {}),
        declaredApprovalMode=row.declaredApprovalMode or "",
        status=row.status,
        approvedBy=row.approvedBy,
        approvedAt=row.approvedAt,
        retiredAt=row.retiredAt,
        rejectionReason=row.rejectionReason or "",
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
        updatedAt=row.updatedAt,
    )


def approvalToEntity(row: AIAgentApprovalModel) -> AIAgentApproval:
    return AIAgentApproval(
        tenantId=row.tenantId,
        agentCode=row.agentCode,
        agentVersion=row.agentVersion,
        inputFingerprint=row.inputFingerprint,
        mode=row.mode,
        decision=row.decision,
        requiredApprovals=row.requiredApprovals,
        approvals=tuple(uuid.UUID(str(value)) for value in (row.approvals or [])),
        requestedBy=row.requestedBy,
        executionId=row.executionId,
        reason=row.reason or "",
        expiresAt=row.expiresAt,
        decidedAt=row.decidedAt,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


def runToEntity(row: AIAgentRunModel) -> AIAgentRun:
    return AIAgentRun(
        tenantId=row.tenantId,
        agentId=row.agentId,
        agentCode=row.agentCode,
        agentVersion=row.agentVersion,
        input=dict(row.input or {}),
        status=row.status,
        requestedBy=row.requestedBy,
        inputFingerprint=row.inputFingerprint,
        answer=row.answer or "",
        output=dict(row.output or {}),
        errorCode=row.errorCode or "",
        approvalId=row.approvalId,
        startedAt=row.startedAt,
        completedAt=row.completedAt,
        latencyMs=row.latencyMs,
        modelCallCount=row.modelCallCount,
        toolCallCount=row.toolCallCount,
        inputTokens=row.inputTokens,
        outputTokens=row.outputTokens,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


def stepToEntity(row: AIAgentStepModel) -> AIAgentStep:
    return AIAgentStep(
        tenantId=row.tenantId,
        runId=row.runId,
        ordinal=row.ordinal,
        kind=row.kind,
        status=row.status,
        toolCode=row.toolCode or "",
        toolVersion=row.toolVersion,
        arguments=dict(row.arguments or {}),
        result=dict(row.result or {}),
        reason=row.reason or "",
        tokensIn=row.tokensIn,
        tokensOut=row.tokensOut,
        latencyMs=row.latencyMs,
        errorCode=row.errorCode or "",
        id=row.id,
        createdAt=row.createdAt,
    )


class DjangoAgentDefinitionStore:
    """``AgentDefinitionStore`` over ``aiAgentDefinitions``."""

    def saveDefinition(self, definition: AIAgentDefinition) -> AIAgentDefinition:
        row = AIAgentDefinitionModel.objects.create(
            id=definition.id,
            tenantId=definition.tenantId,
            code=definition.code,
            version=definition.version,
            name=definition.name,
            description=definition.description,
            instructions=definition.instructions,
            accessLevel=definition.accessLevel,
            riskLevel=definition.riskLevel,
            capabilityCodes=list(definition.capabilityCodes),
            toolCodes=list(definition.toolCodes),
            outputSchema=dict(definition.outputSchema),
            contextPolicy=dict(definition.contextPolicy),
            modelPolicy=dict(definition.modelPolicy),
            permissionPolicy=dict(definition.permissionPolicy),
            executionPolicy=dict(definition.executionPolicy),
            declaredApprovalMode=definition.declaredApprovalMode,
            status=definition.status,
            approvedBy=definition.approvedBy,
            approvedAt=definition.approvedAt,
            retiredAt=definition.retiredAt,
            rejectionReason=definition.rejectionReason,
            metadata=dict(definition.metadata),
        )
        return definitionToEntity(row)

    def updateDefinition(self, definition: AIAgentDefinition) -> AIAgentDefinition:
        updated = AIAgentDefinitionModel.objects.filter(
            tenantId=definition.tenantId, id=definition.id
        ).update(
            name=definition.name,
            description=definition.description,
            instructions=definition.instructions,
            status=definition.status,
            approvedBy=definition.approvedBy,
            approvedAt=definition.approvedAt,
            retiredAt=definition.retiredAt,
            rejectionReason=definition.rejectionReason,
            declaredApprovalMode=definition.declaredApprovalMode,
            metadata=dict(definition.metadata),
        )
        if not updated:
            raise AIAgentInvalid("Agent definition row was not found for update.")
        return definitionToEntity(
            AIAgentDefinitionModel.objects.get(tenantId=definition.tenantId, id=definition.id)
        )

    def getDefinition(
        self, tenantId: uuid.UUID, definitionId: uuid.UUID
    ) -> AIAgentDefinition | None:
        row = AIAgentDefinitionModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(definitionId, "definitionId"),
        ).first()
        return None if row is None else definitionToEntity(row)

    def findVersion(
        self, tenantId: uuid.UUID, agentCode: str, version: int
    ) -> AIAgentDefinition | None:
        row = AIAgentDefinitionModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            code=str(agentCode).strip().upper(),
            version=int(version),
        ).first()
        return None if row is None else definitionToEntity(row)

    def listVersions(self, tenantId: uuid.UUID, agentCode: str) -> tuple[AIAgentDefinition, ...]:
        rows = AIAgentDefinitionModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), code=str(agentCode).strip().upper()
        ).order_by("version")
        return tuple(definitionToEntity(row) for row in rows)

    def listDefinitions(
        self, tenantId: uuid.UUID, *, statuses: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AIAgentDefinition, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if statuses:
            query &= Q(status__in=[str(value).strip().upper() for value in statuses])
        rows = AIAgentDefinitionModel.objects.filter(query).order_by("code", "version")[
            : max(1, int(limit))
        ]
        return tuple(definitionToEntity(row) for row in rows)


class DjangoAgentApprovalStore:
    """``AgentApprovalStore`` over ``aiAgentApprovals``."""

    def saveApproval(self, approval: AIAgentApproval) -> AIAgentApproval:
        row = AIAgentApprovalModel.objects.create(
            id=approval.id,
            tenantId=approval.tenantId,
            agentCode=approval.agentCode,
            agentVersion=approval.agentVersion,
            inputFingerprint=approval.inputFingerprint,
            mode=approval.mode,
            decision=approval.decision,
            requiredApprovals=approval.requiredApprovals,
            approvals=[str(value) for value in approval.approvals],
            requestedBy=approval.requestedBy,
            executionId=approval.executionId,
            reason=approval.reason,
            expiresAt=approval.expiresAt,
            decidedAt=approval.decidedAt,
            metadata=dict(approval.metadata),
        )
        return approvalToEntity(row)

    def updateApproval(self, approval: AIAgentApproval) -> AIAgentApproval:
        updated = AIAgentApprovalModel.objects.filter(
            tenantId=approval.tenantId, id=approval.id
        ).update(
            decision=approval.decision,
            approvals=[str(value) for value in approval.approvals],
            reason=approval.reason,
            decidedAt=approval.decidedAt,
            metadata=dict(approval.metadata),
        )
        if not updated:
            raise AIAgentInvalid("Agent approval row was not found for update.")
        return approvalToEntity(
            AIAgentApprovalModel.objects.get(tenantId=approval.tenantId, id=approval.id)
        )

    def getApproval(self, tenantId: uuid.UUID, approvalId: uuid.UUID) -> AIAgentApproval | None:
        row = AIAgentApprovalModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(approvalId, "approvalId"),
        ).first()
        return None if row is None else approvalToEntity(row)

    def findPending(
        self, tenantId: uuid.UUID, agentCode: str, fingerprint: str
    ) -> AIAgentApproval | None:
        row = (
            AIAgentApprovalModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                agentCode=str(agentCode).strip().upper(),
                inputFingerprint=fingerprint,
                decision="PENDING",
            )
            .order_by("-createdAt")
            .first()
        )
        return None if row is None else approvalToEntity(row)

    def findUsable(
        self,
        tenantId: uuid.UUID,
        agentCode: str,
        fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> AIAgentApproval | None:
        query = AIAgentApprovalModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            agentCode=str(agentCode).strip().upper(),
            inputFingerprint=fingerprint,
            decision="GRANTED",
        )
        if now is not None:
            query = query.filter(Q(expiresAt__isnull=True) | Q(expiresAt__gt=now))
        row = query.order_by("-decidedAt", "-createdAt").first()
        return None if row is None else approvalToEntity(row)

    def findLatest(
        self, tenantId: uuid.UUID, agentCode: str, fingerprint: str
    ) -> AIAgentApproval | None:
        """The most recent decision about this exact run input, whatever it was.

        A denial has to be findable, otherwise a retrying agent could
        re-open the same request forever and turn human review into spam.
        """

        row = (
            AIAgentApprovalModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                agentCode=str(agentCode).strip().upper(),
                inputFingerprint=fingerprint,
            )
            .order_by("-createdAt")
            .first()
        )
        return None if row is None else approvalToEntity(row)

    def listApprovals(
        self, tenantId: uuid.UUID, *, decisions: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AIAgentApproval, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if decisions:
            query &= Q(decision__in=[str(value).strip().upper() for value in decisions])
        rows = AIAgentApprovalModel.objects.filter(query).order_by("-createdAt")[
            : max(1, int(limit))
        ]
        return tuple(approvalToEntity(row) for row in rows)


class DjangoAgentExecutionStore:
    """``AgentExecutionStore`` over ``aiAgentRuns`` and ``aiAgentSteps``."""

    def saveRun(self, run: AIAgentRun) -> AIAgentRun:
        row = AIAgentRunModel.objects.create(
            id=run.id,
            tenantId=run.tenantId,
            agentId=run.agentId,
            agentCode=run.agentCode,
            agentVersion=run.agentVersion,
            requestedBy=run.requestedBy,
            input=dict(run.input),
            inputFingerprint=run.inputFingerprint,
            status=run.status,
            answer=run.answer,
            output=dict(run.output),
            errorCode=run.errorCode,
            approvalId=run.approvalId,
            startedAt=run.startedAt,
            completedAt=run.completedAt,
            latencyMs=run.latencyMs,
            modelCallCount=run.modelCallCount,
            toolCallCount=run.toolCallCount,
            inputTokens=run.inputTokens,
            outputTokens=run.outputTokens,
            metadata=dict(run.metadata),
        )
        return runToEntity(row)

    def updateRun(self, run: AIAgentRun) -> AIAgentRun:
        updated = AIAgentRunModel.objects.filter(tenantId=run.tenantId, id=run.id).update(
            status=run.status,
            answer=run.answer,
            output=dict(run.output),
            errorCode=run.errorCode,
            approvalId=run.approvalId,
            startedAt=run.startedAt,
            completedAt=run.completedAt,
            latencyMs=run.latencyMs,
            modelCallCount=run.modelCallCount,
            toolCallCount=run.toolCallCount,
            inputTokens=run.inputTokens,
            outputTokens=run.outputTokens,
            metadata=dict(run.metadata),
        )
        if not updated:
            raise AIAgentInvalid("Agent run row was not found for update.")
        return runToEntity(AIAgentRunModel.objects.get(tenantId=run.tenantId, id=run.id))

    def getRun(self, tenantId: uuid.UUID, runId: uuid.UUID) -> AIAgentRun | None:
        row = AIAgentRunModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(runId, "runId"),
        ).first()
        return None if row is None else runToEntity(row)

    def listRuns(
        self,
        tenantId: uuid.UUID,
        *,
        agentCode: str = "",
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[AIAgentRun, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if agentCode:
            query &= Q(agentCode=str(agentCode).strip().upper())
        if statuses:
            query &= Q(status__in=[str(value).strip().upper() for value in statuses])
        rows = AIAgentRunModel.objects.filter(query).order_by("createdAt", "id")[
            : max(1, int(limit))
        ]
        return tuple(runToEntity(row) for row in rows)

    def saveStep(self, step: AIAgentStep) -> AIAgentStep:
        row = AIAgentStepModel.objects.create(
            id=step.id,
            tenantId=step.tenantId,
            runId=step.runId,
            ordinal=step.ordinal,
            kind=step.kind,
            status=step.status,
            toolCode=step.toolCode,
            toolVersion=step.toolVersion,
            arguments=dict(step.arguments),
            result=dict(step.result),
            reason=step.reason,
            tokensIn=step.tokensIn,
            tokensOut=step.tokensOut,
            latencyMs=step.latencyMs,
            errorCode=step.errorCode,
        )
        return stepToEntity(row)

    def listSteps(self, tenantId: uuid.UUID, runId: uuid.UUID) -> tuple[AIAgentStep, ...]:
        rows = AIAgentStepModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            runId=requireUuid(runId, "runId"),
        ).order_by("ordinal")
        return tuple(stepToEntity(row) for row in rows)

    def deleteSettledBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> tuple[int, int]:
        """Purge settled runs (with their step rows) only; in-flight runs
        awaiting a human decision are spared (§Y.11)."""

        query = AIAgentRunModel.objects.filter(
            createdAt__lt=cutoff,
            status__in=("COMPLETED", "FAILED", "CANCELLED", "DENIED"),
        )
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        runIds = list(query.values_list("id", flat=True))
        stepRows = AIAgentStepModel.objects.filter(runId__in=runIds)
        removedSteps = int(stepRows.count())
        stepRows.delete()
        removedRuns, _ = query.delete()
        return (int(removedRuns), removedSteps)


__all__ = [
    "DjangoAgentApprovalStore",
    "DjangoAgentDefinitionStore",
    "DjangoAgentExecutionStore",
    "approvalToEntity",
    "definitionToEntity",
    "runToEntity",
    "stepToEntity",
]
