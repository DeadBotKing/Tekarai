"""Pure Context Engine and Context Builder for Phase 13-J.

J assembles the minimum authorized context for an ``AIRequest``.  It consumes
Tenant-bound source candidates, applies the Domain ``ContextPolicy`` before
assembly, redacts allowed restricted sources when configured, enforces source,
character and token budgets, and returns the Phase 13-B ``AIContext`` entity.

No source repository, ORM, HTTP client, queue, worker, vector store, provider
SDK, or permission service is used here.  The caller supplies an already
Tenant-scoped source set and may supply a pure permission predicate.  An
unscoped ``ContextSource`` is rejected rather than guessed to belong to the
requested Tenant.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from apps.ai.domain.entities.aiRecords import AIContext, requireUuid, utcNow
from apps.ai.domain.exceptions import (
    AIContextAlreadyRegistered,
    AIContextNotFound,
    AIContextPolicyInvalid,
    AIContextSourceInvalid,
    AIContextTenantMismatch,
    AIContextTooLarge,
)
from apps.ai.domain.policies.aiPolicies import ContextPolicy
from apps.ai.domain.services.aiRules import estimateTokens
from apps.ai.domain.valueObjects.aiTypes import ContextSource, DataClassification


REDACTED_RESTRICTED_TEXT = "[REDACTED:RESTRICTED]"
SENSITIVE_METADATA_KEYS = frozenset(
    {
        "api_key",
        "apikey",
        "password",
        "secret",
        "secret_key",
        "token",
        "access_token",
        "refresh_token",
        "connection_string",
    }
)


def _normalizeClassification(value: str) -> str:
    try:
        return str(DataClassification(value))
    except Exception as exc:
        raise AIContextSourceInvalid("Context source classification is invalid.") from exc


def _redactMetadata(value: Any) -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                continue
            normalized = key.replace("-", "_").lower()
            if normalized in SENSITIVE_METADATA_KEYS:
                continue
            result[key] = _redactMetadata(item)
        return result
    if isinstance(value, (list, tuple)):
        return [_redactMetadata(item) for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    return "[REDACTED]"


def _contentFingerprint(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def _sourceKey(source: "ContextSourceCandidate") -> tuple[str, str, str]:
    return source.sourceDomain, source.sourceEntityType, source.sourceEntityId


@dataclass(frozen=True)
class ContextSourceCandidate:
    """Tenant-bound source input supplied by an Application/Domain adapter."""

    tenantId: uuid.UUID | str
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    content: str
    classification: str = "INTERNAL"
    authorized: bool = True
    metadata: Mapping[str, Any] | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        object.__setattr__(self, "classification", _normalizeClassification(self.classification))
        if not all(
            isinstance(value, str) and value.strip()
            for value in (self.sourceDomain, self.sourceEntityType, self.sourceEntityId)
        ):
            raise AIContextSourceInvalid("Context source identity is required.")
        if not isinstance(self.content, str):
            raise AIContextSourceInvalid("Context source content must be a string.")
        if self.metadata is not None and not isinstance(self.metadata, Mapping):
            raise AIContextSourceInvalid("Context source metadata must be a mapping.")
        if self.metadata is not None:
            object.__setattr__(self, "metadata", copy.deepcopy(dict(self.metadata)))

    def sanitizedMetadata(self) -> dict[str, Any]:
        return _redactMetadata(self.metadata or {})

    def toEntity(self, *, content: str | None = None, allowed: bool = True) -> ContextSource:
        return ContextSource(
            sourceDomain=self.sourceDomain,
            sourceEntityType=self.sourceEntityType,
            sourceEntityId=self.sourceEntityId,
            content=self.content if content is None else content,
            classification=self.classification,
            allowed=allowed,
            metadata=self.sanitizedMetadata(),
        )


@dataclass(frozen=True)
class ContextSourceDescriptor:
    """Safe source decision; content and metadata are intentionally omitted."""

    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    classification: str
    included: bool
    exclusionReason: str = ""
    wasRedacted: bool = False


@dataclass(frozen=True)
class ContextDescriptor:
    """Safe, immutable Context read model for traceability and observability."""

    tenantId: uuid.UUID
    requestId: uuid.UUID
    contextId: uuid.UUID
    sourceCount: int
    includedSourceKeys: tuple[tuple[str, str, str], ...]
    excludedSourceCount: int
    contentLength: int
    tokenCount: int
    contentFingerprint: str
    redacted: bool
    externalProvider: bool
    createdAt: datetime


@dataclass(frozen=True)
class ContextBuildResult:
    """Build output containing the Context entity plus safe decision metadata."""

    context: AIContext
    descriptor: ContextDescriptor
    includedSources: tuple[ContextSourceDescriptor, ...]
    excludedSources: tuple[ContextSourceDescriptor, ...]
    tenantScoped: bool = field(default=False, repr=False, compare=False)


class ContextBuilder:
    """Build an authorized, budgeted ``AIContext`` without fetching data."""

    def __init__(self, *, now: Callable[[], datetime] = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now

    def build(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        sources: Iterable[ContextSourceCandidate],
        policy: ContextPolicy | None = None,
        *,
        externalProvider: bool = False,
        contextId: uuid.UUID | str | None = None,
        permissionFilter: Callable[[ContextSourceCandidate], bool] | None = None,
    ) -> ContextBuildResult:
        tenant = requireUuid(tenantId, "tenantId")
        request = requireUuid(requestId, "requestId")
        contextPolicy = ContextPolicy() if policy is None else policy
        if not isinstance(contextPolicy, ContextPolicy):
            raise AIContextPolicyInvalid("Context policy must be a ContextPolicy.")
        if permissionFilter is not None and not callable(permissionFilter):
            raise AIContextPolicyInvalid("permissionFilter must be callable.")

        includedEntities: list[Any] = []
        includedDescriptors: list[ContextSourceDescriptor] = []
        excludedDescriptors: list[ContextSourceDescriptor] = []
        includedKeys: list[tuple[str, str, str]] = []
        seenKeys: set[tuple[str, str, str]] = set()
        pieces: list[str] = []
        redactedAny = False

        for rawSource in sources:
            source = self._requireTenantSource(tenant, rawSource)
            key = _sourceKey(source)
            if key in seenKeys:
                excludedDescriptors.append(
                    self._descriptor(source, included=False, reason="DUPLICATE_SOURCE")
                )
                continue
            seenKeys.add(key)

            if not source.authorized:
                excludedDescriptors.append(
                    self._descriptor(source, included=False, reason="NOT_AUTHORIZED")
                )
                continue
            if permissionFilter is not None:
                try:
                    permitted = bool(permissionFilter(source))
                except Exception as exc:
                    raise AIContextPolicyInvalid("Context permission filter failed safely.") from exc
                if not permitted:
                    excludedDescriptors.append(
                        self._descriptor(source, included=False, reason="PERMISSION_FILTERED")
                    )
                    continue
            if not contextPolicy.permits(source.classification, externalProvider=externalProvider):
                reason = (
                    "EXTERNAL_PROVIDER_NOT_PERMITTED"
                    if externalProvider and not contextPolicy.allowExternalProvider
                    else "CLASSIFICATION_NOT_PERMITTED"
                )
                excludedDescriptors.append(self._descriptor(source, included=False, reason=reason))
                continue
            if not source.content.strip():
                excludedDescriptors.append(
                    self._descriptor(source, included=False, reason="EMPTY_CONTENT")
                )
                continue
            if len(includedEntities) >= contextPolicy.maxSources:
                excludedDescriptors.append(
                    self._descriptor(source, included=False, reason="MAX_SOURCES")
                )
                continue

            content = source.content
            wasRedacted = False
            if source.classification == "RESTRICTED" and contextPolicy.redactRestricted:
                content = REDACTED_RESTRICTED_TEXT
                wasRedacted = True
            candidatePieces = pieces + [content]
            candidateContent = "\n\n".join(candidatePieces)
            if len(candidateContent) > contextPolicy.maxCharacters:
                excludedDescriptors.append(
                    self._descriptor(source, included=False, reason="MAX_CHARACTERS")
                )
                continue
            candidateTokens = estimateTokens(candidateContent)
            if candidateTokens > contextPolicy.maxTokens:
                excludedDescriptors.append(
                    self._descriptor(source, included=False, reason="MAX_TOKENS")
                )
                continue

            pieces = candidatePieces
            redactedAny = redactedAny or wasRedacted
            includedKeys.append(key)
            includedEntities.append(
                source.toEntity(content=content, allowed=True)
            )
            includedDescriptors.append(
                self._descriptor(source, included=True, wasRedacted=wasRedacted)
            )

        content = "\n\n".join(pieces)
        tokenCount = estimateTokens(content)
        try:
            context = AIContext(
                tenantId=tenant,
                requestId=request,
                sources=tuple(includedEntities),
                content=content,
                tokenCount=tokenCount,
                id=(requireUuid(contextId, "contextId") if contextId is not None else uuid.uuid4()),
                redacted=redactedAny,
                createdAt=self._now(),
            )
            context.enforceLimit(contextPolicy.maxTokens, contextPolicy.maxCharacters)
        except AIContextTooLarge:
            raise
        except (TypeError, ValueError) as exc:
            raise AIContextPolicyInvalid("Context could not be assembled under the policy.") from exc

        descriptor = ContextDescriptor(
            tenantId=tenant,
            requestId=request,
            contextId=context.id,
            sourceCount=len(includedEntities),
            includedSourceKeys=tuple(includedKeys),
            excludedSourceCount=len(excludedDescriptors),
            contentLength=len(content),
            tokenCount=tokenCount,
            contentFingerprint=_contentFingerprint(content),
            redacted=redactedAny,
            externalProvider=externalProvider,
            createdAt=context.createdAt,
        )
        return ContextBuildResult(
            context=context,
            descriptor=descriptor,
            includedSources=tuple(includedDescriptors),
            excludedSources=tuple(excludedDescriptors),
            tenantScoped=True,
        )

    def buildContext(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        sources: Iterable[ContextSourceCandidate],
        policy: ContextPolicy | None = None,
        *,
        externalProvider: bool = False,
        contextId: uuid.UUID | str | None = None,
        permissionFilter: Callable[[ContextSourceCandidate], bool] | None = None,
    ) -> ContextBuildResult:
        """Named alias matching the orchestration terminology."""

        return self.build(
            tenantId,
            requestId,
            sources,
            policy,
            externalProvider=externalProvider,
            contextId=contextId,
            permissionFilter=permissionFilter,
        )

    @staticmethod
    def _requireTenantSource(
        tenantId: uuid.UUID,
        source: ContextSourceCandidate,
    ) -> ContextSourceCandidate:
        if not isinstance(source, ContextSourceCandidate):
            raise AIContextSourceInvalid(
                "Context sources must be Tenant-bound ContextSourceCandidate objects."
            )
        if source.tenantId != tenantId:
            raise AIContextTenantMismatch("Context source belongs to another Tenant.")
        return source

    @staticmethod
    def _descriptor(
        source: ContextSourceCandidate,
        *,
        included: bool,
        reason: str = "",
        wasRedacted: bool = False,
    ) -> ContextSourceDescriptor:
        return ContextSourceDescriptor(
            sourceDomain=source.sourceDomain,
            sourceEntityType=source.sourceEntityType,
            sourceEntityId=source.sourceEntityId,
            classification=source.classification,
            included=included,
            exclusionReason=reason,
            wasRedacted=wasRedacted,
        )


class ContextEngine:
    """Tenant-scoped in-memory Context registration and safe read boundary."""

    def __init__(
        self,
        *,
        builder: ContextBuilder | None = None,
        now: Callable[[], datetime] = utcNow,
    ) -> None:
        if builder is not None and not isinstance(builder, ContextBuilder):
            raise TypeError("builder must be a ContextBuilder.")
        if not callable(now):
            raise TypeError("now must be callable.")
        self.builder = builder or ContextBuilder(now=now)
        self._now = now
        self._results: dict[tuple[uuid.UUID, uuid.UUID], ContextBuildResult] = {}

    def buildContext(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
        sources: Iterable[ContextSourceCandidate],
        policy: ContextPolicy | None = None,
        *,
        externalProvider: bool = False,
        contextId: uuid.UUID | str | None = None,
        permissionFilter: Callable[[ContextSourceCandidate], bool] | None = None,
    ) -> ContextBuildResult:
        result = self.builder.build(
            tenantId,
            requestId,
            sources,
            policy,
            externalProvider=externalProvider,
            contextId=contextId,
            permissionFilter=permissionFilter,
        )
        key = (result.context.tenantId, result.context.id)
        if key in self._results:
            raise AIContextAlreadyRegistered(str(result.context.id))
        self._results[key] = copy.deepcopy(result)
        return copy.deepcopy(result)

    def registerContext(
        self,
        context: AIContext,
        *,
        descriptor: ContextDescriptor | None = None,
    ) -> AIContext:
        """Register a context that has no unscoped source payload.

        A raw B ``ContextSource`` has no Tenant identity, so a caller cannot
        safely register an arbitrary populated ``AIContext`` here.  Populated
        contexts must come from ``buildContext`` or ``registerResult`` where
        the source candidates carry explicit Tenant scope.
        """

        if not isinstance(context, AIContext):
            raise AIContextPolicyInvalid("Context must be an AIContext.")
        key = (context.tenantId, context.id)
        if key in self._results:
            raise AIContextAlreadyRegistered(str(context.id))
        if context.sources:
            raise AIContextSourceInvalid(
                "Populated contexts must be built from Tenant-scoped source candidates."
            )
        safeDescriptor = descriptor or self._descriptorFromContext(context)
        if safeDescriptor.tenantId != context.tenantId or safeDescriptor.contextId != context.id:
            raise AIContextTenantMismatch("Context descriptor does not belong to the Context.")
        result = ContextBuildResult(
            context=copy.deepcopy(context),
            descriptor=copy.deepcopy(safeDescriptor),
            includedSources=(),
            excludedSources=(),
            tenantScoped=True,
        )
        self._results[key] = result
        return copy.deepcopy(context)

    def registerResult(self, result: ContextBuildResult) -> AIContext:
        """Register a previously built, explicitly Tenant-scoped result."""

        if not isinstance(result, ContextBuildResult) or not result.tenantScoped:
            raise AIContextSourceInvalid(
                "Only a ContextBuildResult produced by the Tenant-scoped builder may be registered."
            )
        if result.descriptor.tenantId != result.context.tenantId or result.descriptor.contextId != result.context.id:
            raise AIContextTenantMismatch("Context result descriptor does not belong to the Context.")
        key = (result.context.tenantId, result.context.id)
        if key in self._results:
            raise AIContextAlreadyRegistered(str(result.context.id))
        self._results[key] = copy.deepcopy(result)
        return copy.deepcopy(result.context)

    createContext = buildContext

    def register(self, context: AIContext, *, descriptor: ContextDescriptor | None = None) -> AIContext:
        return self.registerContext(context, descriptor=descriptor)

    def getContext(self, tenantId: uuid.UUID | str, contextId: uuid.UUID | str) -> AIContext:
        result = self._getResult(tenantId, contextId)
        return copy.deepcopy(result.context)

    def getResult(self, tenantId: uuid.UUID | str, contextId: uuid.UUID | str) -> ContextBuildResult:
        return copy.deepcopy(self._getResult(tenantId, contextId))

    def describeContext(self, tenantId: uuid.UUID | str, contextId: uuid.UUID | str) -> ContextDescriptor:
        return copy.deepcopy(self._getResult(tenantId, contextId).descriptor)

    def latestForRequest(
        self,
        tenantId: uuid.UUID | str,
        requestId: uuid.UUID | str,
    ) -> ContextBuildResult | None:
        tenant = requireUuid(tenantId, "tenantId")
        request = requireUuid(requestId, "requestId")
        matches = [
            result
            for (contextTenant, _), result in self._results.items()
            if contextTenant == tenant and result.context.requestId == request
        ]
        if not matches:
            return None
        return copy.deepcopy(max(matches, key=lambda result: (result.context.createdAt, str(result.context.id))))

    def listContexts(
        self,
        tenantId: uuid.UUID | str,
        *,
        requestId: uuid.UUID | str | None = None,
    ) -> tuple[ContextDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        request = requireUuid(requestId, "requestId") if requestId is not None else None
        descriptors = [
            result.descriptor
            for (contextTenant, _), result in self._results.items()
            if contextTenant == tenant and (request is None or result.context.requestId == request)
        ]
        return tuple(
            sorted(
                (copy.deepcopy(descriptor) for descriptor in descriptors),
                key=lambda item: (item.createdAt, str(item.contextId)),
            )
        )

    def clear(self) -> None:
        self._results.clear()

    def _getResult(
        self,
        tenantId: uuid.UUID | str,
        contextId: uuid.UUID | str,
    ) -> ContextBuildResult:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(contextId, "contextId")
        result = self._results.get((tenant, identifier))
        if result is None:
            raise AIContextNotFound(str(identifier))
        return result

    @staticmethod
    def _descriptorFromContext(context: AIContext) -> ContextDescriptor:
        keys = tuple(
            (source.sourceDomain, source.sourceEntityType, source.sourceEntityId)
            for source in context.sources
        )
        return ContextDescriptor(
            tenantId=context.tenantId,
            requestId=context.requestId,
            contextId=context.id,
            sourceCount=len(context.sources),
            includedSourceKeys=keys,
            excludedSourceCount=0,
            contentLength=len(context.content),
            tokenCount=context.tokenCount,
            contentFingerprint=_contentFingerprint(context.content),
            redacted=context.redacted,
            externalProvider=False,
            createdAt=context.createdAt,
        )


AIContextBuilder = ContextBuilder
AIContextEngine = ContextEngine
AIContextSourceCandidate = ContextSourceCandidate
TenantBoundContextSource = ContextSourceCandidate
ContextService = ContextEngine
InMemoryContextEngine = ContextEngine
ContextBuilderService = ContextBuilder

__all__ = [
    "AIContextBuilder",
    "AIContextEngine",
    "AIContextSourceCandidate",
    "ContextBuildResult",
    "ContextBuilder",
    "ContextBuilderService",
    "ContextDescriptor",
    "ContextEngine",
    "ContextService",
    "ContextSourceCandidate",
    "ContextSourceDescriptor",
    "InMemoryContextEngine",
    "TenantBoundContextSource",
    "REDACTED_RESTRICTED_TEXT",
]
