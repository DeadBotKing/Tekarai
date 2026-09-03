"""Secret vault — protects TOTP secrets at rest (Phase 07 §24, §41).

Uses Django's HMAC signer (keyed by SECRET_KEY): the stored ``secretRef``
is signed, tamper-evident and reversible only with the server key — no raw
secret ever lands in the database or logs.
"""

from __future__ import annotations

from django.core import signing


class SigningSecretVault:
    def protect(self, raw: str) -> str:
        return signing.Signer(salt="tekarai.mfa").sign(raw)

    def reveal(self, protected: str) -> str:
        try:
            return signing.Signer(salt="tekarai.mfa").unsign(protected)
        except signing.BadSignature as exc:  # pragma: no cover - tamper guard
            from apps.sharedKernel.domain.errors import AuthenticationRequiredError

            raise AuthenticationRequiredError("Corrupted secret reference.") from exc
