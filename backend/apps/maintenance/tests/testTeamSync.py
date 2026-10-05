"""تست‌های موج دوم — هم‌گام‌سازی تیمی رزرو قطعات و چک‌لیست‌های بازرسی."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from django.test import TestCase

from apps.maintenance.application.commands.teamSyncCommands import (
    CloseReservationCommand,
    CommitInspectionTemplateCommand,
    ListInspectionRecordsQuery,
    ListInspectionTemplatesQuery,
    ListReservationsQuery,
    SaveInspectionRecordCommand,
    SaveInspectionTemplateCommand,
    SaveReservationCommand,
)
from apps.maintenance.application.useCases.teamSyncUseCases import (
    CloseReservationUseCase,
    CommitInspectionTemplateUseCase,
    ListInspectionRecordsUseCase,
    ListInspectionTemplatesUseCase,
    ListReservationsUseCase,
    SaveInspectionRecordUseCase,
    SaveInspectionTemplateUseCase,
    SaveReservationUseCase,
)
from apps.maintenance.infrastructure.repositories.teamSyncRepositoryImpl import (
    InspectionSyncRepositoryImpl,
    PartReservationRepositoryImpl,
)
from apps.sharedKernel.application.requestContext import RequestContext, bindContext, resetContext
from apps.sharedKernel.domain.errors import ValidationFailedError


class FakeUnitOfWork:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


class NoopPort:
    def __getattr__(self, name):  # audit/events — در تست اهمیتی ندارند
        return lambda *args, **kwargs: None


class AllowAllGate:
    def hasPermission(self, *args, **kwargs):
        return True


class FixedClock:
    def nowUtc(self):
        return datetime(2026, 9, 28, 12, 0, tzinfo=UTC)


KERNEL_PORTS = {
    "unitOfWork": FakeUnitOfWork(),
    "auditRecorder": NoopPort(),
    "eventDispatcher": NoopPort(),
    "permissionGate": AllowAllGate(),
    "clock": FixedClock(),
}


class TeamSyncBase(TestCase):
    def setUp(self):
        super().setUp()
        self.tenant = uuid.uuid4()
        self.otherTenant = uuid.uuid4()
        self.token = bindContext(
            RequestContext(actorId=str(uuid.uuid4()), actorTenantId=str(self.tenant))
        )
        self.reservations = PartReservationRepositoryImpl()
        self.inspections = InspectionSyncRepositoryImpl()

    def tearDown(self):
        resetContext(self.token)
        super().tearDown()

    def _switchTenant(self, tenantId):
        resetContext(self.token)
        self.token = bindContext(
            RequestContext(actorId=str(uuid.uuid4()), actorTenantId=str(tenantId))
        )


class ReservationFlowTests(TeamSyncBase):
    def testReserveThenCloseFlow(self):
        orderId = uuid.uuid4()
        saved = SaveReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            SaveReservationCommand(
                id="rsv-test-1",
                workOrderId=str(orderId),
                partCode="BLB-6204",
                quantity="4",
                reservedByName="علی",
            )
        )
        self.assertEqual(saved.status, "active")

        listing = ListReservationsUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            ListReservationsQuery()
        )
        self.assertEqual(listing.totalCount, 1)
        self.assertEqual(listing.items[0].partCode, "BLB-6204")

        closed = CloseReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            CloseReservationCommand(reservationId="rsv-test-1", status="consumed")
        )
        self.assertEqual(closed.status, "consumed")

        # بستن مجدد — بدون خطا و بدون تغییر وضعیت
        again = CloseReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            CloseReservationCommand(reservationId="rsv-test-1", status="released")
        )
        self.assertEqual(again.status, "consumed")

        filtered = ListReservationsUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            ListReservationsQuery(workOrderId=str(orderId))
        )
        self.assertEqual(filtered.totalCount, 1)
        self.assertEqual(filtered.items[0].status, "consumed")

    def testTenantIsolation(self):
        SaveReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            SaveReservationCommand(
                id="rsv-iso-1", workOrderId=str(uuid.uuid4()), partCode="OIL-10", quantity="1"
            )
        )
        self._switchTenant(self.otherTenant)
        listing = ListReservationsUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
            ListReservationsQuery()
        )
        self.assertEqual(listing.totalCount, 0)

    def testBadInputsRaiseValidation(self):
        with self.assertRaises(ValidationFailedError):
            SaveReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
                SaveReservationCommand(
                    id="rsv-bad-1", workOrderId="not-a-uuid", partCode="X", quantity="1"
                )
            )
        with self.assertRaises(ValidationFailedError):
            SaveReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
                SaveReservationCommand(
                    id="rsv-bad-2", workOrderId=str(uuid.uuid4()), partCode="X", quantity="0"
                )
            )
        with self.assertRaises(ValidationFailedError):
            CloseReservationUseCase(repository=self.reservations, **KERNEL_PORTS).execute(
                CloseReservationCommand(reservationId="missing", status="released")
            )


class InspectionFlowTests(TeamSyncBase):
    def testTemplateAndRecordFlow(self):
        template = SaveInspectionTemplateUseCase(
            repository=self.inspections, **KERNEL_PORTS
        ).execute(
            SaveInspectionTemplateCommand(
                id="itpl-test-1",
                name="بازرسی روزانه پمپ",
                deviceCode="DEV-01",
                checks=["روغن کافی است", "نشتی ندارد"],
            )
        )
        # قالب‌های تازه از همان ابتدا قابل اجرا ساخته می‌شوند
        self.assertTrue(template.isCommitted)
        self.assertEqual(template.deviceCode, "DEV-01")
        self.assertEqual(len(template.checks), 2)

        listing = ListInspectionTemplatesUseCase(
            repository=self.inspections, **KERNEL_PORTS
        ).execute(ListInspectionTemplatesQuery())
        self.assertEqual(listing.totalCount, 1)

        # رکورد روی قالب ناموجود (یا تیم دیگر) ممنوع است
        with self.assertRaises(ValidationFailedError):
            SaveInspectionRecordUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
                SaveInspectionRecordCommand(
                    id="rec-x",
                    templateId="itpl-missing",
                    workOrderId=str(uuid.uuid4()),
                    deviceId=str(uuid.uuid4()),
                    passedChecks=["روغن کافی است"],
                    failedChecks=[],
                )
            )

        record = SaveInspectionRecordUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            SaveInspectionRecordCommand(
                id="rec-1",
                templateId="itpl-test-1",
                workOrderId=str(uuid.uuid4()),
                deviceId=str(uuid.uuid4()),
                passedChecks=["روغن کافی است"],
                failedChecks=["نشتی ندارد"],
            )
        )
        self.assertEqual(len(record.failedChecks), 1)

        records = ListInspectionRecordsUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            ListInspectionRecordsQuery()
        )
        self.assertEqual(records.totalCount, 1)

    def testRecordOrderlessAccepted(self):
        SaveInspectionTemplateUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            SaveInspectionTemplateCommand(id="itpl-orderless", name="عمومی", checks=["x"])
        )
        record = SaveInspectionRecordUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            SaveInspectionRecordCommand(
                id="rec-free-1",
                templateId="itpl-orderless",
                workOrderId="",
                deviceId=str(uuid.uuid4()),
                passedChecks=["x"],
                failedChecks=[],
                performedByName="علی",
            )
        )
        self.assertEqual(record.workOrderId, "")

    def testTemplateDeleteFlow(self):
        from apps.maintenance.application.commands.teamSyncCommands import (
            DeleteInspectionTemplateCommand,
        )
        from apps.maintenance.application.useCases.teamSyncUseCases import (
            DeleteInspectionTemplateUseCase,
        )

        SaveInspectionTemplateUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            SaveInspectionTemplateCommand(id="itpl-del-1", name="حذف‌شونده", checks=["x"])
        )
        DeleteInspectionTemplateUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            DeleteInspectionTemplateCommand(templateId="itpl-del-1")
        )
        listing = ListInspectionTemplatesUseCase(
            repository=self.inspections, **KERNEL_PORTS
        ).execute(ListInspectionTemplatesQuery())
        self.assertEqual(listing.totalCount, 0)
        with self.assertRaises(ValidationFailedError):
            DeleteInspectionTemplateUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
                DeleteInspectionTemplateCommand(templateId="itpl-del-1")
            )

    def testTemplateTenantIsolation(self):
        SaveInspectionTemplateUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
            SaveInspectionTemplateCommand(id="itpl-iso-1", name="قالب A", checks=["x"])
        )
        self._switchTenant(self.otherTenant)
        listing = ListInspectionTemplatesUseCase(
            repository=self.inspections, **KERNEL_PORTS
        ).execute(ListInspectionTemplatesQuery())
        self.assertEqual(listing.totalCount, 0)
        with self.assertRaises(ValidationFailedError):
            CommitInspectionTemplateUseCase(repository=self.inspections, **KERNEL_PORTS).execute(
                CommitInspectionTemplateCommand(templateId="itpl-iso-1")
            )
