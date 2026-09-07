"""Phase 17 routes."""

from django.urls import path

from apps.projectIntelligence.presentation.api.views.intelligenceViews import (
    AnalyzeView,
    ArchitectureView,
    BuildContextView,
    ChangesView,
    CompareView,
    ContextView,
    DependenciesView,
    InsightsView,
    JobView,
    OverviewView,
    ReanalyzeView,
    RecommendationsView,
    ResumeView,
    SnapshotView,
    StateView,
)

urlpatterns = [
    path(
        "projects/<uuid:projectId>/intelligence/",
        OverviewView.as_view(),
        name="projectIntelligence",
    ),
    path(
        "projects/<uuid:projectId>/intelligence/snapshot/",
        SnapshotView.as_view(),
        name="projectIntelligenceSnapshot",
    ),
    path(
        "projects/<uuid:projectId>/intelligence/analyze/",
        AnalyzeView.as_view(),
        name="projectIntelligenceAnalyze",
    ),
    path(
        "projects/<uuid:projectId>/intelligence/reanalyze/",
        ReanalyzeView.as_view(),
        name="projectIntelligenceReanalyze",
    ),
    path("projects/<uuid:projectId>/intelligence/state/", StateView.as_view()),
    path("projects/<uuid:projectId>/intelligence/architecture/", ArchitectureView.as_view()),
    path("projects/<uuid:projectId>/intelligence/dependencies/", DependenciesView.as_view()),
    path("projects/<uuid:projectId>/intelligence/insights/", InsightsView.as_view()),
    path("projects/<uuid:projectId>/intelligence/recommendations/", RecommendationsView.as_view()),
    path("projects/<uuid:projectId>/intelligence/context/", ContextView.as_view()),
    path("projects/<uuid:projectId>/intelligence/context/build/", BuildContextView.as_view()),
    path("projects/<uuid:projectId>/intelligence/resume/", ResumeView.as_view()),
    path("projects/<uuid:projectId>/intelligence/changes/", ChangesView.as_view()),
    path("projects/<uuid:projectId>/intelligence/compare/", CompareView.as_view()),
    path(
        "project-intelligence/jobs/<uuid:jobId>/", JobView.as_view(), name="projectIntelligenceJob"
    ),
]
