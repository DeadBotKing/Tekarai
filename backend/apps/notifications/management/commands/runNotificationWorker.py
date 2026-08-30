"""§31/§32 — independent notification worker tick.

Development runs this as a loop; production wires the same ``tick()``
call into any scheduler (cron, Celery beat, Kubernetes job) — the broker
stays replaceable because the queue port is the only entry point.

Usage:
    python manage.py runNotificationWorker [--once] [--interval 5]
"""

from __future__ import annotations

import logging
import time

from django.core.management.base import BaseCommand

logger = logging.getLogger(__name__)


def tick(limit: int = 100) -> dict:
    """One full worker pass: dispatch → retry → schedules → digests → expiry."""
    from apps.notifications.infrastructure.container import container

    summary: dict = {}
    summary["expired"] = container.expireNotificationsService().execute(
        type("ExpireCommand", (), {"limit": limit})()
    )["expired"]
    outcomes = container.dispatchService().dispatchPending(limit=limit)
    summary["dispatched"] = len(outcomes)
    summary["retry"] = container.retryService().execute(
        type("RetryCommand", (), {"limit": limit})()
    )
    summary["schedules"] = container.runDueSchedulesService().execute(
        type("SchedulesCommand", (), {"limit": limit})()
    )
    summary["digests"] = container.sendDigestService().execute(
        type("DigestCommand", (), {"kind": ""})()
    )
    return summary


class Command(BaseCommand):
    help = "Notification worker (§31/§32): dispatch, retry, schedules, digests, expiry."

    def add_arguments(self, parser) -> None:  # noqa: ANN001 — Django contract
        parser.add_argument("--once", action="store_true", help="Run one tick and exit.")
        parser.add_argument("--interval", type=int, default=5, help="Seconds between ticks.")
        parser.add_argument("--limit", type=int, default=100, help="Batch size per phase.")

    def handle(self, *args, **options) -> None:  # noqa: ANN002/ANN003 — Django contract
        if options["once"]:
            self.stdout.write(str(tick(limit=options["limit"])))
            return
        self.stdout.write(
            self.style.SUCCESS(
                f"Notification worker looping every {options['interval']}s (Ctrl+C to stop)."
            )
        )
        try:
            while True:
                startedAt = time.monotonic()
                summary = tick(limit=options["limit"])
                logger.info("Worker tick", extra={"summary": summary})
                elapsed = time.monotonic() - startedAt
                time.sleep(max(0.0, options["interval"] - elapsed))
        except KeyboardInterrupt:
            self.stdout.write(self.style.SUCCESS("Notification worker stopped."))
