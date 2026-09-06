"""Phase 13-Z routes — mounted under ``/api/v1/ai/``."""

from django.urls import path

from apps.ai.presentation.api.views import (
    AgentDetailView,
    AgentLifecycleView,
    AgentListView,
    AgentRunCreateView,
    AgentVersionView,
    ApprovalDecisionView,
    ApprovalDetailView,
    ApprovalListView,
    JobCancelView,
    JobDetailView,
    JobListView,
    ReleaseReadinessView,
    RunDetailView,
    RunListView,
    RunStepListView,
)

urlpatterns = [
    path("agents", AgentListView.as_view(), name="aiAgentList"),
    path("agents/<str:agentCode>/versions", AgentVersionView.as_view(), name="aiAgentVersion"),
    path("agents/<str:agentCode>/runs", AgentRunCreateView.as_view(), name="aiAgentRun"),
    path(
        "agents/<str:agentCode>/versions/<int:version>",
        AgentDetailView.as_view(),
        name="aiAgentDetail",
    ),
    path(
        "agents/<str:agentCode>/versions/<int:version>/<str:action>",
        AgentLifecycleView.as_view(),
        name="aiAgentLifecycle",
    ),
    path("runs", RunListView.as_view(), name="aiRunList"),
    path("runs/<str:runId>", RunDetailView.as_view(), name="aiRunDetail"),
    path("runs/<str:runId>/steps", RunStepListView.as_view(), name="aiRunSteps"),
    path("approvals", ApprovalListView.as_view(), name="aiApprovalList"),
    path("approvals/<str:approvalId>", ApprovalDetailView.as_view(), name="aiApprovalDetail"),
    path(
        "approvals/<str:approvalId>/<str:action>",
        ApprovalDecisionView.as_view(),
        name="aiApprovalDecision",
    ),
    path("jobs", JobListView.as_view(), name="aiJobList"),
    path("jobs/<str:jobId>", JobDetailView.as_view(), name="aiJobDetail"),
    path("jobs/<str:jobId>/cancel", JobCancelView.as_view(), name="aiJobCancel"),
    path("release/readiness", ReleaseReadinessView.as_view(), name="aiReleaseReadiness"),
]
