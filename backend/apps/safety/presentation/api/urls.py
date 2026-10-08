from django.urls import path

from .views import (
    PermitActionView,
    PermitDetailView,
    PermitExpiryScanView,
    PermitIsolationActionView,
    PermitIsolationListView,
    PermitListView,
    PermitPrecautionView,
)

urlpatterns = [
    path("permits", PermitListView.as_view()),
    path("permits/expiry-scan", PermitExpiryScanView.as_view()),
    path("permits/<uuid:permitId>", PermitDetailView.as_view()),
    path("permits/<uuid:permitId>/isolations", PermitIsolationListView.as_view()),
    path(
        "permits/<uuid:permitId>/isolations/<uuid:isolationId>/<str:action>",
        PermitIsolationActionView.as_view(),
    ),
    path(
        "permits/<uuid:permitId>/precautions/<uuid:precautionId>/confirm",
        PermitPrecautionView.as_view(),
    ),
    path("permits/<uuid:permitId>/<str:action>", PermitActionView.as_view()),
]
