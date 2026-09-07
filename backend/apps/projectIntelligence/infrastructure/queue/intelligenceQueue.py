"""Reliable Celery queue adapter."""

from __future__ import annotations

import uuid

from django.db import transaction


class CeleryIntelligenceJobQueue:
    def publish(self, jobId: uuid.UUID) -> None:
        from apps.projectIntelligence.infrastructure.queue.intelligenceJobs import (
            processIntelligenceJob,
        )

        transaction.on_commit(
            lambda: processIntelligenceJob.apply_async(
                args=[str(jobId)], queue="project-intelligence.analysis"
            )
        )
