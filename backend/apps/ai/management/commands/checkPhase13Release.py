"""Fail-closed operational gate for the Phase 13-Z release."""

from __future__ import annotations

import json
from typing import Any

from django.core.management.base import BaseCommand, CommandError

from apps.ai.infrastructure.container import releaseReadiness


class Command(BaseCommand):
    help = "Check Phase 13 migrations, provider/model configuration, queue and audit readiness."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--allow-not-ready",
            action="store_true",
            help="Print the report without returning a failing exit status.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        report = releaseReadiness()
        rendered = json.dumps(report, indent=2, sort_keys=True)
        if report["ready"]:
            self.stdout.write(self.style.SUCCESS(rendered))
            return
        if options["allow_not_ready"]:
            self.stdout.write(self.style.WARNING(rendered))
            return
        raise CommandError(rendered)
