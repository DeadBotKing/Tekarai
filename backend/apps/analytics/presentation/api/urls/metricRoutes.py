"""Analytics routes — mounted under /api/v1/analytics/."""

from __future__ import annotations

from django.urls import path

from apps.analytics.presentation.api.views.metricViews import (
    MetricDefinitionDetailView,
    MetricDefinitionListView,
    MetricReadingBatchView,
    MetricReadingDetailView,
    MetricReadingListView,
    MetricReadingSummaryView,
)

urlpatterns = [
    path("metric-definitions", MetricDefinitionListView.as_view(), name="metricDefinitionList"),
    path(
        "metric-definitions/<uuid:definitionId>",
        MetricDefinitionDetailView.as_view(),
        name="metricDefinitionDetail",
    ),
    # Static paths precede UUID capture.
    path("metric-readings/batch", MetricReadingBatchView.as_view(), name="metricReadingBatch"),
    path(
        "metric-readings/summary",
        MetricReadingSummaryView.as_view(),
        name="metricReadingSummary",
    ),
    path("metric-readings", MetricReadingListView.as_view(), name="metricReadingList"),
    path(
        "metric-readings/<uuid:readingId>",
        MetricReadingDetailView.as_view(),
        name="metricReadingDetail",
    ),
]
