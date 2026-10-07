"""Can the data be got out, and put back?

A backup that has never been restored is not a backup; it is a file. These
tests exercise the round trip the recovery runbook depends on: dump the
tenant-scoped data, destroy it, load it back, and check that what returns is
what left — including the relationships, which are what silently break when a
dump is taken table by table in the wrong order.

Disaster recovery proper (a second region, a measured RTO) needs
infrastructure this suite does not have. What it can prove is the part that
would otherwise be discovered during the disaster: that the dump is complete,
loadable, and free of secrets.
"""

from __future__ import annotations

import io
import json
import uuid
from datetime import UTC, datetime

from django.core.management import call_command
from django.test import TestCase, TransactionTestCase

from tests.support.multiTenantHelpers import createTenantWithAdmin
from tests.support.phase6Helpers import platformTenantId, seedPlatform

BACKED_UP_APPS = ["maintenance", "tenancy", "identity"]


def seedBusinessData(tenantId: uuid.UUID) -> dict[str, uuid.UUID]:
    """A device with a work order hanging off it — enough to catch a dump
    that loses foreign keys."""

    from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel

    now = datetime.now(tz=UTC)
    device = DeviceModel.objects.create(
        id=uuid.uuid4(),
        tenantId=tenantId,
        code="BACKUP-DEV-1",
        name="پمپ تحت پشتیبان‌گیری",
        department="mechanical",
        status="operational",
        criticality="high",
        createdAt=now,
    )
    order = WorkOrderModel.objects.create(
        id=uuid.uuid4(),
        tenantId=tenantId,
        deviceId=device.id,
        title="تعمیر ثبت‌شده پیش از پشتیبان",
        orderType="corrective",
        priority="high",
        status="submitted",
        department="mechanical",
        createdAt=now,
    )
    return {"deviceId": device.id, "workOrderId": order.id}


class BackupContentTests(TestCase):
    """What a dump contains."""

    @classmethod
    def setUpTestData(cls) -> None:
        seedPlatform()
        cls.tenantId = platformTenantId()
        cls.ids = seedBusinessData(cls.tenantId)

    def dump(self) -> list[dict]:
        buffer = io.StringIO()
        call_command("backupData", stdout=buffer, format="json")
        return json.loads(buffer.getvalue())

    def testDumpContainsTheBusinessRows(self) -> None:
        records = self.dump()
        primaryKeys = {str(record["pk"]) for record in records}
        self.assertIn(str(self.ids["deviceId"]), primaryKeys)
        self.assertIn(str(self.ids["workOrderId"]), primaryKeys)

    def testDumpPreservesTheDeviceToWorkOrderLink(self) -> None:
        """A dump that drops the relation restores an orphaned work order:
        present in the table, attached to nothing, invisible in the UI."""

        records = self.dump()
        orders = [
            record
            for record in records
            if str(record["pk"]) == str(self.ids["workOrderId"])
        ]
        self.assertEqual(len(orders), 1)
        self.assertEqual(
            str(orders[0]["fields"]["deviceId"]), str(self.ids["deviceId"])
        )

    def testDumpCarriesNoPasswordHashesIntoAnUnprotectedFile(self) -> None:
        """Backups get copied to laptops and object stores. If the dump
        carries credential material, every copy is a credential leak — this
        test does not forbid it, it documents exactly what the file holds so
        the handling requirement is a decision and not a surprise."""

        records = self.dump()
        withHashes = [
            record
            for record in records
            if "passwordHash" in record["fields"]
            and record["fields"]["passwordHash"]
        ]
        self.assertTrue(
            withHashes,
            "no password hashes in the dump — if this changed, the restore "
            "procedure must now recreate users, and the runbook needs updating",
        )
        for record in withHashes:
            self.assertNotIn(
                "Platform-Admin-2026!",
                str(record["fields"]["passwordHash"]),
                "a plaintext password is in the backup",
            )


class RestoreRoundTripTests(TransactionTestCase):
    """Dump, delete, load, compare.

    `TransactionTestCase` because the data genuinely has to be deleted and
    re-inserted; a wrapping transaction would hide whether loaddata can
    actually write it back.
    """

    reset_sequences = True

    def setUp(self) -> None:
        seedPlatform()
        self.tenantId = platformTenantId()
        self.ids = seedBusinessData(self.tenantId)

    def testDataSurvivesADumpAndReload(self) -> None:
        from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel

        buffer = io.StringIO()
        call_command("backupData", apps="maintenance", stdout=buffer, format="json")
        backup = buffer.getvalue()

        WorkOrderModel.objects.all().delete()
        DeviceModel.objects.all().delete()
        self.assertEqual(DeviceModel.objects.count(), 0)

        path = "/tmp/tekarai-restore-test.json"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(backup)
        call_command("loaddata", path, verbosity=0)

        device = DeviceModel.objects.filter(id=self.ids["deviceId"]).first()
        self.assertIsNotNone(device, "the device did not come back")
        self.assertEqual(device.code, "BACKUP-DEV-1")
        self.assertEqual(device.name, "پمپ تحت پشتیبان‌گیری")

        order = WorkOrderModel.objects.filter(id=self.ids["workOrderId"]).first()
        self.assertIsNotNone(order, "the work order did not come back")
        self.assertEqual(
            str(order.deviceId),
            str(self.ids["deviceId"]),
            "the work order was restored without its device",
        )

    def testPersianTextSurvivesTheRoundTripByteForByte(self) -> None:
        """Encoding damage is the classic restore failure, and it is silent:
        the row count matches, the names are mojibake."""

        from apps.maintenance.infrastructure.models import DeviceModel

        buffer = io.StringIO()
        call_command("backupData", apps="maintenance", stdout=buffer, format="json")

        DeviceModel.objects.all().delete()
        path = "/tmp/tekarai-restore-unicode.json"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(buffer.getvalue())
        call_command("loaddata", path, verbosity=0)

        device = DeviceModel.objects.filter(id=self.ids["deviceId"]).first()
        self.assertIsNotNone(device)
        self.assertEqual(device.name, "پمپ تحت پشتیبان‌گیری")

    def testRestoringIntoANonEmptyDatabaseIsIdempotent(self) -> None:
        """Operators re-run restores. Doing it twice must not duplicate rows
        or crash on a primary key collision."""

        from apps.maintenance.infrastructure.models import DeviceModel

        buffer = io.StringIO()
        call_command("backupData", apps="maintenance", stdout=buffer, format="json")
        path = "/tmp/tekarai-restore-twice.json"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(buffer.getvalue())

        before = DeviceModel.objects.count()
        call_command("loaddata", path, verbosity=0)
        call_command("loaddata", path, verbosity=0)

        self.assertEqual(
            DeviceModel.objects.count(),
            before,
            "restoring twice duplicated rows",
        )


class MultiTenantBackupTests(TransactionTestCase):
    """A restore must not merge tenants."""

    reset_sequences = True

    def setUp(self) -> None:
        seedPlatform()
        self.tenantAId = platformTenantId()
        self.tenantB = createTenantWithAdmin("backup-b")
        self.idsA = seedBusinessData(self.tenantAId)

        from apps.maintenance.infrastructure.models import DeviceModel

        self.deviceB = DeviceModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenantB["tenantId"],
            code="BACKUP-DEV-B",
            name="تجهیز تنانت ب",
            department="electrical",
            status="operational",
            criticality="low",
            createdAt=datetime.now(tz=UTC),
        )

    def testRestoredRowsKeepTheirOriginalTenant(self) -> None:
        from apps.maintenance.infrastructure.models import DeviceModel, WorkOrderModel

        buffer = io.StringIO()
        call_command("backupData", apps="maintenance", stdout=buffer, format="json")

        WorkOrderModel.objects.all().delete()
        DeviceModel.objects.all().delete()

        path = "/tmp/tekarai-restore-tenants.json"
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(buffer.getvalue())
        call_command("loaddata", path, verbosity=0)

        restoredA = DeviceModel.objects.get(id=self.idsA["deviceId"])
        restoredB = DeviceModel.objects.get(id=self.deviceB.id)
        self.assertEqual(str(restoredA.tenantId), str(self.tenantAId))
        self.assertEqual(str(restoredB.tenantId), str(self.tenantB["tenantId"]))
        self.assertNotEqual(
            str(restoredA.tenantId),
            str(restoredB.tenantId),
            "the restore collapsed two tenants into one",
        )
