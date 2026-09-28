"""فیلدهای بستن کار (گزارشنامه‌ی خرابی) — DTO مدل‌خور نگاشت درست می‌کند."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.test import TestCase

from apps.maintenance.application.dto.maintenanceDtos import workOrderDtoFromDomain
from apps.maintenance.infrastructure.models import WorkOrderModel
from apps.maintenance.infrastructure.repositories.workOrderRepositoryImpl import WorkOrderRepositoryDjango


class ClosureDtoMappingTests(TestCase):
    def test_domain_to_dto_closure_fields(self):
        tenant = uuid.uuid4()
        WorkOrderModel.objects.create(
            id=uuid.uuid4(),
            tenantId=tenant,
            deviceId=uuid.uuid4(),
            title="تعویض بلبرینگ پرس ریمک",
            status="completed",
            orderType="corrective",
            failureType="mec-bearing",
            failedComponent="بلبرینگ",
            failureSymptom="صدای غیرعادی",
            rootCause="کمبود روغنکاری",
            actionTaken="بلبرینگ تعویض شد",
            repeatFailure=True,
            downtimeMinutes=75,
            labourHours=Decimal("2.5"),
            labourCost=Decimal("150000"),
            partsCost=Decimal("80000"),
        )
        model = WorkOrderModel.objects.get()
        domain = WorkOrderRepositoryDjango.toDomain(model)
        dto = workOrderDtoFromDomain(domain)
        self.assertEqual(dto.failureType, "mec-bearing")
        self.assertEqual(dto.failedComponent, "بلبرینگ")
        self.assertTrue(dto.repeatFailure)
        self.assertEqual(dto.downtimeMinutes, 75)
        self.assertEqual(Decimal(dto.labourHours).normalize(), Decimal("2.5"))
        self.assertEqual(Decimal(dto.partsCost).normalize(), Decimal("80000"))
