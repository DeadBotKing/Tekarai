"""Phase 16 API routes."""

from django.urls import path

from apps.learning.presentation.api.views.learningViews import (
    ArtifactActionView,
    ArtifactDetailView,
    ArtifactListView,
    DatasetBuildView,
    DatasetListView,
    DatasetValidateView,
    DeploymentListView,
    DriftView,
    ExperienceListView,
    ExperimentListView,
    ExperimentRunView,
    FeedbackView,
    JobDetailView,
    MetricsView,
)

urlpatterns = [
    path("experiences/", ExperienceListView.as_view(), name="learningExperiences"),
    path("datasets/", DatasetListView.as_view(), name="learningDatasets"),
    path(
        "datasets/<uuid:datasetId>/build/", DatasetBuildView.as_view(), name="learningDatasetBuild"
    ),
    path(
        "datasets/<uuid:datasetId>/validate/",
        DatasetValidateView.as_view(),
        name="learningDatasetValidate",
    ),
    path("experiments/", ExperimentListView.as_view(), name="learningExperiments"),
    path(
        "experiments/<uuid:experimentId>/run/",
        ExperimentRunView.as_view(),
        name="learningExperimentRun",
    ),
    path("artifacts/", ArtifactListView.as_view(), name="learningArtifacts"),
    path("artifacts/<uuid:artifactId>/", ArtifactDetailView.as_view(), name="learningArtifact"),
    path(
        "artifacts/<uuid:artifactId>/<str:action>/",
        ArtifactActionView.as_view(),
        name="learningArtifactAction",
    ),
    path("deployments/", DeploymentListView.as_view(), name="learningDeployments"),
    path("jobs/<uuid:jobId>/", JobDetailView.as_view(), name="learningJob"),
    path("metrics/", MetricsView.as_view(), name="learningMetrics"),
    path("drift/", DriftView.as_view(), name="learningDrift"),
    path("feedback/", FeedbackView.as_view(), name="learningFeedback"),
]
