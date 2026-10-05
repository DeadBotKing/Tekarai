"""Initial migration for the documents context."""

from __future__ import annotations

import uuid
from pathlib import Path

import django.utils.timezone
from django.db import migrations, models


def documentStoragePath(instance, filename):
    return str(Path("documents") / str(instance.tenantId) / str(instance.id) / filename)


class Migration(migrations.Migration):
    initial = True
    dependencies = []

    operations = [
        migrations.CreateModel(
            name="DocumentModel",
            fields=[
                (
                    "id",
                    models.UUIDField(
                        primary_key=True, default=uuid.uuid4, editable=False, serialize=False
                    ),
                ),
                ("tenantId", models.UUIDField(db_index=True)),
                ("name", models.CharField(max_length=300)),
                ("contentType", models.CharField(blank=True, default="", max_length=200)),
                ("sizeBytes", models.BigIntegerField(default=0)),
                ("category", models.CharField(blank=True, default="", max_length=80)),
                ("description", models.TextField(blank=True, default="")),
                ("file", models.FileField(max_length=500, upload_to=documentStoragePath)),
                ("uploadedByIdentifier", models.CharField(blank=True, default="", max_length=200)),
                ("uploadedAt", models.DateTimeField(default=django.utils.timezone.now)),
                ("deletedAt", models.DateTimeField(blank=True, null=True)),
            ],
            options={
                "db_table": "documents_document",
                "ordering": ["-uploadedAt"],
            },
        ),
    ]
