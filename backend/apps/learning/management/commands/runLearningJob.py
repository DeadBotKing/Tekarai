"""Operational replay command for a durable Phase 16 learning job."""

from django.core.management.base import BaseCommand, CommandError

from apps.learning.application.commands.learningCommands import ProcessLearningJobCommand
from apps.learning.infrastructure.container import processJobService


class Command(BaseCommand):
    help = "Process one durable learning job by identifier (replay-safe)."

    def add_arguments(self, parser):
        parser.add_argument("jobId")

    def handle(self, *args, **options):
        try:
            result = processJobService().execute(ProcessLearningJobCommand(options["jobId"]))
        except Exception as exc:
            raise CommandError(str(exc)) from exc
        self.stdout.write(self.style.SUCCESS(str(result)))
