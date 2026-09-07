"""Celery application for durable Phase 15 asynchronous work."""

from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.production")

app = Celery("tekarai")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()

__all__ = ["app"]
