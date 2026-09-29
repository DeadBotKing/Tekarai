"""دفتر تراکنش انبار — رسید/حواله/برگشت/تعدیل، مانده‌ی جاری و جلوگیری از موجودی منفی."""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from decimal import Decimal

from django.test import TestCase

from apps.maintenance.domain.entities.sparePart import (
    PART_TRANSACTION_ADJUSTMENT,
    PART_TRANSACTION_ISSUE,
    PART_TRANSACTION_RECEIPT,
    PART_TRANSACTION_RETURN,
)
from apps.maintenance.infrastructure.models import PartTransactionModel, SparePartModel
from apps.maintenance.infrastructure.repositories.sparePartRepositoryImpl import (
    SparePartRepositoryDjango,
)
from apps.sharedKernel.domain.errors import EntityNotFoundError, ValidationFailedError

NOW = datetime(2026, 9, 28, 8, 0, tzinfo=UTC)


class PartTransactionRepositoryTests(TestCase):
    def setUp(self):
        self.tenant = uuid.uuid4()
        self.repo = SparePartRepositoryDjango()
        self.part = SparePartModel.objects.create(
            id=uuid.uuid4(),
            tenantId=self.tenant,
            code="BRG-6204",
            name="بلبرینگ ۶۲۰۴",
            unit="عدد",
            quantityOnHand=Decimal("10"),
            minimumStock=Decimal("2"),
            unitCost=Decimal("1000"),
        )

    def _record(self, transactionType, quantity, note="", reference=""):
        return self.repo.recordTransaction(
            self.tenant,
            self.part.id,
            transactionType,
            Decimal(quantity),
            note,
            reference,
            None,
            NOW,
        )

    def test_receipt_adds_stock_and_running_balance(self):
        row = self._record(PART_TRANSACTION_RECEIPT, "5", reference="رسید-۱۲")
        self.assertEqual(row.quantity, Decimal("5"))
        self.assertEqual(row.balanceAfter, Decimal("15"))
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("15"))

    def test_issue_then_return_running_balance_chain(self):
        self._record(PART_TRANSACTION_ISSUE, "-4")
        second = self._record(PART_TRANSACTION_RETURN, "2")
        self.assertEqual(second.balanceAfter, Decimal("8"))
        rows = self.repo.listTransactions(self.tenant, self.part.id)
        self.assertEqual(len(rows), 2)
        # جدیدترین اول
        self.assertEqual(rows[0].balanceAfter, Decimal("8"))
        self.assertEqual(rows[1].balanceAfter, Decimal("6"))

    def test_issue_beyond_stock_rejected_atomically(self):
        with self.assertRaises(ValidationFailedError):
            self._record(PART_TRANSACTION_ISSUE, "-11")
        self.part.refresh_from_db()
        self.assertEqual(self.part.quantityOnHand, Decimal("10"))
        self.assertEqual(PartTransactionModel.objects.count(), 0)

    def test_adjustment_signed_value(self):
        row = self._record(PART_TRANSACTION_ADJUSTMENT, "-3", note="کسر شمارش")
        self.assertEqual(row.balanceAfter, Decimal("7"))
        row = self._record(PART_TRANSACTION_ADJUSTMENT, "1.5", note="ازدیاد")
        self.assertEqual(row.balanceAfter, Decimal("8.5"))

    def test_snapshot_keeps_part_code_name(self):
        row = self._record(PART_TRANSACTION_RECEIPT, "1")
        self.assertEqual(row.partCode, "BRG-6204")
        self.assertEqual(row.partName, "بلبرینگ ۶۲۰۴")

    def test_unknown_part_raises_not_found(self):
        with self.assertRaises(EntityNotFoundError):
            self.repo.recordTransaction(
                self.tenant,
                uuid.uuid4(),
                PART_TRANSACTION_RECEIPT,
                Decimal("1"),
                "",
                "",
                None,
                NOW,
            )

    def test_tenant_isolation_in_list(self):
        self._record(PART_TRANSACTION_RECEIPT, "1")
        other_tenant = uuid.uuid4()
        self.assertEqual(self.repo.listTransactions(other_tenant), [])
