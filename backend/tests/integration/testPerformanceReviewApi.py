"""End-to-end tests for employee performance review — Phase 29.

The engine's arithmetic is proved separately in
``apps/maintenance/tests/testPerformanceReviewRules.py``. What these tests
prove is the part a unit test cannot: that the marks actually survive the
round trip through HTTP and the database, that the measured half is really
built from work orders and PM executions rather than from a fixture, and that
the bias correction still holds when the numbers arrive the way a real
manager would send them.

They drive real HTTP and then re-read the database, because the promise that
matters is "the result was stored and can be defended later", not "the
response had the right shape".
"""

from __future__ import annotations

import json
import uuid
from datetime import date, datetime, timedelta

from django.core.cache import cache
from django.test import TestCase
from django.utils import timezone as djtz
from django.utils.timezone import make_aware
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import (
    DeviceModel,
    MaintenancePersonnelModel,
    PerformanceRaterScoreModel,
    PerformanceResultModel,
    PerformanceReviewCycleModel,
    PmExecutionModel,
    WorkOrderModel,
)
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/maintenance"

PERIOD_FROM = date(2026, 1, 1)
PERIOD_TO = date(2026, 3, 31)


class PerformanceReviewApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

        self.javad = self._person("P-001", "جواد امیرشاهی")
        self.mina = self._person("P-002", "مینا رستمی")
        self.device = self._device("DEV-1", "پمپ ۱")

    # -- helpers ------------------------------------------------------------------
    def _person(self, code: str, name: str) -> uuid.UUID:
        row = MaintenancePersonnelModel.objects.create(
            tenantId=self.tenantId,
            personnelCode=code,
            fullName=name,
            specialty="مکانیک",
            unit="نگهداری",
            createdAt=djtz.now(),
        )
        return row.id

    def _device(self, code: str, name: str) -> uuid.UUID:
        row = DeviceModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=name,
            createdAt=djtz.now(),
        )
        return row.id

    def _cycle(self, code: str = "REV-1", systemWeight: int = 30) -> str:
        response = self.client.post(
            f"{BASE}/performance-reviews/cycles",
            {
                "code": code,
                "name": "ارزیابی بهار",
                "fromDate": PERIOD_FROM.isoformat(),
                "toDate": PERIOD_TO.isoformat(),
                "status": "open",
                "systemWeightPercent": systemWeight,
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        return response.json()["data"]["id"]

    def _submit(self, cycleId: str, personnelId: uuid.UUID, role: str, score: float):
        return self.client.post(
            f"{BASE}/performance-reviews/scores",
            {
                "cycleId": cycleId,
                "personnelId": str(personnelId),
                "raterRole": role,
                "score": score,
                "raterName": role,
            },
            format="json",
            **self.auth,
        )

    def _workOrder(self, name: str, status: str, repeat: bool = False) -> None:
        row = WorkOrderModel.objects.create(
            tenantId=self.tenantId,
            deviceId=self.device,
            title="تعمیر",
            status=status,
            assignedToName=name,
            repeatFailure=repeat,
        )
        # createdAt is auto_now_add, so it has to be forced back into the
        # review period after the row exists.
        WorkOrderModel.objects.filter(id=row.id).update(
            createdAt=make_aware(
                datetime.combine(PERIOD_FROM + timedelta(days=5), datetime.min.time())
            )
        )

    def _pmExecution(self, name: str, onTime: bool) -> None:
        PmExecutionModel.objects.create(
            tenantId=self.tenantId,
            planId=uuid.uuid4(),
            deviceId=self.device,
            performedOn=PERIOD_FROM + timedelta(days=10),
            onTime=onTime,
            performedByName=name,
            createdAt=djtz.now(),
        )

    # -- cycles -------------------------------------------------------------------
    def testCycleIsCreatedAndListed(self) -> None:
        cycleId = self._cycle()
        response = self.client.get(f"{BASE}/performance-reviews/cycles", **self.auth)
        self.assertEqual(response.status_code, 200)
        payload = response.json()["data"]
        self.assertEqual(len(payload["cycles"]), 1)
        self.assertEqual(payload["cycles"][0]["id"], cycleId)
        # The roster of who may rate ships with the list so the UI never
        # hardcodes it.
        self.assertIn("technicalManager", payload["raterRoles"])
        self.assertIn("productionManager", payload["defaultRoleWeights"])

    def testCycleEndingBeforeItStartsIsRejected(self) -> None:
        response = self.client.post(
            f"{BASE}/performance-reviews/cycles",
            {
                "code": "BAD",
                "name": "بد",
                "fromDate": "2026-03-31",
                "toDate": "2026-01-01",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422, response.content)

    def testAJalaliYearInAGregorianFieldIsRefused(self) -> None:
        """«1405-01-01» is a valid Gregorian date, which is what makes it dangerous.

        Nothing rejects it on the way in; it only reveals itself when the
        date is rendered back and reads «۱۱ دی ۷۸۳». Catching it at entry is
        the difference between an error message and a baffling display.
        """
        response = self.client.post(
            f"{BASE}/performance-reviews/cycles",
            {
                "code": "REV-JALALI",
                "name": "دوره",
                "fromDate": "1405-01-01",
                "toDate": "1405-06-31",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422, response.content)
        self.assertEqual(
            PerformanceReviewCycleModel.objects.filter(code="REV-JALALI").count(), 0
        )

    def testTheGregorianEquivalentOfThatPeriodIsAccepted(self) -> None:
        """1405/1/1 .. 1405/6/31 really is 2026-03-21 .. 2026-09-22."""
        response = self.client.post(
            f"{BASE}/performance-reviews/cycles",
            {
                "code": "REV-OK",
                "name": "نیمهٔ اول ۱۴۰۵",
                "fromDate": "2026-03-21",
                "toDate": "2026-09-22",
            },
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)
        self.assertEqual(response.json()["data"]["fromDate"], "2026-03-21")

    def testDeletingACycleTakesItsScoresWithIt(self) -> None:
        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 70)
        response = self.client.delete(
            f"{BASE}/performance-reviews/cycles/{cycleId}", **self.auth
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(
            PerformanceRaterScoreModel.objects.filter(
                cycleId=cycleId, deletedAt__isnull=True
            ).count(),
            0,
        )

    def testAClosedCycleCannotBeDeleted(self) -> None:
        """Erasing a published appraisal round is not an undo button.

        Deleting a cycle takes every mark and every stored justification with
        it. Once people have been told their scores, that leaves an appraisal
        that was acted on but can no longer be explained.
        """
        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 70)
        PerformanceReviewCycleModel.objects.filter(id=cycleId).update(status="closed")

        response = self.client.delete(
            f"{BASE}/performance-reviews/cycles/{cycleId}", **self.auth
        )
        self.assertEqual(response.status_code, 422, response.content)
        # Nothing was taken away on the way to refusing.
        self.assertEqual(
            PerformanceRaterScoreModel.objects.filter(
                cycleId=cycleId, deletedAt__isnull=True
            ).count(),
            1,
        )
        self.assertTrue(
            PerformanceReviewCycleModel.objects.filter(
                id=cycleId, deletedAt__isnull=True
            ).exists()
        )

    def testReopeningLetsADeleteThroughAgain(self) -> None:
        cycleId = self._cycle()
        PerformanceReviewCycleModel.objects.filter(id=cycleId).update(status="closed")
        self.assertEqual(
            self.client.delete(
                f"{BASE}/performance-reviews/cycles/{cycleId}", **self.auth
            ).status_code,
            422,
        )
        PerformanceReviewCycleModel.objects.filter(id=cycleId).update(status="open")
        self.assertEqual(
            self.client.delete(
                f"{BASE}/performance-reviews/cycles/{cycleId}", **self.auth
            ).status_code,
            200,
        )

    # -- marks --------------------------------------------------------------------
    def testScoreIsStoredAndReadBack(self) -> None:
        cycleId = self._cycle()
        response = self._submit(cycleId, self.javad, "unitHead", 72)
        self.assertEqual(response.status_code, 200, response.content)

        listed = self.client.get(
            f"{BASE}/performance-reviews/scores?cycleId={cycleId}", **self.auth
        ).json()["data"]
        self.assertEqual(len(listed["scores"]), 1)
        self.assertEqual(listed["scores"][0]["score"], 72.0)
        # The employee's name is resolved for display, not stored twice.
        self.assertEqual(listed["scores"][0]["personnelName"], "جواد امیرشاهی")

    def testTheSameRoleCannotVoteTwice(self) -> None:
        """A second submission revises the first rather than adding a vote."""
        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 60)
        self._submit(cycleId, self.javad, "unitHead", 80)
        rows = PerformanceRaterScoreModel.objects.filter(
            cycleId=cycleId, personnelId=self.javad, deletedAt__isnull=True
        )
        self.assertEqual(rows.count(), 1)
        self.assertEqual(float(rows.first().score), 80.0)

    def testScoreOutsideTheScaleIsRejected(self) -> None:
        cycleId = self._cycle()
        self.assertEqual(self._submit(cycleId, self.javad, "unitHead", 140).status_code, 422)
        self.assertEqual(self._submit(cycleId, self.javad, "unitHead", -5).status_code, 422)

    def testUnknownRoleIsRejectedRatherThanGivenZeroWeight(self) -> None:
        """A typo must be refused at the door, not silently ignored later."""
        cycleId = self._cycle()
        response = self._submit(cycleId, self.javad, "chiefOfVibes", 90)
        self.assertEqual(response.status_code, 422, response.content)

    def testAClosedCycleRefusesNewMarks(self) -> None:
        cycleId = self._cycle()
        PerformanceReviewCycleModel.objects.filter(id=cycleId).update(status="closed")
        response = self._submit(cycleId, self.javad, "unitHead", 70)
        self.assertEqual(response.status_code, 422, response.content)

    # -- the measured half --------------------------------------------------------
    def testSystemScoreIsBuiltFromRealWorkOrdersAndPmExecutions(self) -> None:
        for _ in range(8):
            self._workOrder("جواد امیرشاهی", "completed")
        for _ in range(2):
            self._workOrder("جواد امیرشاهی", "inProgress")
        for _ in range(9):
            self._pmExecution("جواد امیرشاهی", onTime=True)
        self._pmExecution("جواد امیرشاهی", onTime=False)

        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 70)
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )

        result = PerformanceResultModel.objects.get(
            cycleId=cycleId, personnelId=self.javad
        )
        # 8/10 completed, 9/10 PM on time, no repeat failures.
        self.assertIsNotNone(result.systemScore)
        self.assertGreater(float(result.systemScore), 80.0)
        breakdown = json.loads(result.breakdown)
        self.assertEqual(breakdown["systemMetrics"]["completionRate"], 80.0)
        self.assertEqual(breakdown["systemMetrics"]["pmCompliance"], 90.0)

    def testRepeatFailuresPushTheMeasuredScoreDown(self) -> None:
        for index in range(10):
            self._workOrder("مینا رستمی", "completed", repeat=index < 5)
        cycleId = self._cycle()
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        result = PerformanceResultModel.objects.get(
            cycleId=cycleId, personnelId=self.mina
        )
        breakdown = json.loads(result.breakdown)
        self.assertEqual(breakdown["systemMetrics"]["reworkPenalty"], 50.0)

    def testWorkOutsideTheCycleWindowIsNotCounted(self) -> None:
        """A cycle is a period. Work from another quarter is another quarter's."""
        self._pmExecution("جواد امیرشاهی", onTime=True)
        PmExecutionModel.objects.filter(tenantId=self.tenantId).update(
            performedOn=PERIOD_TO + timedelta(days=60)
        )
        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 70)
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        result = PerformanceResultModel.objects.get(
            cycleId=cycleId, personnelId=self.javad
        )
        # No measurable work in the window: opinion carries the whole mark
        # rather than the person being scored zero for work they did do.
        self.assertIsNone(result.systemScore)
        self.assertEqual(float(result.finalScore), float(result.humanScore))

    # -- the reason the weighting exists ------------------------------------------
    def testFavouritismAndGrudgeAreBothDampedEndToEnd(self) -> None:
        """جواد's case, driven through HTTP exactly as managers would submit it.

        مدیر تولید inflates out of favouritism, مدیر فنی deflates out of a
        grudge, and four honest raters sit together near 71. The final mark
        must land near the honest cluster, and the system must be able to say
        in writing which two marks it discounted.
        """
        cycleId = self._cycle(systemWeight=0)
        self._submit(cycleId, self.javad, "productionManager", 95)
        self._submit(cycleId, self.javad, "technicalManager", 40)
        self._submit(cycleId, self.javad, "unitHead", 72)
        self._submit(cycleId, self.javad, "unitSupervisor", 70)
        self._submit(cycleId, self.javad, "qaManager", 74)
        self._submit(cycleId, self.javad, "hseUnit", 71)

        response = self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200, response.content)

        result = PerformanceResultModel.objects.get(
            cycleId=cycleId, personnelId=self.javad
        )
        self.assertEqual(result.raterCount, 6)
        self.assertEqual(result.dampedCount, 2)
        # Near the honest cluster, not near the midpoint of the two extremes.
        self.assertGreater(float(result.finalScore), 68.0)
        self.assertLess(float(result.finalScore), 76.0)

        breakdown = json.loads(result.breakdown)
        damped = {
            row["raterRole"] for row in breakdown["raters"] if row["damped"]
        }
        self.assertEqual(damped, {"productionManager", "technicalManager"})
        # Every discounted rater carries a written reason — an employee asking
        # "why?" has to get an answer.
        for row in breakdown["raters"]:
            self.assertTrue(row["reason"])

    def testADissenterIsNeverSilencedCompletely(self) -> None:
        cycleId = self._cycle(systemWeight=0)
        self._submit(cycleId, self.javad, "productionManager", 95)
        self._submit(cycleId, self.javad, "technicalManager", 40)
        self._submit(cycleId, self.javad, "unitHead", 72)
        self._submit(cycleId, self.javad, "unitSupervisor", 70)
        self._submit(cycleId, self.javad, "qaManager", 74)
        self._submit(cycleId, self.javad, "hseUnit", 71)
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        breakdown = json.loads(
            PerformanceResultModel.objects.get(
                cycleId=cycleId, personnelId=self.javad
            ).breakdown
        )
        for row in breakdown["raters"]:
            self.assertGreater(
                row["contribution"], 0.0, f"{row['raterRole']} was silenced entirely"
            )

    # -- the comparison read model ------------------------------------------------
    def testResultsAreRankedForComparison(self) -> None:
        cycleId = self._cycle(systemWeight=0)
        self._submit(cycleId, self.javad, "unitHead", 85)
        self._submit(cycleId, self.mina, "unitHead", 60)
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        payload = self.client.get(
            f"{BASE}/performance-reviews/results?cycleId={cycleId}", **self.auth
        ).json()["data"]

        self.assertEqual(payload["summary"]["count"], 2)
        self.assertEqual(payload["results"][0]["personnelName"], "جواد امیرشاهی")
        self.assertEqual(payload["results"][0]["rank"], 1)
        self.assertEqual(payload["results"][1]["rank"], 2)
        self.assertEqual(payload["summary"]["highestScore"], 85.0)
        self.assertEqual(payload["summary"]["averageScore"], 72.5)

    def testAnUnratedPersonDoesNotOutrankAReviewedOne(self) -> None:
        """Nobody gets to win the comparison by never being reviewed.

        The measured half alone will award a perfect 100 to a technician who
        closed the one job they were given. Ranking that against somebody six
        managers scrutinised would reward escaping scrutiny, so the unrated
        are reported separately instead of topping the chart.
        """
        # مینا has a flawless but tiny work record and no marks at all.
        self._workOrder("مینا رستمی", "completed")
        # جواد is genuinely reviewed, and well regarded.
        cycleId = self._cycle(systemWeight=30)
        for role, score in [
            ("unitHead", 84),
            ("technicalManager", 82),
            ("qaManager", 83),
            ("unitSupervisor", 85),
        ]:
            self._submit(cycleId, self.javad, role, score)

        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        payload = self.client.get(
            f"{BASE}/performance-reviews/results?cycleId={cycleId}", **self.auth
        ).json()["data"]

        names = [row["personnelName"] for row in payload["results"]]
        self.assertEqual(names, ["جواد امیرشاهی"])
        self.assertEqual(payload["results"][0]["rank"], 1)

        # She is not hidden — just not ranked, so the gap stays chaseable.
        unrated = [row["personnelName"] for row in payload["unrated"]]
        self.assertIn("مینا رستمی", unrated)
        self.assertEqual(payload["unrated"][0]["rank"], 0)
        self.assertFalse(payload["unrated"][0]["comparable"])
        self.assertEqual(payload["summary"]["unratedCount"], 1)
        # And the averages describe the people who were actually reviewed.
        self.assertEqual(payload["summary"]["count"], 1)

    def testTheUnratedStillCarryTheirMeasuredScore(self) -> None:
        for _ in range(4):
            self._workOrder("مینا رستمی", "completed")
        cycleId = self._cycle()
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        payload = self.client.get(
            f"{BASE}/performance-reviews/results?cycleId={cycleId}", **self.auth
        ).json()["data"]
        mina = next(
            row for row in payload["unrated"] if row["personnelName"] == "مینا رستمی"
        )
        self.assertIsNotNone(mina["systemScore"])
        self.assertEqual(mina["raterCount"], 0)

    def testEqualScoresShareARank(self) -> None:
        cycleId = self._cycle(systemWeight=0)
        self._submit(cycleId, self.javad, "unitHead", 75)
        self._submit(cycleId, self.mina, "unitHead", 75)
        self.client.post(
            f"{BASE}/performance-reviews/compute",
            {"cycleId": cycleId},
            format="json",
            **self.auth,
        )
        payload = self.client.get(
            f"{BASE}/performance-reviews/results?cycleId={cycleId}", **self.auth
        ).json()["data"]
        self.assertEqual([row["rank"] for row in payload["results"]], [1, 1])

    def testRecomputingReplacesRatherThanDuplicates(self) -> None:
        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 70)
        for _ in range(2):
            self.client.post(
                f"{BASE}/performance-reviews/compute",
                {"cycleId": cycleId},
                format="json",
                **self.auth,
            )
        self.assertEqual(
            PerformanceResultModel.objects.filter(
                cycleId=cycleId, personnelId=self.javad, deletedAt__isnull=True
            ).count(),
            1,
        )

    def testAnotherTenantsMarksAreInvisible(self) -> None:
        cycleId = self._cycle()
        self._submit(cycleId, self.javad, "unitHead", 70)
        PerformanceRaterScoreModel.objects.filter(cycleId=cycleId).update(
            tenantId=uuid.uuid4()
        )
        listed = self.client.get(
            f"{BASE}/performance-reviews/scores?cycleId={cycleId}", **self.auth
        ).json()["data"]
        self.assertEqual(listed["scores"], [])

    def testEndpointsRefuseAnonymousCallers(self) -> None:
        anonymous = APIClient()
        self.assertEqual(
            anonymous.get(f"{BASE}/performance-reviews/cycles").status_code, 401
        )
        self.assertEqual(
            anonymous.post(
                f"{BASE}/performance-reviews/compute", {}, format="json"
            ).status_code,
            401,
        )
