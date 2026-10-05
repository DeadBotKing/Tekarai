"""Scoring arithmetic for workforce performance reviews — Phase 29.

Pure-function tests: no database, no Django ORM.
"""

from __future__ import annotations

import unittest

from apps.maintenance.domain.services.performanceReviewRules import (
    RaterScore,
    SystemMetrics,
    clampScore,
    dampingFactor,
    median,
    medianAbsoluteDeviation,
    rankOutcomes,
    reliabilityFromHistory,
    roleWeight,
    scoreReview,
    systemScore,
)
from apps.maintenance.domain.valueObjects.performanceState import (
    DEFAULT_ROLE_WEIGHTS,
    MIN_DAMPING_FACTOR,
    MIN_RATERS_FOR_DAMPING,
    RATER_ROLES,
    REASON_CODES,
    REASON_DAMPED_ABOVE,
    REASON_DAMPED_BELOW,
    REASON_FULL_WEIGHT,
)


class ScaleTests(unittest.TestCase):
    def testClampPullsOutOfRangeOntoTheScale(self) -> None:
        self.assertEqual(clampScore(-20), 0.0)
        self.assertEqual(clampScore(140), 100.0)
        self.assertEqual(clampScore(72), 72.0)

    def testClampTreatsRubbishAsZeroRatherThanRaising(self) -> None:
        self.assertEqual(clampScore(None), 0.0)
        self.assertEqual(clampScore("abc"), 0.0)
        self.assertEqual(clampScore(float("nan")), 0.0)


class MedianTests(unittest.TestCase):
    def testOddAndEvenCounts(self) -> None:
        self.assertEqual(median([70, 72, 95]), 72)
        self.assertEqual(median([70, 72, 74, 96]), 73)

    def testEmptyIsZeroNotAnError(self) -> None:
        self.assertEqual(median([]), 0.0)

    def testMedianBarelyMovesWhenOneRaterGoesExtreme(self) -> None:
        """The property the whole engine rests on."""
        honest = [70, 72, 74, 76, 78]
        self.assertEqual(median(honest), 74)
        self.assertEqual(median(honest + [100]), 75)
        self.assertEqual(median(honest + [0]), 73)

    def testMadIgnoresTheOutlierItMeasures(self) -> None:
        self.assertEqual(medianAbsoluteDeviation([70, 72, 74, 76, 78]), 2.0)
        self.assertEqual(medianAbsoluteDeviation([70, 72, 74, 76, 1000]), 2.0)


class RoleWeightTests(unittest.TestCase):
    def testEveryDeclaredRoleCarriesAWeight(self) -> None:
        for role in RATER_ROLES:
            self.assertGreater(roleWeight(role), 0, role)

    def testUnknownRoleIsWorthNothing(self) -> None:
        """A typo must not quietly buy somebody a vote."""
        self.assertEqual(roleWeight("productionManger"), 0.0)
        self.assertEqual(roleWeight(""), 0.0)

    def testOverridesApplyAndRubbishIsIgnored(self) -> None:
        self.assertEqual(roleWeight("qaManager", {"qaManager": 40}), 40.0)
        self.assertEqual(
            roleWeight("qaManager", {"qaManager": "x"}),
            float(DEFAULT_ROLE_WEIGHTS["qaManager"]),
        )

    def testOverrideCannotInventARole(self) -> None:
        self.assertEqual(roleWeight("chiefVibes", {"chiefVibes": 99}), 0.0)


class DampingTests(unittest.TestCase):
    def testOrdinaryDisagreementCostsNothing(self) -> None:
        self.assertEqual(dampingFactor(0.0), 1.0)
        self.assertEqual(dampingFactor(1.4), 1.0)
        self.assertEqual(dampingFactor(-1.5), 1.0)

    def testBeyondToleranceTheWeightFalls(self) -> None:
        self.assertLess(dampingFactor(2.5), 1.0)
        self.assertLess(dampingFactor(4.0), dampingFactor(2.5))

    def testDampingIsSymmetric(self) -> None:
        """Inflating and deflating must cost the same."""
        self.assertEqual(dampingFactor(3.0), dampingFactor(-3.0))

    def testADampedRaterIsNeverSilenced(self) -> None:
        self.assertGreaterEqual(dampingFactor(50.0), MIN_DAMPING_FACTOR)

    def testThereIsNoCliffEdge(self) -> None:
        """One point of difference must not flip counted to ignored."""
        self.assertLess(abs(dampingFactor(1.50) - dampingFactor(1.51)), 0.01)


class ReliabilityTests(unittest.TestCase):
    def testANewRaterIsTrustedCompletely(self) -> None:
        self.assertEqual(reliabilityFromHistory(None, 0), 1.0)
        self.assertEqual(reliabilityFromHistory(9.0, 0), 1.0)

    def testSuspicionNeedsEnoughHistory(self) -> None:
        self.assertEqual(reliabilityFromHistory(5.0, 1), 1.0)
        self.assertLess(reliabilityFromHistory(5.0, 6), 1.0)

    def testAConsistentRaterKeepsFullStanding(self) -> None:
        self.assertEqual(reliabilityFromHistory(0.5, 10), 1.0)

    def testStandingHasAFloor(self) -> None:
        self.assertGreaterEqual(reliabilityFromHistory(100.0, 50), 0.40)


class SystemScoreTests(unittest.TestCase):
    def testBlendsTheMeasuredMetrics(self) -> None:
        value = systemScore(
            SystemMetrics(
                pmCompliance=90,
                onTimeCompletion=80,
                completionRate=100,
                reworkPenalty=60,
            )
        )
        assert value is not None  # narrows the Optional for the type checker
        self.assertAlmostEqual(value, 84.5, places=1)

    def testNothingMeasuredIsNoneNotZero(self) -> None:
        """A silent record must not be read as a bad record."""
        self.assertIsNone(systemScore(SystemMetrics()))

    def testMissingMetricsAreDroppedNotCountedAsZero(self) -> None:
        onlyPm = systemScore(SystemMetrics(pmCompliance=80))
        self.assertEqual(onlyPm, 80.0)

    def testATechnicianNeverAssignedPmIsNotPunished(self) -> None:
        withoutPm = systemScore(SystemMetrics(onTimeCompletion=90, completionRate=90))
        withPmZeroed = systemScore(
            SystemMetrics(pmCompliance=0, onTimeCompletion=90, completionRate=90)
        )
        assert withoutPm is not None and withPmZeroed is not None
        self.assertEqual(withoutPm, 90.0)
        self.assertLess(withPmZeroed, withoutPm)


class JavadScenarioTests(unittest.TestCase):
    """The exact case the feature was asked for.

    جواد امیرشاهی is rated by several managers. The production manager
    inflates him, the technical manager buries him, and the rest report what
    they saw. The engine has to land near what the honest raters said.
    """

    def _raters(self) -> list[RaterScore]:
        return [
            RaterScore("productionManager", 95, raterName="مدیر تولید"),
            RaterScore("technicalManager", 40, raterName="مدیر فنی"),
            RaterScore("unitHead", 72, raterName="رئیس واحد"),
            RaterScore("unitSupervisor", 70, raterName="سرپرست واحد"),
            RaterScore("qaManager", 74, raterName="مدیر کیفیت"),
            RaterScore("hseUnit", 71, raterName="ایمنی و بهداشت"),
        ]

    def testTheTwoBiasedRatersAreBothDamped(self) -> None:
        outcome = scoreReview("p-javad", self._raters(), personnelName="جواد امیرشاهی")
        byRole = {row.raterRole: row for row in outcome.raters}
        self.assertTrue(byRole["productionManager"].damped)
        self.assertTrue(byRole["technicalManager"].damped)
        self.assertFalse(byRole["unitHead"].damped)
        self.assertFalse(byRole["unitSupervisor"].damped)
        self.assertEqual(outcome.dampedCount, 2)

    def testTheHonestRatersEndUpCarryingMoreThanTheBiasedOnes(self) -> None:
        outcome = scoreReview("p-javad", self._raters())
        byRole = {row.raterRole: row for row in outcome.raters}
        # The unit head started on a *smaller* base weight than the technical
        # manager (16 vs 18) and still ends up counting for more.
        self.assertGreater(byRole["unitHead"].contribution, byRole["technicalManager"].contribution)
        self.assertGreater(
            byRole["unitHead"].contribution, byRole["productionManager"].contribution
        )

    def testTheResultLandsNearWhatTheHonestRatersSaid(self) -> None:
        outcome = scoreReview("p-javad", self._raters())
        # Honest raters said 70-74. A plain weighted mean would be dragged
        # well below that by the 40.
        self.assertGreater(outcome.humanScore, 68.0)
        self.assertLess(outcome.humanScore, 78.0)

    def testItBeatsThePlainWeightedAverageItReplaces(self) -> None:
        raters = self._raters()
        outcome = scoreReview("p-javad", raters)
        plain = sum(r.score * roleWeight(r.raterRole) for r in raters) / sum(
            roleWeight(r.raterRole) for r in raters
        )
        honest = median([72, 70, 74, 71])
        self.assertLess(
            abs(outcome.humanScore - honest),
            abs(plain - honest),
            "damped score must sit closer to the honest consensus than a plain average",
        )

    def testOneBiasedRaterCannotMoveTheResultMuch(self) -> None:
        """Push the production manager from 95 to 100 — barely anything moves."""
        base = scoreReview("p-javad", self._raters()).humanScore
        pushed = list(self._raters())
        pushed[0] = RaterScore("productionManager", 100, raterName="مدیر تولید")
        self.assertLess(abs(scoreReview("p-javad", pushed).humanScore - base), 0.6)

    def testCollusionStillMovesTheResultAndIsNotHidden(self) -> None:
        """Honesty about the limit: if most raters collude, they win.

        Four of six marking 95 makes 95 the consensus, and the engine will
        follow it. No statistic can out-vote a majority; this test exists so
        that limitation is written down rather than assumed away.
        """
        colluding = [
            RaterScore("productionManager", 95),
            RaterScore("technicalManager", 95),
            RaterScore("unitHead", 95),
            RaterScore("unitSupervisor", 95),
            RaterScore("qaManager", 74),
            RaterScore("hseUnit", 71),
        ]
        outcome = scoreReview("p-javad", colluding)
        self.assertGreater(outcome.humanScore, 88.0)

    def testTheBreakdownExplainsItself(self) -> None:
        outcome = scoreReview("p-javad", self._raters())
        byRole = {row.raterRole: row for row in outcome.raters}
        # Codes, not prose — the interface decides the wording and the
        # language. The percentage rides along so the UI need not recompute it.
        self.assertTrue(byRole["technicalManager"].reason.startswith(f"{REASON_DAMPED_BELOW}:"))
        self.assertTrue(byRole["productionManager"].reason.startswith(f"{REASON_DAMPED_ABOVE}:"))
        self.assertEqual(byRole["unitHead"].reason, REASON_FULL_WEIGHT)
        # The number after the colon is the percentage of weight removed.
        self.assertEqual(
            int(byRole["technicalManager"].reason.split(":")[1]),
            round((1 - byRole["technicalManager"].damping) * 100),
        )

    def testNoReasonIsEverUntranslatedProse(self) -> None:
        """Every reason must be a known code, so the UI can always render it."""
        outcome = scoreReview("p-javad", self._raters())
        for row in outcome.raters:
            for part in row.reason.split(";"):
                code = part.split(":")[0]
                self.assertIn(code, REASON_CODES, f"unknown reason code «{code}»")

    def testSharesAddUpToOneHundredPercent(self) -> None:
        outcome = scoreReview("p-javad", self._raters())
        total = sum(row.contribution for row in outcome.raters)
        self.assertAlmostEqual(total, 100.0, places=1)

    def testSystemScoreIsBlendedIn(self) -> None:
        metrics = SystemMetrics(
            pmCompliance=92, onTimeCompletion=88, completionRate=95, reworkPenalty=80
        )
        outcome = scoreReview("p-javad", self._raters(), metrics)
        systemScoreValue = outcome.systemScoreValue
        self.assertIsNotNone(systemScoreValue)
        assert systemScoreValue is not None
        self.assertEqual(outcome.systemWeightPercent, 30)
        expected = (systemScoreValue * 30 + outcome.humanScore * 70) / 100.0
        self.assertAlmostEqual(outcome.finalScore, expected, places=1)

    def testAGoodRecordLiftsAManWhoseManagerDislikesHim(self) -> None:
        strong = SystemMetrics(
            pmCompliance=96, onTimeCompletion=94, completionRate=98, reworkPenalty=90
        )
        withRecord = scoreReview("p-javad", self._raters(), strong).finalScore
        withoutRecord = scoreReview("p-javad", self._raters()).finalScore
        self.assertGreater(withRecord, withoutRecord)


class GuardTests(unittest.TestCase):
    def testTooFewRatersDisablesDampingEntirely(self) -> None:
        """With three scores the 'consensus' is one opinion."""
        raters = [
            RaterScore("technicalManager", 20),
            RaterScore("unitHead", 80),
            RaterScore("qaManager", 82),
        ]
        outcome = scoreReview("p-1", raters)
        self.assertFalse(outcome.dampingApplied)
        self.assertEqual(outcome.dampedCount, 0)
        self.assertIn("tooFewRatersToDamp", outcome.notes)

    def testDampingSwitchesOnAtTheThreshold(self) -> None:
        raters = [RaterScore(role, 70) for role in RATER_ROLES[:MIN_RATERS_FOR_DAMPING]]
        self.assertTrue(scoreReview("p-1", raters).dampingApplied)

    def testUnanimityDampensNobody(self) -> None:
        raters = [RaterScore(role, 80) for role in RATER_ROLES[:6]]
        outcome = scoreReview("p-1", raters)
        self.assertEqual(outcome.dampedCount, 0)
        self.assertEqual(outcome.humanScore, 80.0)

    def testATightConsensusDoesNotTurnSmallGapsIntoScandals(self) -> None:
        """Without a spread floor, a two-point difference looks like an outlier."""
        raters = [
            RaterScore("technicalManager", 80),
            RaterScore("unitHead", 80),
            RaterScore("unitSupervisor", 80),
            RaterScore("qaManager", 80),
            RaterScore("hseUnit", 82),
        ]
        outcome = scoreReview("p-1", raters)
        self.assertEqual(outcome.dampedCount, 0)

    def testNoRatersFallsBackToTheRecordAlone(self) -> None:
        metrics = SystemMetrics(pmCompliance=70, onTimeCompletion=70)
        outcome = scoreReview("p-1", [], metrics)
        self.assertEqual(outcome.raterCount, 0)
        self.assertEqual(outcome.systemWeightPercent, 100)
        self.assertEqual(outcome.finalScore, 70.0)
        self.assertIn("noRaters", outcome.notes)

    def testNoRatersAndNoRecordIsZeroNotACrash(self) -> None:
        outcome = scoreReview("p-1", [])
        self.assertEqual(outcome.finalScore, 0.0)

    def testNoSystemMetricsLeavesTheOpinionsCarryingEverything(self) -> None:
        outcome = scoreReview("p-1", [RaterScore("unitHead", 64)])
        self.assertEqual(outcome.systemWeightPercent, 0)
        self.assertEqual(outcome.finalScore, 64.0)
        self.assertIn("noSystemMetrics", outcome.notes)

    def testUnknownRolesAreDroppedBeforeScoring(self) -> None:
        raters = [RaterScore("unitHead", 80), RaterScore("chiefVibes", 10)]
        outcome = scoreReview("p-1", raters)
        self.assertEqual(outcome.raterCount, 1)
        self.assertEqual(outcome.humanScore, 80.0)

    def testOutOfRangeScoresAreClampedNotRejected(self) -> None:
        outcome = scoreReview("p-1", [RaterScore("unitHead", 150)])
        self.assertEqual(outcome.humanScore, 100.0)

    def testSystemWeightIsHeldInsideItsBounds(self) -> None:
        metrics = SystemMetrics(pmCompliance=100)
        high = scoreReview("p-1", [RaterScore("unitHead", 0)], metrics, systemWeightPercent=500)
        self.assertEqual(high.systemWeightPercent, 100)
        self.assertEqual(high.finalScore, 100.0)

    def testAFullSystemWeightIgnoresOpinionEntirely(self) -> None:
        metrics = SystemMetrics(pmCompliance=60)
        outcome = scoreReview(
            "p-1",
            [RaterScore("unitHead", 100), RaterScore("qaManager", 100)],
            metrics,
            systemWeightPercent=100,
        )
        self.assertEqual(outcome.finalScore, 60.0)


class RankingTests(unittest.TestCase):
    def makeOutcome(self, personnelId: str, score: float, name: str = ""):
        return scoreReview(personnelId, [RaterScore("unitHead", score)], personnelName=name)

    def testHighestFirst(self) -> None:
        ranked = rankOutcomes(
            [self.makeOutcome("a", 60), self.makeOutcome("b", 90), self.makeOutcome("c", 75)]
        )
        self.assertEqual([row.personnelId for _, row in ranked], ["b", "c", "a"])
        self.assertEqual([rank for rank, _ in ranked], [1, 2, 3])

    def testTiesShareARank(self) -> None:
        """Inventing a gap the data does not support would be a lie."""
        ranked = rankOutcomes(
            [
                self.makeOutcome("a", 80, "الف"),
                self.makeOutcome("b", 80, "ب"),
                self.makeOutcome("c", 60, "پ"),
            ]
        )
        self.assertEqual([rank for rank, _ in ranked], [1, 1, 3])

    def testEmptyListIsEmpty(self) -> None:
        self.assertEqual(rankOutcomes([]), [])


if __name__ == "__main__":
    unittest.main()
