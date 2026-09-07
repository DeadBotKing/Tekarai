"""Idempotent Celery entry points for Phase 15.

Persistent database rows are the source of truth. Messages carry identifiers only,
so broker redelivery or worker restart cannot lose or duplicate a notification.
"""

from __future__ import annotations

from celery import shared_task


@shared_task(
    bind=True,
    autoretry_for=(ConnectionError, TimeoutError),
    retry_backoff=True,
    retry_backoff_max=600,
    retry_jitter=True,
    max_retries=5,
    name="notifications.dispatch",
)
def dispatchNotificationJob(self, notificationId: str) -> str:  # noqa: ARG001
    from apps.notifications.infrastructure.container import container

    # Dispatch service checks persisted status/deliveries, making redelivery safe.
    container.dispatchService().dispatchOne(notificationId)
    return notificationId


@shared_task(name="notifications.workerTick")
def notificationWorkerTick(limit: int = 200) -> dict:
    from apps.notifications.infrastructure import container as phase12Container
    from apps.notifications.management.commands.runNotificationWorker import tick

    result = tick(limit=limit)
    result["broadcastRetries"] = phase12Container.deliveryRetryService().processDue(limit=limit)
    return result


__all__ = ["dispatchNotificationJob", "notificationWorkerTick"]
