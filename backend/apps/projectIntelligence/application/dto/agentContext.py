"""Public application contract consumed by agent adapters."""

from __future__ import annotations

import uuid
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True, slots=True)
class ProjectContextSource:
    tenantId: uuid.UUID
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    content: str
    classification: str
    authorized: bool
    metadata: dict[str, Any]
