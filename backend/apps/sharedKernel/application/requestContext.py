"""Request context — correlation/actor/tenant propagation (Phase 06 §25).

A small contextvar-based holder bound by middleware for every request and
by jobs/commands for background work. Every layer (API, application, audit,
logs, domain events) reads identity and correlation from here instead of
passing these values through every signature.
"""

from __future__ import annotations

import contextvars
import uuid
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field


def newCorrelationId() -> str:
    return uuid.uuid4().hex


@dataclass
class RequestContext:
    correlationId: str = ""
    requestId: str = ""
    actorId: str = ""
    actorTenantId: str = ""
    tenantId: str = ""
    sessionId: str = ""
    ipAddress: str = ""
    userAgent: str = ""

    def correlationIdOrNew(self) -> str:
        return self.correlationId or newCorrelationId()

    def asLogFields(self) -> dict[str, str]:
        return {
            "correlationId": self.correlationId,
            "requestId": self.requestId,
            "actorId": self.actorId,
            "tenantId": self.tenantId or self.actorTenantId,
        }


@dataclass
class ContextSnapshot:
    """Immutable copy used by infrastructure writers (audit rows)."""

    correlationId: str = ""
    requestId: str = ""
    actorId: str = ""
    tenantId: str = ""
    sessionId: str = ""
    ipAddress: str = ""
    userAgent: str = ""
    extra: dict[str, str] = field(default_factory=dict)


_currentContext: contextvars.ContextVar[RequestContext] = contextvars.ContextVar(
    "tekaraiRequestContext"
)


def currentContext() -> RequestContext:
    try:
        return _currentContext.get()
    except LookupError:
        return RequestContext()


def bindContext(context: RequestContext) -> contextvars.Token:
    return _currentContext.set(context)


def resetContext(token: contextvars.Token) -> None:
    _currentContext.reset(token)


def snapshotContext() -> ContextSnapshot:
    context = currentContext()
    return ContextSnapshot(
        correlationId=context.correlationId,
        requestId=context.requestId,
        actorId=context.actorId,
        tenantId=context.tenantId or context.actorTenantId,
        sessionId=context.sessionId,
        ipAddress=context.ipAddress,
        userAgent=context.userAgent,
    )


@contextmanager
def requestScope(context: RequestContext) -> Iterator[RequestContext]:
    """Bind a context (tests, management commands, workers) and restore it."""
    token = bindContext(context)
    try:
        yield context
    finally:
        resetContext(token)
