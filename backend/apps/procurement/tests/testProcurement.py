from decimal import Decimal

from django.test import SimpleTestCase

from apps.procurement.presentation.api.serializers import (
    PurchaseOrderSerializer,
    RequisitionSerializer,
    SupplierSerializer,
)


class ProcurementContractTests(SimpleTestCase):
    def test_supplier_requires_code_and_name(self):
        serializer = SupplierSerializer(data={"code": "", "name": ""})
        self.assertFalse(serializer.is_valid())

    def test_requisition_requires_at_least_one_line(self):
        serializer = RequisitionSerializer(data={"priority": "normal", "lines": []})
        self.assertFalse(serializer.is_valid())

    def test_requisition_accepts_quantity_and_estimated_cost(self):
        serializer = RequisitionSerializer(
            data={
                "requesterName": "تکنسین",
                "priority": "high",
                "lines": [
                    {
                        "partId": "00000000-0000-0000-0000-000000000001",
                        "partCode": "BRG-01",
                        "partName": "بلبرینگ",
                        "quantity": "2",
                        "estimatedUnitCost": "125000",
                    }
                ],
            }
        )
        self.assertTrue(serializer.is_valid(), serializer.errors)
        self.assertEqual(serializer.validated_data["lines"][0]["quantity"], Decimal("2"))

    def test_purchase_order_requires_supplier_and_lines(self):
        serializer = PurchaseOrderSerializer(
            data={"supplierId": "00000000-0000-0000-0000-000000000001", "lines": []}
        )
        self.assertFalse(serializer.is_valid())
