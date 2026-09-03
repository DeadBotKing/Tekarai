# ADR-019 — Opaque rotating session tokens before JWT

**Status:** Accepted (Phase 06) · **Context:** Phase 06 §16 requires
architecture for JWT, refresh tokens, sessions, service accounts and agent
authentication — architecture, not necessarily full JWT now.

## Decision

Phase 06 ships **opaque bearer session tokens**: 256-bit random
(`secrets.token_urlsafe`), stored **hashed** (SHA-256) in `Session`,
8-hour TTL, rotation on refresh (old row revoked, new row issued), explicit
logout revocation, sliding `lastUsedAt`. All consumption flows through the
`SessionVerifier` port (`BearerSessionAuthentication` in the shared kernel).

## Consequences

- No new dependency (no PyJWT/simplejwt); tokens carry no claims to leak;
  instant server-side revocation (impossible with stateless JWT).
- Refresh semantics = rotation inside the same aggregate family (ADR-019
  pattern); replay of a rotated token fails (`AUTH_CREDENTIALS_INVALID`).
- When federation/mobile offline needs arise, a JWT provider implements the
  same `SessionVerifier` port — views, permissions and use cases unchanged.
- Service-account and agent credentials plug into the same port with their
  own principal type (later phases).

## Alternatives rejected

- **djangorestframework-simplejwt now** — adds a dependency before its
  driving requirement exists (§34: no dependency without architectural
  review); revocation still needs a store, which we already have.
