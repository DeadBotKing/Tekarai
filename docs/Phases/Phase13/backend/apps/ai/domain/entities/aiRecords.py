"""Pure AI domain entities and aggregate behaviours (Phase 13-B).

The records in this module intentionally contain no ORM, HTTP, provider SDK,
Redis, or Django dependency. Later application and infrastructure layers map
them to persistence and external systems.
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from decimal import Decimal
from typing import Any, Iterable

from apps.ai.domain.exceptions import AIContextTooLarge, AIOutputValidationFailed
from apps.ai.domain.valueObjects.aiTypes import (
    AGENT_EXECUTION_STATUSES,
    CAPABILITY_CODES,
    DATA_CLASSIFICATIONS,
    EVALUATION_METHODS,
    FEEDBACK_SENTIMENTS,
    KNOWLEDGE_STATUSES,
    MEMORY_SCOPES,
    MODEL_TYPES,
    OUTPUT_CLASSIFICATIONS,
    PRIORITIES,
    REQUEST_STATUSES,
    REQUEST_TYPES,
    RESPONSE_STATUSES,
    TOOL_EXECUTION_STATUSES,
    ContextSource,
    CostRate,
    TokenUsage,
    ensureEnum,
    validateCode,
)


def utcNow() -> datetime:
    return datetime.now(tz=UTC)


def newId() -> uuid.UUID:
    return uuid.uuid4()


def requireUuid(value: uuid.UUID | str, fieldName: str) -> uuid.UUID:
    if isinstance(value, uuid.UUID):
        return value
    try:
        return uuid.UUID(str(value))
    except (ValueError, AttributeError) as exc:
        raise ValueError(f"{fieldName} must be a UUID.") from exc


@dataclass
class AIProvider:
    tenantId: uuid.UUID
    code: str
    name: str
    providerType: str
    id: uuid.UUID = field(default_factory=newId)
    isActive: bool = True
    configurationReference: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    allowedDataClassifications: tuple[str, ...] = ("PUBLIC", "INTERNAL")
    createdAt: datetime = field(default_factory=utcNow)
    updatedAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.code = validateCode(self.code)
        self.providerType = validateCode(self.providerType, "providerType")
        if not self.name.strip():
            raise ValueError("Provider name is required.")
        self.allowedDataClassifications = tuple(
            ensureEnum(value, DATA_CLASSIFICATIONS, "classification")
            for value in self.allowedDataClassifications
        )

    def permitsClassifications(self, classifications: Iterable[str]) -> bool:
        return all(value in self.allowedDataClassifications for value in classifications)


@dataclass
class AIModel:
    tenantId: uuid.UUID
    providerId: uuid.UUID
    code: str
    name: str
    modelType: str = "LLM"
    version: str = "1"
    id: uuid.UUID = field(default_factory=newId)
    contextWindow: int = 8192
    inputCapability: tuple[str, ...] = ()
    outputCapability: tuple[str, ...] = ()
    supportsStreaming: bool = False
    supportsTools: bool = False
    supportsEmbeddings: bool = False
    supportsVision: bool = False
    isActive: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)
    inputCostPer1k: Decimal = Decimal("0")
    outputCostPer1k: Decimal = Decimal("0")

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.providerId = requireUuid(self.providerId, "providerId")
        self.id = requireUuid(self.id, "id")
        self.code = validateCode(self.code)
        normalizedModelType = str(self.modelType or "").strip().upper()
        if normalizedModelType not in MODEL_TYPES and not normalizedModelType.startswith("CUSTOM_"):
            raise ValueError(f"Unsupported model type: {normalizedModelType}")
        self.modelType = normalizedModelType
        self.inputCapability = tuple(validateCode(value, "inputCapability") for value in self.inputCapability)
        self.outputCapability = tuple(validateCode(value, "outputCapability") for value in self.outputCapability)
        self.inputCostPer1k = Decimal(str(self.inputCostPer1k))
        self.outputCostPer1k = Decimal(str(self.outputCostPer1k))
        if self.contextWindow < 1:
            raise ValueError("Model context window must be positive.")
        if self.inputCostPer1k < 0 or self.outputCostPer1k < 0:
            raise ValueError("Model token rates cannot be negative.")

    def supportsCapability(self, capabilityCode: str) -> bool:
        return not self.inputCapability or capabilityCode in self.inputCapability or capabilityCode in self.outputCapability

    def costRate(self) -> CostRate:
        return CostRate(self.inputCostPer1k, self.outputCostPer1k)


@dataclass
class AICapability:
    tenantId: uuid.UUID
    code: str
    name: str
    description: str = ""
    id: uuid.UUID = field(default_factory=newId)
    isActive: bool = True
    policy: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.code = validateCode(self.code, "capabilityCode")
        if self.code not in CAPABILITY_CODES and not self.code.startswith("CUSTOM_"):
            raise ValueError(f"Unsupported AI capability: {self.code}")
        if not self.name.strip():
            raise ValueError("Capability name is required.")

    def accepts(self, requestType: str) -> bool:
        return self.isActive and requestType in REQUEST_TYPES


@dataclass
class AIOperation:
    """Logical operation that can contain retries and provider fallbacks."""

    tenantId: uuid.UUID
    operationType: str
    requestedBy: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    correlationId: str = ""
    traceId: str = ""
    requestIds: list[uuid.UUID] = field(default_factory=list)
    status: str = "PENDING"
    createdAt: datetime = field(default_factory=utcNow)
    completedAt: datetime | None = None

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        self.operationType = validateCode(self.operationType, "operationType")
        self.status = ensureEnum(
            self.status,
            ("PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"),
            "operationStatus",
        )
        if not self.correlationId:
            self.correlationId = uuid.uuid4().hex
        if not self.traceId:
            self.traceId = uuid.uuid4().hex
        self.transitionTo(self.status)

    def transitionTo(self, status: str, now: datetime | None = None) -> None:
        allowedStates = {"PENDING", "RUNNING", "COMPLETED", "FAILED", "CANCELLED"}
        status = ensureEnum(status, tuple(sorted(allowedStates)), "operationStatus")
        transitions = {
            "PENDING": {"RUNNING", "CANCELLED"},
            "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
            "COMPLETED": set(),
            "FAILED": set(),
            "CANCELLED": set(),
        }
        if status != self.status and status not in transitions[self.status]:
            raise ValueError(f"Invalid operation transition {self.status} → {status}.")
        self.status = status
        if status in {"COMPLETED", "FAILED", "CANCELLED"}:
            self.completedAt = now or utcNow()

    def addRequest(self, requestId: uuid.UUID) -> None:
        requestId = requireUuid(requestId, "requestId")
        if requestId not in self.requestIds:
            self.requestIds.append(requestId)


@dataclass
class AIRequest:
    tenantId: uuid.UUID
    capabilityId: uuid.UUID
    requestType: str
    requestedBy: uuid.UUID | None = None
    sourceDomain: str = ""
    sourceEntityType: str = ""
    sourceEntityId: str = ""
    priority: str = "NORMAL"
    id: uuid.UUID = field(default_factory=newId)
    status: str = "PENDING"
    correlationId: str = ""
    traceId: str = ""
    parentRequestId: uuid.UUID | None = None
    inputData: dict[str, Any] = field(default_factory=dict)
    contextTokenCount: int = 0
    retryCount: int = 0
    idempotencyKey: str = ""
    createdAt: datetime = field(default_factory=utcNow)
    queuedAt: datetime | None = None
    startedAt: datetime | None = None
    completedAt: datetime | None = None
    errorCode: str = ""

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.capabilityId = requireUuid(self.capabilityId, "capabilityId")
        self.id = requireUuid(self.id, "id")
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        if self.parentRequestId is not None:
            self.parentRequestId = requireUuid(self.parentRequestId, "parentRequestId")
        self.requestType = ensureEnum(self.requestType, REQUEST_TYPES, "requestType")
        self.priority = ensureEnum(self.priority, PRIORITIES, "priority")
        self.status = ensureEnum(self.status, REQUEST_STATUSES, "requestStatus")
        if not self.correlationId:
            self.correlationId = uuid.uuid4().hex
        if not self.traceId:
            self.traceId = uuid.uuid4().hex
        if self.contextTokenCount < 0 or self.retryCount < 0:
            raise ValueError("Request counters cannot be negative.")

    def transitionTo(self, status: str, now: datetime | None = None, *, errorCode: str = "") -> None:
        status = ensureEnum(status, REQUEST_STATUSES, "requestStatus")
        allowed = {
            "PENDING": {"QUEUED", "RUNNING", "CANCELLED"},
            "QUEUED": {"RUNNING", "CANCELLED"},
            "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
            "COMPLETED": set(),
            "FAILED": {"QUEUED", "CANCELLED"},
            "CANCELLED": set(),
        }
        if status != self.status and status not in allowed[self.status]:
            raise ValueError(f"Invalid AI request transition {self.status} → {status}.")
        moment = now or utcNow()
        self.status = status
        if status == "QUEUED":
            self.queuedAt = moment
        elif status == "RUNNING":
            self.startedAt = moment
        elif status in {"COMPLETED", "FAILED", "CANCELLED"}:
            self.completedAt = moment
        if errorCode:
            self.errorCode = errorCode

    def recordRetry(self) -> None:
        if self.status != "FAILED":
            raise ValueError("Only failed AI requests can be retried.")
        self.retryCount += 1
        self.transitionTo("QUEUED")


@dataclass
class AIContext:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    sources: tuple[ContextSource, ...] = ()
    content: str = ""
    tokenCount: int = 0
    id: uuid.UUID = field(default_factory=newId)
    redacted: bool = True
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.id = requireUuid(self.id, "id")
        if self.tokenCount < 0:
            raise ValueError("Context token count cannot be negative.")

    def enforceLimit(self, maxTokens: int, maxCharacters: int) -> None:
        if self.tokenCount > maxTokens or len(self.content) > maxCharacters:
            raise AIContextTooLarge("AI context exceeds the configured limit.")


@dataclass
class AIResponse:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    modelId: uuid.UUID
    providerId: uuid.UUID
    status: str = "COMPLETED"
    content: str = ""
    structuredData: dict[str, Any] = field(default_factory=dict)
    inputTokens: int = 0
    outputTokens: int = 0
    totalTokens: int = 0
    latencyMs: int = 0
    outputClassification: str = "ADVISORY"
    promptVersionId: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    errorCode: str = ""
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.modelId = requireUuid(self.modelId, "modelId")
        self.providerId = requireUuid(self.providerId, "providerId")
        self.id = requireUuid(self.id, "id")
        if self.promptVersionId is not None:
            self.promptVersionId = requireUuid(self.promptVersionId, "promptVersionId")
        self.status = ensureEnum(self.status, RESPONSE_STATUSES, "responseStatus")
        self.outputClassification = ensureEnum(
            self.outputClassification, OUTPUT_CLASSIFICATIONS, "outputClassification"
        )
        if min(self.inputTokens, self.outputTokens, self.latencyMs) < 0:
            raise ValueError("Response counters cannot be negative.")
        self.totalTokens = self.totalTokens or self.inputTokens + self.outputTokens
        if self.totalTokens != self.inputTokens + self.outputTokens:
            raise ValueError("Total token count must equal input plus output tokens.")

    def validateStructuredOutput(self, schema: dict[str, Any]) -> None:
        from apps.ai.domain.services.aiRules import validateJsonSchema

        if not validateJsonSchema(self.structuredData, schema):
            raise AIOutputValidationFailed("AI structured output does not match its schema.")


@dataclass
class AIPrompt:
    tenantId: uuid.UUID
    code: str
    name: str
    description: str = ""
    id: uuid.UUID = field(default_factory=newId)
    isActive: bool = True
    activeVersionId: uuid.UUID | None = None
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.code = validateCode(self.code, "promptCode")
        if not self.name.strip():
            raise ValueError("Prompt name is required.")

    def activateVersion(self, versionId: uuid.UUID) -> None:
        self.activeVersionId = requireUuid(versionId, "versionId")


@dataclass
class AIPromptVersion:
    tenantId: uuid.UUID
    promptId: uuid.UUID
    version: int
    template: str
    systemInstruction: str = ""
    variables: tuple[str, ...] = ()
    outputSchema: dict[str, Any] = field(default_factory=dict)
    modelConstraints: dict[str, Any] = field(default_factory=dict)
    createdBy: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    isActive: bool = False
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.promptId = requireUuid(self.promptId, "promptId")
        self.id = requireUuid(self.id, "id")
        if self.createdBy is not None:
            self.createdBy = requireUuid(self.createdBy, "createdBy")
        if self.version < 1 or not self.template.strip():
            raise ValueError("Prompt version and template are required.")
        if any(not name or not reIdentifier(name) for name in self.variables):
            raise ValueError("Prompt variables must be valid identifiers.")

    def render(self, values: dict[str, Any]) -> str:
        missing = [name for name in self.variables if name not in values]
        if missing:
            raise ValueError(f"Missing prompt variables: {', '.join(missing)}")
        return self.template.format(**values)


def reIdentifier(value: str) -> bool:
    return value.replace("_", "a").isalnum() and not value[0].isdigit()


@dataclass
class AIMemory:
    tenantId: uuid.UUID
    scope: str
    key: str
    value: Any
    userId: uuid.UUID | None = None
    version: int = 1
    id: uuid.UUID = field(default_factory=newId)
    isActive: bool = True
    expiresAt: datetime | None = None
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        if self.userId is not None:
            self.userId = requireUuid(self.userId, "userId")
        self.scope = ensureEnum(self.scope, MEMORY_SCOPES, "memoryScope")
        if self.version < 1 or not self.key.strip():
            raise ValueError("Memory key and positive version are required.")

    def nextVersion(self, value: Any, now: datetime | None = None) -> AIMemory:
        return AIMemory(
            tenantId=self.tenantId,
            scope=self.scope,
            key=self.key,
            value=value,
            userId=self.userId,
            version=self.version + 1,
            expiresAt=self.expiresAt,
            createdAt=now or utcNow(),
        )

    def isExpiredAt(self, now: datetime | None = None) -> bool:
        return self.expiresAt is not None and self.expiresAt <= (now or utcNow())


@dataclass
class AIKnowledgeItem:
    tenantId: uuid.UUID
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    title: str
    content: str
    classification: str = "INTERNAL"
    checksum: str = ""
    id: uuid.UUID = field(default_factory=newId)
    status: str = "PENDING"
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.classification = ensureEnum(self.classification, DATA_CLASSIFICATIONS, "classification")
        self.status = ensureEnum(self.status, KNOWLEDGE_STATUSES, "knowledgeStatus")
        if not self.sourceDomain or not self.sourceEntityType or not self.sourceEntityId or not self.content:
            raise ValueError("Knowledge source and content are required.")

    def transitionTo(self, status: str) -> None:
        status = ensureEnum(status, KNOWLEDGE_STATUSES, "knowledgeStatus")
        allowed = {
            "PENDING": {"INDEXING", "ARCHIVED"},
            "INDEXING": {"READY", "FAILED"},
            "READY": {"INDEXING", "ARCHIVED"},
            "FAILED": {"INDEXING", "ARCHIVED"},
            "ARCHIVED": set(),
        }
        if status != self.status and status not in allowed[self.status]:
            raise ValueError(f"Invalid knowledge transition {self.status} → {status}.")
        self.status = status


@dataclass
class AIKnowledgeChunk:
    tenantId: uuid.UUID
    itemId: uuid.UUID
    ordinal: int
    content: str
    tokenCount: int = 0
    id: uuid.UUID = field(default_factory=newId)
    metadata: dict[str, Any] = field(default_factory=dict)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.itemId = requireUuid(self.itemId, "itemId")
        self.id = requireUuid(self.id, "id")
        if self.ordinal < 0 or self.tokenCount < 0 or not self.content:
            raise ValueError("Chunk ordinal, content, and token count are invalid.")


@dataclass
class AIEmbedding:
    tenantId: uuid.UUID
    sourceType: str
    sourceId: str
    modelId: uuid.UUID
    vector: tuple[float, ...]
    chunkId: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    dimensions: int = 0
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.modelId = requireUuid(self.modelId, "modelId")
        self.id = requireUuid(self.id, "id")
        if self.chunkId is not None:
            self.chunkId = requireUuid(self.chunkId, "chunkId")
        self.dimensions = self.dimensions or len(self.vector)
        if not self.sourceType or not self.sourceId or self.dimensions != len(self.vector) or not self.vector:
            raise ValueError("Embedding source and dimensions are required.")


@dataclass
class AIRetrieval:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    query: str
    candidates: tuple[AIKnowledgeChunk, ...] = ()
    authorizedCandidates: tuple[AIKnowledgeChunk, ...] = ()
    selectedCandidates: tuple[AIKnowledgeChunk, ...] = ()
    id: uuid.UUID = field(default_factory=newId)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.id = requireUuid(self.id, "id")
        if not self.query.strip():
            raise ValueError("Retrieval query is required.")

    def authorize(self, items: Iterable[AIKnowledgeChunk]) -> None:
        self.authorizedCandidates = tuple(items)

    def select(self, limit: int) -> None:
        if limit < 1:
            raise ValueError("Retrieval limit must be positive.")
        self.selectedCandidates = self.authorizedCandidates[:limit]


@dataclass
class AIUsage:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    providerId: uuid.UUID
    modelId: uuid.UUID
    usage: TokenUsage
    latencyMs: int = 0
    queueTimeMs: int = 0
    contextBuildTimeMs: int = 0
    providerTimeMs: int = 0
    validationTimeMs: int = 0
    id: uuid.UUID = field(default_factory=newId)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.providerId = requireUuid(self.providerId, "providerId")
        self.modelId = requireUuid(self.modelId, "modelId")
        self.id = requireUuid(self.id, "id")
        if min(self.latencyMs, self.queueTimeMs, self.contextBuildTimeMs, self.providerTimeMs, self.validationTimeMs) < 0:
            raise ValueError("AI timings cannot be negative.")

    def cost(self, rate: CostRate) -> Decimal:
        return rate.calculate(self.usage).amount


@dataclass
class AICost:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    usageId: uuid.UUID
    amount: Decimal
    currency: str = "USD"
    id: uuid.UUID = field(default_factory=newId)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.usageId = requireUuid(self.usageId, "usageId")
        self.amount = Decimal(str(self.amount))
        self.currency = str(self.currency or "").upper()
        if self.amount < 0 or len(self.currency) != 3 or not self.currency.isalpha():
            raise ValueError("AI cost amount/currency is invalid.")


@dataclass
class AIFeedback:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    responseId: uuid.UUID
    userId: uuid.UUID | None = None
    rating: int | None = None
    sentiment: str = "NEUTRAL"
    correction: str = ""
    comment: str = ""
    id: uuid.UUID = field(default_factory=newId)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.responseId = requireUuid(self.responseId, "responseId")
        self.id = requireUuid(self.id, "id")
        if self.userId is not None:
            self.userId = requireUuid(self.userId, "userId")
        if self.rating is not None and not 1 <= self.rating <= 5:
            raise ValueError("Feedback rating must be between one and five.")
        self.sentiment = ensureEnum(self.sentiment, FEEDBACK_SENTIMENTS, "feedbackSentiment")


@dataclass
class AIEvaluation:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    method: str
    evaluatorId: uuid.UUID | None = None
    id: uuid.UUID = field(default_factory=newId)
    metrics: dict[str, float] = field(default_factory=dict)
    notes: str = ""
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.id = requireUuid(self.id, "id")
        if self.evaluatorId is not None:
            self.evaluatorId = requireUuid(self.evaluatorId, "evaluatorId")
        self.method = ensureEnum(self.method, EVALUATION_METHODS, "evaluationMethod")
        if any(value < 0 or value > 1 for value in self.metrics.values()):
            raise ValueError("Evaluation metrics must be between zero and one.")


@dataclass
class AIAuditRecord:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    action: str
    actorId: uuid.UUID | None = None
    providerCode: str = ""
    modelCode: str = ""
    promptVersion: str = ""
    contextSources: tuple[str, ...] = ()
    resultClassification: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    redacted: bool = True
    id: uuid.UUID = field(default_factory=newId)
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.id = requireUuid(self.id, "id")
        if self.actorId is not None:
            self.actorId = requireUuid(self.actorId, "actorId")
        if self.resultClassification:
            self.resultClassification = ensureEnum(
                self.resultClassification, OUTPUT_CLASSIFICATIONS, "resultClassification"
            )


@dataclass
class AITool:
    tenantId: uuid.UUID
    code: str
    name: str
    description: str
    inputSchema: dict[str, Any] = field(default_factory=dict)
    outputSchema: dict[str, Any] = field(default_factory=dict)
    requiredPermission: str = ""
    enabled: bool = True
    id: uuid.UUID = field(default_factory=newId)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.code = validateCode(self.code, "toolCode")
        if not self.name.strip() or not self.description.strip():
            raise ValueError("Tool name and description are required.")


@dataclass
class AIToolExecution:
    tenantId: uuid.UUID
    requestId: uuid.UUID
    toolId: uuid.UUID
    inputData: dict[str, Any]
    id: uuid.UUID = field(default_factory=newId)
    status: str = "PENDING"
    outputData: dict[str, Any] = field(default_factory=dict)
    errorCode: str = ""
    approved: bool = False
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.requestId = requireUuid(self.requestId, "requestId")
        self.toolId = requireUuid(self.toolId, "toolId")
        self.id = requireUuid(self.id, "id")
        self.status = ensureEnum(self.status, TOOL_EXECUTION_STATUSES, "toolExecutionStatus")

    def transitionTo(self, status: str, *, errorCode: str = "") -> None:
        status = ensureEnum(status, TOOL_EXECUTION_STATUSES, "toolExecutionStatus")
        allowed = {
            "PENDING": {"RUNNING", "DENIED", "CANCELLED"},
            "RUNNING": {"SUCCEEDED", "FAILED", "CANCELLED"},
            "SUCCEEDED": set(),
            "FAILED": set(),
            "DENIED": set(),
            "CANCELLED": set(),
        }
        if status != self.status and status not in allowed[self.status]:
            raise ValueError(f"Invalid tool execution transition {self.status} → {status}.")
        self.status = status
        if errorCode:
            self.errorCode = errorCode


@dataclass
class AIAgent:
    tenantId: uuid.UUID
    code: str
    name: str
    instructions: str
    capabilityCodes: tuple[str, ...] = ()
    toolCodes: tuple[str, ...] = ()
    memoryScope: str = "AGENT"
    contextPolicy: dict[str, Any] = field(default_factory=dict)
    modelPolicy: dict[str, Any] = field(default_factory=dict)
    permissionPolicy: dict[str, Any] = field(default_factory=dict)
    executionPolicy: dict[str, Any] = field(default_factory=dict)
    id: uuid.UUID = field(default_factory=newId)
    isActive: bool = True

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.id = requireUuid(self.id, "id")
        self.code = validateCode(self.code, "agentCode")
        self.memoryScope = ensureEnum(self.memoryScope, MEMORY_SCOPES, "memoryScope")
        if not self.name.strip() or not self.instructions.strip():
            raise ValueError("Agent name and instructions are required.")


@dataclass
class AIAgentExecution:
    tenantId: uuid.UUID
    agentId: uuid.UUID
    requestedBy: uuid.UUID | None
    inputData: dict[str, Any]
    id: uuid.UUID = field(default_factory=newId)
    status: str = "PENDING"
    rootRequestId: uuid.UUID | None = None
    outputData: dict[str, Any] = field(default_factory=dict)
    errorCode: str = ""
    createdAt: datetime = field(default_factory=utcNow)

    def __post_init__(self) -> None:
        self.tenantId = requireUuid(self.tenantId, "tenantId")
        self.agentId = requireUuid(self.agentId, "agentId")
        self.id = requireUuid(self.id, "id")
        if self.requestedBy is not None:
            self.requestedBy = requireUuid(self.requestedBy, "requestedBy")
        if self.rootRequestId is not None:
            self.rootRequestId = requireUuid(self.rootRequestId, "rootRequestId")
        self.status = ensureEnum(self.status, AGENT_EXECUTION_STATUSES, "agentExecutionStatus")

    def transitionTo(self, status: str, *, errorCode: str = "") -> None:
        status = ensureEnum(status, AGENT_EXECUTION_STATUSES, "agentExecutionStatus")
        allowed = {
            "PENDING": {"RUNNING", "DENIED", "CANCELLED"},
            "RUNNING": {"COMPLETED", "FAILED", "CANCELLED"},
            "COMPLETED": set(),
            "FAILED": set(),
            "CANCELLED": set(),
            "DENIED": set(),
        }
        if status != self.status and status not in allowed[self.status]:
            raise ValueError(f"Invalid agent execution transition {self.status} → {status}.")
        self.status = status
        if errorCode:
            self.errorCode = errorCode
