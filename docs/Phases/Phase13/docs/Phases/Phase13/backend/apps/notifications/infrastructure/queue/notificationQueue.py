"""§31 queue seam — the broker stays replaceable.

``InlineNotificationQueue`` executes the worker synchronously after the
creating transaction commits (development + tests). ``runNotificationWorker``
is the independent tick that picks up anything the inline pass missed
(crash recovery §42). A Celery/RQ adapter would implement the same
``NotificationJobQueue`` port with zero application changes.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


class InlineNotificationQueue:
    """Default queue: dispatch immediately, never lose the job."""

    def submit(self, job: dict[str, Any]) -> None:
        if job.get("kind") != "DISPATCH":
            logger.warning("Unknown job kind ignored", extra={"kind": job.get("kind")})
            return
        from apps.notifications.infrastructure.container import container

        try:
            container.dispatchService().dispatchOne(job["notificationId"])
        except Exception:  # noqa: BLE001 — queue boundary isolation (§47)
            logger.exception(
                "Inline dispatch failed; the worker tick will retry",
                extra={"notificationId": job.get("notificationId")},
            )
