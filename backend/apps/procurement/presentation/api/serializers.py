from __future__ import annotations

from decimal import Decimal

from rest_framework import serializers


class SupplierSerializer(serializers.Serializer):
    code = serializers.CharField(max_length=60)
    name = serializers.CharField(max_length=240)
    supplierType = serializers.CharField(max_length=40, required=False, default="vendor")
    status = serializers.ChoiceField(
        choices=["active", "inactive", "blocked"], required=False, default="active"
    )
    contactName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    email = serializers.EmailField(required=False, allow_blank=True, default="")
    phone = serializers.CharField(max_length=60, required=False, allow_blank=True, default="")
    taxId = serializers.CharField(max_length=80, required=False, allow_blank=True, default="")
    address = serializers.CharField(required=False, allow_blank=True, default="")
    paymentTerms = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    currency = serializers.CharField(max_length=8, required=False, default="IRR")
    defaultLeadTimeDays = serializers.IntegerField(min_value=0, required=False, default=0)
    notes = serializers.CharField(required=False, allow_blank=True, default="")


class SupplierPartSerializer(serializers.Serializer):
    partId = serializers.UUIDField()
    supplierSku = serializers.CharField(
        max_length=100, required=False, allow_blank=True, default=""
    )
    unitPrice = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), default=0
    )
    minimumOrderQty = serializers.DecimalField(
        max_digits=14, decimal_places=3, min_value=Decimal("0.001"), default=1
    )
    leadTimeDays = serializers.IntegerField(min_value=0, default=0)
    isPreferred = serializers.BooleanField(default=False)


class LineSerializer(serializers.Serializer):
    partId = serializers.UUIDField()
    partCode = serializers.CharField(max_length=60)
    partName = serializers.CharField(max_length=240)
    unit = serializers.CharField(max_length=30, default="عدد")
    quantity = serializers.DecimalField(max_digits=14, decimal_places=3, min_value=Decimal("0.001"))
    unitPrice = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), required=False, default=0
    )
    estimatedUnitCost = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), required=False, default=0
    )
    supplierId = serializers.UUIDField(required=False, allow_null=True, default=None)
    preferredSupplierId = serializers.UUIDField(required=False, allow_null=True, default=None)
    note = serializers.CharField(max_length=500, required=False, allow_blank=True, default="")
    taxRate = serializers.DecimalField(
        max_digits=6, decimal_places=3, min_value=Decimal("0"), required=False, default=0
    )


class RequisitionSerializer(serializers.Serializer):
    requesterName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    neededBy = serializers.DateField(required=False, allow_null=True, default=None)
    priority = serializers.ChoiceField(
        choices=["low", "normal", "high", "critical"], default="normal"
    )
    justification = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, min_length=1)


class PurchaseOrderSerializer(serializers.Serializer):
    supplierId = serializers.UUIDField()
    requisitionId = serializers.UUIDField(required=False, allow_null=True, default=None)
    expectedDate = serializers.DateField(required=False, allow_null=True, default=None)
    currency = serializers.CharField(max_length=8, default="IRR")
    paymentTerms = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    shippingAddress = serializers.CharField(required=False, allow_blank=True, default="")
    taxAmount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = LineSerializer(many=True, min_length=1)


class ReceiptSerializer(serializers.Serializer):
    purchaseOrderId = serializers.UUIDField()
    receiverName = serializers.CharField(
        max_length=160, required=False, allow_blank=True, default=""
    )
    deliveryNote = serializers.CharField(
        max_length=120, required=False, allow_blank=True, default=""
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
    lines = serializers.ListField(child=serializers.DictField(), min_length=1)


class ReturnSerializer(serializers.Serializer):
    supplierId = serializers.UUIDField()
    purchaseOrderId = serializers.UUIDField(required=False, allow_null=True, default=None)
    reason = serializers.CharField(required=False, allow_blank=True, default="")
    lines = serializers.ListField(child=serializers.DictField(), min_length=1)


class InvoiceSerializer(serializers.Serializer):
    invoiceNumber = serializers.CharField(max_length=80)
    supplierId = serializers.UUIDField()
    purchaseOrderId = serializers.UUIDField(required=False, allow_null=True, default=None)
    status = serializers.ChoiceField(
        choices=["draft", "received", "approved", "paid", "disputed"], default="received"
    )
    invoiceDate = serializers.DateField(required=False, allow_null=True, default=None)
    dueDate = serializers.DateField(required=False, allow_null=True, default=None)
    currency = serializers.CharField(max_length=8, default="IRR")
    subtotal = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), default=0
    )
    taxAmount = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), default=0
    )
    total = serializers.DecimalField(
        max_digits=18, decimal_places=2, min_value=Decimal("0"), default=0
    )
    notes = serializers.CharField(required=False, allow_blank=True, default="")
