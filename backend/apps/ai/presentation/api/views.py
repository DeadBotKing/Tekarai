"""Thin Phase 13-Z REST boundary.

Every view performs only authentication/authorization, input validation,
application-service invocation and response mapping. No ORM or provider SDK is
imported here (Master Specification §39).
"""

from __future__ import annotations

import uuid
from dataclasses import asdict, is_dataclass
from datetime import datetime
from typing import Any, cast

from rest_framework import serializers as drfSerializers
from rest_framework.request import Request
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.ai.application.services.agentService import RegisterAgentCommand, RunAgentCommand
from apps.ai.application.services.queueService import SubmitJobCommand
from apps.ai.domain.services.authorizationService import AuthorizationPrincipal
from apps.ai.domain.services.jobQueue import JobFilter
from apps.ai.domain.valueObjects.agentTypes import redactInput
from apps.ai.infrastructure import container
from apps.ai.presentation.api.serializers import (
    AgentActionSerializer,
    AgentRegistrationSerializer,
    AgentRunSerializer,
    AgentVersionSerializer,
    ApprovalDecisionSerializer,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.presentation.api.permissions import actionPermission
from apps.sharedKernel.presentation.api.response import successEnvelope

ReadPermission = actionPermission("ai.agent.read")
ManagePermission = actionPermission("ai.agent.manage")
RunPermission = actionPermission("ai.agent.run")
ApprovePermission = actionPermission("ai.agent.approve")


class AgentListView(APIView):
    def get_permissions(self):
        permission = ManagePermission if self.request.method == "POST" else ReadPermission
        return [permission()]

    def get(self, request: Request) -> Response:
        service = container.agentService()
        statuses = _csv(request.query_params.get("status", ""))
        items = service.listAgents(_tenantId(), statuses=statuses, limit=_limit(request))
        return Response(successEnvelope([_json(item) for item in items], _listMeta(items)))

    def post(self, request: Request) -> Response:
        serializer = AgentRegistrationSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        descriptor = container.agentService().registerAgent(
            _tenantId(),
            RegisterAgentCommand(
                code=data["code"],
                name=data["name"],
                instructions=data["instructions"],
                description=data.get("description", ""),
                version=data.get("version"),
                accessLevel=data.get("accessLevel", "ADVISORY"),
                riskLevel=data.get("riskLevel", "LOW"),
                capabilityCodes=tuple(data.get("capabilityCodes", ())),
                toolCodes=tuple(data.get("toolCodes", ())),
                outputSchema=dict(data.get("outputSchema", {})),
                contextPolicy=dict(data.get("contextPolicy", {})),
                modelPolicy=dict(data.get("modelPolicy", {})),
                permissionPolicy=dict(data.get("permissionPolicy", {})),
                executionPolicy=dict(data.get("executionPolicy", {})),
                declaredApprovalMode=data.get("declaredApprovalMode", ""),
                metadata=dict(data.get("metadata", {})),
            ),
        )
        return Response(successEnvelope(_json(descriptor)), status=201)


class AgentDetailView(APIView):
    permission_classes = [ReadPermission]

    def get(self, request: Request, agentCode: str, version: int) -> Response:
        item = container.agentService().describeAgent(_tenantId(), agentCode, version)
        return Response(successEnvelope(_json(item)))


class AgentVersionView(APIView):
    permission_classes = [ManagePermission]

    def post(self, request: Request, agentCode: str) -> Response:
        serializer = AgentVersionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        item = container.agentService().publishNewVersion(
            _tenantId(), agentCode, **dict(serializer.validated_data.get("overrides", {}))
        )
        return Response(successEnvelope(_json(item)), status=201)


class AgentLifecycleView(APIView):
    def get_permissions(self):
        permission = (
            ApprovePermission
            if self.kwargs.get("action") in ("approve", "reject")
            else ManagePermission
        )
        return [permission()]

    def post(self, request: Request, agentCode: str, version: int, action: str) -> Response:
        serializer = AgentActionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        reason = serializer.validated_data.get("reason", "")
        service = container.agentService()
        actorId = _actorId()
        operations = {
            "submit": lambda: service.submitForApproval(_tenantId(), agentCode, version),
            "approve": lambda: service.approveAgent(
                _tenantId(), agentCode, version, approverId=actorId
            ),
            "reject": lambda: service.rejectAgent(_tenantId(), agentCode, version, reason),
            "suspend": lambda: service.suspendAgent(_tenantId(), agentCode, version, reason),
            "resume": lambda: service.resumeAgent(_tenantId(), agentCode, version),
            "retire": lambda: service.retireAgent(_tenantId(), agentCode, version),
        }
        if action not in operations:
            raise drfSerializers.ValidationError({"action": "Unsupported lifecycle action."})
        return Response(successEnvelope(_json(operations[action]())))


class AgentRunCreateView(APIView):
    permission_classes = [RunPermission]

    def post(self, request: Request, agentCode: str) -> Response:
        serializer = AgentRunSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        data = serializer.validated_data
        if data.get("mode", "SYNC") == "ASYNC":
            return self._async(request, agentCode, data)
        result = container.agentService().runAgent(
            _tenantId(),
            RunAgentCommand(
                agentCode=agentCode,
                input=dict(data.get("input", {})),
                version=data.get("version"),
                principal=_principal(),
                actorId=_actorId(),
                reason=data.get("reason", ""),
                approvalId=data.get("approvalId"),
            ),
        )
        status = 202 if result.awaitingApproval else 201
        return Response(successEnvelope(_runResult(result)), status=status)

    def _async(self, request: Request, agentCode: str, data: dict[str, Any]) -> Response:
        key = str(data.get("idempotencyKey") or request.headers.get("Idempotency-Key", "")).strip()
        if not key:
            raise drfSerializers.ValidationError(
                {"idempotencyKey": "Async agent runs require an idempotency key."}
            )
        payload = {
            "agentCode": agentCode,
            "version": data.get("version"),
            "input": redactInput(data.get("input", {})),
            "reason": data.get("reason", ""),
            "approvalId": str(data["approvalId"]) if data.get("approvalId") else None,
            "actorId": str(_actorId()),
            "subjectType": "USER",
        }
        context = currentContext()
        job = container.queueService().submitJob(
            SubmitJobCommand(
                tenantId=_tenantId(),
                kind="AGENT_RUN",
                payload=payload,
                idempotencyKey=key,
                priority=data.get("priority", 5),
                correlationId=context.correlationId,
            )
        )
        return Response(successEnvelope(_job(job)), status=202)


class RunListView(APIView):
    permission_classes = [ReadPermission]

    def get(self, request: Request) -> Response:
        service = container.agentService()
        items = service.listRuns(
            _tenantId(),
            agentCode=str(request.query_params.get("agentCode", "")),
            statuses=_csv(request.query_params.get("status", "")),
            limit=_limit(request),
        )
        return Response(successEnvelope([_json(item) for item in items], _listMeta(items)))


class RunDetailView(APIView):
    permission_classes = [ReadPermission]

    def get(self, request: Request, runId: str) -> Response:
        run = container.agentService().describeRun(_tenantId(), runId)
        return Response(successEnvelope(_json(run)))


class RunStepListView(APIView):
    permission_classes = [ReadPermission]

    def get(self, request: Request, runId: str) -> Response:
        items = container.agentService().listSteps(_tenantId(), runId)
        return Response(successEnvelope([_json(item) for item in items], _listMeta(items)))


class ApprovalListView(APIView):
    permission_classes = [ApprovePermission]

    def get(self, request: Request) -> Response:
        items = container.agentService().listApprovals(
            _tenantId(),
            decisions=_csv(request.query_params.get("decision", "")),
            limit=_limit(request),
        )
        return Response(successEnvelope([_json(item) for item in items], _listMeta(items)))


class ApprovalDetailView(APIView):
    permission_classes = [ApprovePermission]

    def get(self, request: Request, approvalId: str) -> Response:
        item = container.agentService().describeApproval(_tenantId(), approvalId)
        return Response(successEnvelope(_json(item)))


class ApprovalDecisionView(APIView):
    permission_classes = [ApprovePermission]

    def post(self, request: Request, approvalId: str, action: str) -> Response:
        serializer = ApprovalDecisionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        service = container.agentService()
        if action == "grant":
            item = service.grantApproval(_tenantId(), approvalId, approverId=_actorId())
        elif action == "deny":
            item = service.denyApproval(
                _tenantId(),
                approvalId,
                serializer.validated_data.get("reason", ""),
                approverId=_actorId(),
            )
        else:
            raise drfSerializers.ValidationError({"action": "Unsupported approval action."})
        return Response(successEnvelope(_json(item)))


class JobListView(APIView):
    permission_classes = [ReadPermission]

    def get(self, request: Request) -> Response:
        jobFilter = JobFilter(
            status=request.query_params.get("status") or None,
            kind=request.query_params.get("kind") or "AGENT_RUN",
        )
        items = container.queueService().listJobs(_tenantId(), jobFilter)
        return Response(successEnvelope([_job(item) for item in items], _listMeta(items)))


class JobDetailView(APIView):
    permission_classes = [ReadPermission]

    def get(self, request: Request, jobId: str) -> Response:
        item = container.queueService().describeJob(_tenantId(), jobId)
        return Response(successEnvelope(_job(item)))


class JobCancelView(APIView):
    permission_classes = [RunPermission]

    def post(self, request: Request, jobId: str) -> Response:
        item = container.queueService().cancelJob(_tenantId(), jobId)
        return Response(successEnvelope(_job(item)))


class ReleaseReadinessView(APIView):
    permission_classes = [ManagePermission]

    def get(self, request: Request) -> Response:
        result = container.releaseReadiness()
        return Response(successEnvelope(result), status=200 if result["ready"] else 503)


def _tenantId() -> uuid.UUID:
    value = currentContext().tenantId or currentContext().actorTenantId
    if not value:
        from rest_framework.exceptions import PermissionDenied

        raise PermissionDenied("Tenant context is required.")
    return uuid.UUID(value)


def _actorId() -> uuid.UUID:
    value = currentContext().actorId
    if not value:
        from rest_framework.exceptions import NotAuthenticated

        raise NotAuthenticated()
    return uuid.UUID(value)


def _principal() -> AuthorizationPrincipal:
    return AuthorizationPrincipal(tenantId=_tenantId(), subjectId=_actorId())


def _csv(value: Any) -> tuple[str, ...]:
    return tuple(part.strip().upper() for part in str(value or "").split(",") if part.strip())


def _limit(request: Request) -> int:
    try:
        value = int(request.query_params.get("limit", "100"))
    except (TypeError, ValueError) as exc:
        raise drfSerializers.ValidationError({"limit": "Must be an integer."}) from exc
    if value < 1 or value > 200:
        raise drfSerializers.ValidationError({"limit": "Must be between 1 and 200."})
    return value


def _json(value: Any) -> Any:
    if is_dataclass(value) and not isinstance(value, type):
        return _json(asdict(cast(Any, value)))
    if isinstance(value, dict):
        return {str(key): _json(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json(item) for item in value]
    if isinstance(value, (uuid.UUID, datetime)):
        return value.isoformat() if isinstance(value, datetime) else str(value)
    return value


def _runResult(result: Any) -> dict[str, Any]:
    return {
        "run": _json(result.run),
        "approval": _json(result.approval) if result.approval is not None else None,
        "decision": _json(result.decision) if result.decision is not None else None,
        "executed": result.executed,
        "awaitingApproval": result.awaitingApproval,
    }


def _job(item: Any) -> dict[str, Any]:
    # Deliberately omit payload: it can contain business input. Clients receive
    # status and the bounded result summary, never another user's queued data.
    return {
        "jobId": str(item.jobId),
        "kind": item.kind,
        "status": item.status,
        "priority": item.priority,
        "attempts": item.attempts,
        "maxAttempts": item.maxAttempts,
        "runAt": item.runAt.isoformat(),
        "resultSummary": _json(item.resultSummary),
        "errorCode": item.errorCode,
        "correlationId": item.correlationId,
        "createdAt": item.createdAt.isoformat(),
        "updatedAt": item.updatedAt.isoformat(),
    }


def _listMeta(items: Any) -> dict[str, Any]:
    return {"count": len(items)}
