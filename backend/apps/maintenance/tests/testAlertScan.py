"""یادآورهای زمان‌دار — اسکن SLA درخواست‌های باز و موجودی کم انبار."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from django.test import TestCase

from apps.maintenance.application.commands.maintenanceCommands import (
    RunMaintenanceAlertScanCommand,
)
from apps.maintenance.infrastructure import container
from apps.maintenance.infrastructure.models import SparePartModel, WorkOrderModel


class CaptureDispatcher:
    def __init__(self):
        self.events = []

    def dispatch(self, event):
        self.events.append(event)


def _capture(value=None):
    return CaptureDispatcher()


def _useCase(dispatcher=None):
    useCase = container.runMaintenanceAlertScanUseCase()
    useCase.eventDispatcher = dispatcher or CaptureDispatcher()
    return useCase


def _order(tenant, priority, status="submitted", ageHours=0):
    order = WorkOrderModel.objects.create(
        id=uuid.uuid4(),
        tenantId=tenant,
        deviceId=uuid.uuid4(),
        title="دستور کار آزمایشی",
        status=status,
        priority=priority,
    )
    if ageHours:
        WorkOrderModel.objects.filter(id=order.id).update(
            createdAt=datetime.now(tz=UTC) - timedelta(hours=ageHours)
        )
        order.refresh_from_db()
    return order


class MaintenanceAlertScanTests(TestCase):
    def setUp(self):
        self.tenant = uuid.uuid4()
        self.dispatcher = CaptureDispatcher()
        self.useCase = _useCase(self.dispatcher)

    def _run(self):
        return self.useCase.execute(RunMaintenanceAlertScanCommand(tenantId=str(self.tenant)))

    def testCriticalOpenOrderPastSlaEmitsEvent(self):
        order = _order(self.tenant, "critical", ageHours=10)  # SLA ۴ ساعت
        dto = self._run()
        self.assertEqual(dto.overdueWorkOrders, 1)
        event = self.dispatcher.events[0]
        self.assertEqual(event.name, "workOrderOverdue")
        self.assertEqual(event.payload["workOrderId"], str(order.id))
        # شناسه‌ی قطعی هفتگی — اجرای دوباره در همان هفته تکراری محسوب می‌شود
        self.assertIn(dto.isoWeek, event.payload["eventId"])

    def testOpenOrderWithinSlaIsSilent(self):
        _order(self.tenant, "normal", ageHours=10)  # SLA ۷۲ ساعت
        dto = self._run()
        self.assertEqual(dto.overdueWorkOrders, 0)

    def testTerminalStatusesNeverAlert(self):
        _order(self.tenant, "critical", status="completed", ageHours=200)
        _order(self.tenant, "critical", status="cancelled", ageHours=200)
        dto = self._run()
        self.assertEqual(dto.overdueWorkOrders, 0)

    def testLowStockPartEmitsEvent(self):
        SparePartModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenant,
            code="SEAL-1",
            name="سیل",
            quantityOnHand=Decimal("3"),
            minimumStock=Decimal("5"),
        )
        dto = self._run()
        self.assertEqual(dto.lowStockParts, 1)
        event = self.dispatcher.events[0]
        self.assertEqual(event.name, "sparePartLowStock")
        self.assertIn(dto.isoWeek, event.payload["eventId"])

    def testHealthyStockIsSilent(self):
        SparePartModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenant,
            code="BRG-1",
            name="بلبرینگ",
            quantityOnHand=Decimal("40"),
            minimumStock=Decimal("10"),
        )
        dto = self._run()
        self.assertEqual(dto.lowStockParts, 0)

    def testWeeklyEventIdIsDeterministic(self):
        order = _order(self.tenant, "high", ageHours=30)  # SLA ۲۴ ساعت
        first = self._run()
        secondDispatcher = CaptureDispatcher()
        second = _useCase(secondDispatcher).execute(
            RunMaintenanceAlertScanCommand(tenantId=str(self.tenant))
        )
        self.assertEqual(first.isoWeek, second.isoWeek)
        self.assertEqual(
            self.dispatcher.events[0].payload["eventId"],
            secondDispatcher.events[0].payload["eventId"],
        )
        self.assertEqual(first.isoWeek and 1, 1)  # week key present
        self.assertIn(str(order.id), self.dispatcher.events[0].payload["eventId"])
