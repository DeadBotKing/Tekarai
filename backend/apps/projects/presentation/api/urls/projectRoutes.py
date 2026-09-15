"""Projects routes — mounted under /api/v1/projects/."""

from __future__ import annotations

from django.urls import path

from apps.projects.presentation.api.views.projectViews import (
    ProjectDetailView,
    ProjectListView,
    ProjectStatusView,
)

urlpatterns = [
    path("", ProjectListView.as_view(), name="projectList"),
    path("<uuid:projectId>", ProjectDetailView.as_view(), name="projectDetail"),
    path("<uuid:projectId>/status", ProjectStatusView.as_view(), name="projectStatus"),
]
