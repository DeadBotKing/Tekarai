"""Root URL configuration for the Tekarai backend.

Phase 01 exposes only framework-level health endpoints. Business API routes
arrive with their phases under a versioned prefix (/api/v1/...).
"""

from django.urls import path

from config import healthCheck

urlpatterns = [
    path("healthz/", healthCheck.healthLive, name="healthLive"),
    path("readyz/", healthCheck.healthReady, name="healthReady"),
]
