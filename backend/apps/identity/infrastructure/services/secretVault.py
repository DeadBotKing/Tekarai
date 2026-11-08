"""Legacy tamper-evident TOTP storage, NOT confidential encryption.

Django's HMAC signer authenticates plaintext; a database reader can see the
secret. Kept for compatibility with existing factors. New administrative
factors MUST use EncryptedAdministrativeSecretVault instead. Changing this
format requires a deliberate legacy factor migration, never a silent swap.
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
