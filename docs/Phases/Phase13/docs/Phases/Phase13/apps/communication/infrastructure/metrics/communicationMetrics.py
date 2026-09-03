"""Communication metrics registry (Phase 08 §39).

Counters/gauges named exactly as the spec requires:
messagesPerSecond, activeConnections, activeCalls, activeMeetings,
websocketErrors, messageDeliveryLatency, eventProcessingLatency,
failedSignalingRequests.

§39 logging rule honoured everywhere: no passwords, tokens or message
bodies are ever recorded — counters only.
"""

from __future__ import annotations

import threading
import time
from collections import deque
from typing import Any


class CommunicationMetrics:
    """Process-local registry; a Prometheus exporter can scrape ``snapshot``."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counters: dict[str, int] = {
            "messagesSent": 0,
            "failedSignalingRequests": 0,
            "websocketErrors": 0,
            "callsStarted": 0,
            "meetingsStarted": 0,
            "outboxEventsPublished": 0,
        }
        self._gauges: dict[str, int] = {
            "activeConnections": 0,
            "activeCalls": 0,
            "activeMeetings": 0,
        }
        self._messageTimestamps: deque[float] = deque(maxlen=10_000)
        self._messageDeliveryLatencies: deque[float] = deque(maxlen=1_000)
        self._eventProcessingLatencies: deque[float] = deque(maxlen=1_000)

    # -- counters -----------------------------------------------------------

    def increment(self, name: str, amount: int = 1) -> None:
        with self._lock:
            if name in self._gauges:
                self._gauges[name] += amount
            else:
                self._counters[name] = self._counters.get(name, 0) + amount
            if name == "messagesSent":
                self._messageTimestamps.append(time.monotonic())

    def decrement(self, name: str, amount: int = 1) -> None:
        with self._lock:
            if name in self._gauges:
                self._gauges[name] -= amount

    def observeMessageDelivery(self, sendStartedAt: float) -> None:
        with self._lock:
            self._messageDeliveryLatencies.append(time.monotonic() - sendStartedAt)

    def observeEventProcessing(self, seconds: float) -> None:
        with self._lock:
            self._eventProcessingLatencies.append(seconds)

    # -- readings -----------------------------------------------------------

    @staticmethod
    def _avg(values: deque[float]) -> float:
        return round(sum(values) / len(values), 6) if values else 0.0

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            now = time.monotonic()
            recent = [t for t in self._messageTimestamps if now - t <= 1.0]
            delivery = list(self._messageDeliveryLatencies)
            processing = list(self._eventProcessingLatencies)
            return {
                "messagesPerSecond": len(recent),
                "activeConnections": self._gauges["activeConnections"],
                "activeCalls": self._gauges["activeCalls"],
                "activeMeetings": self._gauges["activeMeetings"],
                "websocketErrors": self._counters["websocketErrors"],
                "messageDeliveryLatencyMs": round(self._avg(delivery) * 1000, 3),
                "eventProcessingLatencyMs": round(self._avg(processing) * 1000, 3),
                "failedSignalingRequests": self._counters["failedSignalingRequests"],
                "messagesSent": self._counters["messagesSent"],
                "outboxEventsPublished": self._counters["outboxEventsPublished"],
            }


_metricsSingleton: CommunicationMetrics | None = None


def communicationMetrics() -> CommunicationMetrics:
    global _metricsSingleton
    if _metricsSingleton is None:
        _metricsSingleton = CommunicationMetrics()
    return _metricsSingleton
