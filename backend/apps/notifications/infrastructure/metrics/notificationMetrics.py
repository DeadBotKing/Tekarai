"""Notification metrics registry (Phase 09 §44).

Exact spec names: notificationsCreated, notificationsDelivered,
notificationsFailed, deliveryLatency, readRate, acknowledgementRate,
channelUsage, retryRate, providerFailureRate, notificationVolume.
No content ever enters a metric (§45).
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class NotificationMetrics:
    """Process-local registry; a Prometheus exporter can scrape
    ``snapshot``. Rates are computed lazily from repository counters."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {
            "notificationsCreated": 0,
            "notificationsDelivered": 0,
            "notificationsFailed": 0,
            "retryAttempts": 0,
            "providerFailures": 0,
            "digestsSent": 0,
            "escalationsRaised": 0,
        }
        self._channelUsage: dict[str, int] = {}
        self._deliveryLatencies: deque[float] = deque(maxlen=1_000)

    # -- writers --------------------------------------------------------------

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            if name.startswith("channelUsage."):
                channel = name.split(".", 1)[1]
                self._channelUsage[channel] = self._channelUsage.get(channel, 0) + amount
                return
            self._counters[name] = self._counters.get(name, 0) + amount

    def observeDeliveryLatency(self, seconds: float) -> None:
        with self._lock:
            self._deliveryLatencies.append(seconds)

    # -- §44 readings -----------------------------------------------------------

    @staticmethod
    def _avg(values: deque[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    def snapshot(
        self,
        *,
        totals: tuple[int, int, int] | None = None,
        channelUsage: dict[str, int] | None = None,
        retried: int | None = None,
    ) -> dict[str, Any]:
        """``totals`` = (total, read, acknowledged) from the repository —
        keeps readRate/acknowledgementRate honest instead of guessed."""
        with self._lock:
            counters = dict(self._counters)
            channelUsageSnapshot = dict(self._channelUsage)
            latencies = list(self._deliveryLatencies)
        created = counters.get("notificationsCreated", 0)
        delivered = counters.get("notificationsDelivered", 0)
        failed = counters.get("notificationsFailed", 0)
        snapshot: dict[str, Any] = {
            "notificationsCreated": created,
            "notificationsDelivered": delivered,
            "notificationsFailed": failed,
            "deliveryLatencyMs": round(self._avg(latencies) * 1000, 3),
            "channelUsage": channelUsageSnapshot or (channelUsage or {}),
            "retryAttempts": counters.get("retryAttempts", 0),
            "providerFailureRate": round(
                counters.get("providerFailures", 0) / created, 4
            ) if created else 0.0,
            "notificationVolume": created,
            "digestsSent": counters.get("digestsSent", 0),
            "escalationsRaised": counters.get("escalationsRaised", 0),
        }
        snapshot["retryRate"] = (
            round(counters.get("retryAttempts", 0) / delivered, 4) if delivered else 0.0
        )
        if totals is not None:
            total, read, acknowledged = totals
            snapshot["readRate"] = round(read / total, 4) if total else 0.0
            snapshot["acknowledgementRate"] = (
                round(acknowledged / total, 4) if total else 0.0
            )
        else:
            snapshot["readRate"] = 0.0
            snapshot["acknowledgementRate"] = 0.0
        return snapshot


_metricsSingleton: NotificationMetrics | None = None


def notificationMetrics() -> NotificationMetrics:
    global _metricsSingleton
    if _metricsSingleton is None:
        _metricsSingleton = NotificationMetrics()
    return _metricsSingleton
