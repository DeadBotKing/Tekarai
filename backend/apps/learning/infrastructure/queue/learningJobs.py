"""Celery jobs for replay-safe, identifier-only Phase 16 work."""

from __future__ import annotations

from celery import shared_task

from apps.learning.application.commands.learningCommands import ProcessLearningJobCommand


@shared_task(
    bind=True,
    name="learning.processJob",
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=900,
    retry_jitter=True,
    max_retries=3,
    acks_late=True,
)
def processLearningJob(self, jobId: str) -> dict:  # noqa: ARG001
    from apps.learning.infrastructure.container import processJobService

    return processJobService().execute(ProcessLearningJobCommand(jobId=jobId))


@shared_task(name="learning.monitorDeployments", acks_late=True)
def monitorLearningDeployments() -> dict:
    # Provider-specific telemetry ingestion uses the public metric service.
    # This heartbeat proves scheduler liveness without fabricating observations.
    return {"status": "READY"}
