"""End-to-end tests for the explicit asset hierarchy.

The chain a plant actually reads is سایت ← ساختمان ← خط تولید ← سیستم ←
تجهیز اصلی ← زیرتجهیز ← قطعه. Phase 26 stored both halves but joined
neither and guarded neither: a device could be made its own ancestor, and a
transfer overwrote the only record of where the asset had been.

These tests drive the real HTTP endpoints and then re-read the database,
because the promise that matters is "the previous location survived" and
"the bad write never landed", not "the response had the right shape".
"""

from __future__ import annotations

import uuid
from datetime import date

from django.core.cache import cache
from django.test import TestCase
from rest_framework.test import APIClient

from apps.maintenance.infrastructure.models import (
    AssetMovementModel,
    DeviceHistoryModel,
    DeviceModel,
    MaintenanceLocationModel,
)
from tests.support.phase6Helpers import loginViaApi, platformTenantId, seedPlatform

BASE = "/api/v1/maintenance"


class AssetHierarchyApiTests(TestCase):
    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}

        # سایت ← ساختمان ← خط تولید ← سیستم
        self.site = self._location("SITE-01", "سایت اصلی", "site", None)
        self.building = self._location("BLD-01", "سالن تولید", "building", self.site)
        self.line = self._location("LINE-01", "خط تولید ۱", "line", self.building)
        self.system = self._location("SYS-01", "سیستم خنک‌کاری", "system", self.line)
        self.otherLine = self._location("LINE-02", "خط تولید ۲", "line", self.building)

        # تجهیز اصلی ← زیرتجهیز ← قطعه
        self.machine = self._device("PRESS-01", "پرس ۱", "mainEquipment", self.system)
        self.motor = self._device(
            "MTR-01", "الکتروموتور", "subEquipment", self.system, parent=self.machine
        )
        self.bearing = self._device(
            "BRG-01", "یاتاقان", "component", self.system, parent=self.motor
        )

    # -- helpers -------------------------------------------------------------
    def _location(
        self, code: str, name: str, kind: str, parent: MaintenanceLocationModel | None
    ) -> MaintenanceLocationModel:
        path = f"{parent.path} / {name}" if parent else name
        return MaintenanceLocationModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=name,
            kind=kind,
            parentId=parent.id if parent else None,
            path=path,
            createdAt=self._now(),
        )

    def _device(
        self,
        code: str,
        name: str,
        level: str,
        location: MaintenanceLocationModel,
        parent: DeviceModel | None = None,
    ) -> DeviceModel:
        return DeviceModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=name,
            location=location.name,
            status="operational",
            department="mechanical",
            assetLevel=level,
            locationId=location.id,
            locationPath=location.path,
            parentDeviceId=parent.id if parent else None,
            installedOn=date(2024, 1, 10),
            costCenterCode="CC-100",
            costCenterName="تولید",
            createdAt=self._now(),
        )

    @staticmethod
    def _now():  # noqa: ANN205
        from django.utils import timezone

        return timezone.now()

    def _post(self, url: str, payload: dict):  # noqa: ANN202
        return self.client.post(url, payload, format="json", **self.auth)

    # -- the tree ------------------------------------------------------------
    def testTreeNestsLocationsAndDevicesIntoOneChain(self) -> None:
        response = self.client.get(f"{BASE}/assets/tree", **self.auth)
        self.assertEqual(response.status_code, 200)
        roots = response.json()["data"]["roots"]
        self.assertEqual(len(roots), 1)

        site = roots[0]
        self.assertEqual(site["code"], "SITE-01")
        building = site["children"][0]
        line = building["children"][0]
        system = line["children"][0]
        self.assertEqual(
            [building["kind"], line["kind"], system["kind"]],
            ["building", "line", "system"],
        )

        # Only the main asset hangs off the system; the sub-assembly and the
        # component nest under their parent device, not beside it.
        devices = [node for node in system["children"] if node["nodeType"] == "device"]
        self.assertEqual([node["code"] for node in devices], ["PRESS-01"])
        motor = devices[0]["children"][0]
        self.assertEqual(motor["code"], "MTR-01")
        self.assertEqual(motor["children"][0]["code"], "BRG-01")

    def testTreeRollsUpDeviceCounts(self) -> None:
        response = self.client.get(f"{BASE}/assets/tree", **self.auth)
        site = response.json()["data"]["roots"][0]
        # Three devices sit somewhere beneath the site.
        self.assertEqual(site["deviceCount"], 3)

    def testTreeCanBeScopedToOneSubtree(self) -> None:
        response = self.client.get(f"{BASE}/assets/tree?rootId={self.line.id}", **self.auth)
        roots = response.json()["data"]["roots"]
        self.assertEqual([node["code"] for node in roots], ["LINE-01"])

    def testTreeHidesRetiredAssetsUnlessAsked(self) -> None:
        self._post(
            f"{BASE}/devices/{self.bearing.id}/retirement",
            {"retiredOn": "2026-02-01", "reason": "فرسودگی"},
        )
        hidden = self.client.get(f"{BASE}/assets/tree", **self.auth).json()["data"]
        self.assertEqual(hidden["counts"]["devices"], 2)
        shown = self.client.get(f"{BASE}/assets/tree?includeRetired=true", **self.auth).json()[
            "data"
        ]
        self.assertEqual(shown["counts"]["devices"], 3)

    def testTreeListsDevicesThatHaveNoLocation(self) -> None:
        DeviceModel.objects.create(
            tenantId=self.tenantId,
            code="SPARE-01",
            name="تجهیز بدون محل",
            location="",
            status="operational",
            department="mechanical",
            createdAt=self._now(),
        )
        data = self.client.get(f"{BASE}/assets/tree", **self.auth).json()["data"]
        self.assertEqual([node["code"] for node in data["unplacedDevices"]], ["SPARE-01"])

    # -- ancestry ------------------------------------------------------------
    def testAncestryReturnsTheUpstreamChainRootFirst(self) -> None:
        response = self.client.get(f"{BASE}/devices/{self.bearing.id}/ancestry", **self.auth)
        self.assertEqual(response.status_code, 200)
        data = response.json()["data"]
        self.assertEqual([node["code"] for node in data["deviceChain"]], ["PRESS-01", "MTR-01"])
        self.assertEqual(
            [node["code"] for node in data["locationChain"]],
            ["SITE-01", "BLD-01", "LINE-01", "SYS-01"],
        )

    def testAncestryCarriesTheCostCentre(self) -> None:
        data = self.client.get(f"{BASE}/devices/{self.machine.id}/ancestry", **self.auth).json()[
            "data"
        ]
        self.assertEqual(data["device"]["costCenterCode"], "CC-100")
        self.assertEqual(data["device"]["costCenterName"], "تولید")

    def testAncestryCountsChildrenAndDescendants(self) -> None:
        data = self.client.get(f"{BASE}/devices/{self.machine.id}/ancestry", **self.auth).json()[
            "data"
        ]
        self.assertEqual([node["code"] for node in data["children"]], ["MTR-01"])
        self.assertEqual(data["descendantCount"], 2)

    def testAnUnplacedComponentInheritsItsParentsLocationChain(self) -> None:
        self.bearing.locationId = None
        self.bearing.locationPath = ""
        self.bearing.save(update_fields=["locationId", "locationPath"])
        data = self.client.get(f"{BASE}/devices/{self.bearing.id}/ancestry", **self.auth).json()[
            "data"
        ]
        self.assertEqual(data["locationChain"][-1]["code"], "SYS-01")

    # -- transfers -----------------------------------------------------------
    def testMovingAnAssetKeepsWhereItCameFrom(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {
                "toLocationId": str(self.otherLine.id),
                "movedOn": "2026-03-05",
                "reason": "تغییر چیدمان خط",
                "performedBy": "رضا احمدی",
            },
        )
        self.assertEqual(response.status_code, 201)

        self.machine.refresh_from_db()
        self.assertEqual(self.machine.locationId, self.otherLine.id)
        self.assertEqual(self.machine.locationPath, self.otherLine.path)

        movement = AssetMovementModel.objects.get(deviceId=self.machine.id)
        self.assertEqual(movement.fromLocationId, self.system.id)
        self.assertEqual(movement.fromLocationPath, self.system.path)
        self.assertEqual(movement.toLocationId, self.otherLine.id)
        self.assertEqual(movement.movedOn, date(2026, 3, 5))
        self.assertEqual(movement.reason, "تغییر چیدمان خط")

    def testTheLedgerAnswersWhereItWasBefore(self) -> None:
        self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(self.otherLine.id), "movedOn": "2026-03-05"},
        )
        data = self.client.get(f"{BASE}/devices/{self.machine.id}/ancestry", **self.auth).json()[
            "data"
        ]
        self.assertEqual(data["previousLocation"]["locationPath"], self.system.path)

    def testEveryTransferIsKeptNotOverwritten(self) -> None:
        self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(self.otherLine.id), "movedOn": "2026-03-05"},
        )
        self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(self.line.id), "movedOn": "2026-04-05"},
        )
        rows = self.client.get(f"{BASE}/devices/{self.machine.id}/movements", **self.auth).json()[
            "data"
        ]
        self.assertEqual(len(rows), 2)
        # Newest first, so the top row is the move that is currently in force.
        self.assertEqual(rows[0]["movedOn"], "2026-04-05")
        self.assertEqual(rows[0]["fromLocationPath"], self.otherLine.path)
        self.assertEqual(rows[1]["fromLocationPath"], self.system.path)

    def testATransferAppearsOnTheDeviceTimeline(self) -> None:
        self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(self.otherLine.id), "reason": "بازچینش"},
        )
        entry = DeviceHistoryModel.objects.get(deviceId=self.machine.id, action="relocated")
        self.assertIn(self.otherLine.path, entry.note)

    def testInstallationDateIsUpdatedOnlyWhenAsked(self) -> None:
        self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(self.otherLine.id), "movedOn": "2026-03-05"},
        )
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.installedOn, date(2024, 1, 10))

        self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {
                "toLocationId": str(self.line.id),
                "movedOn": "2026-04-05",
                "updateInstalledOn": True,
            },
        )
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.installedOn, date(2026, 4, 5))

    def testATransferThatChangesNothingIsRefused(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(self.system.id)},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(AssetMovementModel.objects.count(), 0)

    def testMovingUnderOwnDescendantIsRefusedByTheLevelLadder(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toParentDeviceId": str(self.bearing.id)},
        )
        self.assertEqual(response.status_code, 422)
        self.machine.refresh_from_db()
        self.assertIsNone(self.machine.parentDeviceId)
        self.assertEqual(AssetMovementModel.objects.count(), 0)

    def testMovingUnderOwnDescendantIsRefusedWhenLevelsDoNotSayNo(self) -> None:
        """The cycle guard, isolated.

        Between catalogued levels a loop is already impossible — the ladder
        refuses it first. But ``assetLevel`` is an open vocabulary, so a plant
        that files its assets as «دستگاه» gets no ladder at all, and the cycle
        check is then the only thing standing between it and a self-referencing
        chain that hangs every ancestry walk.
        """
        top = self._device("GEN-01", "ژنراتور", "دستگاه", self.system)
        under = self._device("GEN-02", "زیرمجموعه", "دستگاه", self.system, parent=top)

        response = self._post(
            f"{BASE}/devices/{top.id}/movements",
            {"toParentDeviceId": str(under.id)},
        )
        self.assertEqual(response.status_code, 422)
        top.refresh_from_db()
        self.assertIsNone(top.parentDeviceId)
        self.assertEqual(AssetMovementModel.objects.count(), 0)

    def testAnAssetCannotBeMovedUnderItself(self) -> None:
        loner = self._device("GEN-03", "ژنراتور تک", "دستگاه", self.system)
        response = self._post(
            f"{BASE}/devices/{loner.id}/movements",
            {"toParentDeviceId": str(loner.id)},
        )
        self.assertEqual(response.status_code, 422)
        loner.refresh_from_db()
        self.assertIsNone(loner.parentDeviceId)

    def testAComponentMayNotOwnASubAssembly(self) -> None:
        """The level ladder, isolated from the cycle guard.

        The target component sits in a different branch, so no loop is
        involved: the write is refused purely because a قطعه cannot own a
        زیرتجهیز.
        """
        otherMachine = self._device("PRESS-03", "پرس ۳", "mainEquipment", self.otherLine)
        strayComponent = self._device(
            "BRG-09", "یاتاقان جدا", "component", self.otherLine, parent=otherMachine
        )
        response = self._post(
            f"{BASE}/devices/{self.motor.id}/movements",
            {"toParentDeviceId": str(strayComponent.id)},
        )
        self.assertEqual(response.status_code, 422)
        self.motor.refresh_from_db()
        self.assertEqual(self.motor.parentDeviceId, self.machine.id)
        self.assertEqual(AssetMovementModel.objects.count(), 0)

    def testAnUnclassifiedAssetIsDemotedRatherThanRefused(self) -> None:
        """`mainEquipment` is the default every legacy row carries.

        Treating it as a firm claim would have refused every parent/child
        link in the existing plant, so it is read as "not classified yet" and
        derived from the new parent instead.
        """
        otherMachine = self._device("PRESS-04", "پرس ۴", "mainEquipment", self.otherLine)
        response = self._post(
            f"{BASE}/devices/{otherMachine.id}/movements",
            {"toParentDeviceId": str(self.machine.id)},
        )
        self.assertEqual(response.status_code, 201)
        otherMachine.refresh_from_db()
        self.assertEqual(otherMachine.parentDeviceId, self.machine.id)
        self.assertEqual(otherMachine.assetLevel, "subEquipment")

    def testDerivationStepsDownOnlyOneRung(self) -> None:
        stray = self._device("CMP-07", "قطعهٔ آزاد", "mainEquipment", self.otherLine)
        self._post(
            f"{BASE}/devices/{stray.id}/movements",
            {"toParentDeviceId": str(self.motor.id)},
        )
        stray.refresh_from_db()
        # Under a زیرتجهیز, an unclassified asset becomes a قطعه.
        self.assertEqual(stray.assetLevel, "component")

    def testAStatedLevelIsNeverSilentlyRewritten(self) -> None:
        stray = self._device("MTR-08", "الکتروموتور", "subEquipment", self.otherLine)
        self._post(
            f"{BASE}/devices/{stray.id}/movements",
            {"toParentDeviceId": str(self.machine.id)},
        )
        stray.refresh_from_db()
        self.assertEqual(stray.assetLevel, "subEquipment")

    def testALegalDeepeningIsAccepted(self) -> None:
        # The mirror image of the two tests above: one rung down, so it lands.
        stray = self._device("MTR-09", "الکتروموتور یدکی", "subEquipment", self.otherLine)
        response = self._post(
            f"{BASE}/devices/{stray.id}/movements",
            {"toParentDeviceId": str(self.machine.id)},
        )
        self.assertEqual(response.status_code, 201)
        stray.refresh_from_db()
        self.assertEqual(stray.parentDeviceId, self.machine.id)

    def testReParentingASubAssemblyIsRecorded(self) -> None:
        other = self._device("PRESS-02", "پرس ۲", "mainEquipment", self.otherLine)
        response = self._post(
            f"{BASE}/devices/{self.motor.id}/movements",
            {"toParentDeviceId": str(other.id), "reason": "نصب روی پرس ۲"},
        )
        self.assertEqual(response.status_code, 201)
        self.motor.refresh_from_db()
        self.assertEqual(self.motor.parentDeviceId, other.id)
        movement = AssetMovementModel.objects.get(deviceId=self.motor.id)
        self.assertEqual(movement.fromParentDeviceId, self.machine.id)
        self.assertEqual(movement.toParentDeviceId, other.id)

    def testAnUnknownLocationIsRejected(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.machine.id}/movements",
            {"toLocationId": str(uuid.uuid4())},
        )
        self.assertEqual(response.status_code, 404)

    # -- retirement ----------------------------------------------------------
    def testRetiringRecordsTheDateAndReason(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.bearing.id}/retirement",
            {"retiredOn": "2026-05-01", "reason": "فرسودگی کامل"},
        )
        self.assertEqual(response.status_code, 200)
        self.bearing.refresh_from_db()
        self.assertEqual(self.bearing.status, "retired")
        self.assertEqual(self.bearing.retiredOn, date(2026, 5, 1))
        self.assertEqual(self.bearing.retirementReason, "فرسودگی کامل")

    def testRetiringIsRefusedWhileLiveChildrenHangOffIt(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.machine.id}/retirement", {"retiredOn": "2026-05-01"}
        )
        self.assertEqual(response.status_code, 422)
        self.machine.refresh_from_db()
        self.assertEqual(self.machine.status, "operational")

    def testTheWholeSubtreeCanBeRetiredTogether(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.machine.id}/retirement",
            {"retiredOn": "2026-05-01", "retireChildren": True},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["data"]["retiredCount"], 3)
        for device in (self.machine, self.motor, self.bearing):
            device.refresh_from_db()
            self.assertEqual(device.status, "retired")

    def testRetirementCannotPredateInstallation(self) -> None:
        response = self._post(
            f"{BASE}/devices/{self.bearing.id}/retirement", {"retiredOn": "2020-01-01"}
        )
        self.assertEqual(response.status_code, 422)
        self.bearing.refresh_from_db()
        self.assertEqual(self.bearing.status, "operational")

    def testARetiredAssetMayNotBeMoved(self) -> None:
        self._post(f"{BASE}/devices/{self.bearing.id}/retirement", {})
        response = self._post(
            f"{BASE}/devices/{self.bearing.id}/movements",
            {"toLocationId": str(self.otherLine.id)},
        )
        self.assertEqual(response.status_code, 422)
        self.assertEqual(AssetMovementModel.objects.count(), 0)

    def testRetiringTwiceIsRefused(self) -> None:
        self._post(f"{BASE}/devices/{self.bearing.id}/retirement", {})
        response = self._post(f"{BASE}/devices/{self.bearing.id}/retirement", {})
        self.assertEqual(response.status_code, 422)

    def testReinstatingClearsTheRetirementFacts(self) -> None:
        self._post(
            f"{BASE}/devices/{self.bearing.id}/retirement",
            {"retiredOn": "2026-05-01", "reason": "فرسودگی"},
        )
        response = self.client.delete(
            f"{BASE}/devices/{self.bearing.id}/retirement",
            {"status": "underMaintenance"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 200)
        self.bearing.refresh_from_db()
        self.assertEqual(self.bearing.status, "underMaintenance")
        self.assertIsNone(self.bearing.retiredOn)
        self.assertEqual(self.bearing.retirementReason, "")

    def testReinstatingRefusesAnInvalidStatus(self) -> None:
        self._post(f"{BASE}/devices/{self.bearing.id}/retirement", {})
        response = self.client.delete(
            f"{BASE}/devices/{self.bearing.id}/retirement",
            {"status": "retired"},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)


class AssetHierarchyGuardTests(TestCase):
    """The nameplate form is the other door into the hierarchy; it needs the
    same guards as the transfer endpoint."""

    def setUp(self) -> None:
        cache.clear()
        seedPlatform()
        self.tenantId = platformTenantId()
        self.client = APIClient()
        tokens = loginViaApi(self.client)
        self.auth = {"HTTP_AUTHORIZATION": f"Bearer {tokens['accessToken']}"}
        from django.utils import timezone

        self.parent = DeviceModel.objects.create(
            tenantId=self.tenantId,
            code="LINE-A",
            name="خط A",
            location="سالن",
            status="operational",
            department="mechanical",
            assetLevel="mainEquipment",
            createdAt=timezone.now(),
        )
        self.child = DeviceModel.objects.create(
            tenantId=self.tenantId,
            code="PUMP-A",
            name="پمپ A",
            location="سالن",
            status="operational",
            department="mechanical",
            assetLevel="subEquipment",
            parentDeviceId=self.parent.id,
            createdAt=timezone.now(),
        )
        # `assetLevel` is an open vocabulary; these rows carry a plant's own
        # word, so the level ladder abstains and the cycle guard stands alone.
        self.loose = self._loose("FREE-01", "دستگاه آزاد", None)
        self.looseParent = self._loose("FREE-02", "دستگاه بالا", None)
        self.looseChild = self._loose("FREE-03", "دستگاه پایین", self.looseParent)

    def _loose(self, code: str, name: str, parent):  # noqa: ANN001, ANN202
        from django.utils import timezone

        return DeviceModel.objects.create(
            tenantId=self.tenantId,
            code=code,
            name=name,
            location="سالن",
            status="operational",
            department="mechanical",
            assetLevel="دستگاه",
            parentDeviceId=parent.id if parent else None,
            createdAt=timezone.now(),
        )

    def _patch(self, deviceId, payload: dict):  # noqa: ANN001, ANN202
        return self.client.patch(
            f"{BASE}/devices/{deviceId}/nameplate", payload, format="json", **self.auth
        )

    def testADeviceCannotBeMadeItsOwnParentThroughTheNameplate(self) -> None:
        # Previously the repository quietly swallowed this write, leaving the
        # user staring at a form that claimed to have saved something it
        # had thrown away. Now it is refused out loud.
        response = self._patch(self.loose.id, {"parentDeviceId": str(self.loose.id)})
        self.assertEqual(response.status_code, 422)
        self.loose.refresh_from_db()
        self.assertIsNone(self.loose.parentDeviceId)

    def testATwoStepLoopIsRefusedThroughTheNameplate(self) -> None:
        """Isolates the cycle guard from the level ladder.

        Both devices carry a plant-specific level, so the ladder abstains and
        only the cycle check can refuse the write. Before Phase 27 nothing
        did: A→B→A landed, and every ancestry walk after it ran until
        something timed out.
        """
        response = self._patch(self.looseParent.id, {"parentDeviceId": str(self.looseChild.id)})
        self.assertEqual(response.status_code, 422)
        self.looseParent.refresh_from_db()
        self.assertIsNone(self.looseParent.parentDeviceId)

    def testTheNameplateDerivesAnUnstatedLevelFromTheNewParent(self) -> None:
        """The pre-Phase-27 flow — "set this device's parent" — still works,
        and now classifies the child as a side effect."""
        from django.utils import timezone

        unrelated = DeviceModel.objects.create(
            tenantId=self.tenantId,
            code="LINE-B",
            name="خط B",
            location="سالن",
            status="operational",
            department="mechanical",
            assetLevel="mainEquipment",
            createdAt=timezone.now(),
        )
        response = self._patch(unrelated.id, {"parentDeviceId": str(self.parent.id)})
        self.assertEqual(response.status_code, 200)
        unrelated.refresh_from_db()
        self.assertEqual(unrelated.parentDeviceId, self.parent.id)
        self.assertEqual(unrelated.assetLevel, "subEquipment")

    def testALevelChangeIsValidatedAgainstTheNewParent(self) -> None:
        # Promoting a sub-assembly to a main asset while it still hangs off a
        # main asset would put two equal rungs on top of each other.
        response = self._patch(
            self.child.id,
            {"assetLevel": "mainEquipment", "parentDeviceId": str(self.parent.id)},
        )
        self.assertEqual(response.status_code, 422)
        self.child.refresh_from_db()
        self.assertEqual(self.child.assetLevel, "subEquipment")

    def testTheCostCentreCanBeWrittenThroughTheNameplate(self) -> None:
        response = self._patch(
            self.child.id, {"costCenterCode": "CC-200", "costCenterName": "تأسیسات"}
        )
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.costCenterCode, "CC-200")
        self.assertEqual(self.child.costCenterName, "تأسیسات")

    def testTheAssetLevelCanBeWrittenThroughTheNameplate(self) -> None:
        response = self._patch(self.child.id, {"assetLevel": "component"})
        self.assertEqual(response.status_code, 200)
        self.child.refresh_from_db()
        self.assertEqual(self.child.assetLevel, "component")

    def testAnInvertedLocationNestingIsRefused(self) -> None:
        from django.utils import timezone

        line = MaintenanceLocationModel.objects.create(
            tenantId=self.tenantId,
            code="L-1",
            name="خط ۱",
            kind="line",
            path="خط ۱",
            createdAt=timezone.now(),
        )
        response = self.client.post(
            f"{BASE}/locations",
            {"code": "S-1", "name": "سایت", "kind": "site", "parentId": str(line.id)},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 422)
        self.assertFalse(MaintenanceLocationModel.objects.filter(code="S-1").exists())

    def testAPlantsOwnWordIsStillAccepted(self) -> None:
        from django.utils import timezone

        site = MaintenanceLocationModel.objects.create(
            tenantId=self.tenantId,
            code="S-2",
            name="سایت دو",
            kind="site",
            path="سایت دو",
            createdAt=timezone.now(),
        )
        response = self.client.post(
            f"{BASE}/locations",
            {"code": "H-1", "name": "سوله ۳", "kind": "سوله", "parentId": str(site.id)},
            format="json",
            **self.auth,
        )
        self.assertEqual(response.status_code, 201)
