"""Phase 17 asynchronous workers with retry policy."""

from __future__ import annotations

import uuid

from celery import shared_task

from apps.projectIntelligence.application.commands.intelligenceCommands import (
    ProcessIntelligenceJobCommand,
)


@shared_task(
    name="projectIntelligence.processJob",
    bind=True,
    autoretry_for=(OSError,),
    retry_backoff=True,
    retry_jitter=True,
    max_retries=3,
)
def processIntelligenceJob(self, jobId: str):
    from apps.projectIntelligence.infrastructure import container

    return container.processJobService().execute(ProcessIntelligenceJobCommand(uuid.UUID(jobId)))
