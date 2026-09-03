"""Rate limiting for sensitive endpoints (Phase 06 §23).

Policies live in settings (``API_RATE_LIMIT_POLICIES``) as
``scope: (limit, windowSeconds)``; the decorator counts hits per
scope + identity (IP and, when authenticated, actor) through the
``RateLimiter`` port — LocMem cache today, Redis backend later behind the
same port. Exceeding the limit raises ``SYS_RATE_LIMITED`` (429 + Retry-After).

Sensitive classes per spec: login, authentication, password reset, OTP,
AI, file upload, public API.
"""

from __future__ import annotations

import functools
import logging
from collections.abc import Callable
from typing import Any

from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import RateLimitedError
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

logger = logging.getLogger("tekarai.api.rateLimit")


def enforceRateLimit(policyScope: str) -> Callable[[Callable[..., Any]], Callable[..., Any]]:
    """Decorator for APIView ``post``/``get`` handlers (§23)."""

    def decorator(handler: Callable[..., Any]) -> Callable[..., Any]:
        @functools.wraps(handler)
        def wrapper(viewSelf: Any, request: Any, *args: Any, **kwargs: Any) -> Any:
            from django.conf import settings

            policies = getattr(settings, "API_RATE_LIMIT_POLICIES", {})
            if policyScope in policies:
                limit, windowSeconds = policies[policyScope]
                identity = rateLimitIdentity(request)
                limiter = sharedKernelProvider("rateLimiter")()
                count = limiter.hit(policyScope, identity, int(limit), int(windowSeconds))
                if count > limit:
                    logger.warning(
                        "Rate limit exceeded",
                        extra={"scope": policyScope, "identity": identity},
                    )
                    raise RateLimitedError(retryAfterSeconds=int(windowSeconds))
            return handler(viewSelf, request, *args, **kwargs)

        wrapper.rateLimitScope = policyScope  # type: ignore[attr-defined]
        return wrapper

    return decorator


def rateLimitIdentity(request: Any) -> str:
    context = currentContext()
    if context.actorId:
        return f"actor:{context.actorId}"
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    ip = forwarded.split(",")[0].strip() if forwarded else request.META.get("REMOTE_ADDR", "")
    return f"ip:{ip or 'unknown'}"
