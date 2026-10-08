"""Permit-to-work against a real database.

``testPermitRules`` proves the decisions in isolation; this proves they are
actually wired to stored data — that the checklist the guard reads is the
one on disk, that the audit trail is written, and that tenant scoping holds.
"""

from __future__ import annotations

import uuid
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from apps.safety.application.services.permitService import (
    Actor,
    activatePermit,
    applyIsolation,
    approvePermit,
    cancelPermit,
    closePermit,
    completePermit,
    confirmPrecaution,
    createPermit,
    permitReadiness,
    permitValidityView,
    rejectPermit,
    removeIsolation,
    resumePermit,
    scanPermitExpiry,
    submitPermit,
    suspendPermit,
    verifyIsolation,
)
from apps.safety.domain.services.permitRules import PermitRuleViolation
from apps.safety.domain.valueObjects.permitState import (
    PERMIT_ACTIVE,
    PERMIT_APPROVED,
    PERMIT_CLOSED,
    PERMIT_ELECTRICAL,
    PERMIT_EXPIRED,
    PERMIT_GENERAL,
    PERMIT_HOT_WORK,
    PERMIT_REJECTED,
    PERMIT_SUBMITTED,
    PERMIT_SUSPENDED,
    RISK_HIGH,
    RISK_LOW,
)
from apps.safety.infrastructure.models import (
    PermitEventModel,
    PermitPrecautionModel,
    PermitToWorkModel,
)
from apps.safety.infrastructure.permitRepository import (
    PermitNotFound,
    createIsolationRow,
    isolationRows,
    loadPermit,
    precautionRows,
)


class PermitTestBase(TestCase):
    def setUp(self):
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.now = timezone.now()
        self.requester = Actor(id=uuid.uuid4(), name="تکنسین احمدی")
        self.supervisor = Actor(id=uuid.uuid4(), name="سرپرست رضایی")
        self.secondPerson = Actor(id=uuid.uuid4(), name="تکنسین کریمی")

    def makePermit(self, *, permitType=PERMIT_GENERAL, riskLevel=RISK_LOW, hours=8, **kwargs):
        return createPermit(
            self.tenantId,
            permitType=permitType,
            title=kwargs.pop("title", "تعویض بلبرینگ پمپ"),
            actor=kwargs.pop("actor", self.requester),
            riskLevel=riskLevel,
            validFrom=kwargs.pop("validFrom", self.now - timedelta(minutes=5)),
            validTo=kwargs.pop("validTo", self.now + timedelta(hours=hours)),
            now=self.now,
            **kwargs,
        )

    def confirmAllMandatory(self, permit, *, actor=None):
        for row in precautionRows(self.tenantId, permit.id):
            if row.isMandatory:
                confirmPrecaution(
                    self.tenantId,
                    permit.id,
                    row.id,
                    actor=actor or self.requester,
                    now=self.now,
                )

    def readyGeneralPermit(self):
        permit = self.makePermit()
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        return loadPermit(self.tenantId, permit.id)


class PermitCreationTests(PermitTestBase):
    def testANewPermitStartsAsADraft(self):
        permit = self.makePermit()
        self.assertEqual(permit.status, "draft")

    def testTheChecklistIsSeededFromThePermitType(self):
        """A blank checklist gets ticked; one that names this job's hazards
        gets read."""
        permit = self.makePermit(permitType=PERMIT_HOT_WORK)
        rows = precautionRows(self.tenantId, permit.id)
        self.assertTrue(rows)
        self.assertTrue(any(x.isMandatory for x in rows))

    def testDifferentTypesGetDifferentChecklists(self):
        hot = self.makePermit(permitType=PERMIT_HOT_WORK)
        electrical = self.makePermit(permitType=PERMIT_ELECTRICAL)
        hotCodes = {x.code for x in precautionRows(self.tenantId, hot.id)}
        electricalCodes = {x.code for x in precautionRows(self.tenantId, electrical.id)}
        self.assertNotEqual(hotCodes, electricalCodes)

    def testPermitNumbersAreHumanReadableAndSequential(self):
        """Permits get read aloud over a radio and written on a board."""
        first = self.makePermit()
        second = self.makePermit()
        self.assertTrue(first.number.startswith("PTW-"))
        self.assertNotEqual(first.number, second.number)
        self.assertLess(first.number, second.number)

    def testNumbersDoNotCollideAcrossTenants(self):
        mine = self.makePermit()
        theirs = createPermit(
            self.otherTenantId,
            permitType=PERMIT_GENERAL,
            title="کار دیگر",
            actor=self.requester,
            now=self.now,
        )
        # Same day, same sequence — the uniqueness constraint is per tenant,
        # so both plants number their own permits from 001.
        self.assertEqual(mine.number, theirs.number)

    def testCreationIsRecordedInTheTrail(self):
        permit = self.makePermit()
        events = PermitEventModel.objects.filter(permitId=permit.id)
        self.assertEqual(events.count(), 1)
        self.assertEqual(events.first().action, "created")

    def testExtraPrecautionsAreAddedOnTopOfTheStandardOnes(self):
        standard = len(precautionRows(self.tenantId, self.makePermit().id))
        permit = self.makePermit(
            extraPrecautions=[{"code": "site", "text": "هماهنگی با اتاق کنترل", "isMandatory": True}]
        )
        self.assertEqual(len(precautionRows(self.tenantId, permit.id)), standard + 1)

    def testBlankExtraPrecautionsAreIgnored(self):
        standard = len(precautionRows(self.tenantId, self.makePermit().id))
        permit = self.makePermit(extraPrecautions=[{"code": "x", "text": "   "}])
        self.assertEqual(len(precautionRows(self.tenantId, permit.id)), standard)


class ApprovalTests(PermitTestBase):
    def testTheRequesterCannotApproveTheirOwnPermit(self):
        """Segregation of duties, against stored data."""
        permit = self.readyGeneralPermit()
        with self.assertRaises(PermitRuleViolation) as caught:
            approvePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        self.assertEqual(caught.exception.code, "permit.approval.selfApproval")
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_SUBMITTED)

    def testASupervisorCanApprove(self):
        permit = self.readyGeneralPermit()
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        stored = loadPermit(self.tenantId, permit.id)
        self.assertEqual(stored.status, PERMIT_APPROVED)
        self.assertEqual(stored.approverId, self.supervisor.id)
        self.assertEqual(stored.approverName, self.supervisor.name)

    def testApprovalIsRefusedWhileAMandatoryItemIsUnconfirmed(self):
        permit = self.makePermit()
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        with self.assertRaises(PermitRuleViolation) as caught:
            approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        self.assertEqual(caught.exception.code, "permit.issue.notReady")

    def testAnElectricalPermitNeedsAVerifiedIsolationRegister(self):
        permit = self.makePermit(permitType=PERMIT_ELECTRICAL)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        with self.assertRaises(PermitRuleViolation) as caught:
            approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        self.assertIn("جداسازی", caught.exception.message)

    def testAppliedButUnverifiedIsolationStillBlocksApproval(self):
        permit = self.makePermit(permitType=PERMIT_ELECTRICAL)
        point = createIsolationRow(
            tenantId=self.tenantId,
            permitId=permit.id,
            pointCode="ISO-1",
            description="کلید اصلی",
            energyType="electrical",
        )
        applyIsolation(self.tenantId, permit.id, point.id, actor=self.requester, now=self.now)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        with self.assertRaises(PermitRuleViolation):
            approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)

    def testAFullyPreparedElectricalPermitIsApproved(self):
        permit = self.makePermit(permitType=PERMIT_ELECTRICAL)
        point = createIsolationRow(
            tenantId=self.tenantId,
            permitId=permit.id,
            pointCode="ISO-1",
            description="کلید اصلی",
            energyType="electrical",
        )
        applyIsolation(self.tenantId, permit.id, point.id, actor=self.requester, now=self.now)
        verifyIsolation(self.tenantId, permit.id, point.id, actor=self.secondPerson, now=self.now)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_APPROVED)

    def testRejectionRequiresAReason(self):
        permit = self.readyGeneralPermit()
        with self.assertRaises(PermitRuleViolation) as caught:
            rejectPermit(self.tenantId, permit.id, actor=self.supervisor, reason="  ", now=self.now)
        self.assertEqual(caught.exception.code, "permit.reject.reasonRequired")

    def testRejectionStoresTheReason(self):
        permit = self.readyGeneralPermit()
        rejectPermit(
            self.tenantId, permit.id, actor=self.supervisor, reason="داربست ناایمن", now=self.now
        )
        stored = loadPermit(self.tenantId, permit.id)
        self.assertEqual(stored.status, PERMIT_REJECTED)
        self.assertEqual(stored.rejectionReason, "داربست ناایمن")

    def testApprovalNotesConflictingLivePermitsOnTheSameAsset(self):
        """Two crews on one machine must be a decision, not a surprise."""
        deviceId = uuid.uuid4()
        first = self.makePermit(deviceId=deviceId)
        self.confirmAllMandatory(first)
        submitPermit(self.tenantId, first.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, first.id, actor=self.supervisor, now=self.now)

        second = self.makePermit(deviceId=deviceId, title="کار دوم روی همان پمپ")
        self.confirmAllMandatory(second)
        submitPermit(self.tenantId, second.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, second.id, actor=self.supervisor, now=self.now)

        event = PermitEventModel.objects.filter(permitId=second.id, action="approved").first()
        self.assertIn(first.number, event.note)


class ChecklistLockTests(PermitTestBase):
    def testTheChecklistCannotChangeAfterAuthorisation(self):
        """The checklist is the assessment the permit was signed against."""
        permit = self.readyGeneralPermit()
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        row = precautionRows(self.tenantId, permit.id)[0]
        with self.assertRaises(PermitRuleViolation) as caught:
            confirmPrecaution(self.tenantId, permit.id, row.id, actor=self.requester, now=self.now)
        self.assertEqual(caught.exception.code, "permit.precaution.locked")

    def testConfirmationRecordsWhoAndWhen(self):
        permit = self.makePermit()
        row = precautionRows(self.tenantId, permit.id)[0]
        confirmPrecaution(self.tenantId, permit.id, row.id, actor=self.requester, now=self.now)
        stored = PermitPrecautionModel.objects.get(id=row.id)
        self.assertTrue(stored.confirmed)
        self.assertEqual(stored.confirmedById, self.requester.id)
        self.assertEqual(stored.confirmedByName, self.requester.name)
        self.assertIsNotNone(stored.confirmedAt)

    def testConfirmationIsLogged(self):
        permit = self.makePermit()
        row = precautionRows(self.tenantId, permit.id)[0]
        confirmPrecaution(self.tenantId, permit.id, row.id, actor=self.requester, now=self.now)
        self.assertTrue(
            PermitEventModel.objects.filter(
                permitId=permit.id, action="precautionConfirmed"
            ).exists()
        )


class IsolationRegisterTests(PermitTestBase):
    def setUp(self):
        super().setUp()
        self.permit = self.makePermit(permitType=PERMIT_ELECTRICAL, riskLevel=RISK_HIGH)
        self.point = createIsolationRow(
            tenantId=self.tenantId,
            permitId=self.permit.id,
            pointCode="ISO-1",
            description="کلید اصلی تابلو",
            energyType="electrical",
        )

    def testVerificationRequiresAnAppliedLockFirst(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            verifyIsolation(
                self.tenantId, self.permit.id, self.point.id, actor=self.secondPerson, now=self.now
            )
        self.assertEqual(caught.exception.code, "permit.isolation.notApplied")

    def testHighRiskRefusesSelfVerification(self):
        applyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.requester, now=self.now
        )
        with self.assertRaises(PermitRuleViolation) as caught:
            verifyIsolation(
                self.tenantId, self.permit.id, self.point.id, actor=self.requester, now=self.now
            )
        self.assertEqual(caught.exception.code, "permit.isolation.selfVerification")

    def testASecondPersonMayVerify(self):
        applyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.requester, now=self.now
        )
        verifyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.secondPerson, now=self.now
        )
        stored = isolationRows(self.tenantId, self.permit.id)[0]
        self.assertEqual(stored.verifiedById, self.secondPerson.id)
        self.assertEqual(stored.appliedById, self.requester.id)

    def testReapplyingALockInvalidatesTheOldVerification(self):
        """What was checked is not necessarily what is now in place."""
        applyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.requester, now=self.now
        )
        verifyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.secondPerson, now=self.now
        )
        applyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.requester, now=self.now
        )
        stored = isolationRows(self.tenantId, self.permit.id)[0]
        self.assertIsNone(stored.verifiedById)

    def testEverySignatureIsLogged(self):
        applyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.requester, now=self.now
        )
        verifyIsolation(
            self.tenantId, self.permit.id, self.point.id, actor=self.secondPerson, now=self.now
        )
        actions = set(
            PermitEventModel.objects.filter(permitId=self.permit.id).values_list(
                "action", flat=True
            )
        )
        self.assertIn("isolationApplied", actions)
        self.assertIn("isolationVerified", actions)


class WorkInProgressTests(PermitTestBase):
    def approvedPermit(self, **kwargs):
        permit = self.makePermit(**kwargs)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        return loadPermit(self.tenantId, permit.id)

    def testWorkCannotStartOnAnExpiredPermit(self):
        permit = self.approvedPermit()
        later = self.now + timedelta(hours=20)
        with self.assertRaises(PermitRuleViolation) as caught:
            activatePermit(self.tenantId, permit.id, actor=self.requester, now=later)
        self.assertEqual(caught.exception.code, "permit.activate.expired")

    def testWorkStartsInsideTheWindow(self):
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_ACTIVE)

    def testSuspendAndResume(self):
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        suspendPermit(
            self.tenantId, permit.id, actor=self.supervisor, reason="باد شدید", now=self.now
        )
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_SUSPENDED)
        resumePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        stored = loadPermit(self.tenantId, permit.id)
        self.assertEqual(stored.status, PERMIT_ACTIVE)
        self.assertEqual(stored.suspensionReason, "")

    def testResumingAfterTheWindowLapsedIsRefused(self):
        """Suspended at end of shift, resumed next morning."""
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        suspendPermit(
            self.tenantId, permit.id, actor=self.supervisor, reason="پایان شیفت", now=self.now
        )
        nextMorning = self.now + timedelta(hours=16)
        with self.assertRaises(PermitRuleViolation) as caught:
            resumePermit(self.tenantId, permit.id, actor=self.requester, now=nextMorning)
        self.assertEqual(caught.exception.code, "permit.resume.expired")

    def testLocksCannotComeOffWhileWorkIsRunning(self):
        permit = self.makePermit(permitType=PERMIT_ELECTRICAL)
        point = createIsolationRow(
            tenantId=self.tenantId,
            permitId=permit.id,
            pointCode="ISO-1",
            description="کلید",
            energyType="electrical",
        )
        applyIsolation(self.tenantId, permit.id, point.id, actor=self.requester, now=self.now)
        verifyIsolation(self.tenantId, permit.id, point.id, actor=self.secondPerson, now=self.now)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)

        with self.assertRaises(PermitRuleViolation) as caught:
            removeIsolation(self.tenantId, permit.id, point.id, actor=self.requester, now=self.now)
        self.assertEqual(caught.exception.code, "permit.isolation.removalBlocked")

    def testAPermitCannotBeClosedWithLocksStillOn(self):
        """The failure this whole feature exists to prevent."""
        permit = self.makePermit(permitType=PERMIT_ELECTRICAL)
        point = createIsolationRow(
            tenantId=self.tenantId,
            permitId=permit.id,
            pointCode="ISO-1",
            description="کلید",
            energyType="electrical",
        )
        applyIsolation(self.tenantId, permit.id, point.id, actor=self.requester, now=self.now)
        verifyIsolation(self.tenantId, permit.id, point.id, actor=self.secondPerson, now=self.now)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        completePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)

        with self.assertRaises(PermitRuleViolation) as caught:
            closePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        self.assertEqual(caught.exception.code, "permit.close.isolationsLive")

        removeIsolation(self.tenantId, permit.id, point.id, actor=self.requester, now=self.now)
        closePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_CLOSED)

    def testTheFullHappyPathIsReachable(self):
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        completePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        closePermit(
            self.tenantId, permit.id, actor=self.supervisor, note="تجهیز تحویل شد", now=self.now
        )
        stored = loadPermit(self.tenantId, permit.id)
        self.assertEqual(stored.status, PERMIT_CLOSED)
        self.assertEqual(stored.closedById, self.supervisor.id)
        self.assertEqual(stored.closureNote, "تجهیز تحویل شد")

    def testTheTrailRecordsTheWholeJourneyInOrder(self):
        """The status says where it is; the trail says how it got there."""
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        completePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        closePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        actions = list(
            PermitEventModel.objects.filter(permitId=permit.id)
            .order_by("occurredAt", "createdAt")
            .values_list("action", flat=True)
        )
        for expected in ("created", "submitted", "approved", "activated", "completed", "closed"):
            self.assertIn(expected, actions)
        self.assertLess(actions.index("approved"), actions.index("activated"))
        self.assertLess(actions.index("completed"), actions.index("closed"))


class ExpiryScanTests(PermitTestBase):
    def approvedPermit(self, *, hours=4):
        permit = self.makePermit(hours=hours)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        return loadPermit(self.tenantId, permit.id)

    def testAnUnstartedPermitPastItsWindowIsExpired(self):
        permit = self.approvedPermit()
        later = self.now + timedelta(hours=6)
        result = scanPermitExpiry(self.tenantId, now=later, apply=True)
        self.assertIn(permit.number, result["expired"])
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_EXPIRED)

    def testALivePermitPastItsWindowIsNeverAutoExpired(self):
        """People may still be inside the vessel. Alarm, do not cancel."""
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        later = self.now + timedelta(hours=6)
        result = scanPermitExpiry(self.tenantId, now=later, apply=True)
        self.assertIn(permit.number, result["overdueWithWorkInProgress"])
        self.assertNotIn(permit.number, result["expired"])
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_ACTIVE)

    def testASuspendedPermitPastItsWindowIsAlsoOnlyAlarmed(self):
        permit = self.approvedPermit()
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        suspendPermit(
            self.tenantId, permit.id, actor=self.supervisor, reason="وقفه", now=self.now
        )
        later = self.now + timedelta(hours=6)
        result = scanPermitExpiry(self.tenantId, now=later, apply=True)
        self.assertIn(permit.number, result["overdueWithWorkInProgress"])
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_SUSPENDED)

    def testPermitsNearTheEndAreFlaggedWhileThereIsTimeToAct(self):
        permit = self.approvedPermit()
        nearEnd = self.now + timedelta(hours=3, minutes=40)
        result = scanPermitExpiry(self.tenantId, now=nearEnd, apply=False)
        self.assertIn(permit.number, result["expiringSoon"])

    def testDryRunChangesNothing(self):
        permit = self.approvedPermit()
        later = self.now + timedelta(hours=6)
        result = scanPermitExpiry(self.tenantId, now=later, apply=False)
        self.assertIn(permit.number, result["expired"])
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_APPROVED)

    def testDraftsAreNeverExpired(self):
        """A draft has no authority to lapse."""
        permit = self.makePermit(hours=1)
        later = self.now + timedelta(hours=5)
        result = scanPermitExpiry(self.tenantId, now=later, apply=True)
        self.assertEqual(result["expired"], [])
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, "draft")

    def testTheScanIsIdempotent(self):
        permit = self.approvedPermit()
        later = self.now + timedelta(hours=6)
        scanPermitExpiry(self.tenantId, now=later, apply=True)
        again = scanPermitExpiry(self.tenantId, now=later, apply=True)
        self.assertEqual(again["expired"], [])
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_EXPIRED)
        self.assertEqual(permit.number, permit.number)

    def testTheScanDoesNotCrossTenants(self):
        mine = self.approvedPermit()
        later = self.now + timedelta(hours=6)
        result = scanPermitExpiry(self.otherTenantId, now=later, apply=True)
        self.assertEqual(result["expired"], [])
        self.assertEqual(loadPermit(self.tenantId, mine.id).status, PERMIT_APPROVED)


class TenantIsolationTests(PermitTestBase):
    def testAPermitCannotBeLoadedFromAnotherTenant(self):
        """In a multi-tenant safety system this is one plant closing another
        plant's permit."""
        permit = self.makePermit()
        with self.assertRaises(PermitNotFound):
            loadPermit(self.otherTenantId, permit.id)

    def testAPermitCannotBeApprovedFromAnotherTenant(self):
        permit = self.readyGeneralPermit()
        with self.assertRaises(PermitNotFound):
            approvePermit(self.otherTenantId, permit.id, actor=self.supervisor, now=self.now)
        self.assertEqual(loadPermit(self.tenantId, permit.id).status, PERMIT_SUBMITTED)

    def testAPermitCannotBeCancelledFromAnotherTenant(self):
        permit = self.makePermit()
        with self.assertRaises(PermitNotFound):
            cancelPermit(
                self.otherTenantId, permit.id, actor=self.supervisor, reason="x", now=self.now
            )


class ReadModelTests(PermitTestBase):
    def testReadinessListsWhatIsStillMissing(self):
        permit = self.makePermit(permitType=PERMIT_ELECTRICAL)
        readiness = permitReadiness(self.tenantId, loadPermit(self.tenantId, permit.id))
        self.assertFalse(readiness["isReadyToIssue"])
        self.assertTrue(readiness["blockers"])

    def testValidityIsComputedFreshNotStored(self):
        permit = self.makePermit(hours=2)
        stored = loadPermit(self.tenantId, permit.id)
        self.assertFalse(permitValidityView(stored, now=self.now)["isExpired"])
        self.assertTrue(
            permitValidityView(stored, now=self.now + timedelta(hours=3))["isExpired"]
        )
        # No column was written in between.
        self.assertEqual(
            PermitToWorkModel.objects.get(id=permit.id).status, "draft"
        )

    def testOverdueWorkInProgressIsSurfacedInTheReadModel(self):
        permit = self.makePermit(hours=2)
        self.confirmAllMandatory(permit)
        submitPermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        approvePermit(self.tenantId, permit.id, actor=self.supervisor, now=self.now)
        activatePermit(self.tenantId, permit.id, actor=self.requester, now=self.now)
        stored = loadPermit(self.tenantId, permit.id)
        view = permitValidityView(stored, now=self.now + timedelta(hours=3))
        self.assertTrue(view["isOverdueWithWorkInProgress"])
