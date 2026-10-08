from django.urls import path

from .views import (
    AccessMatrixView,
    AssignmentDetailView,
    AssignmentListView,
    DepartmentDetailView,
    DepartmentListView,
    MyAccessView,
    OrganizationAuditView,
    PositionDetailView,
    PositionListView,
    SeedOrganizationView,
)

urlpatterns = [
    path("departments", DepartmentListView.as_view()),
    path("departments/<uuid:departmentId>", DepartmentDetailView.as_view()),
    path("positions", PositionListView.as_view()),
    path("positions/<uuid:positionId>", PositionDetailView.as_view()),
    path("assignments", AssignmentListView.as_view()),
    path("assignments/<uuid:assignmentId>", AssignmentDetailView.as_view()),
    path("access-matrix", AccessMatrixView.as_view()),
    path("my-access", MyAccessView.as_view()),
    path("audit", OrganizationAuditView.as_view()),
    path("seed", SeedOrganizationView.as_view()),
]
