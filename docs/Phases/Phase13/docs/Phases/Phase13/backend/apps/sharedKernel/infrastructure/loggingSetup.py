"""Structured logging (Phase 06 §30).

``TekaraiJsonFormatter`` renders one JSON object per record with the §30
field set — timestamp, level, service, module, operation, actor, tenant,
correlationId, requestId, message, exception — pulling identity fields from
the request context bound by middleware. Settings wire this formatter into
the ``tekarai`` loggers (see config/settings/base.py LOGGING).
"""

from __future__ import annotations

import json
import logging
from datetime import UTC, datetime
from typing import Any

from apps.sharedKernel.application.requestContext import currentContext

RESERVED = {
    "args",
    "asctime",
    "created",
    "exc_info",
    "exc_text",
    "filename",
    "funcName",
    "levelname",
    "levelno",
    "lineno",
    "module",
    "msecs",
    "message",
    "msg",
    "name",
    "pathname",
    "process",
    "processName",
    "relativeCreated",
    "stack_info",
    "stacklevel",
    "thread",
    "threadName",
    "taskName",
}


class TekaraiJsonFormatter(logging.Formatter):
    service = "tekarai-backend"

    def format(self, record: logging.LogRecord) -> str:
        context = currentContext()
        payload: dict[str, Any] = {
            "timestamp": datetime.fromtimestamp(record.created, tz=UTC).isoformat(),
            "level": record.levelname,
            "service": self.service,
            "module": record.name,
            "operation": record.funcName,
            "message": record.getMessage(),
            "actor": context.actorId or None,
            "tenant": context.tenantId or context.actorTenantId or None,
            "correlationId": context.correlationId or None,
            "requestId": context.requestId or None,
        }
        for key, value in record.__dict__.items():
            if key not in RESERVED and not key.startswith("_") and key not in payload:
                payload[key] = value
        if record.exc_info:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, default=str, ensure_ascii=False)
