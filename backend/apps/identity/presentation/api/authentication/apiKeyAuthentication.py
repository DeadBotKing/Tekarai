"""X-API-Key authentication (Phase 07 §22) for server-to-server callers.

Resolves ``X-API-Key`` through the ApiKeyVerifier port and binds the
principal into the request context; scopes (§22) ride on the principal.
Authentication only — permission decisions stay with the gate (§20).
"""

from __future__ import annotations

from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request


class ApiKeyAuthentication(BaseAuthentication):
    keyword = "X-API-Key"

    def authenticate(self, request: Request) -> tuple[object, str | None] | None:
        rawKey: str = request.headers.get("X-API-Key", "").strip()
        if not rawKey:
            return None  # not an API-key request — the Bearer path applies
        from apps.identity.infrastructure.services.principals import ApiKeyVerifierDjango

        principal = ApiKeyVerifierDjango().verifyApiKey(rawKey)
        from apps.sharedKernel.presentation.api.authentication import (
            bindPrincipalIntoContext,
        )

        bindPrincipalIntoContext(principal)
        return principal, rawKey

    def authenticate_header(self, request: Request) -> str:
        return self.keyword
