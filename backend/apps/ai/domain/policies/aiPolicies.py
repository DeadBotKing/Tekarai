"""AI security and governance policies (Phase 13-B §§29, 38, 47, 48)."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Iterable

from apps.ai.domain.exceptions import AIToolDenied, AIQuotaExceeded
from apps.ai.domain.valueObjects.aiTypes import DATA_CLASSIFICATIONS, DataClassification


@dataclass(frozen=True)
class ContextPolicy:
    """Least-privilege policy evaluated before context assembly/inference."""

    allowedClassifications: tuple[str, ...] = ("PUBLIC", "INTERNAL")
    maxSources: int = 50
    maxCharacters: int = 120_000
    maxTokens: int = 32_000
    allowExternalProvider: bool = False
    redactRestricted: bool = True

    def __post_init__(self) -> None:
        normalized = tuple(str(DataClassification(value)) for value in self.allowedClassifications)
        object.__setattr__(self, "allowedClassifications", normalized)
        if self.maxSources < 1 or self.maxCharacters < 1 or self.maxTokens < 1:
            raise ValueError("Context limits must be positive.")

    def permits(self, classification: str, *, externalProvider: bool = False) -> bool:
        if classification not in DATA_CLASSIFICATIONS:
            return False
        return classification in self.allowedClassifications and (
            not externalProvider or self.allowExternalProvider
        )


@dataclass(frozen=True)
class ProviderPolicy:
    allowedProviderCodes: tuple[str, ...] = ()
    allowedModelCodes: tuple[str, ...] = ()
    allowedDataClassifications: tuple[str, ...] = ("PUBLIC", "INTERNAL")
    externalAllowed: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "allowedProviderCodes", tuple(value.upper() for value in self.allowedProviderCodes))
        object.__setattr__(self, "allowedModelCodes", tuple(value.upper() for value in self.allowedModelCodes))
        object.__setattr__(
            self,
            "allowedDataClassifications",
            tuple(str(DataClassification(value)) for value in self.allowedDataClassifications),
        )

    def permits(self, providerCode: str, modelCode: str, classifications: Iterable[str]) -> bool:
        classifications = tuple(str(DataClassification(value)) for value in classifications)
        if self.allowedProviderCodes and providerCode.upper() not in self.allowedProviderCodes:
            return False
        if self.allowedModelCodes and modelCode.upper() not in self.allowedModelCodes:
            return False
        if not self.externalAllowed and any(value in {"CONFIDENTIAL", "RESTRICTED"} for value in classifications):
            return False
        return all(value in self.allowedDataClassifications for value in classifications)


@dataclass(frozen=True)
class QuotaPolicy:
    dailyTokenLimit: int = 0
    dailyCostLimit: float = 0.0

    def __post_init__(self) -> None:
        if self.dailyTokenLimit < 0 or self.dailyCostLimit < 0:
            raise ValueError("Quota limits cannot be negative.")

    def checkTokens(self, usedTokens: int, requestedTokens: int) -> None:
        if self.dailyTokenLimit and usedTokens + requestedTokens > self.dailyTokenLimit:
            raise AIQuotaExceeded("Daily token quota exceeded.")

    def checkCost(self, usedCost: float, requestedCost: float) -> None:
        if self.dailyCostLimit and usedCost + requestedCost > self.dailyCostLimit:
            raise AIQuotaExceeded("Daily AI cost quota exceeded.")


@dataclass(frozen=True)
class ToolPolicy:
    allowedActions: frozenset[str] = field(default_factory=frozenset)
    requireApproval: bool = True
    maxExecutionsPerRequest: int = 10

    def __post_init__(self) -> None:
        if self.maxExecutionsPerRequest < 1:
            raise ValueError("Tool execution limit must be positive.")

    def permits(self, action: str, *, approved: bool = False, executions: int = 0) -> bool:
        if action not in self.allowedActions:
            raise AIToolDenied("AI tool action is not allowed.")
        if self.requireApproval and not approved:
            raise AIToolDenied("AI tool action requires explicit approval.")
        if executions >= self.maxExecutionsPerRequest:
            raise AIQuotaExceeded("AI tool execution limit exceeded.")
        return True
