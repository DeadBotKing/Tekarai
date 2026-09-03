"""Tenancy routes — mounted under /api/v1/ (Phase 06 §13).

Registered when the context's urls package is imported by config/urls.py.
"""

from __future__ import annotations

from django.urls import path

from apps.tenancy.presentation.api.views.tenantViews import (
    TenantDetailView,
    TenantListView,
    TenantStatusView,
    registerTenancyEndpoints,
)

urlpatterns = [
    path("tenants", TenantListView.as_view(), name="tenantList"),
    path("tenants/<uuid:tenantId>", TenantDetailView.as_view(), name="tenantDetail"),
    path(
        "tenants/<uuid:tenantId>/status",
        TenantStatusView.as_view(),
        name="tenantStatus",
    ),
]

registerTenancyEndpoints()
