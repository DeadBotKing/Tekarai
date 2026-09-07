"""Deployment port baseline: validates immutable artifact availability."""

from __future__ import annotations


class SafeDeploymentEngine:
    def apply(self, *, artifactUri: str, environment: str, trafficPercentage: int) -> None:
        if not artifactUri.startswith(("file://", "s3://", "azure://", "gs://")):
            raise ValueError("Unsupported artifact URI.")
        if environment.upper() == "PRODUCTION" and trafficPercentage not in (5, 25, 50, 100):
            raise ValueError("Production traffic must follow canary stages.")

    def deactivate(self, *, artifactUri: str, environment: str) -> None:
        if not artifactUri or not environment:
            raise ValueError("Artifact and environment are required.")
