"""Documents library route map (Phase 31)."""

from __future__ import annotations

from django.urls import path

from apps.documents.presentation.api.views.documentViews import (
    DocumentDetailView,
    DocumentDownloadView,
    DocumentListView,
)

app_name = "documents"

urlpatterns = [
    path("documents", DocumentListView.as_view(), name="documentsList"),
    path(
        "documents/<uuid:documentId>/download",
        DocumentDownloadView.as_view(),
        name="documentsDownload",
    ),
    path(
        "documents/<uuid:documentId>",
        DocumentDetailView.as_view(),
        name="documentsDetail",
    ),
]
