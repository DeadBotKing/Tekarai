"""Root URL configuration for the Tekarai backend.

Phase 06: every business surface is versioned under ``/api/v1/`` (§13);
health endpoints remain framework-level (Phase 01).
"""

from __future__ import annotations

from django.urls import include, path

from config import healthCheck

urlpatterns = [
    path("healthz/", healthCheck.healthLive, name="healthLive"),
    path("readyz/", healthCheck.healthReady, name="healthReady"),
    path(
        "api/v1/",
        include(
            [
                path("", include("apps.sharedKernel.presentation.api.platformRoutes")),
                path("", include("apps.tenancy.presentation.api.urls.tenantRoutes")),
                path("", include("apps.identity.presentation.api.urls.identityRoutes")),
            ]
        ),
    ),
]
