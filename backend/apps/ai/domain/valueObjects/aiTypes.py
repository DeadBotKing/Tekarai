"""Framework-free AI value objects and controlled vocabularies (Phase 13-B).

These objects validate concepts at the domain boundary. They do not know
Django, HTTP, a database, Redis, or any provider SDK.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from apps.sharedKernel.domain.errors import ValidationFailedError

MODEL_TYPES = (
    "LLM",
    "EMBEDDING",
    "VISION",
    "SPEECH_TO_TEXT",
    "TEXT_TO_SPEECH",
    "CLASSIFICATION",
    "RERANKER",
    "MULTIMODAL",
    "CUSTOM",
)
CAPABILITY_CODES = (
    "TEXT_GENERATION",
    "SUMMARIZATION",
    "CLASSIFICATION",
    "EXTRACTION",
    "TRANSLATION",
    "QUESTION_ANSWERING",
    "RECOMMENDATION",
    "PREDICTION",
    "ANOMALY_DETECTION",
    "DOCUMENT_ANALYSIS",
    "MEETING_SUMMARY",
    "TASK_EXTRACTION",
    "KPI_ANALYSIS",
    "KNOWLEDGE_RETRIEVAL",
    "EMBEDDING",
    "RERANKING",
)
REQUEST_TYPES = (
    "GENERATE",
    "SUMMARIZE",
    "CLASSIFY",
    "EXTRACT",
    "PREDICT",
    "RECOMMEND",
    "ASK",
    "EMBED",
    "RERANK",
    "TOOL",
)
REQUEST_STATUSES = ("PENDING", "QUEUED", "RUNNING", "COMPLETED", "FAILED", "CANCELLED")
RESPONSE_STATUSES = ("COMPLETED", "FAILED", "VALIDATION_FAILED")
OUTPUT_CLASSIFICATIONS = ("ADVISORY", "DRAFT", "AUTOMATED", "AUTHORITATIVE")
DATA_CLASSIFICATIONS = ("PUBLIC", "INTERNAL", "CONFIDENTIAL", "RESTRICTED")
MEMORY_SCOPES = ("SHORT_TERM", "LONG_TERM", "CONVERSATION", "TASK", "AGENT")
KNOWLEDGE_STATUSES = ("PENDING", "INDEXING", "READY", "FAILED", "ARCHIVED")
EVALUATION_METHODS = ("MANUAL", "AUTOMATIC", "BATCH")
FEEDBACK_SENTIMENTS = ("POSITIVE", "NEGATIVE", "NEUTRAL")
TOOL_EXECUTION_STATUSES = ("PENDING", "RUNNING", "SUCCEEDED", "FAILED", "DENIED", "CANCELLED")
AGENT_EXECUTION_STATUSES = ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED", "DENIED")
PRIORITIES = ("LOW", "NORMAL", "HIGH", "CRITICAL")
CODE_PATTERN = re.compile(r"^[A-Z][A-Z0-9_]{1,79}$")


def validateCode(value: str, fieldName: str = "code") -> str:
    normalized = str(value or "").strip().upper()
    if not CODE_PATTERN.fullmatch(normalized):
        raise ValidationFailedError("AI code is invalid.", fieldErrors={fieldName: normalized})
    return normalized


def ensureEnum(value: str, allowed: tuple[str, ...], fieldName: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized not in allowed:
        raise ValidationFailedError(f"Unknown {fieldName}.", fieldErrors={fieldName: normalized})
    return normalized


@dataclass(frozen=True)
class ModelType:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureEnum(self.value, MODEL_TYPES, "modelType"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class CapabilityCode:
    value: str

    def __post_init__(self) -> None:
        normalized = validateCode(self.value, "capabilityCode")
        if normalized not in CAPABILITY_CODES and not normalized.startswith("CUSTOM_"):
            raise ValidationFailedError("Unknown AI capability.", fieldErrors={"capabilityCode": normalized})
        object.__setattr__(self, "value", normalized)

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RequestType:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureEnum(self.value, REQUEST_TYPES, "requestType"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class RequestStatus:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureEnum(self.value, REQUEST_STATUSES, "requestStatus"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OutputClassification:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureEnum(self.value, OUTPUT_CLASSIFICATIONS, "outputClassification"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class DataClassification:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureEnum(self.value, DATA_CLASSIFICATIONS, "classification"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class MemoryScope:
    value: str

    def __post_init__(self) -> None:
        object.__setattr__(self, "value", ensureEnum(self.value, MEMORY_SCOPES, "memoryScope"))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class TokenUsage:
    inputTokens: int = 0
    outputTokens: int = 0

    def __post_init__(self) -> None:
        if self.inputTokens < 0 or self.outputTokens < 0:
            raise ValidationFailedError("Token counts cannot be negative.")

    @property
    def totalTokens(self) -> int:
        return self.inputTokens + self.outputTokens


@dataclass(frozen=True)
class Money:
    amount: Decimal
    currency: str = "USD"

    def __post_init__(self) -> None:
        amount = Decimal(str(self.amount))
        if amount < Decimal("0"):
            raise ValidationFailedError("AI cost cannot be negative.", fieldErrors={"amount": str(amount)})
        currency = str(self.currency or "").upper()
        if len(currency) != 3 or not currency.isalpha():
            raise ValidationFailedError("Currency must be an ISO-4217 code.", fieldErrors={"currency": currency})
        object.__setattr__(self, "amount", amount)
        object.__setattr__(self, "currency", currency)


@dataclass(frozen=True)
class CostRate:
    inputPer1k: Decimal = Decimal("0")
    outputPer1k: Decimal = Decimal("0")
    currency: str = "USD"

    def __post_init__(self) -> None:
        inputRate = Decimal(str(self.inputPer1k))
        outputRate = Decimal(str(self.outputPer1k))
        if inputRate < Decimal("0") or outputRate < Decimal("0"):
            raise ValidationFailedError("Cost rates cannot be negative.")
        object.__setattr__(self, "inputPer1k", inputRate)
        object.__setattr__(self, "outputPer1k", outputRate)
        object.__setattr__(self, "currency", str(self.currency or "").upper())
        Money(Decimal("0"), self.currency)

    def calculate(self, usage: TokenUsage) -> Money:
        amount = Decimal(usage.inputTokens) / Decimal("1000") * self.inputPer1k
        amount += Decimal(usage.outputTokens) / Decimal("1000") * self.outputPer1k
        return Money(amount.quantize(Decimal("0.00000001")), self.currency)


@dataclass(frozen=True)
class RetryPolicy:
    maxAttempts: int = 3
    initialDelaySeconds: int = 30
    multiplier: float = 2.0
    maxDelaySeconds: int = 600

    def __post_init__(self) -> None:
        if (
            self.maxAttempts < 1
            or self.initialDelaySeconds < 0
            or self.multiplier < 1
            or self.maxDelaySeconds < 0
        ):
            raise ValidationFailedError("Retry policy values are invalid.")


@dataclass(frozen=True)
class ContextSource:
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    content: str
    classification: str = "INTERNAL"
    allowed: bool = True
    metadata: dict[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "classification", str(DataClassification(self.classification)))
        if not self.sourceDomain or not self.sourceEntityType or not self.sourceEntityId:
            raise ValidationFailedError("Context source identity is required.")


@dataclass(frozen=True)
class JsonSchema:
    schema: dict[str, Any]

    def __post_init__(self) -> None:
        if not isinstance(self.schema, dict):
            raise ValidationFailedError("JSON Schema must be an object.")
