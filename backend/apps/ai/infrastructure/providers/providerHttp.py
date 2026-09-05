"""Minimal JSON-over-HTTP transport for provider adapters (Phase 13-L).

Decision L-D1: zero new dependencies. The house precedent (in-house JWT in
ADR-022, in-house OpenAPI builder in ADR-020) applies — provider calls need
plain JSON POST/GET with timeouts and streaming line iteration, which the
standard library ``urllib`` covers. A vendor SDK would drag release cycles
into the platform without adding capability in this sub-phase.

The transport is framework-free and injectable: adapters receive it through
their constructor, so tests can substitute a fake transport without sockets
and integration tests can run against a real local HTTP server.
"""

from __future__ import annotations

import json
import socket
import ssl
from collections.abc import Iterator
from dataclasses import dataclass, field
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from apps.ai.infrastructure.providers.providerErrors import (
    TransportConnectionFailed,
    TransportTimeout,
)

DEFAULT_TIMEOUT_SECONDS = 30.0
STREAM_CHUNK_SIZE = 4096


@dataclass(frozen=True)
class HttpResponse:
    """Normalized transport result; body stays raw until the adapter parses it."""

    status: int
    body: bytes
    headers: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return 200 <= self.status < 300


class UrllibJsonTransport:
    """Standard-library JSON transport with timeouts and line streaming."""

    def __init__(self, *, timeoutSeconds: float = DEFAULT_TIMEOUT_SECONDS) -> None:
        if timeoutSeconds <= 0:
            raise ValueError("Transport timeout must be positive.")
        self.timeoutSeconds = float(timeoutSeconds)

    def request(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeoutSeconds: float | None = None,
    ) -> HttpResponse:
        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, method=method.upper())
        request.add_header("Accept", "application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urlopen(request, timeout=timeoutSeconds or self.timeoutSeconds) as response:
                return HttpResponse(
                    status=response.status,
                    body=response.read(),
                    headers={key: value for key, value in response.headers.items()},
                )
        except HTTPError:
            # Non-2xx responses surface as HTTPError; the provider error
            # mapper (not the transport) owns their classification.
            raise
        except TimeoutError as exc:
            raise TransportTimeout(str(exc) or "provider call timed out") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, socket.timeout):
                raise TransportTimeout(str(reason)) from exc
            raise TransportConnectionFailed(str(exc) or "provider unreachable") from exc
        except ssl.SSLError as exc:
            raise TransportConnectionFailed(f"TLS failure: {exc}") from exc

    def streamLines(
        self,
        method: str,
        url: str,
        *,
        payload: dict[str, Any] | None = None,
        headers: dict[str, str] | None = None,
        timeoutSeconds: float | None = None,
    ) -> Iterator[str]:
        """Yield response lines for streaming protocols (SSE / NDJSON)."""

        body = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = Request(url, data=body, method=method.upper())
        request.add_header("Accept", "text/event-stream, application/x-ndjson, application/json")
        if body is not None:
            request.add_header("Content-Type", "application/json")
        for key, value in (headers or {}).items():
            request.add_header(key, value)
        try:
            with urlopen(request, timeout=timeoutSeconds or self.timeoutSeconds) as response:
                buffer = b""
                while True:
                    chunk = response.read(STREAM_CHUNK_SIZE)
                    if not chunk:
                        break
                    buffer += chunk
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        yield line.decode("utf-8", errors="replace").strip()
                if buffer.strip():
                    yield buffer.decode("utf-8", errors="replace").strip()
        except HTTPError:
            raise
        except TimeoutError as exc:
            raise TransportTimeout(str(exc) or "provider stream timed out") from exc
        except URLError as exc:
            reason = getattr(exc, "reason", None)
            if isinstance(reason, socket.timeout):
                raise TransportTimeout(str(reason)) from exc
            raise TransportConnectionFailed(str(exc) or "provider unreachable") from exc


__all__ = [
    "DEFAULT_TIMEOUT_SECONDS",
    "HttpResponse",
    "UrllibJsonTransport",
]
