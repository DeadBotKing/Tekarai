# ADR-022 — Access Tokens: In-House HS256 JWT (Phase 07)

- **Status:** Accepted (supersedes the token *format* part of ADR-019)
- **Date:** Phase 07
- **Scope:** Identity & Access — session token model (§7/§8 of the Phase 07 spec)

## Context

Phase 06 (ADR-019) shipped opaque, rotating session tokens. The Phase 07
spec §7 *requires* a **JWT access token + refresh token** architecture and
its DoD item 5 explicitly supersedes the opaque-only decision. Requirements:

1. Access token = short-lived JWT (§7), minimal claims (§8): `sub`, `jti`,
   `iat`, `exp`, `iss`, `aud`, `tenantId`, `sessionId`, `typ` — **no bulk
   permissions** inside the token, so permission changes never wait for
   token expiry (§8; invariant §35.9).
2. JWT is **never the sole session mechanism**: every authenticated request
   re-resolves the Session row, so revocation/expiry take effect instantly
   (§35.4/§35.5).
3. Refresh token = opaque secret, stored **hashed** (SHA-256) on the session
   row, rotated on every use (ADR-019's rotation model survives unchanged).

## Decision

Implement the JWT in-house with the Python standard library
(`hmac` + `hashlib.sha256`, compact JWS `HS256`), behind the
`TokenIssuer` port in the shared kernel. `defaultJwtService()` reads
`settings.JWT_AUTH` (`jwtSigningKey` env; falls back to `SECRET_KEY`).

`JwtService`:

- `issueAccessToken(userId, tenantId, sessionId) → (token, ttlSeconds)`
- `issueMfaChallenge(...)` — `typ=mfaChallenge` (never accepted as access)
- `verifyAccessToken / verifyMfaChallenge` — checks signature
  (`hmac.compare_digest`), algorithm pinning (`alg=HS256` only), issuer,
  audience, token type and expiry; raises `AUTH_*` domain errors.

`SessionVerifierDjango` (principals.py) verifies the JWT and then loads the
`Session` row: revoked → `AUTH_AUTHENTICATION_REQUIRED`, expired →
`AUTH_TOKEN_EXPIRED`, inactive user → denied (§35.7). The API-key path
(`X-API-Key`) sits beside it and follows the same hash-and-recheck rule.

## Why in-house (rejected alternatives)

| Option | Verdict |
| --- | --- |
| **PyJWT / djangorestframework-simplejwt** | Rejected: adds a dependency for ~80 lines of HS256; drags the "Reserved for the Identity phase (SimpleJWT)" Phase-01 note forward while coupling us to its claim/validation semantics and release cycle. |
| **Keep opaque tokens (ADR-019)** | Rejected: Phase 07 §7 + DoD 5 mandate JWT+Refresh. |
| **RS256/EdDSA with a key pair** | Deferred (not rejected): the `TokenIssuer` port isolates the algorithm; swapping in asymmetric signing later is a single-infrastructure change (useful once multiple services verify tokens). |

A dedicated stdlib implementation keeps the security surface small,
auditable (one file, ~140 lines) and dependency-free — the same reasoning
that produced the in-house TOTP (RFC 6238) service and the in-house OpenAPI
builder (ADR-020).

## Consequences

- **+** Zero new dependencies; full control over the §8 claim set; the
  `TokenIssuer` port keeps the application layer framework-free.
- **+** Rotation/revocation/tracking model from ADR-019 is preserved
  verbatim for refresh tokens.
- **−** We own the cryptographic code: mitigated by the dedicated test
  battery (round-trip, tampering, expiry, wrong audience, wrong token type)
  and by architecture tests that force the Session-row re-check.
- **→** If token consumers multiply beyond this API, revisit RS256 via the
  same port (see ADR-023 when needed).
