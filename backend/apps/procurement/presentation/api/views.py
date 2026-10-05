"""Procurement API: suppliers, requisitions, purchase orders, receipts, returns and invoices."""

from __future__ import annotations

import uuid
from decimal import Decimal

from django.db import transaction
from django.db.models import Q
from rest_framework import serializers
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.maintenance.application.services.inventoryContract import (
    recordGoodsReceipt,
    recordSupplierReturn,
)
from apps.procurement.domain.services.receiptRules import (
    asQuantity,
    guardOrderAcceptsDelivery,
    guardReceiptLine,
)
from apps.procurement.infrastructure.models import (
    GoodsReceiptLineModel,
    GoodsReceiptModel,
    ProcurementApprovalModel,
    PurchaseOrderLineModel,
    PurchaseOrderModel,
    PurchaseRequisitionLineModel,
    PurchaseRequisitionModel,
    PurchaseReturnLineModel,
    PurchaseReturnModel,
    SupplierInvoiceModel,
    SupplierModel,
    SupplierPartModel,
)
from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.presentation.api.authentication import BearerSessionAuthentication
from apps.sharedKernel.presentation.api.idempotency import IdempotencyMixin
from apps.sharedKernel.presentation.api.permissions import IsAuthenticated, actionPermission
from apps.sharedKernel.presentation.api.response import successEnvelope

from .serializers import (
    InvoiceSerializer,
    PurchaseOrderSerializer,
    ReceiptSerializer,
    RequisitionSerializer,
    ReturnSerializer,
    SupplierPartSerializer,
    SupplierSerializer,
)


def tenant() -> uuid.UUID:
    context = currentContext()
    value = context.tenantId or context.actorTenantId
    if not value:
        raise ValueError("Tenant scope could not be resolved.")
    return uuid.UUID(str(value))


def row(obj, extra=None):
    data = {f.name: getattr(obj, f.name) for f in obj._meta.fields if f.name not in {"tenantId"}}
    if extra:
        data.update(extra)
    return data


def listView(model, request, searchFields=()):
    qs = model.objects.filter(tenantId=tenant())
    search = str(request.query_params.get("search", "")).strip()
    if search and searchFields:
        query = Q()
        for field in searchFields:
            query |= Q(**{f"{field}__icontains": search})
        qs = qs.filter(query)
    return [row(item) for item in qs[:500]]


class Base(IdempotencyMixin, APIView):
    authentication_classes = [BearerSessionAuthentication]
    permission_classes = [IsAuthenticated]

    def get_permissions(self):
        path = self.request.path
        method = self.request.method
        action = "procurement.supplier.view"
        if "/suppliers" in path:
            action = (
                "procurement.supplier.view" if method == "GET" else "procurement.supplier.manage"
            )
        elif "/requisitions" in path:
            action = (
                "procurement.requisition.approve"
                if path.rsplit("/", 1)[-1] in {"approve", "reject", "cancel"}
                else "procurement.requisition.create"
            )
        elif "/purchase-orders" in path:
            action = (
                "procurement.purchaseOrder.approve"
                if path.rsplit("/", 1)[-1] in {"approve", "cancel", "submit"}
                else "procurement.purchaseOrder.create"
            )
        elif "/receipts" in path:
            action = "procurement.receipt.post"
        elif "/returns" in path:
            action = "procurement.return.post"
        elif "/invoices" in path:
            action = "procurement.invoice.manage"
        elif "/dashboard" in path:
            action = "procurement.supplier.view"
        return [IsAuthenticated(), actionPermission(action)()]


class SupplierListView(Base):
    def get(self, request):
        return Response(
            successEnvelope(listView(SupplierModel, request, ("code", "name", "contactName")))
        )

    def post(self, request):
        s = SupplierSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(
            successEnvelope(
                row(SupplierModel.objects.create(tenantId=tenant(), **s.validated_data))
            ),
            status=201,
        )


class SupplierDetailView(Base):
    def patch(self, request, supplierId):
        s = SupplierSerializer(data=request.data, partial=True)
        s.is_valid(raise_exception=True)
        obj = SupplierModel.objects.get(id=supplierId, tenantId=tenant())
        for field, value in s.validated_data.items():
            setattr(obj, field, value)
        obj.save()
        return Response(successEnvelope(row(obj)))

    def delete(self, request, supplierId):
        SupplierModel.objects.filter(id=supplierId, tenantId=tenant()).update(status="inactive")
        return Response(successEnvelope({"deleted": True}))


class SupplierPartsView(Base):
    def get(self, request, supplierId):
        return Response(
            successEnvelope(
                [
                    row(x)
                    for x in SupplierPartModel.objects.filter(
                        tenantId=tenant(), supplierId=supplierId
                    )
                ]
            )
        )

    def post(self, request, supplierId):
        s = SupplierPartSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        obj, _ = SupplierPartModel.objects.update_or_create(
            tenantId=tenant(),
            supplierId=supplierId,
            partId=s.validated_data["partId"],
            defaults=s.validated_data,
        )
        return Response(successEnvelope(row(obj)), status=201)


def requisitionDetail(obj):
    return row(
        obj,
        {
            "lines": [
                row(x)
                for x in PurchaseRequisitionLineModel.objects.filter(
                    tenantId=obj.tenantId, requisitionId=obj.id
                )
            ],
            "approvals": [
                row(x)
                for x in ProcurementApprovalModel.objects.filter(
                    tenantId=obj.tenantId, documentId=obj.id
                )
            ],
        },
    )


class RequisitionListView(Base):
    def get(self, request):
        return Response(
            successEnvelope(
                [
                    requisitionDetail(x)
                    for x in PurchaseRequisitionModel.objects.filter(tenantId=tenant())[:500]
                ]
            )
        )

    @transaction.atomic
    def post(self, request):
        s = RequisitionSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        t = tenant()
        lines = data.pop("lines")
        obj = PurchaseRequisitionModel.objects.create(
            tenantId=t, number=f"PR-{uuid.uuid4().hex[:8].upper()}", status="draft", **data
        )
        total = Decimal("0")
        for item in lines:
            cost = item.get("estimatedUnitCost", item.get("unitPrice", 0))
            total += item["quantity"] * cost
            PurchaseRequisitionLineModel.objects.create(
                tenantId=t,
                requisitionId=obj.id,
                **{
                    k: v
                    for k, v in item.items()
                    if k
                    in {
                        "partId",
                        "partCode",
                        "partName",
                        "unit",
                        "quantity",
                        "estimatedUnitCost",
                        "preferredSupplierId",
                        "note",
                    }
                },
            )
        obj.totalEstimated = total
        obj.save(update_fields=["totalEstimated", "updatedAt"])
        return Response(successEnvelope(requisitionDetail(obj)), status=201)


class RequisitionActionView(Base):
    @transaction.atomic
    def post(self, request, requisitionId, action):
        obj = PurchaseRequisitionModel.objects.get(id=requisitionId, tenantId=tenant())
        note = str(request.data.get("comment", ""))
        target = {
            "submit": "submitted",
            "approve": "approved",
            "reject": "rejected",
            "cancel": "cancelled",
        }.get(action)
        if not target:
            return Response(successEnvelope({"error": "unknown action"}), status=400)
        if action == "approve" and obj.status != "submitted":
            return Response(
                successEnvelope({"error": "only submitted requisitions can be approved"}),
                status=409,
            )
        obj.status = target
        obj.save(update_fields=["status", "updatedAt"])
        ProcurementApprovalModel.objects.create(
            tenantId=obj.tenantId,
            documentType="requisition",
            documentId=obj.id,
            action=action,
            actorName=str(getattr(currentContext(), "actorId", "")),
            comment=note,
        )
        return Response(successEnvelope(requisitionDetail(obj)))


def purchaseOrderDetail(obj):
    return row(
        obj,
        {
            "lines": [
                row(x)
                for x in PurchaseOrderLineModel.objects.filter(
                    tenantId=obj.tenantId, purchaseOrderId=obj.id
                )
            ],
            "approvals": [
                row(x)
                for x in ProcurementApprovalModel.objects.filter(
                    tenantId=obj.tenantId, documentId=obj.id
                )
            ],
        },
    )


class PurchaseOrderListView(Base):
    def get(self, request):
        return Response(
            successEnvelope(
                [
                    purchaseOrderDetail(x)
                    for x in PurchaseOrderModel.objects.filter(tenantId=tenant())[:500]
                ]
            )
        )

    @transaction.atomic
    def post(self, request):
        s = PurchaseOrderSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        t = tenant()
        lines = data.pop("lines")
        subtotal = sum((x.get("unitPrice", 0) * x["quantity"] for x in lines), Decimal("0"))
        tax = data.get("taxAmount", 0)
        obj = PurchaseOrderModel.objects.create(
            tenantId=t,
            number=f"PO-{uuid.uuid4().hex[:8].upper()}",
            subtotal=subtotal,
            total=subtotal + tax,
            **data,
        )
        for item in lines:
            PurchaseOrderLineModel.objects.create(
                tenantId=t,
                purchaseOrderId=obj.id,
                partId=item["partId"],
                partCode=item["partCode"],
                partName=item["partName"],
                unit=item.get("unit", "عدد"),
                orderedQuantity=item["quantity"],
                unitPrice=item.get("unitPrice", 0),
                taxRate=item.get("taxRate", 0),
            )
        if obj.requisitionId:
            PurchaseRequisitionModel.objects.filter(id=obj.requisitionId, tenantId=t).update(
                status="ordered"
            )
        return Response(successEnvelope(purchaseOrderDetail(obj)), status=201)


class PurchaseOrderDetailView(Base):
    def get(self, request, purchaseOrderId):
        return Response(
            successEnvelope(
                purchaseOrderDetail(
                    PurchaseOrderModel.objects.get(id=purchaseOrderId, tenantId=tenant())
                )
            )
        )

    def post(self, request, purchaseOrderId, action):
        obj = PurchaseOrderModel.objects.get(id=purchaseOrderId, tenantId=tenant())
        target = {"submit": "submitted", "approve": "approved", "cancel": "cancelled"}.get(action)
        if not target:
            return Response(successEnvelope({"error": "unknown action"}), status=400)
        obj.status = target
        obj.save(update_fields=["status", "updatedAt"])
        ProcurementApprovalModel.objects.create(
            tenantId=obj.tenantId,
            documentType="purchaseOrder",
            documentId=obj.id,
            action=action,
            comment=str(request.data.get("comment", "")),
        )
        return Response(successEnvelope(purchaseOrderDetail(obj)))


class ReceiptListView(Base):
    def get(self, request):
        return Response(
            successEnvelope(
                [row(x) for x in GoodsReceiptModel.objects.filter(tenantId=tenant())[:500]]
            )
        )

    @transaction.atomic
    def post(self, request):
        s = ReceiptSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        t = tenant()
        raw = data.pop("lines")
        po = PurchaseOrderModel.objects.get(id=data["purchaseOrderId"], tenantId=t)
        guardOrderAcceptsDelivery(po.status, po.number)
        rec = GoodsReceiptModel.objects.create(
            tenantId=t, number=f"GR-{uuid.uuid4().hex[:8].upper()}", status="posted", **data
        )
        # Quantities already claimed by earlier lines of *this* receipt: each
        # could pass on its own while together they exceed what was ordered.
        pending: dict[str, Decimal] = {}
        for item in raw:
            line = PurchaseOrderLineModel.objects.get(
                id=item["purchaseOrderLineId"], purchaseOrderId=po.id, tenantId=t
            )
            label = line.partName or line.partCode
            # A refusal below aborts the atomic block, so the receipt row
            # created above rolls back with it: nothing half-posted.
            qty = asQuantity(item["quantity"], f"مقدار دریافتی «{label}»")
            rejected = asQuantity(item.get("rejectedQuantity", 0), f"مقدار مردودی «{label}»")
            accepted = guardReceiptLine(
                label,
                line.orderedQuantity,
                line.receivedQuantity,
                pending.get(str(line.id), Decimal("0")),
                qty,
                rejected,
            )
            pending[str(line.id)] = pending.get(str(line.id), Decimal("0")) + accepted
            GoodsReceiptLineModel.objects.create(
                tenantId=t,
                receiptId=rec.id,
                purchaseOrderLineId=line.id,
                partId=line.partId,
                quantity=qty,
                unitCost=Decimal(str(item.get("unitCost", line.unitPrice))),
                rejectedQuantity=rejected,
            )
            line.receivedQuantity += accepted
            line.save(update_fields=["receivedQuantity", "updatedAt"])
            # Stock movement goes through maintenance's public application
            # contract: it owns the ledger and takes the row lock.
            recordGoodsReceipt(
                tenantId=t,
                partId=line.partId,
                quantity=accepted,
                unitCost=Decimal(str(item.get("unitCost", line.unitPrice))),
                reference=rec.number,
                note="رسید خرید",
            )
        lines = list(PurchaseOrderLineModel.objects.filter(purchaseOrderId=po.id, tenantId=t))
        po.status = (
            "received"
            if all(x.receivedQuantity >= x.orderedQuantity for x in lines)
            else "partiallyReceived"
        )
        po.save(update_fields=["status", "updatedAt"])
        return Response(
            successEnvelope(
                row(
                    rec,
                    {
                        "lines": [
                            row(x)
                            for x in GoodsReceiptLineModel.objects.filter(
                                receiptId=rec.id, tenantId=t
                            )
                        ]
                    },
                )
            ),
            status=201,
        )


class ReturnListView(Base):
    def get(self, request):
        return Response(
            successEnvelope(
                [row(x) for x in PurchaseReturnModel.objects.filter(tenantId=tenant())[:500]]
            )
        )

    @transaction.atomic
    def post(self, request):
        s = ReturnSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        data = s.validated_data
        t = tenant()
        raw = data.pop("lines")
        obj = PurchaseReturnModel.objects.create(
            tenantId=t, number=f"RET-{uuid.uuid4().hex[:8].upper()}", status="posted", **data
        )
        for item in raw:
            qty = Decimal(str(item["quantity"]))
            partId = item["partId"]
            PurchaseReturnLineModel.objects.create(
                tenantId=t,
                returnId=obj.id,
                partId=partId,
                quantity=qty,
                unitCost=item.get("unitCost", 0),
            )
            # The contract takes the row lock and refuses an overdraw itself,
            # so the old read-then-check-then-write race is gone.
            try:
                recordSupplierReturn(
                    tenantId=t,
                    partId=partId,
                    quantity=qty,
                    reference=obj.number,
                    note="برگشت به تأمین‌کننده",
                )
            except ValueError as error:
                raise serializers.ValidationError("موجودی برای برگشت کافی نیست") from error
        return Response(successEnvelope(row(obj)), status=201)


class InvoiceListView(Base):
    def get(self, request):
        return Response(
            successEnvelope(
                [row(x) for x in SupplierInvoiceModel.objects.filter(tenantId=tenant())[:500]]
            )
        )

    def post(self, request):
        s = InvoiceSerializer(data=request.data)
        s.is_valid(raise_exception=True)
        return Response(
            successEnvelope(
                row(SupplierInvoiceModel.objects.create(tenantId=tenant(), **s.validated_data))
            ),
            status=201,
        )


class ProcurementDashboardView(Base):
    def get(self, request):
        t = tenant()
        return Response(
            successEnvelope(
                {
                    "suppliers": SupplierModel.objects.filter(tenantId=t, status="active").count(),
                    "openRequisitions": PurchaseRequisitionModel.objects.filter(
                        tenantId=t, status__in=["draft", "submitted", "approved"]
                    ).count(),
                    "openPurchaseOrders": PurchaseOrderModel.objects.filter(
                        tenantId=t, status__in=["submitted", "approved", "partiallyReceived"]
                    ).count(),
                    "pendingReceipts": PurchaseOrderModel.objects.filter(
                        tenantId=t, status__in=["approved", "partiallyReceived"]
                    ).count(),
                    "invoiceTotal": sum(
                        (x.total for x in SupplierInvoiceModel.objects.filter(tenantId=t)),
                        Decimal("0"),
                    ),
                }
            )
        )


class ApprovalHistoryView(Base):
    """Immutable approval trail for requisitions and purchase orders."""

    def get(self, request, documentType, documentId):
        if documentType not in {"requisition", "purchaseOrder"}:
            return Response(successEnvelope({"error": "unknown document type"}), status=400)
        items = ProcurementApprovalModel.objects.filter(
            tenantId=tenant(), documentType=documentType, documentId=documentId
        )
        return Response(successEnvelope([row(item) for item in items]))


class ProcurementSupplierPerformanceView(Base):
    """Supplier delivery and purchasing summary for the current tenant."""

    def get(self, request):
        t = tenant()
        result = []
        for supplier in SupplierModel.objects.filter(tenantId=t, status="active"):
            orders = list(PurchaseOrderModel.objects.filter(tenantId=t, supplierId=supplier.id))
            received = [x for x in orders if x.status == "received"]
            on_time = sum(
                1 for x in received if not x.expectedDate or x.updatedAt.date() <= x.expectedDate
            )
            result.append(
                {
                    "supplierId": str(supplier.id),
                    "supplierName": supplier.name,
                    "orders": len(orders),
                    "receivedOrders": len(received),
                    "onTimeOrders": on_time,
                    "onTimeRate": round((on_time / len(received)) * 100, 1) if received else 0,
                    "averageLeadTimeDays": supplier.defaultLeadTimeDays,
                }
            )
        return Response(successEnvelope(result))
