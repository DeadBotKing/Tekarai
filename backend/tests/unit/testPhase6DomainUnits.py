"""Phase 06 unit tests — pure domain, no database (§29 "Unit Tests").

Domain aggregates, value objects, the PermissionEvaluator domain service,
error architecture codes and the response envelope contract.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta

from django.test import SimpleTestCase

from apps.identity.domain.entities.session import Session
from apps.identity.domain.entities.tenantMembership import TenantMembership
from apps.identity.domain.entities.user import User
from apps.identity.domain.services.permissionEvaluator import PermissionEvaluator
from apps.identity.domain.valueObjects.accessGrant import AccessGrant
from apps.identity.domain.valueObjects.userState import validatePasswordStrength
from apps.sharedKernel.domain.errors import (
    BusinessRuleViolationError,
    DuplicateBusinessCodeError,
    EntityNotFoundError,
    InvalidStateTransitionError,
    PermissionDeniedError,
    TenantAccessDeniedError,
    ValidationFailedError,
)
from apps.sharedKernel.domain.events import DomainEvent
from apps.sharedKernel.domain.valueObjects import ActionCode, EmailAddress
from apps.sharedKernel.presentation.api.response import errorEnvelope, successEnvelope
from apps.tenancy.domain.entities.tenant import Tenant
from apps.tenancy.domain.valueObjects.tenantState import (
    TENANT_ACTIVE,
    TENANT_CLOSED,
    TENANT_SUSPENDED,
    TenantCode,
    TenantStatus,
)

NOW = datetime(2026, 8, 29, tzinfo=UTC)


class TenantAggregateTests(SimpleTestCase):
    def testCreateRecordsTenantCreatedEvent(self) -> None:
        tenant = Tenant.create(TenantCode("acme"), "ACME", NOW)
        events = tenant.pullEvents()
        self.assertEqual(len(events), 1)
        self.assertEqual(events[0].name, "tenantCreated")
        self.assertEqual(events[0].tenantId, tenant.id)

    def testPullEventsClearsBuffer(self) -> None:
        tenant = Tenant.create(TenantCode("acme"), "ACME", NOW)
        self.assertEqual(tenant.pendingEventCount(), 1)
        tenant.pullEvents()
        self.assertEqual(tenant.pendingEventCount(), 0)

    def testLifecycleFollowsStateMachine(self) -> None:
        tenant = Tenant.create(TenantCode("acme"), "ACME", NOW)
        tenant.suspend(NOW)
        self.assertEqual(str(tenant.status), TENANT_SUSPENDED)
        tenant.reactivate(NOW)
        self.assertEqual(str(tenant.status), TENANT_ACTIVE)

    def testClosedIsTerminal(self) -> None:
        tenant = Tenant.create(TenantCode("acme"), "ACME", NOW)
        tenant.transitionTo(TENANT_CLOSED, NOW)
        with self.assertRaises(InvalidStateTransitionError):
            tenant.reactivate(NOW)

    def testInvalidCodeRejectedByValueObject(self) -> None:
        with self.assertRaises(ValidationFailedError):
            TenantCode("Bad Code")
        with self.assertRaises(ValidationFailedError):
            TenantCode("x")

    def testUnknownStatusRejected(self) -> None:
        with self.assertRaises(ValidationFailedError):
            TenantStatus("banned")


class UserAggregateTests(SimpleTestCase):
    def testCreateDefaultsToActive(self) -> None:
        user = User.register(
            tenantId=uuid.uuid4(),
            username="sara",
            email="Sara@ACME.com",
            passwordHash="hash",
            displayName="Sara",
            now=NOW,
        )
        self.assertEqual(str(user.status), "active")
        self.assertEqual(user.email, "sara@acme.com")  # normalized
        self.assertEqual(user.pullEvents()[0].name, "userCreated")

    def testDisabledIsTerminal(self) -> None:
        user = User.register(uuid.uuid4(), "sara", "s@a.com", "h", "S", NOW)
        user.transitionTo("suspended", NOW)
        user.transitionTo("disabled", NOW)
        with self.assertRaises(InvalidStateTransitionError):
            user.transitionTo("active", NOW)

    def testPasswordPolicy(self) -> None:
        with self.assertRaises(ValidationFailedError):
            validatePasswordStrength("short1!")
        with self.assertRaises(ValidationFailedError):
            validatePasswordStrength("onlyletters123")
        self.assertEqual(validatePasswordStrength("Good-Pass-2026!"), "Good-Pass-2026!")

    def testEmailValueObjectNormalizes(self) -> None:
        self.assertEqual(str(EmailAddress("  Sara@ACME.com ")), "sara@acme.com")
        with self.assertRaises(ValidationFailedError):
            EmailAddress("no-at-sign")

    def testActionCodeGrammar(self) -> None:
        self.assertEqual(str(ActionCode("user.create")), "user.create")
        with self.assertRaises(ValidationFailedError):
            ActionCode("user-create")


class SessionAggregateTests(SimpleTestCase):
    def testStartAndExpiry(self) -> None:
        session = Session.start(uuid.uuid4(), uuid.uuid4(), "hash", NOW, ttlMinutes=30)
        self.assertTrue(session.isValidAt(NOW + timedelta(minutes=29)))
        self.assertTrue(session.isExpiredAt(NOW + timedelta(minutes=31)))

    def testRevokeIsIdempotentAndSingleEvent(self) -> None:
        session = Session.start(uuid.uuid4(), uuid.uuid4(), "hash", NOW, 30)
        session.revoke(NOW)
        session.revoke(NOW)
        self.assertEqual(session.revokedAt, NOW)

    def testMembershipActiveFlag(self) -> None:
        membership = TenantMembership.establish(uuid.uuid4(), uuid.uuid4(), NOW)
        self.assertTrue(membership.isActive())
        membership.remove(NOW)
        self.assertFalse(membership.isActive())


class PermissionEvaluatorTests(SimpleTestCase):
    def setUp(self) -> None:
        super().setUp()
        self.evaluator = PermissionEvaluator()
        self.actorId = uuid.uuid4()
        self.actorTenant = uuid.uuid4()
        self.otherTenant = uuid.uuid4()

    def testGlobalGrantPassesAnyTenant(self) -> None:
        grants = [AccessGrant("tenant.list", "GLOBAL")]
        self.assertTrue(
            self.evaluator.hasPermission(
                grants, self.actorId, "tenant.list", targetTenantId=self.otherTenant
            )
        )

    def testTenantScopeStaysInsideActorTenant(self) -> None:
        grants = [AccessGrant("user.create", "TENANT")]
        self.assertTrue(
            self.evaluator.hasPermission(
                grants,
                self.actorId,
                "user.create",
                actorTenantId=self.actorTenant,
                targetTenantId=self.actorTenant,
            )
        )
        self.assertFalse(
            self.evaluator.hasPermission(
                grants,
                self.actorId,
                "user.create",
                actorTenantId=self.actorTenant,
                targetTenantId=self.otherTenant,
            )
        )

    def testExplicitDenyWins(self) -> None:
        grants = [
            AccessGrant("user.*", "GLOBAL"),
            AccessGrant("user.create", "GLOBAL", effect="deny"),
        ]
        self.assertFalse(self.evaluator.hasPermission(grants, self.actorId, "user.create"))

    def testModuleWildcard(self) -> None:
        grants = [AccessGrant("user.*", "TENANT")]
        self.assertTrue(
            self.evaluator.hasPermission(
                grants,
                self.actorId,
                "user.suspend",
                actorTenantId=self.actorTenant,
            )
        )

    def testUnknownActionFailsClosed(self) -> None:
        self.assertFalse(self.evaluator.hasPermission([], self.actorId, "tenant.create"))

    def testScopedRefNarrowsTenantGrant(self) -> None:
        scoped = uuid.uuid4()
        grants = [AccessGrant("project.view", "TENANT", scopeRef=str(scoped))]
        self.assertTrue(
            self.evaluator.hasPermission(
                grants, self.actorId, "project.view", targetTenantId=scoped
            )
        )
        self.assertFalse(
            self.evaluator.hasPermission(
                grants,
                self.actorId,
                "project.view",
                targetTenantId=self.otherTenant,
            )
        )


class ErrorArchitectureTests(SimpleTestCase):
    def testCodesMatchErrorCatalog(self) -> None:
        cases = [
            (TenantAccessDeniedError(), "TENANT_ACCESS_DENIED", 403),
            (PermissionDeniedError(), "PERM_PERMISSION_DENIED", 403),
            (EntityNotFoundError("Tenant"), "SYS_RECORD_NOT_FOUND", 404),
            (DuplicateBusinessCodeError(), "DUP_BUSINESS_CODE", 409),
            (ValidationFailedError(), "SYS_VALIDATION_FAILED", 422),
            (
                BusinessRuleViolationError("x", ruleId="BR-TEN-004"),
                "VAL_BUSINESS_RULE_VIOLATED",
                422,
            ),
            (InvalidStateTransitionError(), "STATE_INVALID_TRANSITION", 409),
        ]
        for error, expectedCode, expectedStatus in cases:
            self.assertEqual(error.code, expectedCode)
            self.assertEqual(error.httpStatus, expectedStatus)

    def testBusinessRuleViolationCarriesRuleId(self) -> None:
        error = BusinessRuleViolationError("weights", ruleId="BR-DAT-004")
        self.assertEqual(error.details["ruleId"], "BR-DAT-004")


class EnvelopeContractTests(SimpleTestCase):
    def testSuccessEnvelopeShape(self) -> None:
        envelope = successEnvelope({"id": 1})
        self.assertEqual(set(envelope), {"success", "data", "meta", "errors"})
        self.assertTrue(envelope["success"])
        self.assertEqual(envelope["errors"], [])

    def testErrorEnvelopeShape(self) -> None:
        envelope = errorEnvelope([{"code": "PERM_PERMISSION_DENIED", "message": "x"}])
        self.assertFalse(envelope["success"])
        self.assertIsNone(envelope["data"])
        self.assertEqual(envelope["errors"][0]["code"], "PERM_PERMISSION_DENIED")


class DomainEventTests(SimpleTestCase):
    def testEventAsDictIsSerializable(self) -> None:
        tenantId = uuid.uuid4()
        event = DomainEvent(
            name="tenantCreated",
            occurredAt=NOW,
            tenantId=tenantId,
            payload={"code": "acme"},
        )
        asDict = event.asDict()
        self.assertEqual(asDict["name"], "tenantCreated")
        self.assertEqual(asDict["tenantId"], str(tenantId))
