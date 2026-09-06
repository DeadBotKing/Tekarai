"""Django persistence for the Phase 13-X tool platform.

Row↔entity mapping only — no business rule lives here. Every read and
write is tenant-scoped, and entities are rehydrated through the domain
records so an invalid stored row can never re-enter the domain.

``deleteInvocationsBefore`` spares calls that are still in flight: an
invocation waiting on a human approval must not vanish under retention
while somebody is still deciding.
"""

from __future__ import annotations

import uuid
from datetime import datetime

from django.db.models import Q

from apps.ai.domain.entities.aiRecords import requireUuid
from apps.ai.domain.entities.toolRecords import (
    AIToolApproval,
    AIToolDefinition,
    AIToolInvocation,
)
from apps.ai.domain.exceptions import AIToolInvalid
from apps.ai.infrastructure.models import (
    AIToolApprovalModel,
    AIToolDefinitionModel,
    AIToolInvocationModel,
)


def definitionToEntity(row: AIToolDefinitionModel) -> AIToolDefinition:
    return AIToolDefinition(
        tenantId=row.tenantId,
        code=row.code,
        name=row.name,
        description=row.description,
        version=row.version,
        effect=row.effect,
        riskLevel=row.riskLevel,
        inputSchema=dict(row.inputSchema or {}),
        outputSchema=dict(row.outputSchema or {}),
        requiredPermission=row.requiredPermission or "",
        declaredApprovalMode=row.declaredApprovalMode or "",
        timeoutSeconds=row.timeoutSeconds,
        maxCallsPerRequest=row.maxCallsPerRequest,
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


def approvalToEntity(row: AIToolApprovalModel) -> AIToolApproval:
    return AIToolApproval(
        tenantId=row.tenantId,
        toolCode=row.toolCode,
        toolVersion=row.toolVersion,
        argumentFingerprint=row.argumentFingerprint,
        mode=row.mode,
        decision=row.decision,
        requiredApprovals=row.requiredApprovals,
        approvals=tuple(uuid.UUID(str(value)) for value in (row.approvals or [])),
        requestedBy=row.requestedBy,
        invocationId=row.invocationId,
        reason=row.reason or "",
        expiresAt=row.expiresAt,
        decidedAt=row.decidedAt,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


def invocationToEntity(row: AIToolInvocationModel) -> AIToolInvocation:
    return AIToolInvocation(
        tenantId=row.tenantId,
        toolCode=row.toolCode,
        toolVersion=row.toolVersion,
        requestId=row.requestId,
        arguments=dict(row.arguments or {}),
        fingerprint=row.fingerprint,
        status=row.status,
        result=dict(row.result or {}),
        errorCode=row.errorCode or "",
        approvalId=row.approvalId,
        actorId=row.actorId,
        startedAt=row.startedAt,
        completedAt=row.completedAt,
        latencyMs=row.latencyMs,
        toolId=row.toolId,
        id=row.id,
        metadata=dict(row.metadata or {}),
        createdAt=row.createdAt,
    )


class DjangoToolDefinitionStore:
    """``ToolDefinitionStore`` over ``aiToolDefinitions``."""

    def saveDefinition(self, definition: AIToolDefinition) -> AIToolDefinition:
        row = AIToolDefinitionModel.objects.create(
            id=definition.id,
            tenantId=definition.tenantId,
            code=definition.code,
            version=definition.version,
            name=definition.name,
            description=definition.description,
            effect=definition.effect,
            riskLevel=definition.riskLevel,
            inputSchema=dict(definition.inputSchema),
            outputSchema=dict(definition.outputSchema),
            requiredPermission=definition.requiredPermission,
            declaredApprovalMode=definition.declaredApprovalMode,
            timeoutSeconds=definition.timeoutSeconds,
            maxCallsPerRequest=definition.maxCallsPerRequest,
            status=definition.status,
            approvedBy=definition.approvedBy,
            approvedAt=definition.approvedAt,
            retiredAt=definition.retiredAt,
            rejectionReason=definition.rejectionReason,
            metadata=dict(definition.metadata),
        )
        return definitionToEntity(row)

    def updateDefinition(self, definition: AIToolDefinition) -> AIToolDefinition:
        updated = AIToolDefinitionModel.objects.filter(
            tenantId=definition.tenantId, id=definition.id
        ).update(
            name=definition.name,
            description=definition.description,
            status=definition.status,
            approvedBy=definition.approvedBy,
            approvedAt=definition.approvedAt,
            retiredAt=definition.retiredAt,
            rejectionReason=definition.rejectionReason,
            timeoutSeconds=definition.timeoutSeconds,
            maxCallsPerRequest=definition.maxCallsPerRequest,
            metadata=dict(definition.metadata),
        )
        if not updated:
            raise AIToolInvalid("Tool definition row was not found for update.")
        return definitionToEntity(
            AIToolDefinitionModel.objects.get(tenantId=definition.tenantId, id=definition.id)
        )

    def getDefinition(
        self, tenantId: uuid.UUID, definitionId: uuid.UUID
    ) -> AIToolDefinition | None:
        row = AIToolDefinitionModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(definitionId, "definitionId"),
        ).first()
        return None if row is None else definitionToEntity(row)

    def findVersion(
        self, tenantId: uuid.UUID, toolCode: str, version: int
    ) -> AIToolDefinition | None:
        row = AIToolDefinitionModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            code=str(toolCode).strip().upper(),
            version=int(version),
        ).first()
        return None if row is None else definitionToEntity(row)

    def listVersions(self, tenantId: uuid.UUID, toolCode: str) -> tuple[AIToolDefinition, ...]:
        rows = AIToolDefinitionModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"), code=str(toolCode).strip().upper()
        ).order_by("version")
        return tuple(definitionToEntity(row) for row in rows)

    def listDefinitions(
        self, tenantId: uuid.UUID, *, statuses: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AIToolDefinition, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if statuses:
            query &= Q(status__in=[str(value).strip().upper() for value in statuses])
        rows = AIToolDefinitionModel.objects.filter(query).order_by("code", "version")[
            : max(1, int(limit))
        ]
        return tuple(definitionToEntity(row) for row in rows)


class DjangoToolApprovalStore:
    """``ToolApprovalStore`` over ``aiToolApprovals``."""

    def saveApproval(self, approval: AIToolApproval) -> AIToolApproval:
        row = AIToolApprovalModel.objects.create(
            id=approval.id,
            tenantId=approval.tenantId,
            toolCode=approval.toolCode,
            toolVersion=approval.toolVersion,
            argumentFingerprint=approval.argumentFingerprint,
            mode=approval.mode,
            decision=approval.decision,
            requiredApprovals=approval.requiredApprovals,
            approvals=[str(value) for value in approval.approvals],
            requestedBy=approval.requestedBy,
            invocationId=approval.invocationId,
            reason=approval.reason,
            expiresAt=approval.expiresAt,
            decidedAt=approval.decidedAt,
            metadata=dict(approval.metadata),
        )
        return approvalToEntity(row)

    def updateApproval(self, approval: AIToolApproval) -> AIToolApproval:
        updated = AIToolApprovalModel.objects.filter(
            tenantId=approval.tenantId, id=approval.id
        ).update(
            decision=approval.decision,
            approvals=[str(value) for value in approval.approvals],
            reason=approval.reason,
            decidedAt=approval.decidedAt,
            metadata=dict(approval.metadata),
        )
        if not updated:
            raise AIToolInvalid("Tool approval row was not found for update.")
        return approvalToEntity(
            AIToolApprovalModel.objects.get(tenantId=approval.tenantId, id=approval.id)
        )

    def getApproval(self, tenantId: uuid.UUID, approvalId: uuid.UUID) -> AIToolApproval | None:
        row = AIToolApprovalModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(approvalId, "approvalId"),
        ).first()
        return None if row is None else approvalToEntity(row)

    def findPending(
        self, tenantId: uuid.UUID, toolCode: str, fingerprint: str
    ) -> AIToolApproval | None:
        row = (
            AIToolApprovalModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                toolCode=str(toolCode).strip().upper(),
                argumentFingerprint=fingerprint,
                decision="PENDING",
            )
            .order_by("-createdAt")
            .first()
        )
        return None if row is None else approvalToEntity(row)

    def findUsable(
        self,
        tenantId: uuid.UUID,
        toolCode: str,
        fingerprint: str,
        *,
        now: datetime | None = None,
    ) -> AIToolApproval | None:
        query = AIToolApprovalModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            toolCode=str(toolCode).strip().upper(),
            argumentFingerprint=fingerprint,
            decision="GRANTED",
        )
        if now is not None:
            query = query.filter(Q(expiresAt__isnull=True) | Q(expiresAt__gt=now))
        row = query.order_by("-decidedAt", "-createdAt").first()
        return None if row is None else approvalToEntity(row)

    def findLatest(
        self, tenantId: uuid.UUID, toolCode: str, fingerprint: str
    ) -> AIToolApproval | None:
        """The most recent decision about this exact proposal, whatever it was.

        A denial has to be findable, otherwise a retrying agent could
        re-open the same request forever and turn human review into spam.
        """

        row = (
            AIToolApprovalModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                toolCode=str(toolCode).strip().upper(),
                argumentFingerprint=fingerprint,
            )
            .order_by("-createdAt")
            .first()
        )
        return None if row is None else approvalToEntity(row)

    def listApprovals(
        self, tenantId: uuid.UUID, *, decisions: tuple[str, ...] = (), limit: int = 200
    ) -> tuple[AIToolApproval, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if decisions:
            query &= Q(decision__in=[str(value).strip().upper() for value in decisions])
        rows = AIToolApprovalModel.objects.filter(query).order_by("-createdAt")[
            : max(1, int(limit))
        ]
        return tuple(approvalToEntity(row) for row in rows)


class DjangoToolInvocationStore:
    """``ToolInvocationStore`` over ``aiToolInvocations``."""

    def saveInvocation(self, invocation: AIToolInvocation) -> AIToolInvocation:
        row = AIToolInvocationModel.objects.create(
            id=invocation.id,
            tenantId=invocation.tenantId,
            toolCode=invocation.toolCode,
            toolVersion=invocation.toolVersion,
            toolId=invocation.toolId,
            requestId=invocation.requestId,
            actorId=invocation.actorId,
            approvalId=invocation.approvalId,
            arguments=dict(invocation.arguments),
            fingerprint=invocation.fingerprint,
            status=invocation.status,
            result=dict(invocation.result),
            errorCode=invocation.errorCode,
            startedAt=invocation.startedAt,
            completedAt=invocation.completedAt,
            latencyMs=invocation.latencyMs,
            metadata=dict(invocation.metadata),
        )
        return invocationToEntity(row)

    def updateInvocation(self, invocation: AIToolInvocation) -> AIToolInvocation:
        updated = AIToolInvocationModel.objects.filter(
            tenantId=invocation.tenantId, id=invocation.id
        ).update(
            status=invocation.status,
            result=dict(invocation.result),
            errorCode=invocation.errorCode,
            approvalId=invocation.approvalId,
            startedAt=invocation.startedAt,
            completedAt=invocation.completedAt,
            latencyMs=invocation.latencyMs,
            metadata=dict(invocation.metadata),
        )
        if not updated:
            raise AIToolInvalid("Tool invocation row was not found for update.")
        return invocationToEntity(
            AIToolInvocationModel.objects.get(tenantId=invocation.tenantId, id=invocation.id)
        )

    def getInvocation(
        self, tenantId: uuid.UUID, invocationId: uuid.UUID
    ) -> AIToolInvocation | None:
        row = AIToolInvocationModel.objects.filter(
            tenantId=requireUuid(tenantId, "tenantId"),
            id=requireUuid(invocationId, "invocationId"),
        ).first()
        return None if row is None else invocationToEntity(row)

    def listInvocations(
        self,
        tenantId: uuid.UUID,
        *,
        requestId: uuid.UUID | None = None,
        toolCode: str = "",
        statuses: tuple[str, ...] = (),
        limit: int = 200,
    ) -> tuple[AIToolInvocation, ...]:
        query = Q(tenantId=requireUuid(tenantId, "tenantId"))
        if requestId is not None:
            query &= Q(requestId=requireUuid(requestId, "requestId"))
        if toolCode:
            query &= Q(toolCode=str(toolCode).strip().upper())
        if statuses:
            query &= Q(status__in=[str(value).strip().upper() for value in statuses])
        rows = AIToolInvocationModel.objects.filter(query).order_by("createdAt", "id")[
            : max(1, int(limit))
        ]
        return tuple(invocationToEntity(row) for row in rows)

    def fingerprintsForRequest(self, tenantId: uuid.UUID, requestId: uuid.UUID) -> tuple[str, ...]:
        rows = (
            AIToolInvocationModel.objects.filter(
                tenantId=requireUuid(tenantId, "tenantId"),
                requestId=requireUuid(requestId, "requestId"),
            )
            .order_by("createdAt")
            .values_list("fingerprint", flat=True)
        )
        return tuple(rows)

    def deleteInvocationsBefore(self, tenantId: uuid.UUID | None, cutoff: datetime) -> int:
        """Purge settled calls only; one awaiting approval is spared."""

        query = AIToolInvocationModel.objects.filter(
            createdAt__lt=cutoff,
            status__in=("SUCCEEDED", "FAILED", "DENIED", "CANCELLED"),
        )
        if tenantId is not None:
            query = query.filter(tenantId=requireUuid(tenantId, "tenantId"))
        removed, _ = query.delete()
        return int(removed)


__all__ = [
    "DjangoToolApprovalStore",
    "DjangoToolDefinitionStore",
    "DjangoToolInvocationStore",
    "approvalToEntity",
    "definitionToEntity",
    "invocationToEntity",
]
