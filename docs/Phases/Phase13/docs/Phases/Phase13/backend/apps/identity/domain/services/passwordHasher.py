"""PasswordHasher port (domain) — infrastructure binds Django hashers.

Domain stays framework-free; only the contract lives here (§10).
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class PasswordHasher(Protocol):
    def hash(self, plain: str) -> str: ...

    def verify(self, plain: str, hashed: str) -> bool: ...
