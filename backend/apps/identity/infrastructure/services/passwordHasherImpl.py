"""Password hashing via Django hashers (§31 password hashing; §28 Django as
framework). Implements the domain ``PasswordHasher`` port."""

from __future__ import annotations

from django.contrib.auth.hashers import check_password, make_password

from apps.identity.domain.services.passwordHasher import PasswordHasher


class PasswordHasherDjango:
    def hash(self, plain: str) -> str:
        return make_password(plain)

    def verify(self, plain: str, hashed: str) -> bool:
        return check_password(plain, hashed)


assert isinstance(PasswordHasherDjango(), PasswordHasher)  # port conformance
