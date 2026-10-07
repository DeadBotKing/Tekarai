"""Write a restorable backup of every business table.

`manage.py dumpdata` does not work on this project, and fails silently.

Django only dumps apps whose `models_module` is set, which means apps with a
`models.py` at their root. This codebase deliberately keeps models in
`infrastructure/models.py` — `tests/architecture/testPhase4DatabaseArchitecture`
enforces it — so every business app has `models_module = None` and `dumpdata`
skips all of them without a word. The resulting file contains
`contenttypes` and `auth.permission` and nothing else: 20 records standing in
for the entire database. An operator following the obvious Django backup
procedure would not discover this until a restore, which is the worst
possible moment.

This command collects the models through the app registry instead of the
models module, and writes a fixture `loaddata` can read back.

    python manage.py backupData --output backup.json
    python manage.py loaddata backup.json
"""

from __future__ import annotations

from typing import Any

from django.apps import apps
from django.core import serializers
from django.core.management.base import BaseCommand, CommandError
from django.db.models import Model

#: Apps whose tables carry tenant data. `contenttypes` and `auth` are
#: recreated by migrations; including them makes a restore collide on
#: primary keys for no benefit.
BUSINESS_APPS: tuple[str, ...] = (
    "ai",
    "analytics",
    "communication",
    "documents",
    "identity",
    "learning",
    "maintenance",
    "notifications",
    "procurement",
    "projectIntelligence",
    "projects",
    "sharedKernel",
    "tasks",
    "tenancy",
)


def collectModels(appLabels: tuple[str, ...]) -> list[type[Model]]:
    """Every concrete model in the named apps, taken from the registry."""

    collected: list[type[Model]] = []
    for label in appLabels:
        try:
            config = apps.get_app_config(label)
        except LookupError as exc:
            raise CommandError(f"Unknown app label: {label}") from exc
        for model in config.get_models():
            if model._meta.proxy or not model._meta.managed:
                continue
            collected.append(model)
    return collected


class Command(BaseCommand):
    help = "Dump all business tables to a loaddata-compatible fixture."

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--output",
            default="",
            help="File to write. Defaults to stdout.",
        )
        parser.add_argument(
            "--format",
            default="json",
            help="Serialization format (json, jsonl, xml, yaml).",
        )
        parser.add_argument(
            "--apps",
            default="",
            help="Comma-separated app labels. Defaults to every business app.",
        )
        parser.add_argument(
            "--tenant",
            default="",
            help="Limit to one tenantId where the model is tenant-scoped.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        labels = (
            tuple(label.strip() for label in options["apps"].split(",") if label.strip())
            or BUSINESS_APPS
        )
        models = collectModels(labels)
        tenantId = options["tenant"].strip()

        records: list[Model] = []
        skipped: list[str] = []
        for model in models:
            queryset = model._base_manager.using("default").all()
            if tenantId:
                if not any(field.name == "tenantId" for field in model._meta.fields):
                    skipped.append(model._meta.label)
                    continue
                queryset = queryset.filter(tenantId=tenantId)
            records.extend(queryset.iterator())

        payload = serializers.serialize(
            options["format"],
            records,
            indent=2,
            use_natural_foreign_keys=False,
            use_natural_primary_keys=False,
        )

        destination = options["output"]
        if destination:
            with open(destination, "w", encoding="utf-8") as handle:
                handle.write(payload)
            self.stderr.write(
                f"backupData: {len(records)} records from {len(models)} models "
                f"written to {destination}"
            )
        else:
            # self.stdout, not sys.stdout: call_command redirects the former,
            # and writing to the latter makes the command untestable.
            self.stdout.write(payload)

        if skipped:
            self.stderr.write(
                f"backupData: {len(skipped)} models have no tenantId and were "
                f"skipped by --tenant: {', '.join(sorted(skipped)[:5])}…"
            )
