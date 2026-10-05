from django.urls import path

from .views import (
    ApprovalHistoryView,
    InvoiceListView,
    ProcurementDashboardView,
    ProcurementSupplierPerformanceView,
    PurchaseOrderDetailView,
    PurchaseOrderListView,
    ReceiptListView,
    RequisitionActionView,
    RequisitionListView,
    ReturnListView,
    SupplierDetailView,
    SupplierListView,
    SupplierPartsView,
)

urlpatterns = [
    path("dashboard", ProcurementDashboardView.as_view()),
    path("approval-history/<str:documentType>/<uuid:documentId>", ApprovalHistoryView.as_view()),
    path("supplier-performance", ProcurementSupplierPerformanceView.as_view()),
    path("suppliers", SupplierListView.as_view()),
    path("suppliers/<uuid:supplierId>", SupplierDetailView.as_view()),
    path("suppliers/<uuid:supplierId>/parts", SupplierPartsView.as_view()),
    path("requisitions", RequisitionListView.as_view()),
    path("requisitions/<uuid:requisitionId>/<str:action>", RequisitionActionView.as_view()),
    path("purchase-orders", PurchaseOrderListView.as_view()),
    path("purchase-orders/<uuid:purchaseOrderId>", PurchaseOrderDetailView.as_view()),
    path("purchase-orders/<uuid:purchaseOrderId>/<str:action>", PurchaseOrderDetailView.as_view()),
    path("receipts", ReceiptListView.as_view()),
    path("returns", ReturnListView.as_view()),
    path("invoices", InvoiceListView.as_view()),
]
