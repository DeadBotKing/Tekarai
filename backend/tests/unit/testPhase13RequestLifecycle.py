"""Phase 13-G Request and Operation Lifecycle tests (pure Python, offline)."""

from __future__ import annotations

import unittest
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

from apps.ai.domain.entities.aiRecords import AICapability
from apps.ai.domain.exceptions import (
    AICapabilityInactive,
    AIOperationLifecycleInvalid,
    AIOperationNotFound,
    AIIdempotencyConflict,
    AIRequestCapabilityInvalid,
    AIRequestLifecycleInvalid,
    AIRequestNotFound,
)
from apps.ai.domain.registries.capabilityRegistry import CapabilityRegistry
from apps.ai.domain.services.requestLifecycle import (
    AIRequestLifecycle,
    OperationDescriptor,
    RequestDescriptor,
    RequestLifecycleService,
)


class Phase13GRequestLifecycleTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.capabilityId = uuid.uuid4()
        self.clock = datetime(2026, 1, 2, 3, 4, 5, tzinfo=UTC)
        self.lifecycle = RequestLifecycleService(now=lambda: self.clock)

    def _operation(self, tenantId: uuid.UUID | None = None):
        return self.lifecycle.createOperation(
            tenantId or self.tenantId,
            "CHAT_OPERATION",
            correlationId="corr-001",
            traceId="trace-001",
        )

    def _request(self, *, operationId=None, tenantId=None, **kwargs):
        return self.lifecycle.createRequest(
            tenantId or self.tenantId,
            self.capabilityId,
            "GENERATE",
            operationId=operationId,
            **kwargs,
        )

    def testCreationAssociationCorrelationAndSafeDescriptors(self) -> None:
        operation = self._operation()
        request = self._request(
            operationId=operation.id,
            inputData={"prompt": "private input", "secret": "must not be in a descriptor"},
            idempotencyKey="request-key-1",
        )
        self.assertEqual(operation.requestIds, [request.id])
        self.assertEqual(request.status, "PENDING")
        self.assertEqual(request.correlationId, operation.correlationId)
        self.assertEqual(request.traceId, operation.traceId)

        requestDescriptor = self.lifecycle.describeRequest(self.tenantId, request.id)
        operationDescriptor = self.lifecycle.describeOperation(self.tenantId, operation.id)
        self.assertIsInstance(requestDescriptor, RequestDescriptor)
        self.assertIsInstance(operationDescriptor, OperationDescriptor)
        self.assertEqual(requestDescriptor.operationId, operation.id)
        self.assertEqual(operationDescriptor.requestIds, (request.id,))
        self.assertEqual(operationDescriptor.requestStatuses, ("PENDING",))
        self.assertNotIn("private input", repr(requestDescriptor))
        self.assertNotIn("secret", repr(requestDescriptor))
        self.assertNotIn("request-key-1", repr(requestDescriptor))

    def testRequestAndOperationTransitionsAreExplicitAndTimestamped(self) -> None:
        operation = self._operation()
        request = self._request(operationId=operation.id)
        queuedAt = self.clock + timedelta(seconds=1)
        startedAt = self.clock + timedelta(seconds=2)
        completedAt = self.clock + timedelta(seconds=3)

        self.lifecycle.queueRequest(self.tenantId, request.id, now=queuedAt)
        self.assertEqual(request.status, "QUEUED")
        self.assertEqual(request.queuedAt, queuedAt)
        self.lifecycle.startRequest(self.tenantId, request.id, now=startedAt)
        self.assertEqual(request.status, "RUNNING")
        self.assertEqual(request.startedAt, startedAt)
        self.assertEqual(operation.status, "RUNNING")
        self.lifecycle.completeRequest(self.tenantId, request.id, now=completedAt)
        self.assertEqual(request.status, "COMPLETED")
        self.assertEqual(request.completedAt, completedAt)
        self.lifecycle.completeOperation(self.tenantId, operation.id, now=completedAt)
        self.assertEqual(operation.status, "COMPLETED")
        self.assertEqual(operation.completedAt, completedAt)

    def testInvalidTransitionsAndOperationCompletionGates(self) -> None:
        operation = self._operation()
        request = self._request(operationId=operation.id)
        with self.assertRaises(AIOperationLifecycleInvalid):
            self.lifecycle.completeOperation(self.tenantId, operation.id)
        self.lifecycle.startOperation(self.tenantId, operation.id)
        with self.assertRaises(AIOperationLifecycleInvalid):
            self.lifecycle.completeOperation(self.tenantId, operation.id)
        with self.assertRaises(AIRequestLifecycleInvalid):
            self.lifecycle.completeRequest(self.tenantId, request.id)
        self.lifecycle.startRequest(self.tenantId, request.id)
        self.lifecycle.failRequest(self.tenantId, request.id, errorCode="PROVIDER_RESULT_INVALID")
        self.assertEqual(request.errorCode, "PROVIDER_RESULT_INVALID")
        with self.assertRaises(AIOperationLifecycleInvalid):
            self.lifecycle.completeOperation(self.tenantId, operation.id)
        self.lifecycle.failOperation(self.tenantId, operation.id)
        self.assertEqual(operation.status, "FAILED")
        with self.assertRaises(AIOperationLifecycleInvalid):
            self.lifecycle.cancelOperation(self.tenantId, operation.id)
        self.assertEqual(request.status, "FAILED")
        with self.assertRaises(AIOperationLifecycleInvalid):
            self.lifecycle.startOperation(self.tenantId, operation.id)

    def testExplicitRetryOnlyRequeuesFailedRequestWithoutRetryPolicy(self) -> None:
        request = self._request()
        self.lifecycle.startRequest(self.tenantId, request.id)
        self.lifecycle.failRequest(self.tenantId, request.id, errorCode="TRANSIENT_RESULT")
        self.lifecycle.retryRequest(self.tenantId, request.id)
        self.assertEqual(request.status, "QUEUED")
        self.assertEqual(request.retryCount, 1)
        with self.assertRaises(AIRequestLifecycleInvalid):
            self.lifecycle.retryRequest(self.tenantId, request.id)

    def testOperationCancellationCascadesOnlyToItsChildren(self) -> None:
        operation = self._operation()
        first = self._request(operationId=operation.id)
        second = self._request(operationId=operation.id)
        unrelated = self._request()
        self.lifecycle.cancelOperation(self.tenantId, operation.id)
        self.assertEqual(operation.status, "CANCELLED")
        self.assertEqual(first.status, "CANCELLED")
        self.assertEqual(second.status, "CANCELLED")
        self.assertEqual(unrelated.status, "PENDING")
        # Repeated cancellation is an idempotent terminal command.
        self.lifecycle.cancelOperation(self.tenantId, operation.id)
        self.assertEqual(operation.status, "CANCELLED")

    def testTenantIsolationAppliesToReadsTransitionsAndAssociations(self) -> None:
        sharedId = uuid.uuid4()
        operation = self.lifecycle.createOperation(
            self.tenantId,
            "CHAT_OPERATION",
            operationId=sharedId,
        )
        request = self.lifecycle.createRequest(
            self.tenantId,
            self.capabilityId,
            "GENERATE",
            operationId=operation.id,
            requestId=sharedId,
        )
        with self.assertRaises(AIOperationNotFound):
            self.lifecycle.getOperation(self.otherTenantId, operation.id)
        with self.assertRaises(AIRequestNotFound):
            self.lifecycle.getRequest(self.otherTenantId, request.id)
        with self.assertRaises(AIRequestNotFound):
            self.lifecycle.cancelRequest(self.otherTenantId, request.id)
        self.assertEqual(self.lifecycle.listRequests(self.otherTenantId), ())
        self.assertEqual(self.lifecycle.listOperations(self.otherTenantId), ())

    def testIdempotencyReplayConflictAndTenantScope(self) -> None:
        first = self._request(
            idempotencyKey="same-key",
            inputData={"value": "same"},
        )
        replay = self._request(
            idempotencyKey="same-key",
            inputData={"value": "same"},
        )
        self.assertIs(replay, first)
        with self.assertRaises(AIIdempotencyConflict):
            self._request(idempotencyKey="same-key", inputData={"value": "different"})
        other = self._request(
            tenantId=self.otherTenantId,
            idempotencyKey="same-key",
            inputData={"value": "other tenant"},
        )
        self.assertNotEqual(other.id, first.id)

    def testCapabilityRegistryCompositionEnforcesTenantActivityAndRequestType(self) -> None:
        registry = CapabilityRegistry()
        capability = AICapability(
            tenantId=self.tenantId,
            code="SUMMARIZATION",
            name="Summarization",
            policy={"allowedRequestTypes": ("SUMMARIZE",)},
        )
        registry.register(capability)
        strict = RequestLifecycleService(capabilityRegistry=registry, now=lambda: self.clock)
        request = strict.createRequest(
            self.tenantId,
            capability.id,
            "SUMMARIZE",
        )
        self.assertEqual(request.capabilityId, capability.id)
        with self.assertRaises(AIRequestCapabilityInvalid):
            strict.createRequest(self.otherTenantId, capability.id, "SUMMARIZE")
        with self.assertRaises(AIRequestCapabilityInvalid):
            strict.createRequest(self.tenantId, capability.id, "GENERATE")
        capability.isActive = False
        with self.assertRaises(AIRequestCapabilityInvalid):
            strict.createRequest(self.tenantId, capability.id, "SUMMARIZE")
        self.assertIs(AIRequestLifecycle, RequestLifecycleService)

    def testParentAssociationCannotCrossOperationsOrTenants(self) -> None:
        operationA = self._operation()
        operationB = self._operation()
        parent = self._request(operationId=operationA.id)
        child = self._request(operationId=operationA.id, parentRequestId=parent.id)
        self.assertEqual(self.lifecycle.describeRequest(self.tenantId, child.id).parentRequestId, parent.id)
        with self.assertRaises(AIRequestLifecycleInvalid):
            self._request(operationId=operationB.id, parentRequestId=parent.id)
        with self.assertRaises(AIRequestNotFound):
            self.lifecycle.createRequest(
                self.otherTenantId,
                self.capabilityId,
                "GENERATE",
                parentRequestId=parent.id,
            )

    def testTenantScopedListingAndStableAliases(self) -> None:
        operation = self._operation()
        first = self._request(operationId=operation.id)
        second = self._request()
        self.lifecycle.queueRequest(self.tenantId, first.id)
        self.assertEqual(tuple(item.requestId for item in self.lifecycle.listRequests(self.tenantId, status="QUEUED")), (first.id,))
        self.assertEqual(tuple(item.requestId for item in self.lifecycle.listRequests(self.tenantId, status="PENDING")), (second.id,))
        self.assertEqual(tuple(item.operationId for item in self.lifecycle.listOperations(self.tenantId)), (operation.id,))
        self.assertEqual(self.lifecycle.operationForRequest(self.tenantId, second.id), None)
        self.assertEqual(self.lifecycle.operationForRequest(self.tenantId, first.id).operationId, operation.id)

    def testPureDomainBoundaryAndNoSecretOrProviderImports(self) -> None:
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/services/requestLifecycle.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "django",
            "rest_framework",
            "redis",
            "requests",
            "httpx",
            "openai",
            "ollama",
            "azure",
            "anthropic",
            "boto3",
        ):
            self.assertNotIn(f"import {forbidden}", source.lower())
        self.assertNotIn("api_key", source.lower())
        self.assertNotIn("secret_key", source.lower())


if __name__ == "__main__":
    unittest.main()
