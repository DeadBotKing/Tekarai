"""Pure Request and Operation lifecycle orchestration for Phase 13-G.

This module coordinates the Phase 13-B ``AIRequest`` and ``AIOperation``
entities without becoming an execution engine.  It owns only an in-memory
aggregate boundary and its indexes; an application adapter is responsible for
persistence, authorization, queues, workers, and external execution.

The service is intentionally provider-agnostic.  It does not resolve secrets,
call a provider, retry on a schedule, enforce timeouts, perform failover, or
perform asynchronous work.  Correlation and trace identifiers are carried as
opaque identifiers, while idempotency keys are used only for a tenant-scoped
in-memory duplicate check and are never returned in read descriptors.
"""

from __future__ import annotations

import hashlib
import json
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from apps.ai.domain.entities.aiRecords import (
    AIOperation,
    AIRequest,
    requireUuid,
    utcNow,
)
from apps.ai.domain.exceptions import (
    AIOperationAlreadyRegistered,
    AIOperationLifecycleInvalid,
    AIOperationNotFound,
    AIError,
    AIIdempotencyConflict,
    AIRequestAlreadyRegistered,
    AIRequestCapabilityInvalid,
    AIRequestLifecycleInvalid,
    AIRequestNotFound,
)
from apps.ai.domain.registries.capabilityRegistry import CapabilityRegistry
from apps.ai.domain.valueObjects.aiTypes import REQUEST_STATUSES, REQUEST_TYPES, ensureEnum


OPERATION_STATUSES: tuple[str, ...] = (
    "PENDING",
    "RUNNING",
    "COMPLETED",
    "FAILED",
    "CANCELLED",
)
TERMINAL_REQUEST_STATUSES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
TERMINAL_OPERATION_STATUSES: frozenset[str] = frozenset({"COMPLETED", "FAILED", "CANCELLED"})
WRITABLE_OPERATION_STATUSES: frozenset[str] = frozenset({"PENDING", "RUNNING"})


def _normalizeOptionalUuid(value: uuid.UUID | str | None, fieldName: str) -> uuid.UUID | None:
    return None if value is None else requireUuid(value, fieldName)


def _stableValue(value: Any) -> Any:
    """Convert arbitrary request input to a deterministic, hash-only shape."""

    if isinstance(value, Mapping):
        return {
            str(key): _stableValue(value[key])
            for key in sorted(value, key=lambda item: str(item))
        }
    if isinstance(value, (list, tuple)):
        return [_stableValue(item) for item in value]
    if isinstance(value, (set, frozenset)):
        return sorted((_stableValue(item) for item in value), key=lambda item: repr(item))
    if isinstance(value, (uuid.UUID, datetime)):
        return str(value)
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return repr(value)


def _requestFingerprint(request: AIRequest, operationId: uuid.UUID | None) -> str:
    """Hash request identity without exposing input data or the idempotency key."""

    identity = {
        "tenantId": str(request.tenantId),
        "capabilityId": str(request.capabilityId),
        "requestType": request.requestType,
        "requestedBy": str(request.requestedBy) if request.requestedBy else None,
        "sourceDomain": request.sourceDomain,
        "sourceEntityType": request.sourceEntityType,
        "sourceEntityId": request.sourceEntityId,
        "priority": request.priority,
        "operationId": str(operationId) if operationId else None,
        "parentRequestId": str(request.parentRequestId) if request.parentRequestId else None,
        "inputData": _stableValue(request.inputData),
        "contextTokenCount": request.contextTokenCount,
    }
    encoded = json.dumps(identity, ensure_ascii=True, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class RequestDescriptor:
    """Safe lifecycle read model; it intentionally omits input and idempotency data."""

    tenantId: uuid.UUID
    requestId: uuid.UUID
    operationId: uuid.UUID | None
    capabilityId: uuid.UUID
    requestType: str
    status: str
    correlationId: str
    traceId: str
    parentRequestId: uuid.UUID | None
    retryCount: int
    errorCode: str
    createdAt: datetime
    queuedAt: datetime | None
    startedAt: datetime | None
    completedAt: datetime | None


@dataclass(frozen=True)
class OperationDescriptor:
    """Safe operation read model with ordered child request identifiers/statuses."""

    tenantId: uuid.UUID
    operationId: uuid.UUID
    operationType: str
    status: str
    correlationId: str
    traceId: str
    requestIds: tuple[uuid.UUID, ...]
    requestStatuses: tuple[str, ...]
    createdAt: datetime
    completedAt: datetime | None


@dataclass
class RegisteredRequestState:
    request: AIRequest
    operationId: uuid.UUID | None
    fingerprint: str


class RequestLifecycleService:
    """Tenant-scoped in-memory coordinator for Request/Operation aggregates.

    This class is deliberately not a repository.  Its state disappears with
    the process and callers must map successful transitions to their own
    transaction/persistence boundary.  The explicit ``tenantId`` on every
    method prevents a caller from using an identifier from another tenant;
    missing or foreign identifiers have the same not-found behavior.
    """

    def __init__(
        self,
        *,
        capabilityRegistry: CapabilityRegistry | None = None,
        now: Any = utcNow,
    ) -> None:
        if capabilityRegistry is not None and not isinstance(capabilityRegistry, CapabilityRegistry):
            raise TypeError("capabilityRegistry must be a CapabilityRegistry.")
        if not callable(now):
            raise TypeError("now must be callable.")
        self.capabilityRegistry = capabilityRegistry
        self._now = now
        self._operations: dict[tuple[uuid.UUID, uuid.UUID], AIOperation] = {}
        self._requests: dict[tuple[uuid.UUID, uuid.UUID], RegisteredRequestState] = {}
        self._idempotency: dict[tuple[uuid.UUID, str], tuple[str, uuid.UUID]] = {}

    # ------------------------------------------------------------------
    # Creation and association
    # ------------------------------------------------------------------
    def createOperation(
        self,
        tenantId: uuid.UUID | str,
        operationType: str,
        *,
        requestedBy: uuid.UUID | str | None = None,
        correlationId: str = "",
        traceId: str = "",
        operationId: uuid.UUID | str | None = None,
    ) -> AIOperation:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(operationId, "operationId") if operationId is not None else uuid.uuid4()
        key = (tenant, identifier)
        if key in self._operations:
            raise AIOperationAlreadyRegistered(str(identifier))
        operation = AIOperation(
            tenantId=tenant,
            operationType=operationType,
            requestedBy=_normalizeOptionalUuid(requestedBy, "requestedBy"),
            id=identifier,
            correlationId=correlationId,
            traceId=traceId,
            status="PENDING",
            createdAt=self._now(),
        )
        self._operations[key] = operation
        return operation

    def createRequest(
        self,
        tenantId: uuid.UUID | str,
        capabilityId: uuid.UUID | str,
        requestType: str,
        *,
        operationId: uuid.UUID | str | None = None,
        requestedBy: uuid.UUID | str | None = None,
        sourceDomain: str = "",
        sourceEntityType: str = "",
        sourceEntityId: str = "",
        priority: str = "NORMAL",
        correlationId: str = "",
        traceId: str = "",
        parentRequestId: uuid.UUID | str | None = None,
        inputData: Mapping[str, Any] | None = None,
        contextTokenCount: int = 0,
        idempotencyKey: str = "",
        requestId: uuid.UUID | str | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        capability = requireUuid(capabilityId, "capabilityId")
        normalizedType = ensureEnum(requestType, REQUEST_TYPES, "requestType")
        operation = None
        associatedOperationId = (
            requireUuid(operationId, "operationId") if operationId is not None else None
        )
        if associatedOperationId is not None:
            operation = self._getOperationOrRaise(tenant, associatedOperationId)
        parent = _normalizeOptionalUuid(parentRequestId, "parentRequestId")
        if parent is not None:
            parentRegistration = self._getRequestRegistrationOrRaise(tenant, parent)
            parentOperationId = parentRegistration.operationId
            if (
                associatedOperationId is not None
                and parentOperationId is not None
                and parentOperationId != associatedOperationId
            ):
                raise AIRequestLifecycleInvalid(
                    "A child request must remain in its parent request's operation."
                )

        self._validateCapability(tenant, capability, normalizedType)
        safeInput = dict(inputData or {})
        request = AIRequest(
            tenantId=tenant,
            capabilityId=capability,
            requestType=normalizedType,
            requestedBy=_normalizeOptionalUuid(requestedBy, "requestedBy"),
            sourceDomain=sourceDomain,
            sourceEntityType=sourceEntityType,
            sourceEntityId=sourceEntityId,
            priority=priority,
            id=requireUuid(requestId, "requestId") if requestId is not None else uuid.uuid4(),
            status="PENDING",
            correlationId=correlationId or (operation.correlationId if operation is not None else ""),
            traceId=traceId or (operation.traceId if operation is not None else ""),
            parentRequestId=parent,
            inputData=safeInput,
            contextTokenCount=contextTokenCount,
            idempotencyKey=str(idempotencyKey or "").strip(),
            createdAt=self._now(),
        )
        requestKey = (tenant, request.id)
        if requestKey in self._requests:
            raise AIRequestAlreadyRegistered(str(request.id))

        if request.idempotencyKey:
            idempotencyKeyValue = (tenant, request.idempotencyKey)
            fingerprint = _requestFingerprint(request, associatedOperationId)
            previous = self._idempotency.get(idempotencyKeyValue)
            if previous is not None:
                previousFingerprint, previousRequestId = previous
                if previousFingerprint == fingerprint:
                    return self._getRequestOrRaise(tenant, previousRequestId)
                raise AIIdempotencyConflict(
                    "The tenant-scoped idempotency key is already bound to another request."
                )
        else:
            fingerprint = _requestFingerprint(request, associatedOperationId)

        if operation is not None and operation.status not in WRITABLE_OPERATION_STATUSES:
            raise AIRequestLifecycleInvalid(
                "A request cannot be associated with a terminal operation."
            )

        # All validation is complete before either aggregate is mutated.
        if operation is not None:
            operation.addRequest(request.id)
        self._requests[requestKey] = RegisteredRequestState(
            request=request,
            operationId=associatedOperationId,
            fingerprint=fingerprint,
        )
        if request.idempotencyKey:
            self._idempotency[(tenant, request.idempotencyKey)] = (fingerprint, request.id)
        return request

    # ------------------------------------------------------------------
    # Request transitions
    # ------------------------------------------------------------------
    def queueRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        request = self._getRequestOrRaise(tenant, requestId)
        self._ensureRequestOperationActive(tenant, request, "QUEUED")
        return self._transitionRequest(request, "QUEUED", now=now)

    def startRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        request = self._getRequestOrRaise(tenant, requestId)
        registration = self._requests[(tenant, request.id)]
        if registration.operationId is not None:
            operation = self._getOperationOrRaise(tenant, registration.operationId)
            if operation.status not in WRITABLE_OPERATION_STATUSES:
                raise AIRequestLifecycleInvalid(
                    "A request cannot start while its operation is not active."
                )
        # Transition the child first so a bad child state cannot partially
        # advance a pending operation to RUNNING.
        transitioned = self._transitionRequest(request, "RUNNING", now=now)
        if registration.operationId is not None and operation.status == "PENDING":
            self._transitionOperation(operation, "RUNNING", now=now)
        return transitioned

    def completeRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        request = self._getRequestOrRaise(tenant, requestId)
        self._ensureRequestOperationActive(tenant, request, "COMPLETED")
        return self._transitionRequest(request, "COMPLETED", now=now)

    def failRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        *,
        errorCode: str = "AI_REQUEST_FAILED",
        now: datetime | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        request = self._getRequestOrRaise(tenant, requestId)
        normalizedErrorCode = str(errorCode or "").strip().upper()
        if not normalizedErrorCode:
            raise AIRequestLifecycleInvalid("A failed request requires a stable error code.")
        self._ensureRequestOperationActive(tenant, request, "FAILED")
        return self._transitionRequest(request, "FAILED", now=now, errorCode=normalizedErrorCode)

    def cancelRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        request = self._getRequestOrRaise(tenant, requestId)
        self._ensureRequestOperationActive(tenant, request, "CANCELLED")
        return self._transitionRequest(request, "CANCELLED", now=now)

    def retryRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        request = self._getRequestOrRaise(tenant, requestId)
        if request.status != "FAILED":
            raise AIRequestLifecycleInvalid("Only a failed request can be explicitly requeued.")
        self._ensureRequestOperationActive(tenant, request, "QUEUED")
        request.retryCount += 1
        request.transitionTo("QUEUED", now=now or self._now())
        return request

    # ------------------------------------------------------------------
    # Operation transitions
    # ------------------------------------------------------------------
    def startOperation(
        self,
        tenantId: uuid.UUID | str,
        operationId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIOperation:
        operation = self._getOperationOrRaise(tenantId, operationId)
        return self._transitionOperation(operation, "RUNNING", now=now)

    def completeOperation(
        self,
        tenantId: uuid.UUID | str,
        operationId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIOperation:
        tenant = requireUuid(tenantId, "tenantId")
        operation = self._getOperationOrRaise(tenant, operationId)
        self._requireTerminalChildren(operation, allowFailed=False)
        return self._transitionOperation(operation, "COMPLETED", now=now)

    def failOperation(
        self,
        tenantId: uuid.UUID | str,
        operationId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIOperation:
        tenant = requireUuid(tenantId, "tenantId")
        operation = self._getOperationOrRaise(tenant, operationId)
        self._requireTerminalChildren(operation, allowFailed=True)
        return self._transitionOperation(operation, "FAILED", now=now)

    def cancelOperation(
        self,
        tenantId: uuid.UUID | str,
        operationId: uuid.UUID | str,
        *,
        now: datetime | None = None,
    ) -> AIOperation:
        tenant = requireUuid(tenantId, "tenantId")
        operation = self._getOperationOrRaise(tenant, operationId)
        if operation.status == "CANCELLED":
            return operation
        if operation.status not in WRITABLE_OPERATION_STATUSES:
            raise AIOperationLifecycleInvalid(
                "Only a pending or running operation can be cancelled."
            )
        moment = now or self._now()
        # Cancellation is the one explicit aggregate cascade: active child
        # requests cannot remain executable after their operation is cancelled.
        for requestId in operation.requestIds:
            request = self._getRequestOrRaise(tenant, requestId)
            if request.status not in TERMINAL_REQUEST_STATUSES:
                self._transitionRequest(request, "CANCELLED", now=moment)
        return self._transitionOperation(operation, "CANCELLED", now=moment)

    # ------------------------------------------------------------------
    # Tenant-scoped reads
    # ------------------------------------------------------------------
    def getRequest(self, tenantId: uuid.UUID | str, requestId: uuid.UUID | str) -> AIRequest:
        return self._getRequestOrRaise(tenantId, requestId)

    def getOperation(self, tenantId: uuid.UUID | str, operationId: uuid.UUID | str) -> AIOperation:
        return self._getOperationOrRaise(tenantId, operationId)

    def describeRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> RequestDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        registration = self._getRequestRegistrationOrRaise(tenant, requestId)
        request = registration.request
        return RequestDescriptor(
            tenantId=request.tenantId,
            requestId=request.id,
            operationId=registration.operationId,
            capabilityId=request.capabilityId,
            requestType=request.requestType,
            status=request.status,
            correlationId=request.correlationId,
            traceId=request.traceId,
            parentRequestId=request.parentRequestId,
            retryCount=request.retryCount,
            errorCode=request.errorCode,
            createdAt=request.createdAt,
            queuedAt=request.queuedAt,
            startedAt=request.startedAt,
            completedAt=request.completedAt,
        )

    def describeOperation(
        self,
        tenantId: uuid.UUID | str,
        operationId: uuid.UUID | str,
    ) -> OperationDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        operation = self._getOperationOrRaise(tenant, operationId)
        statuses = tuple(self._getRequestOrRaise(tenant, requestId).status for requestId in operation.requestIds)
        return OperationDescriptor(
            tenantId=operation.tenantId,
            operationId=operation.id,
            operationType=operation.operationType,
            status=operation.status,
            correlationId=operation.correlationId,
            traceId=operation.traceId,
            requestIds=tuple(operation.requestIds),
            requestStatuses=statuses,
            createdAt=operation.createdAt,
            completedAt=operation.completedAt,
        )

    def listRequests(
        self,
        tenantId: uuid.UUID | str,
        *,
        status: str | None = None,
    ) -> tuple[RequestDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedStatus = ensureEnum(status, REQUEST_STATUSES, "requestStatus") if status else None
        descriptors = [
            self.describeRequest(tenant, request.request.id)
            for (requestTenant, _), request in self._requests.items()
            if requestTenant == tenant and (normalizedStatus is None or request.request.status == normalizedStatus)
        ]
        return tuple(sorted(descriptors, key=lambda item: (item.createdAt, str(item.requestId))))

    def listOperations(
        self,
        tenantId: uuid.UUID | str,
        *,
        status: str | None = None,
    ) -> tuple[OperationDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedStatus = ensureEnum(status, OPERATION_STATUSES, "operationStatus") if status else None
        descriptors = [
            self.describeOperation(tenant, operation.id)
            for (operationTenant, _), operation in self._operations.items()
            if operationTenant == tenant and (normalizedStatus is None or operation.status == normalizedStatus)
        ]
        return tuple(sorted(descriptors, key=lambda item: (item.createdAt, str(item.operationId))))

    def operationForRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> OperationDescriptor | None:
        tenant = requireUuid(tenantId, "tenantId")
        registration = self._getRequestRegistrationOrRaise(tenant, requestId)
        if registration.operationId is None:
            return None
        return self.describeOperation(tenant, registration.operationId)

    # ------------------------------------------------------------------
    # Internal invariants
    # ------------------------------------------------------------------
    def _validateCapability(
        self,
        tenantId: uuid.UUID,
        capabilityId: uuid.UUID,
        requestType: str,
    ) -> None:
        if self.capabilityRegistry is None:
            # B-compatible composition is allowed when an outer adapter has
            # already validated capability ownership. G still enforces tenant
            # ownership for every aggregate it directly stores.
            return
        try:
            descriptors = self.capabilityRegistry.listCapabilities(tenantId, activeOnly=False)
            descriptor = next(
                (item for item in descriptors if item.capabilityId == capabilityId),
                None,
            )
            if descriptor is None:
                raise AIRequestCapabilityInvalid(str(capabilityId))
            self.capabilityRegistry.resolveForRequest(tenantId, descriptor.code, requestType)
        except AIRequestCapabilityInvalid:
            raise
        except AIError as exc:
            raise AIRequestCapabilityInvalid(str(capabilityId)) from exc

    def _requireTerminalChildren(self, operation: AIOperation, *, allowFailed: bool) -> None:
        for requestId in operation.requestIds:
            request = self._getRequestOrRaise(operation.tenantId, requestId)
            if request.status not in TERMINAL_REQUEST_STATUSES:
                raise AIOperationLifecycleInvalid(
                    "An operation can finish only after every child request is terminal."
                )
            if not allowFailed and request.status == "FAILED":
                raise AIOperationLifecycleInvalid(
                    "An operation cannot complete while a child request is failed."
                )

    def _ensureRequestOperationActive(
        self,
        tenantId: uuid.UUID,
        request: AIRequest,
        targetStatus: str,
    ) -> None:
        registration = self._requests[(tenantId, request.id)]
        if registration.operationId is None:
            return
        operation = self._getOperationOrRaise(tenantId, registration.operationId)
        if request.status == targetStatus:
            return
        if operation.status not in WRITABLE_OPERATION_STATUSES:
            raise AIRequestLifecycleInvalid(
                "A request cannot transition while its operation is terminal."
            )

    @staticmethod
    def _transitionRequest(
        request: AIRequest,
        status: str,
        *,
        now: datetime | None = None,
        errorCode: str = "",
    ) -> AIRequest:
        try:
            request.transitionTo(status, now=now, errorCode=errorCode)
        except (TypeError, ValueError) as exc:
            raise AIRequestLifecycleInvalid(str(exc)) from exc
        return request

    @staticmethod
    def _transitionOperation(
        operation: AIOperation,
        status: str,
        *,
        now: datetime | None = None,
    ) -> AIOperation:
        try:
            operation.transitionTo(status, now=now)
        except (TypeError, ValueError) as exc:
            raise AIOperationLifecycleInvalid(str(exc)) from exc
        return operation

    def _getRequestOrRaise(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> AIRequest:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(requestId, "requestId")
        registration = self._requests.get((tenant, identifier))
        if registration is None:
            raise AIRequestNotFound(str(identifier))
        return registration.request

    def _getRequestRegistrationOrRaise(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> RegisteredRequestState:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(requestId, "requestId")
        registration = self._requests.get((tenant, identifier))
        if registration is None:
            raise AIRequestNotFound(str(identifier))
        return registration

    def _getOperationOrRaise(
        self,
        tenantId: uuid.UUID | str,
        operationId: uuid.UUID | str,
    ) -> AIOperation:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(operationId, "operationId")
        operation = self._operations.get((tenant, identifier))
        if operation is None:
            raise AIOperationNotFound(str(identifier))
        return operation


AIRequestLifecycle = RequestLifecycleService
InMemoryRequestLifecycle = RequestLifecycleService
RequestLifecycleManager = RequestLifecycleService
OperationLifecycleService = RequestLifecycleService

__all__ = [
    "AIRequestLifecycle",
    "InMemoryRequestLifecycle",
    "OPERATION_STATUSES",
    "OperationDescriptor",
    "OperationLifecycleService",
    "RequestDescriptor",
    "RequestLifecycleManager",
    "RequestLifecycleService",
    "TERMINAL_OPERATION_STATUSES",
    "TERMINAL_REQUEST_STATUSES",
    "WRITABLE_OPERATION_STATUSES",
]
