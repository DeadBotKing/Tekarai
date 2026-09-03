"""Pure, tenant-aware Prompt Platform and Versioning for Phase 13-I.

This module coordinates the Phase 13-B ``AIPrompt`` and ``AIPromptVersion``
entities.  Prompt contents are immutable by version inside this in-memory
platform: a new change creates a new version, and activation only changes the
prompt's active pointer.  Persistence, authorization, approval workflow and
API concerns remain outside the Domain boundary.

Templates use a deliberately small safe subset of Python's format syntax:
only declared, simple identifier fields are accepted. Attribute access,
indexing, conversion flags and format specifications are rejected so a prompt
cannot turn a variable into an arbitrary object traversal expression.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
import string
import uuid
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Mapping

from apps.ai.domain.entities.aiRecords import AIPrompt, AIPromptVersion, requireUuid
from apps.ai.domain.exceptions import (
    AIError,
    AIPromptAlreadyRegistered,
    AIPromptLifecycleInvalid,
    AIPromptNotFound,
    AIPromptOutputSchemaInvalid,
    AIPromptTemplateInvalid,
    AIPromptVersionAlreadyRegistered,
    AIPromptVersionImmutable,
    AIPromptVersionNotFound,
    AIStructuredSchemaInvalid,
)
from apps.ai.domain.services.responseLifecycle import StructuredOutputSchema
from apps.ai.domain.valueObjects.aiTypes import validateCode


IDENTIFIER_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
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


def utcNow() -> datetime:
    return datetime.now(tz=UTC)


def _normalizePromptCode(value: str) -> str:
    try:
        return validateCode(value, "promptCode")
    except Exception as exc:
        raise AIPromptLifecycleInvalid("Prompt code is invalid.") from exc


def _normalizeVariables(variables: tuple[str, ...] | list[str] | None) -> tuple[str, ...]:
    values = tuple(variables or ())
    if any(not isinstance(value, str) or not IDENTIFIER_PATTERN.fullmatch(value) for value in values):
        raise AIPromptTemplateInvalid("Prompt variables must be simple identifiers.")
    if len(set(values)) != len(values):
        raise AIPromptTemplateInvalid("Prompt variables cannot be duplicated.")
    return values


def _validateTemplate(template: str, variables: tuple[str, ...]) -> None:
    if not isinstance(template, str) or not template.strip():
        raise AIPromptTemplateInvalid("Prompt template is required.")
    try:
        parsed = tuple(string.Formatter().parse(template))
    except (TypeError, ValueError) as exc:
        raise AIPromptTemplateInvalid("Prompt template has invalid format syntax.") from exc
    declared = set(variables)
    for _literal, fieldName, formatSpec, conversion in parsed:
        if fieldName is None:
            continue
        if (
            not IDENTIFIER_PATTERN.fullmatch(fieldName)
            or fieldName not in declared
            or formatSpec
            or conversion is not None
        ):
            raise AIPromptTemplateInvalid(
                "Prompt template may use only declared simple variables without formatting expressions."
            )


def _normalizeSafeMapping(value: Any, path: str = "$") -> Any:
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise AIPromptLifecycleInvalid(f"Prompt metadata key at {path} must be a string.")
            if key.replace("-", "_").lower() in SENSITIVE_METADATA_KEYS:
                raise AIPromptLifecycleInvalid("Prompt metadata cannot contain secret-like keys.")
            result[key] = _normalizeSafeMapping(item, f"{path}.{key}")
        return result
    if isinstance(value, (list, tuple)):
        return [_normalizeSafeMapping(item, f"{path}[]") for item in value]
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    raise AIPromptLifecycleInvalid(f"Prompt metadata at {path} must be JSON-compatible.")


def _copy(value: Any) -> Any:
    return copy.deepcopy(value)


@dataclass(frozen=True)
class PromptDescriptor:
    """Safe immutable Prompt read model without template or instruction text."""

    tenantId: uuid.UUID
    promptId: uuid.UUID
    code: str
    name: str
    description: str
    isActive: bool
    activeVersionId: uuid.UUID | None
    versionCount: int
    activeVersion: int | None
    createdAt: datetime


@dataclass(frozen=True)
class PromptVersionDescriptor:
    """Safe immutable version read model without prompt content or full Schema."""

    tenantId: uuid.UUID
    promptId: uuid.UUID
    versionId: uuid.UUID
    version: int
    isActive: bool
    variables: tuple[str, ...]
    hasOutputSchema: bool
    outputSchemaFingerprint: str
    hasModelConstraints: bool
    createdBy: uuid.UUID | None
    createdAt: datetime


@dataclass(frozen=True)
class RenderedPrompt:
    """A render result; text is available to the caller but hidden from repr/logs."""

    tenantId: uuid.UUID
    promptId: uuid.UUID
    versionId: uuid.UUID
    version: int
    variableNames: tuple[str, ...]
    renderedText: str = field(repr=False)
    outputSchemaFingerprint: str = ""

    def asText(self) -> str:
        return self.renderedText


class PromptPlatformService:
    """In-memory Tenant-scoped Prompt/Version registry for Phase 13-I."""

    def __init__(self, *, now: Any = utcNow) -> None:
        if not callable(now):
            raise TypeError("now must be callable.")
        self._now = now
        self._prompts: dict[tuple[uuid.UUID, str], AIPrompt] = {}
        self._versions: dict[tuple[uuid.UUID, uuid.UUID], AIPromptVersion] = {}
        self._versionKeys: dict[tuple[uuid.UUID, uuid.UUID, int], uuid.UUID] = {}

    # ------------------------------------------------------------------
    # Prompt registration and lifecycle
    # ------------------------------------------------------------------
    def createPrompt(
        self,
        tenantId: uuid.UUID | str,
        code: str,
        name: str,
        *,
        description: str = "",
        promptId: uuid.UUID | str | None = None,
        isActive: bool = True,
    ) -> AIPrompt:
        tenant = requireUuid(tenantId, "tenantId")
        normalizedCode = _normalizePromptCode(code)
        identifier = requireUuid(promptId, "promptId") if promptId is not None else uuid.uuid4()
        key = (tenant, normalizedCode)
        if key in self._prompts:
            raise AIPromptAlreadyRegistered(normalizedCode)
        try:
            prompt = AIPrompt(
                tenantId=tenant,
                code=normalizedCode,
                name=name,
                description=description,
                id=identifier,
                isActive=isActive,
                createdAt=self._now(),
            )
        except AIPromptAlreadyRegistered:
            raise
        except Exception as exc:
            raise AIPromptLifecycleInvalid("Prompt definition is invalid.") from exc
        self._prompts[key] = _copy(prompt)
        return _copy(prompt)

    def registerPrompt(self, prompt: AIPrompt, *, replace: bool = False) -> AIPrompt:
        if not isinstance(prompt, AIPrompt):
            raise AIPromptLifecycleInvalid("Prompt definition must be an AIPrompt.")
        key = (prompt.tenantId, prompt.code)
        if key in self._prompts and not replace:
            raise AIPromptAlreadyRegistered(prompt.code)
        if key in self._prompts and replace:
            existing = self._prompts[key]
            if existing.id != prompt.id:
                raise AIPromptLifecycleInvalid("Prompt replacement cannot change the Prompt ID.")
        self._prompts[key] = _copy(prompt)
        return _copy(prompt)

    def getPrompt(self, tenantId: uuid.UUID | str, promptCode: str) -> AIPrompt:
        tenant = requireUuid(tenantId, "tenantId")
        code = _normalizePromptCode(promptCode)
        prompt = self._prompts.get((tenant, code))
        if prompt is None:
            raise AIPromptNotFound(code)
        return _copy(prompt)

    def getPromptById(self, tenantId: uuid.UUID | str, promptId: uuid.UUID | str) -> AIPrompt:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(promptId, "promptId")
        for (promptTenant, _), prompt in self._prompts.items():
            if promptTenant == tenant and prompt.id == identifier:
                return _copy(prompt)
        raise AIPromptNotFound(str(identifier))

    def activatePrompt(self, tenantId: uuid.UUID | str, promptCode: str) -> PromptDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptEntity(tenant, promptCode)
        prompt.isActive = True
        return self.describePrompt(tenant, prompt.code)

    def deactivatePrompt(self, tenantId: uuid.UUID | str, promptCode: str) -> PromptDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptEntity(tenant, promptCode)
        prompt.isActive = False
        return self.describePrompt(tenant, prompt.code)

    # ------------------------------------------------------------------
    # Version registration and activation
    # ------------------------------------------------------------------
    def createVersion(
        self,
        tenantId: uuid.UUID | str,
        promptId: uuid.UUID | str,
        template: str,
        *,
        version: int | None = None,
        systemInstruction: str = "",
        variables: tuple[str, ...] | list[str] = (),
        outputSchema: Mapping[str, Any] | None = None,
        modelConstraints: Mapping[str, Any] | None = None,
        createdBy: uuid.UUID | str | None = None,
        versionId: uuid.UUID | str | None = None,
        activate: bool = False,
    ) -> AIPromptVersion:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptByIdEntity(tenant, promptId)
        normalizedVariables = _normalizeVariables(variables)
        _validateTemplate(template, normalizedVariables)
        normalizedSchema = self._normalizeOutputSchema(outputSchema)
        normalizedConstraints = _normalizeSafeMapping(modelConstraints or {})
        nextVersion = self._nextVersion(tenant, prompt.id) if version is None else version
        if not isinstance(nextVersion, int) or isinstance(nextVersion, bool) or nextVersion < 1:
            raise AIPromptLifecycleInvalid("Prompt version must be a positive integer.")
        identifier = requireUuid(versionId, "versionId") if versionId is not None else uuid.uuid4()
        try:
            promptVersion = AIPromptVersion(
                tenantId=tenant,
                promptId=prompt.id,
                version=nextVersion,
                template=template,
                systemInstruction=systemInstruction,
                variables=normalizedVariables,
                outputSchema=normalizedSchema,
                modelConstraints=normalizedConstraints,
                createdBy=(requireUuid(createdBy, "createdBy") if createdBy is not None else None),
                id=identifier,
                isActive=False,
                createdAt=self._now(),
            )
        except Exception as exc:
            raise AIPromptLifecycleInvalid("Prompt version definition is invalid.") from exc
        registered = self.registerVersion(promptVersion)
        if activate:
            self.activateVersion(tenant, prompt.id, registered.id)
            registered = self._getVersionEntity(tenant, registered.id)
        return _copy(registered)

    def registerVersion(self, promptVersion: AIPromptVersion, *, replace: bool = False) -> AIPromptVersion:
        if not isinstance(promptVersion, AIPromptVersion):
            raise AIPromptLifecycleInvalid("Prompt version definition must be an AIPromptVersion.")
        prompt = self._getPromptByIdEntity(promptVersion.tenantId, promptVersion.promptId)
        normalizedVariables = _normalizeVariables(promptVersion.variables)
        _validateTemplate(promptVersion.template, normalizedVariables)
        normalizedSchema = self._normalizeOutputSchema(promptVersion.outputSchema)
        normalizedConstraints = _normalizeSafeMapping(promptVersion.modelConstraints or {})
        versionKey = (promptVersion.tenantId, promptVersion.promptId, promptVersion.version)
        idKey = (promptVersion.tenantId, promptVersion.id)
        existingId = self._versionKeys.get(versionKey)
        if existingId is not None:
            if not replace:
                raise AIPromptVersionAlreadyRegistered(promptVersion.version)
            raise AIPromptVersionImmutable("Prompt versions cannot be replaced or overwritten.")
        if idKey in self._versions:
            raise AIPromptVersionAlreadyRegistered(str(promptVersion.id))
        if promptVersion.version < 1:
            raise AIPromptLifecycleInvalid("Prompt version must be positive.")
        latestVersion = max(
            (version.version for version in self._versionsForPrompt(promptVersion.tenantId, promptVersion.promptId)),
            default=0,
        )
        if promptVersion.version <= latestVersion:
            raise AIPromptLifecycleInvalid("A new Prompt Version must be higher than the latest version.")
        if promptVersion.isActive:
            # Registration never silently activates a version; activation is a
            # separate command so only one active pointer can be changed.
            raise AIPromptLifecycleInvalid("Use activateVersion as an explicit command.")
        stored = _copy(promptVersion)
        stored.variables = normalizedVariables
        stored.outputSchema = normalizedSchema
        stored.modelConstraints = normalizedConstraints
        stored.isActive = False
        self._versions[idKey] = stored
        self._versionKeys[versionKey] = stored.id
        # Ensure the containing Prompt exists before any version index is left.
        _ = prompt
        return _copy(stored)

    def getVersion(self, tenantId: uuid.UUID | str, versionId: uuid.UUID | str) -> AIPromptVersion:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(versionId, "versionId")
        return _copy(self._getVersionEntity(tenant, identifier))

    def getActiveVersion(self, tenantId: uuid.UUID | str, promptCode: str) -> AIPromptVersion:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptEntity(tenant, promptCode)
        if not prompt.isActive:
            raise AIPromptLifecycleInvalid("Inactive Prompt cannot resolve an active version.")
        if prompt.activeVersionId is None:
            raise AIPromptVersionNotFound(str(prompt.id))
        version = self._getVersionEntity(tenant, prompt.activeVersionId)
        if version.promptId != prompt.id or not version.isActive:
            raise AIPromptLifecycleInvalid("Prompt active version pointer is inconsistent.")
        return _copy(version)

    def activateVersion(
        self,
        tenantId: uuid.UUID | str,
        promptId: uuid.UUID | str,
        versionId: uuid.UUID | str,
    ) -> PromptVersionDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptByIdEntity(tenant, promptId)
        version = self._getVersionEntity(tenant, versionId)
        if version.promptId != prompt.id:
            raise AIPromptLifecycleInvalid("Prompt version belongs to another Prompt.")
        for (versionTenant, _), sibling in self._versions.items():
            if versionTenant == tenant and sibling.promptId == prompt.id:
                sibling.isActive = sibling.id == version.id
        prompt.activeVersionId = version.id
        return self.describeVersion(tenant, version.id)

    def deactivateVersion(
        self,
        tenantId: uuid.UUID | str,
        promptId: uuid.UUID | str,
        versionId: uuid.UUID | str,
    ) -> PromptVersionDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptByIdEntity(tenant, promptId)
        version = self._getVersionEntity(tenant, versionId)
        if version.promptId != prompt.id:
            raise AIPromptLifecycleInvalid("Prompt version belongs to another Prompt.")
        version.isActive = False
        if prompt.activeVersionId == version.id:
            prompt.activeVersionId = None
        return self.describeVersion(tenant, version.id)

    # ------------------------------------------------------------------
    # Rendering and safe reads
    # ------------------------------------------------------------------
    def render(
        self,
        tenantId: uuid.UUID | str,
        promptCode: str,
        values: Mapping[str, Any],
    ) -> RenderedPrompt:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptEntity(tenant, promptCode)
        version = self.getActiveVersion(tenant, prompt.code)
        return self._renderVersion(tenant, prompt, version, values)

    def renderVersion(
        self,
        tenantId: uuid.UUID | str,
        versionId: uuid.UUID | str,
        values: Mapping[str, Any],
    ) -> RenderedPrompt:
        tenant = requireUuid(tenantId, "tenantId")
        version = self._getVersionEntity(tenant, versionId)
        prompt = self._getPromptByIdEntity(tenant, version.promptId)
        if not prompt.isActive or not version.isActive or prompt.activeVersionId != version.id:
            raise AIPromptLifecycleInvalid("Only the active version of an active Prompt can be rendered.")
        return self._renderVersion(tenant, prompt, version, values)

    def describePrompt(self, tenantId: uuid.UUID | str, promptCode: str) -> PromptDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptEntity(tenant, promptCode)
        versions = self._versionsForPrompt(tenant, prompt.id)
        active = next((version for version in versions if version.id == prompt.activeVersionId), None)
        return PromptDescriptor(
            tenantId=prompt.tenantId,
            promptId=prompt.id,
            code=prompt.code,
            name=prompt.name,
            description=prompt.description,
            isActive=prompt.isActive,
            activeVersionId=prompt.activeVersionId,
            versionCount=len(versions),
            activeVersion=active.version if active is not None else None,
            createdAt=prompt.createdAt,
        )

    def describeVersion(
        self,
        tenantId: uuid.UUID | str,
        versionId: uuid.UUID | str,
    ) -> PromptVersionDescriptor:
        tenant = requireUuid(tenantId, "tenantId")
        version = self._getVersionEntity(tenant, versionId)
        schema = self._schemaObject(version.outputSchema)
        return PromptVersionDescriptor(
            tenantId=version.tenantId,
            promptId=version.promptId,
            versionId=version.id,
            version=version.version,
            isActive=version.isActive,
            variables=tuple(version.variables),
            hasOutputSchema=bool(version.outputSchema),
            outputSchemaFingerprint=schema.fingerprint() if schema is not None else "",
            hasModelConstraints=bool(version.modelConstraints),
            createdBy=version.createdBy,
            createdAt=version.createdAt,
        )

    def listPrompts(
        self,
        tenantId: uuid.UUID | str,
        *,
        activeOnly: bool = False,
    ) -> tuple[PromptDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        descriptors = [
            self.describePrompt(tenant, prompt.code)
            for (promptTenant, _), prompt in self._prompts.items()
            if promptTenant == tenant and (not activeOnly or prompt.isActive)
        ]
        return tuple(sorted(descriptors, key=lambda item: item.code))

    def listVersions(
        self,
        tenantId: uuid.UUID | str,
        promptId: uuid.UUID | str,
        *,
        activeOnly: bool = False,
    ) -> tuple[PromptVersionDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        prompt = self._getPromptByIdEntity(tenant, promptId)
        return tuple(
            self.describeVersion(tenant, version.id)
            for version in sorted(
                self._versionsForPrompt(tenant, prompt.id),
                key=lambda item: item.version,
            )
            if not activeOnly or version.isActive
        )

    def clear(self) -> None:
        """In-memory composition-root/test helper; no persistence is touched."""

        self._prompts.clear()
        self._versions.clear()
        self._versionKeys.clear()

    def register(self, prompt: AIPrompt, *, replace: bool = False) -> AIPrompt:
        return self.registerPrompt(prompt, replace=replace)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------
    def _renderVersion(
        self,
        tenant: uuid.UUID,
        prompt: AIPrompt,
        version: AIPromptVersion,
        values: Mapping[str, Any],
    ) -> RenderedPrompt:
        if not isinstance(values, Mapping):
            raise AIPromptTemplateInvalid("Prompt render values must be a mapping.")
        provided = dict(values)
        declared = set(version.variables)
        if set(provided) != declared:
            raise AIPromptTemplateInvalid("Prompt render values must exactly match declared variables.")
        try:
            rendered = version.template.format(**provided)
        except (KeyError, IndexError, ValueError, TypeError) as exc:
            raise AIPromptTemplateInvalid("Prompt could not be rendered with the declared variables.") from exc
        schema = self._schemaObject(version.outputSchema)
        return RenderedPrompt(
            tenantId=tenant,
            promptId=prompt.id,
            versionId=version.id,
            version=version.version,
            variableNames=tuple(version.variables),
            renderedText=rendered,
            outputSchemaFingerprint=schema.fingerprint() if schema is not None else "",
        )

    def _normalizeOutputSchema(self, outputSchema: Mapping[str, Any] | None) -> dict[str, Any]:
        if outputSchema is None:
            return {}
        if not isinstance(outputSchema, Mapping):
            raise AIPromptOutputSchemaInvalid("Prompt output schema must be an object.")
        try:
            schema = StructuredOutputSchema(schema=outputSchema)
        except AIStructuredSchemaInvalid as exc:
            raise AIPromptOutputSchemaInvalid("Prompt output schema is invalid.") from exc
        return schema.asDict()

    @staticmethod
    def _schemaObject(outputSchema: Mapping[str, Any]) -> StructuredOutputSchema | None:
        if not outputSchema:
            return None
        try:
            return StructuredOutputSchema(schema=outputSchema)
        except AIStructuredSchemaInvalid as exc:
            raise AIPromptOutputSchemaInvalid("Stored prompt output schema is invalid.") from exc

    def _nextVersion(self, tenantId: uuid.UUID, promptId: uuid.UUID) -> int:
        versions = self._versionsForPrompt(tenantId, promptId)
        return max((version.version for version in versions), default=0) + 1

    def _versionsForPrompt(self, tenantId: uuid.UUID, promptId: uuid.UUID) -> list[AIPromptVersion]:
        return [
            version
            for (versionTenant, _), version in self._versions.items()
            if versionTenant == tenantId and version.promptId == promptId
        ]

    def _getPromptEntity(self, tenantId: uuid.UUID, promptCode: str) -> AIPrompt:
        code = _normalizePromptCode(promptCode)
        prompt = self._prompts.get((tenantId, code))
        if prompt is None:
            raise AIPromptNotFound(code)
        return prompt

    def _getPromptByIdEntity(self, tenantId: uuid.UUID, promptId: uuid.UUID | str) -> AIPrompt:
        identifier = requireUuid(promptId, "promptId")
        for (promptTenant, _), prompt in self._prompts.items():
            if promptTenant == tenantId and prompt.id == identifier:
                return prompt
        raise AIPromptNotFound(str(identifier))

    def _getVersionEntity(self, tenantId: uuid.UUID, versionId: uuid.UUID | str) -> AIPromptVersion:
        identifier = requireUuid(versionId, "versionId")
        version = self._versions.get((tenantId, identifier))
        if version is None:
            raise AIPromptVersionNotFound(str(identifier))
        return version


PromptRegistry = PromptPlatformService
AIPromptRegistry = PromptPlatformService
PromptPlatform = PromptPlatformService
InMemoryPromptRegistry = PromptPlatformService
AIPromptPlatformService = PromptPlatformService
PromptVersioningService = PromptPlatformService

__all__ = [
    "AIPromptPlatformService",
    "AIPromptRegistry",
    "InMemoryPromptRegistry",
    "PromptDescriptor",
    "PromptPlatform",
    "PromptPlatformService",
    "PromptRegistry",
    "PromptVersionDescriptor",
    "PromptVersioningService",
    "RenderedPrompt",
]
