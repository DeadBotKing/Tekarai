"""X-API-Key authentication (Phase 07 §22) for server-to-server callers.

The implementation moved to the shared kernel beside the bearer adapter, so
that any context can mount it without reaching into Identity's presentation
layer (RULE E/F: only ``.application`` is public across contexts). Identity
still owns the verifier behind the ``apiKeyVerifier`` port; this module stays
as the historical import path.
"""

from __future__ import annotations

from apps.sharedKernel.presentation.api.authentication import ApiKeyAuthentication

__all__ = ["ApiKeyAuthentication"]
