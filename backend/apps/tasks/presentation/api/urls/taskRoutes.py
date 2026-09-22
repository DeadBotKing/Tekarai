"""Tasks routes — mounted under /api/v1/tasks/."""

from __future__ import annotations

from django.urls import path

from apps.tasks.presentation.api.views.taskViews import (
    TaskDetailView,
    TaskListView,
    TaskStatusView,
)

urlpatterns = [
    path("", TaskListView.as_view(), name="taskList"),
    path("<uuid:taskId>", TaskDetailView.as_view(), name="taskDetail"),
    path("<uuid:taskId>/status", TaskStatusView.as_view(), name="taskStatus"),
]
