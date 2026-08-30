"""Composition wiring (Phase 06 §34 — Architecture → Contract → Implementation).

Settings (``SHARED_KERNEL_PROVIDERS``) map port names to dotted paths; this
module resolves and caches singletons. The composition root is configuration
+ this resolver — application code receives ready-made implementations and
never imports infrastructure directly.
"""

from __future__ import annotations

import importlib
from functools import lru_cache
from typing import Any

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

#: Default bindings — the shared kernel provides its own infrastructure.
DEFAULT_PROVIDERS: dict[str, str] = {
    "unitOfWork": "apps.sharedKernel.infrastructure.djangoPorts.UnitOfWorkDjango",
    "auditRecorder": "apps.sharedKernel.infrastructure.djangoPorts.AuditRecorderDjango",
    "eventDispatcher": "apps.sharedKernel.infrastructure.djangoPorts.InProcessEventDispatcher",
    "clock": "apps.sharedKernel.infrastructure.djangoPorts.SystemClock",
    "idempotencyStore": "apps.sharedKernel.infrastructure.djangoPorts.CacheIdempotencyStore",
    "rateLimiter": "apps.sharedKernel.infrastructure.djangoPorts.CacheRateLimiter",
    "auditStreamReader": (
        "apps.sharedKernel.infrastructure.auditStreamImpl.DjangoAuditStreamReader"
    ),
    # Overridden in settings by the Identity context implementations:
    "sessionVerifier": "apps.identity.infrastructure.services.sessionVerifier.SessionVerifierDjango",
    "apiKeyVerifier": "apps.identity.infrastructure.services.principals.ApiKeyVerifierDjango",
    "permissionGate": "apps.identity.infrastructure.services.permissionGate.PermissionGateDjango",
    "tokenIssuer": "apps.identity.infrastructure.services.jwtService.JwtTokenIssuerDjango",
    "secretVault": "apps.identity.infrastructure.services.secretVault.SigningSecretVault",
}

_instances: dict[str, Any] = {}


def sharedKernelProvider(portName: str) -> Any:
    """Resolve a port implementation (singleton per name)."""
    if portName in _instances:
        return _instances[portName]
    configured = getattr(settings, "SHARED_KERNEL_PROVIDERS", {})
    dottedPath = configured.get(portName) or DEFAULT_PROVIDERS[portName]
    implementation = importFromDottedPath(dottedPath)
    _instances[portName] = implementation
    return implementation


def importFromDottedPath(dottedPath: str) -> Any:
    moduleName, _, attributeName = dottedPath.rpartition(".")
    if not moduleName:
        raise ImproperlyConfigured(f"Invalid provider path: {dottedPath}")
    try:
        module = importlib.import_module(moduleName)
        return getattr(module, attributeName)
    except (ImportError, AttributeError) as exc:
        raise ImproperlyConfigured(f"Cannot load provider {dottedPath}: {exc}") from exc


@lru_cache(maxsize=1)
def defaultEventDispatcher() -> Any:
    """Shared dispatcher instance so subscriptions accumulate in one place."""
    return sharedKernelProvider("eventDispatcher")()
