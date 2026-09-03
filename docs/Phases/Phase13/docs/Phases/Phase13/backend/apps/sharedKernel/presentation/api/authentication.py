"""Bearer session authentication (Phase 06 §16).

Authentication answers "who is this?" only — it resolves the bearer token
through the ``SessionVerifier`` port (implemented by the Identity context)
and binds actor/tenant into the request context. Authorization is a
separate step (§17) done by permission classes.

Opaque rotating session tokens are an ADR-019 decision; JWT-based provider
plugs in behind the same port without touching views.
"""

from __future__ import annotations

import typing

from rest_framework.authentication import BaseAuthentication
from rest_framework.request import Request

from apps.sharedKernel.application.requestContext import currentContext
from apps.sharedKernel.domain.errors import AuthenticationRequiredError
from apps.sharedKernel.infrastructure.wiring import sharedKernelProvider

if typing.TYPE_CHECKING:  # pragma: no cover — typing only
    from apps.sharedKernel.application.ports import SessionPrincipal


class BearerSessionAuthentication(BaseAuthentication):
    keyword = "Bearer"

    def authenticate(self, request: Request) -> tuple[object, str | None] | None:
        header: str = request.headers.get("Authorization", "")
        if not header.startswith(f"{self.keyword} "):
            return None  # anonymous — permission classes decide if that's OK
        token = header[len(self.keyword) + 1 :].strip()
        if not token:
            raise AuthenticationRequiredError("Authentication required.")
        verifier = sharedKernelProvider("sessionVerifier")()
        principal = verifier.verifyToken(token)
        bindPrincipalIntoContext(principal)
        return principal, token

    def authenticate_header(self, request: Request) -> str:
        return self.keyword


def bindPrincipalIntoContext(principal: SessionPrincipal) -> None:
    """Enrich the request context with actor/tenant identity (§26)."""
    from apps.sharedKernel.application.requestContext import bindContext

    context = currentContext()
    context.actorId = str(principal.userId)
    context.actorTenantId = str(principal.tenantId)
    if not context.tenantId:
        context.tenantId = str(principal.tenantId)
    sessionId = getattr(principal, "sessionId", None)
    if sessionId:
        context.sessionId = str(sessionId)  # §9 — "current session" marking
    bindContext(context)
