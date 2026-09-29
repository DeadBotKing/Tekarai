"""Procurement bounded context persistence models.

All relations to maintenance parts and identity actors are UUID references on purpose:
the bounded context stays decoupled from Django models in other contexts.
"""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import models


class TenantStamped(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    tenantId = models.UUIDField(db_index=True)
    createdAt = models.DateTimeField(auto_now_add=True, db_index=True)
    updatedAt = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class SupplierModel(TenantStamped):
    STATUS = [("active", "Active"), ("inactive", "Inactive"), ("blocked", "Blocked")]
    code = models.CharField(max_length=60)
    name = models.CharField(max_length=240)
    supplierType = models.CharField(max_length=40, default="vendor")
    status = models.CharField(max_length=20, choices=STATUS, default="active")
    contactName = models.CharField(max_length=160, blank=True, default="")
    email = models.EmailField(blank=True, default="")
    phone = models.CharField(max_length=60, blank=True, default="")
    taxId = models.CharField(max_length=80, blank=True, default="")
    address = models.TextField(blank=True, default="")
    paymentTerms = models.CharField(max_length=120, blank=True, default="")
    currency = models.CharField(max_length=8, default="IRR")
    defaultLeadTimeDays = models.PositiveIntegerField(default=0)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ProcurementSupplier"
        ordering = ["name"]
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "code"], name="uq_proc_supplier_code")
        ]


class SupplierPartModel(TenantStamped):
    supplierId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    supplierSku = models.CharField(max_length=100, blank=True, default="")
    unitPrice = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    minimumOrderQty = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("1"))
    leadTimeDays = models.PositiveIntegerField(default=0)
    isPreferred = models.BooleanField(default=False)
    lastQuotedAt = models.DateField(null=True, blank=True)

    class Meta:
        db_table = "ProcurementSupplierPart"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "supplierId", "partId"], name="uq_proc_supplier_part"
            )
        ]


class PurchaseRequisitionModel(TenantStamped):
    STATUS = [
        (x, x) for x in ("draft", "submitted", "approved", "rejected", "cancelled", "ordered")
    ]
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=STATUS, default="draft", db_index=True)
    requesterId = models.UUIDField(null=True, blank=True)
    requesterName = models.CharField(max_length=160, blank=True, default="")
    requestedOn = models.DateField(auto_now_add=True)
    neededBy = models.DateField(null=True, blank=True)
    priority = models.CharField(max_length=20, default="normal")
    justification = models.TextField(blank=True, default="")
    totalEstimated = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))

    class Meta:
        db_table = "ProcurementRequisition"
        ordering = ["-createdAt"]
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "number"], name="uq_proc_requisition_number"
            )
        ]


class PurchaseRequisitionLineModel(TenantStamped):
    requisitionId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    partCode = models.CharField(max_length=60)
    partName = models.CharField(max_length=240)
    unit = models.CharField(max_length=30, default="عدد")
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    estimatedUnitCost = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    preferredSupplierId = models.UUIDField(null=True, blank=True)
    note = models.CharField(max_length=500, blank=True, default="")

    class Meta:
        db_table = "ProcurementRequisitionLine"


class ProcurementApprovalModel(TenantStamped):
    documentType = models.CharField(max_length=20)
    documentId = models.UUIDField(db_index=True)
    step = models.PositiveIntegerField(default=1)
    action = models.CharField(max_length=20, default="pending")
    actorId = models.UUIDField(null=True, blank=True)
    actorName = models.CharField(max_length=160, blank=True, default="")
    comment = models.TextField(blank=True, default="")
    actedAt = models.DateTimeField(null=True, blank=True)

    class Meta:
        db_table = "ProcurementApproval"
        ordering = ["step", "-createdAt"]


class PurchaseOrderModel(TenantStamped):
    STATUS = [
        (x, x)
        for x in ("draft", "submitted", "approved", "partiallyReceived", "received", "cancelled")
    ]
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=24, choices=STATUS, default="draft", db_index=True)
    supplierId = models.UUIDField(db_index=True)
    requisitionId = models.UUIDField(null=True, blank=True, db_index=True)
    orderDate = models.DateField(auto_now_add=True)
    expectedDate = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=8, default="IRR")
    paymentTerms = models.CharField(max_length=120, blank=True, default="")
    shippingAddress = models.TextField(blank=True, default="")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    taxAmount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ProcurementPurchaseOrder"
        ordering = ["-createdAt"]
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "number"], name="uq_proc_po_number")
        ]


class PurchaseOrderLineModel(TenantStamped):
    purchaseOrderId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    partCode = models.CharField(max_length=60)
    partName = models.CharField(max_length=240)
    unit = models.CharField(max_length=30, default="عدد")
    orderedQuantity = models.DecimalField(max_digits=14, decimal_places=3)
    receivedQuantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))
    unitPrice = models.DecimalField(max_digits=18, decimal_places=2)
    taxRate = models.DecimalField(max_digits=6, decimal_places=3, default=Decimal("0"))

    class Meta:
        db_table = "ProcurementPurchaseOrderLine"


class GoodsReceiptModel(TenantStamped):
    STATUS = [(x, x) for x in ("draft", "posted", "cancelled")]
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    purchaseOrderId = models.UUIDField(db_index=True)
    receivedOn = models.DateField(auto_now_add=True)
    receiverName = models.CharField(max_length=160, blank=True, default="")
    deliveryNote = models.CharField(max_length=120, blank=True, default="")
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ProcurementGoodsReceipt"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "number"], name="uq_proc_receipt_number")
        ]


class GoodsReceiptLineModel(TenantStamped):
    receiptId = models.UUIDField(db_index=True)
    purchaseOrderLineId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unitCost = models.DecimalField(max_digits=18, decimal_places=2)
    rejectedQuantity = models.DecimalField(max_digits=14, decimal_places=3, default=Decimal("0"))

    class Meta:
        db_table = "ProcurementGoodsReceiptLine"


class PurchaseReturnModel(TenantStamped):
    STATUS = [(x, x) for x in ("draft", "posted", "cancelled")]
    number = models.CharField(max_length=40)
    status = models.CharField(max_length=20, choices=STATUS, default="draft")
    supplierId = models.UUIDField(db_index=True)
    purchaseOrderId = models.UUIDField(null=True, blank=True)
    returnedOn = models.DateField(auto_now_add=True)
    reason = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ProcurementPurchaseReturn"
        constraints = [
            models.UniqueConstraint(fields=["tenantId", "number"], name="uq_proc_return_number")
        ]


class PurchaseReturnLineModel(TenantStamped):
    returnId = models.UUIDField(db_index=True)
    partId = models.UUIDField(db_index=True)
    quantity = models.DecimalField(max_digits=14, decimal_places=3)
    unitCost = models.DecimalField(max_digits=18, decimal_places=2)

    class Meta:
        db_table = "ProcurementPurchaseReturnLine"


class SupplierInvoiceModel(TenantStamped):
    STATUS = [(x, x) for x in ("draft", "received", "approved", "paid", "disputed")]
    invoiceNumber = models.CharField(max_length=80)
    supplierId = models.UUIDField(db_index=True)
    purchaseOrderId = models.UUIDField(null=True, blank=True)
    status = models.CharField(max_length=20, choices=STATUS, default="received")
    invoiceDate = models.DateField(null=True, blank=True)
    dueDate = models.DateField(null=True, blank=True)
    currency = models.CharField(max_length=8, default="IRR")
    subtotal = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    taxAmount = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    total = models.DecimalField(max_digits=18, decimal_places=2, default=Decimal("0"))
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ProcurementSupplierInvoice"
        constraints = [
            models.UniqueConstraint(
                fields=["tenantId", "supplierId", "invoiceNumber"], name="uq_proc_invoice"
            )
        ]
