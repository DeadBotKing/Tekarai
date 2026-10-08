"""The safety rules, tested on their own — no database, clock injected.

These are the refusals that make a permit a control rather than paperwork.
Each test names the way someone gets hurt if the rule is missing, because a
future maintainer deciding whether a failing assertion is "just a test being
awkward" needs to know what it is standing in front of.
"""

from __future__ import annotations

from datetime import timedelta

from django.test import SimpleTestCase
from django.utils import timezone

from apps.safety.domain.services.permitRules import (
    EXPIRY_WARNING_MINUTES,
    IsolationSnapshot,
    PermitRuleViolation,
    PrecautionSnapshot,
    evaluateIssueReadiness,
    evaluatePermitValidity,
    guardActivation,
    guardApproval,
    guardClosure,
    guardIsolationRemoval,
    guardIsolationVerifier,
    guardResume,
    guardSegregationOfDuties,
    guardTransition,
    guardValidityWindow,
)
from apps.safety.domain.valueObjects.permitState import (
    PERMIT_ACTIVE,
    PERMIT_APPROVED,
    PERMIT_CANCELLED,
    PERMIT_CLOSED,
    PERMIT_COMPLETED,
    PERMIT_CONFINED_SPACE,
    PERMIT_DRAFT,
    PERMIT_ELECTRICAL,
    PERMIT_EXPIRED,
    PERMIT_GENERAL,
    PERMIT_HOT_WORK,
    PERMIT_REJECTED,
    PERMIT_STATUSES,
    PERMIT_SUBMITTED,
    PERMIT_SUSPENDED,
    PERMIT_TRANSITIONS,
    PERMIT_TYPES,
    RISK_CRITICAL,
    RISK_HIGH,
    RISK_LOW,
    RISK_MEDIUM,
    maxValidityHoursFor,
    requiresIsolation,
    standardPrecautionsFor,
)


def precaution(code: str, *, mandatory: bool = True, confirmed: bool = False):
    return PrecautionSnapshot(
        code=code, text=f"اقدام {code}", isMandatory=mandatory, confirmed=confirmed
    )


def isolation(
    code: str, *, applied: str = "", verified: str = "", removed: str = ""
) -> IsolationSnapshot:
    return IsolationSnapshot(
        pointCode=code,
        description=f"نقطه {code}",
        appliedById=applied,
        verifiedById=verified,
        removedById=removed,
    )


class TransitionTests(SimpleTestCase):
    def testTerminalStatusesAreTerminal(self):
        """A closed permit that can be reopened is not a record of anything."""
        for status in (PERMIT_CLOSED, PERMIT_REJECTED, PERMIT_CANCELLED, PERMIT_EXPIRED):
            with self.assertRaises(PermitRuleViolation) as caught:
                guardTransition(status, PERMIT_ACTIVE)
            self.assertEqual(caught.exception.code, "permit.transition.terminal")

    def testWorkCannotRestartOnAClosedPermit(self):
        with self.assertRaises(PermitRuleViolation):
            guardTransition(PERMIT_CLOSED, PERMIT_ACTIVE)

    def testDraftCannotJumpStraightToActive(self):
        """Skipping authorisation is the whole thing a permit prevents."""
        with self.assertRaises(PermitRuleViolation) as caught:
            guardTransition(PERMIT_DRAFT, PERMIT_ACTIVE)
        self.assertEqual(caught.exception.code, "permit.transition.illegal")

    def testSubmittedCannotBecomeActiveWithoutApproval(self):
        with self.assertRaises(PermitRuleViolation):
            guardTransition(PERMIT_SUBMITTED, PERMIT_ACTIVE)

    def testLegalPathRunsEndToEnd(self):
        guardTransition(PERMIT_DRAFT, PERMIT_SUBMITTED)
        guardTransition(PERMIT_SUBMITTED, PERMIT_APPROVED)
        guardTransition(PERMIT_APPROVED, PERMIT_ACTIVE)
        guardTransition(PERMIT_ACTIVE, PERMIT_SUSPENDED)
        guardTransition(PERMIT_SUSPENDED, PERMIT_ACTIVE)
        guardTransition(PERMIT_ACTIVE, PERMIT_COMPLETED)
        guardTransition(PERMIT_COMPLETED, PERMIT_CLOSED)

    def testCompletedWorkCannotBeCancelledRetroactively(self):
        with self.assertRaises(PermitRuleViolation):
            guardTransition(PERMIT_COMPLETED, PERMIT_CANCELLED)

    def testRepeatingTheCurrentStatusIsRefusedNotSilentlyAccepted(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardTransition(PERMIT_ACTIVE, PERMIT_ACTIVE)
        self.assertEqual(caught.exception.code, "permit.transition.noop")

    def testEveryStatusHasATransitionEntry(self):
        """A status missing from the table would silently allow nothing —
        or, worse, be read as 'no restrictions' by a future edit."""
        for status in PERMIT_STATUSES:
            self.assertIn(status, PERMIT_TRANSITIONS)

    def testEveryTransitionTargetIsAKnownStatus(self):
        for status, targets in PERMIT_TRANSITIONS.items():
            for target in targets:
                self.assertIn(target, PERMIT_STATUSES, f"{status} → {target}")


class SegregationOfDutiesTests(SimpleTestCase):
    """The oldest control in permit-to-work, and the most often bypassed."""

    def testRequesterCannotApproveTheirOwnPermit(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardSegregationOfDuties(requesterId="user-1", approverId="user-1")
        self.assertEqual(caught.exception.code, "permit.approval.selfApproval")

    def testADifferentApproverIsAccepted(self):
        guardSegregationOfDuties(requesterId="user-1", approverId="user-2")

    def testIdentityIsComparedAsAStringNotByObject(self):
        """Same person arriving as UUID and as str must still be caught."""
        import uuid

        someone = uuid.uuid4()
        with self.assertRaises(PermitRuleViolation):
            guardSegregationOfDuties(requesterId=someone, approverId=str(someone))

    def testTheRuleIsEnforcedInsideFullApproval(self):
        now = timezone.now()
        with self.assertRaises(PermitRuleViolation) as caught:
            guardApproval(
                currentStatus=PERMIT_SUBMITTED,
                permitType=PERMIT_GENERAL,
                riskLevel=RISK_LOW,
                requesterId="same",
                approverId="same",
                validFrom=now,
                validTo=now + timedelta(hours=4),
                precautions=[],
                isolations=[],
                now=now,
            )
        self.assertEqual(caught.exception.code, "permit.approval.selfApproval")


class ValidityWindowTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def testAWindowIsRequired(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardValidityWindow(permitType=PERMIT_GENERAL, validFrom=None, validTo=None)
        self.assertEqual(caught.exception.code, "permit.window.missing")

    def testEndMustFollowStart(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardValidityWindow(
                permitType=PERMIT_GENERAL,
                validFrom=self.now,
                validTo=self.now - timedelta(hours=1),
            )
        self.assertEqual(caught.exception.code, "permit.window.inverted")

    def testHotWorkIsCappedAtTwelveHours(self):
        """A gas test is not evidence about tomorrow."""
        guardValidityWindow(
            permitType=PERMIT_HOT_WORK,
            validFrom=self.now,
            validTo=self.now + timedelta(hours=12),
        )
        with self.assertRaises(PermitRuleViolation) as caught:
            guardValidityWindow(
                permitType=PERMIT_HOT_WORK,
                validFrom=self.now,
                validTo=self.now + timedelta(hours=13),
            )
        self.assertEqual(caught.exception.code, "permit.window.tooLong")

    def testEveryPermitTypeHasABoundedCap(self):
        """An open-ended permit is an unassessed one."""
        for permitType in PERMIT_TYPES:
            self.assertGreater(maxValidityHoursFor(permitType), 0)
            self.assertLessEqual(maxValidityHoursFor(permitType), 72)

    def testApprovingAWindowThatAlreadyClosedIsRefused(self):
        """A signed permit that is already dead invites work under it anyway."""
        with self.assertRaises(PermitRuleViolation) as caught:
            guardApproval(
                currentStatus=PERMIT_SUBMITTED,
                permitType=PERMIT_GENERAL,
                riskLevel=RISK_LOW,
                requesterId="a",
                approverId="b",
                validFrom=self.now - timedelta(hours=5),
                validTo=self.now - timedelta(hours=1),
                precautions=[],
                isolations=[],
                now=self.now,
            )
        self.assertEqual(caught.exception.code, "permit.window.alreadyPast")


class ExpiryIsComputedTests(SimpleTestCase):
    """Validity is a function of the clock, never a stored flag."""

    def setUp(self):
        self.now = timezone.now()

    def testInsideTheWindow(self):
        validity = evaluatePermitValidity(
            validFrom=self.now - timedelta(hours=1),
            validTo=self.now + timedelta(hours=1),
            now=self.now,
        )
        self.assertTrue(validity.isWithinWindow)
        self.assertFalse(validity.isExpired)
        self.assertEqual(validity.minutesRemaining, 60)

    def testPastTheWindow(self):
        validity = evaluatePermitValidity(
            validFrom=self.now - timedelta(hours=5),
            validTo=self.now - timedelta(minutes=1),
            now=self.now,
        )
        self.assertTrue(validity.isExpired)
        self.assertFalse(validity.isWithinWindow)
        self.assertEqual(validity.minutesRemaining, 0)

    def testBeforeTheWindow(self):
        validity = evaluatePermitValidity(
            validFrom=self.now + timedelta(minutes=30),
            validTo=self.now + timedelta(hours=4),
            now=self.now,
        )
        self.assertFalse(validity.hasStarted)
        self.assertFalse(validity.isExpired)
        self.assertEqual(validity.minutesUntilStart, 30)

    def testTheSamePermitExpiresPurelyBecauseTimePassed(self):
        """No write happens in between — the verdict follows the clock."""
        validFrom = self.now - timedelta(hours=1)
        validTo = self.now + timedelta(minutes=10)
        self.assertFalse(
            evaluatePermitValidity(validFrom=validFrom, validTo=validTo, now=self.now).isExpired
        )
        later = self.now + timedelta(minutes=11)
        self.assertTrue(
            evaluatePermitValidity(validFrom=validFrom, validTo=validTo, now=later).isExpired
        )

    def testExpiringSoonWarnsWhileThereIsStillTimeToAct(self):
        validity = evaluatePermitValidity(
            validFrom=self.now - timedelta(hours=1),
            validTo=self.now + timedelta(minutes=EXPIRY_WARNING_MINUTES - 5),
            now=self.now,
        )
        self.assertTrue(validity.isExpiringSoon)

    def testAPermitWithNoWindowIsNotCalledExpired(self):
        validity = evaluatePermitValidity(validFrom=None, validTo=None, now=self.now)
        self.assertFalse(validity.isExpired)
        self.assertFalse(validity.hasStarted)


class PrecautionTests(SimpleTestCase):
    def testMandatoryPrecautionBlocksIssue(self):
        """Issuing against an unticked box means nobody checked."""
        report = evaluateIssueReadiness(
            permitType=PERMIT_GENERAL,
            precautions=[precaution("ppe", confirmed=False)],
            isolations=[],
        )
        self.assertFalse(report.isSatisfied)

    def testOptionalPrecautionDoesNotBlock(self):
        report = evaluateIssueReadiness(
            permitType=PERMIT_GENERAL,
            precautions=[precaution("weather", mandatory=False, confirmed=False)],
            isolations=[],
        )
        self.assertTrue(report.isSatisfied)

    def testAllBlockersAreReportedTogetherNotOneAtATime(self):
        """One trip to the permit office, not four."""
        report = evaluateIssueReadiness(
            permitType=PERMIT_GENERAL,
            precautions=[precaution("a"), precaution("b"), precaution("c")],
            isolations=[],
        )
        self.assertEqual(len(report.blockers), 3)

    def testEveryPermitTypeOffersAChecklistWithAtLeastOneMandatoryItem(self):
        """A type with an empty checklist can be issued with no thought."""
        for permitType in PERMIT_TYPES:
            items = standardPrecautionsFor(permitType)
            self.assertTrue(items, permitType)
            self.assertTrue(any(mandatory for _, _, mandatory in items), permitType)

    def testAnUnknownTypeStillGetsAHazardReview(self):
        items = standardPrecautionsFor("somethingNobodyAnticipated")
        self.assertTrue(any(mandatory for _, _, mandatory in items))


class IsolationRegisterTests(SimpleTestCase):
    """Stored energy is what kills during maintenance."""

    def testIsolationClassPermitNeedsAtLeastOnePoint(self):
        report = evaluateIssueReadiness(
            permitType=PERMIT_ELECTRICAL, precautions=[], isolations=[]
        )
        self.assertFalse(report.isSatisfied)

    def testAppliedButUnverifiedIsNotEnough(self):
        """Applied is a claim; verified is the control."""
        report = evaluateIssueReadiness(
            permitType=PERMIT_ELECTRICAL,
            precautions=[],
            isolations=[isolation("ISO-1", applied="bob")],
        )
        self.assertFalse(report.isSatisfied)
        self.assertIn("تأیید نشده", report.blockers[0])

    def testRecordedButNotAppliedIsReportedDistinctly(self):
        report = evaluateIssueReadiness(
            permitType=PERMIT_ELECTRICAL, precautions=[], isolations=[isolation("ISO-1")]
        )
        self.assertIn("اجرا نشده", report.blockers[0])

    def testAppliedAndVerifiedSatisfiesTheRule(self):
        report = evaluateIssueReadiness(
            permitType=PERMIT_ELECTRICAL,
            precautions=[],
            isolations=[isolation("ISO-1", applied="bob", verified="alice")],
        )
        self.assertTrue(report.isSatisfied)

    def testNonIsolationTypesDoNotDemandARegister(self):
        """Demanding one where it does not apply trains people to fake it."""
        report = evaluateIssueReadiness(
            permitType=PERMIT_HOT_WORK, precautions=[], isolations=[]
        )
        self.assertTrue(report.isSatisfied)

    def testTheIsolationClassListIsTheOneWeThinkItIs(self):
        self.assertTrue(requiresIsolation(PERMIT_ELECTRICAL))
        self.assertTrue(requiresIsolation(PERMIT_CONFINED_SPACE))
        self.assertFalse(requiresIsolation(PERMIT_HOT_WORK))

    def testARemovedPointDoesNotCountAsAnIsolation(self):
        report = evaluateIssueReadiness(
            permitType=PERMIT_ELECTRICAL,
            precautions=[],
            isolations=[isolation("ISO-1", applied="bob", verified="alice", removed="bob")],
        )
        self.assertFalse(report.isSatisfied)


class TwoPersonRuleTests(SimpleTestCase):
    def testHighRiskForbidsSelfVerification(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardIsolationVerifier(
                appliedById="bob", verifiedById="bob", riskLevel=RISK_HIGH
            )
        self.assertEqual(caught.exception.code, "permit.isolation.selfVerification")

    def testCriticalRiskForbidsSelfVerification(self):
        with self.assertRaises(PermitRuleViolation):
            guardIsolationVerifier(
                appliedById="bob", verifiedById="bob", riskLevel=RISK_CRITICAL
            )

    def testLowAndMediumRiskAcceptOneCompetentPerson(self):
        # Demanding a second body for every low-risk isolation in a small
        # plant produces signatures nobody witnessed.
        for level in (RISK_LOW, RISK_MEDIUM):
            guardIsolationVerifier(appliedById="bob", verifiedById="bob", riskLevel=level)

    def testDifferentPeopleAlwaysPass(self):
        guardIsolationVerifier(
            appliedById="bob", verifiedById="alice", riskLevel=RISK_CRITICAL
        )

    def testApprovalEnforcesItAcrossTheWholeRegister(self):
        now = timezone.now()
        with self.assertRaises(PermitRuleViolation) as caught:
            guardApproval(
                currentStatus=PERMIT_SUBMITTED,
                permitType=PERMIT_ELECTRICAL,
                riskLevel=RISK_HIGH,
                requesterId="a",
                approverId="b",
                validFrom=now,
                validTo=now + timedelta(hours=4),
                precautions=[],
                isolations=[
                    isolation("ISO-1", applied="x", verified="y"),
                    isolation("ISO-2", applied="bob", verified="bob"),
                ],
                now=now,
            )
        self.assertEqual(caught.exception.code, "permit.isolation.selfVerification")


class ActivationTests(SimpleTestCase):
    def setUp(self):
        self.now = timezone.now()

    def testCannotStartWorkOnAnExpiredPermit(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardActivation(
                currentStatus=PERMIT_APPROVED,
                validFrom=self.now - timedelta(hours=5),
                validTo=self.now - timedelta(minutes=1),
                now=self.now,
            )
        self.assertEqual(caught.exception.code, "permit.activate.expired")

    def testCannotStartWorkBeforeTheWindowOpens(self):
        """Early start is the quiet one: isolations may not be in place and
        the outgoing shift may still be in the area."""
        with self.assertRaises(PermitRuleViolation) as caught:
            guardActivation(
                currentStatus=PERMIT_APPROVED,
                validFrom=self.now + timedelta(hours=2),
                validTo=self.now + timedelta(hours=6),
                now=self.now,
            )
        self.assertEqual(caught.exception.code, "permit.activate.notYetValid")

    def testStartingInsideTheWindowIsAllowed(self):
        guardActivation(
            currentStatus=PERMIT_APPROVED,
            validFrom=self.now - timedelta(minutes=5),
            validTo=self.now + timedelta(hours=4),
            now=self.now,
        )

    def testResumeAfterTheWindowLapsedIsRefused(self):
        """Suspended at end of shift, resumed next morning — the permit died
        overnight and resuming must not be a bookkeeping flip."""
        with self.assertRaises(PermitRuleViolation) as caught:
            guardResume(
                currentStatus=PERMIT_SUSPENDED,
                validFrom=self.now - timedelta(hours=14),
                validTo=self.now - timedelta(hours=2),
                now=self.now,
            )
        self.assertEqual(caught.exception.code, "permit.resume.expired")

    def testResumeInsideTheWindowIsAllowed(self):
        guardResume(
            currentStatus=PERMIT_SUSPENDED,
            validFrom=self.now - timedelta(hours=1),
            validTo=self.now + timedelta(hours=1),
            now=self.now,
        )


class ClosureTests(SimpleTestCase):
    def testCannotCloseWithLocksStillOn(self):
        """A permit closed over a forgotten lock is how equipment is started
        on somebody."""
        with self.assertRaises(PermitRuleViolation) as caught:
            guardClosure(
                currentStatus=PERMIT_COMPLETED,
                isolations=[isolation("ISO-1", applied="bob", verified="alice")],
            )
        self.assertEqual(caught.exception.code, "permit.close.isolationsLive")

    def testTheErrorNamesTheOutstandingLocks(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardClosure(
                currentStatus=PERMIT_COMPLETED,
                isolations=[
                    isolation("ISO-1", applied="b", verified="a"),
                    isolation("ISO-2", applied="b", verified="a", removed="b"),
                    isolation("ISO-3", applied="b", verified="a"),
                ],
            )
        self.assertIn("ISO-1", caught.exception.message)
        self.assertIn("ISO-3", caught.exception.message)
        self.assertNotIn("ISO-2", caught.exception.message)

    def testClosesOnceEveryLockIsBack(self):
        guardClosure(
            currentStatus=PERMIT_COMPLETED,
            isolations=[isolation("ISO-1", applied="b", verified="a", removed="b")],
        )

    def testClosureStillObeysTheLifecycle(self):
        with self.assertRaises(PermitRuleViolation) as caught:
            guardClosure(currentStatus=PERMIT_ACTIVE, isolations=[])
        self.assertEqual(caught.exception.code, "permit.transition.illegal")


class IsolationRemovalTests(SimpleTestCase):
    def testLocksCannotComeOffWhileWorkIsRunning(self):
        """Removing an isolation on an active permit re-energises equipment
        people are still inside."""
        for status in (PERMIT_ACTIVE, PERMIT_SUSPENDED, PERMIT_APPROVED):
            with self.assertRaises(PermitRuleViolation) as caught:
                guardIsolationRemoval(permitStatus=status)
            self.assertEqual(caught.exception.code, "permit.isolation.removalBlocked")

    def testLocksComeOffAfterWorkIsComplete(self):
        guardIsolationRemoval(permitStatus=PERMIT_COMPLETED)

    def testLocksComeOffIfThePermitWasCancelledBeforeItRan(self):
        guardIsolationRemoval(permitStatus=PERMIT_CANCELLED)
        guardIsolationRemoval(permitStatus=PERMIT_REJECTED)


class FullApprovalPathTests(SimpleTestCase):
    """The happy path must actually be reachable.

    A guard suite that only proves things are refused can hide a rule that
    refuses everything — which in a real plant means the permit system is
    bypassed on paper within a week.
    """

    def testAWellPreparedElectricalPermitIsApproved(self):
        now = timezone.now()
        guardApproval(
            currentStatus=PERMIT_SUBMITTED,
            permitType=PERMIT_ELECTRICAL,
            riskLevel=RISK_HIGH,
            requesterId="requester",
            approverId="supervisor",
            validFrom=now,
            validTo=now + timedelta(hours=8),
            precautions=[
                precaution("deEnergised", confirmed=True),
                precaution("lockApplied", confirmed=True),
                precaution("weather", mandatory=False, confirmed=False),
            ],
            isolations=[isolation("ISO-1", applied="bob", verified="alice")],
            now=now,
        )

    def testAWellPreparedHotWorkPermitIsApproved(self):
        now = timezone.now()
        guardApproval(
            currentStatus=PERMIT_SUBMITTED,
            permitType=PERMIT_HOT_WORK,
            riskLevel=RISK_MEDIUM,
            requesterId="requester",
            approverId="supervisor",
            validFrom=now,
            validTo=now + timedelta(hours=6),
            precautions=[precaution("fireWatch", confirmed=True)],
            isolations=[],
            now=now,
        )
