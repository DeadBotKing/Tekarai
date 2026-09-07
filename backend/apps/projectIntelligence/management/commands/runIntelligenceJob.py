import uuid

from django.core.management.base import BaseCommand, CommandError

from apps.projectIntelligence.application.commands.intelligenceCommands import (
    ProcessIntelligenceJobCommand,
)
from apps.projectIntelligence.infrastructure import container


class Command(BaseCommand):
    help = "Process one queued Project Intelligence job"

    def add_arguments(self, parser):
        parser.add_argument("job_id")

    def handle(self, *args, **options):
        try:
            jobId = uuid.UUID(options["job_id"])
        except ValueError as exc:
            raise CommandError("Invalid job UUID") from exc
        result = container.processJobService().execute(ProcessIntelligenceJobCommand(jobId))
        self.stdout.write(self.style.SUCCESS(str(result)))
