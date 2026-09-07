"""Durable Phase 16 queue adapters."""

from __future__ import annotations

from django.db import transaction


class CeleryLearningJobQueue:
    def publish(self, jobId: str) -> None:
        from apps.learning.infrastructure.queue.learningJobs import processLearningJob

        transaction.on_commit(lambda: processLearningJob.delay(jobId))


class InlineLearningJobQueue:
    """Development adapter; still runs after transaction commit."""

    def publish(self, jobId: str) -> None:
        from apps.learning.application.commands.learningCommands import ProcessLearningJobCommand
        from apps.learning.infrastructure.container import processJobService

        transaction.on_commit(
            lambda: processJobService().execute(ProcessLearningJobCommand(jobId=jobId))
        )
