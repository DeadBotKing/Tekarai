"""Pure Tenant authorization and permission filtering for Phase 13-K.

K is the explicit security boundary between an already authenticated
Application subject and AI Domain operations.  It does not authenticate a
user, query Django/ORM, resolve roles from a database, call a provider, or
persist an audit event.  The Application boundary supplies an immutable
Tenant-bound principal snapshot and registers/loads the grants it is allowed
to expose to this pure service.

The default is fail-closed: same-Tenant membership alone is not permission.
Explicit denies win over allows, a foreign Tenant is never evaluated as a
resource in the current scope, and context sources are filtered before J's
ContextBuilder receives them.
"""

from __future__ import annotations

import copy
import hashlib
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Iterable, Mapping

from apps.ai.domain.entities.aiRecords import requireUuid, utcNow
from apps.ai.domain.exceptions import (
    AIAuthorizationAlreadyRegistered,
    AIAuthorizationDenied,
    AIAuthorizationGrantInvalid,
    AIAuthorizationNotFound,
    AIAuthorizationPolicyInvalid,
    AIAuthorizationPrincipalInvalid,
    AIAuthorizationTenantMismatch,
)
from apps.ai.domain.policies.aiPolicies import ContextPolicy
from apps.ai.domain.services.contextEngine import (
    ContextBuildResult,
    ContextEngine,
    ContextSourceCandidate,
)
from apps.ai.domain.valueObjects.aiTypes import DataClassification, validateCode


PERMISSION_ACTIONS = (
    "AI_CONTEXT_BUILD",
    "AI_CONTEXT_READ",
    "AI_CONTEXT_SOURCE_READ",
    "AI_CONTEXT_EXPORT",
    "AI_REQUEST_CREATE",
    "AI_REQUEST_READ",
    "AI_REQUEST_TRANSITION",
    "AI_RESPONSE_CREATE",
    "AI_RESPONSE_READ",
    "AI_PROMPT_READ",
    "AI_PROMPT_RENDER",
    "AI_PROVIDER_USE",
    "AI_MODEL_USE",
    "AI_CAPABILITY_USE",
    "AI_MEMORY_READ",
    "AI_MEMORY_WRITE",
    "AI_KNOWLEDGE_READ",
    "AI_KNOWLEDGE_WRITE",
    "AI_TOOL_USE",
    "AI_AGENT_USE",
    "AI_OUTPUT_AUTHORITATIVE",
)
PERMISSION_EFFECTS = ("ALLOW", "DENY")
PRINCIPAL_TYPES = ("USER", "SERVICE", "SYSTEM")
RESOURCE_TYPES = (
    "AI_CONTEXT",
    "CONTEXT_SOURCE",
    "AI_REQUEST",
    "AI_RESPONSE",
    "AI_PROMPT",
    "AI_PROVIDER",
    "AI_MODEL",
    "AI_CAPABILITY",
    "AI_MEMORY",
    "AI_KNOWLEDGE",
    "AI_TOOL",
    "AI_AGENT",
    "AI_TENANT",
)


def _normalizeCode(value: str, fieldName: str) -> str:
    try:
        return validateCode(value, fieldName)
    except Exception as exc:
        raise AIAuthorizationPolicyInvalid(f"{fieldName} is invalid.") from exc


def _normalizePermission(value: str, fieldName: str = "permissionCode") -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "*":
        return normalized
    if normalized.endswith("_*"):
        prefix = normalized[:-2]
        if not prefix:
            raise AIAuthorizationGrantInvalid(f"{fieldName} is invalid.")
        _normalizeCode(prefix, fieldName)
        return normalized
    return _normalizeCode(normalized, fieldName)


def _normalizeOptionalText(value: str, fieldName: str) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise AIAuthorizationGrantInvalid(f"{fieldName} must be a string.")
    return value.strip()


def _normalizeResourceType(value: str) -> str:
    normalized = str(value or "").strip().upper()
    if normalized == "*":
        return normalized
    try:
        return validateCode(normalized, "resourceType")
    except Exception as exc:
        raise AIAuthorizationGrantInvalid("resourceType is invalid.") from exc


def _normalizeClassification(value: str, errorType: type[Exception]) -> str:
    try:
        return str(DataClassification(value))
    except Exception as exc:
        raise errorType("Data classification is invalid.") from exc


def _permissionMatches(granted: str, requested: str) -> bool:
    return granted == "*" or granted == requested or (
        granted.endswith("_*") and requested.startswith(granted[:-1])
    )


def _fingerprint(
    tenantId: uuid.UUID,
    subjectId: uuid.UUID,
    action: str,
    resource: "AuthorizationResource",
    allowed: bool,
    reason: str,
) -> str:
    value = "|".join(
        (
            str(tenantId),
            str(subjectId),
            action,
            resource.resourceType,
            resource.resourceId,
            resource.sourceDomain,
            resource.sourceEntityType,
            resource.sourceEntityId,
            resource.classification,
            str(resource.externalProvider),
            str(allowed),
            reason,
        )
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class AuthorizationPrincipal:
    """Authenticated subject snapshot supplied by the Application boundary."""

    tenantId: uuid.UUID | str
    subjectId: uuid.UUID | str
    subjectType: str = "USER"
    roles: tuple[str, ...] = ()
    directPermissions: tuple[str, ...] = ()
    isActive: bool = True

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        object.__setattr__(self, "subjectId", requireUuid(self.subjectId, "subjectId"))
        normalizedType = str(self.subjectType or "").strip().upper()
        if normalizedType not in PRINCIPAL_TYPES:
            raise AIAuthorizationPrincipalInvalid("Principal subjectType is invalid.")
        object.__setattr__(self, "subjectType", normalizedType)
        normalizedRoles: list[str] = []
        for role in self.roles:
            normalized = _normalizeCode(role, "roleCode")
            if normalized not in normalizedRoles:
                normalizedRoles.append(normalized)
        object.__setattr__(self, "roles", tuple(normalizedRoles))
        normalizedPermissions: list[str] = []
        for permission in self.directPermissions:
            normalized = _normalizePermission(permission)
            if normalized not in normalizedPermissions:
                normalizedPermissions.append(normalized)
        object.__setattr__(self, "directPermissions", tuple(normalizedPermissions))
        if not isinstance(self.isActive, bool):
            raise AIAuthorizationPrincipalInvalid("Principal isActive must be boolean.")


@dataclass(frozen=True)
class AuthorizationResource:
    """Tenant-bound resource reference without payload or sensitive metadata."""

    tenantId: uuid.UUID | str
    resourceType: str
    resourceId: str = ""
    sourceDomain: str = ""
    sourceEntityType: str = ""
    sourceEntityId: str = ""
    classification: str = ""
    externalProvider: bool = False

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        normalizedType = _normalizeResourceType(self.resourceType)
        if normalizedType == "*":
            raise AIAuthorizationGrantInvalid("Authorization resources require a concrete resourceType.")
        object.__setattr__(self, "resourceType", normalizedType)
        for name in ("resourceId", "sourceDomain", "sourceEntityType", "sourceEntityId"):
            object.__setattr__(self, name, _normalizeOptionalText(getattr(self, name), name))
        if self.classification:
            object.__setattr__(
                self,
                "classification",
                _normalizeClassification(self.classification, AIAuthorizationGrantInvalid),
            )
        if not isinstance(self.externalProvider, bool):
            raise AIAuthorizationGrantInvalid("externalProvider must be boolean.")
        if any((self.sourceDomain, self.sourceEntityType, self.sourceEntityId)) and not all(
            (self.sourceDomain, self.sourceEntityType, self.sourceEntityId)
        ):
            raise AIAuthorizationGrantInvalid("Source resource identity must be complete.")

    @classmethod
    def entity(
        cls,
        tenantId: uuid.UUID | str,
        resourceType: str,
        resourceId: uuid.UUID | str = "",
        *,
        classification: str = "",
        externalProvider: bool = False,
    ) -> "AuthorizationResource":
        return cls(
            tenantId=tenantId,
            resourceType=resourceType,
            resourceId=str(resourceId),
            classification=classification,
            externalProvider=externalProvider,
        )

    @classmethod
    def context(
        cls,
        tenantId: uuid.UUID | str,
        contextId: uuid.UUID | str = "",
        *,
        externalProvider: bool = False,
    ) -> "AuthorizationResource":
        return cls.entity(
            tenantId,
            "AI_CONTEXT",
            contextId,
            externalProvider=externalProvider,
        )

    @classmethod
    def source(cls, source: ContextSourceCandidate) -> "AuthorizationResource":
        if not isinstance(source, ContextSourceCandidate):
            raise AIAuthorizationGrantInvalid("Context source resource must be a ContextSourceCandidate.")
        return cls(
            tenantId=source.tenantId,
            resourceType="CONTEXT_SOURCE",
            resourceId=source.sourceEntityId,
            sourceDomain=source.sourceDomain,
            sourceEntityType=source.sourceEntityType,
            sourceEntityId=source.sourceEntityId,
            classification=source.classification,
        )

    @classmethod
    def tenant(cls, tenantId: uuid.UUID | str) -> "AuthorizationResource":
        return cls.entity(tenantId, "AI_TENANT", tenantId)


@dataclass(frozen=True)
class PermissionGrant:
    """An explicit allow/deny grant for one subject or one role."""

    tenantId: uuid.UUID | str
    permissionCode: str
    effect: str = "ALLOW"
    subjectId: uuid.UUID | str | None = None
    roleCode: str = ""
    resourceType: str = "*"
    resourceId: str = ""
    sourceDomain: str = ""
    sourceEntityType: str = ""
    sourceEntityId: str = ""
    allowedClassifications: tuple[str, ...] = ()
    externalProvider: bool | None = None
    priority: int = 0
    expiresAt: datetime | None = None
    grantId: uuid.UUID | str = field(default_factory=uuid.uuid4)

    def __post_init__(self) -> None:
        object.__setattr__(self, "tenantId", requireUuid(self.tenantId, "tenantId"))
        object.__setattr__(self, "grantId", requireUuid(self.grantId, "grantId"))
        object.__setattr__(self, "permissionCode", _normalizePermission(self.permissionCode))
        normalizedEffect = str(self.effect or "").strip().upper()
        if normalizedEffect not in PERMISSION_EFFECTS:
            raise AIAuthorizationGrantInvalid("Grant effect must be ALLOW or DENY.")
        object.__setattr__(self, "effect", normalizedEffect)
        if self.subjectId is not None and self.roleCode:
            raise AIAuthorizationGrantInvalid("Grant must target a subject or a role, not both.")
        if self.subjectId is None and not self.roleCode:
            raise AIAuthorizationGrantInvalid("Grant must target a subject or a role.")
        if self.subjectId is not None:
            object.__setattr__(self, "subjectId", requireUuid(self.subjectId, "subjectId"))
        if self.roleCode:
            object.__setattr__(self, "roleCode", _normalizeCode(self.roleCode, "roleCode"))
        object.__setattr__(self, "resourceType", _normalizeResourceType(self.resourceType))
        for name in ("resourceId", "sourceDomain", "sourceEntityType", "sourceEntityId"):
            object.__setattr__(self, name, _normalizeOptionalText(getattr(self, name), name))
        normalizedClassifications: list[str] = []
        for value in self.allowedClassifications:
            normalized = _normalizeClassification(value, AIAuthorizationGrantInvalid)
            if normalized not in normalizedClassifications:
                normalizedClassifications.append(normalized)
        object.__setattr__(self, "allowedClassifications", tuple(normalizedClassifications))
        if self.externalProvider is not None and not isinstance(self.externalProvider, bool):
            raise AIAuthorizationGrantInvalid("Grant externalProvider must be boolean or None.")
        if not isinstance(self.priority, int) or isinstance(self.priority, bool):
            raise AIAuthorizationGrantInvalid("Grant priority must be an integer.")
        if self.expiresAt is not None and not isinstance(self.expiresAt, datetime):
            raise AIAuthorizationGrantInvalid("Grant expiresAt must be a datetime or None.")

    def isActiveAt(self, now: datetime) -> bool:
        return self.expiresAt is None or self.expiresAt > now


@dataclass(frozen=True)
class PrincipalDescriptor:
    """Safe principal read model."""

    tenantId: uuid.UUID
    subjectId: uuid.UUID
    subjectType: str
    roles: tuple[str, ...]
    directPermissionCount: int
    isActive: bool


@dataclass(frozen=True)
class GrantDescriptor:
    """Safe grant read model without payload or credential fields."""

    tenantId: uuid.UUID
    grantId: uuid.UUID
    permissionCode: str
    effect: str
    subjectId: uuid.UUID | None
    roleCode: str
    resourceType: str
    resourceId: str
    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    allowedClassifications: tuple[str, ...]
    externalProvider: bool | None
    priority: int
    expiresAt: datetime | None


@dataclass(frozen=True)
class AuthorizationDecision:
    """Immutable, non-sensitive and audit-ready authorization decision."""

    decisionId: uuid.UUID
    tenantId: uuid.UUID
    subjectId: uuid.UUID
    action: str
    resourceType: str
    resourceId: str
    allowed: bool
    reason: str
    matchedGrantId: uuid.UUID | None
    evaluatedAt: datetime
    decisionFingerprint: str


@dataclass(frozen=True)
class SourcePermissionDecision:
    """Safe decision for one source reference; content is intentionally absent."""

    sourceDomain: str
    sourceEntityType: str
    sourceEntityId: str
    classification: str
    allowed: bool
    reason: str
    authorizationDecisionId: uuid.UUID


@dataclass(frozen=True)
class PermissionFilterResult:
    """Safe filtering report plus a non-repr source tuple for downstream assembly."""

    tenantId: uuid.UUID
    subjectId: uuid.UUID
    action: str
    requestedCount: int
    allowedCount: int
    deniedCount: int
    decisions: tuple[SourcePermissionDecision, ...]
    evaluatedAt: datetime
    authorizedSources: tuple[ContextSourceCandidate, ...] = field(repr=False, compare=False)


@dataclass(frozen=True)
class AuthorizationPolicy:
    """Configuration for the K boundary; defaults are deliberately fail-closed."""

    defaultDeny: bool = True
    denyOverridesAllow: bool = True
    contextBuildPermission: str = "AI_CONTEXT_BUILD"
    contextReadPermission: str = "AI_CONTEXT_READ"
    sourceReadPermission: str = "AI_CONTEXT_SOURCE_READ"
    contextExportPermission: str = "AI_CONTEXT_EXPORT"

    def __post_init__(self) -> None:
        if self.defaultDeny is not True:
            raise AIAuthorizationPolicyInvalid("AuthorizationPolicy must remain fail-closed.")
        if not isinstance(self.denyOverridesAllow, bool):
            raise AIAuthorizationPolicyInvalid("denyOverridesAllow must be boolean.")
        for fieldName in (
            "contextBuildPermission",
            "contextReadPermission",
            "sourceReadPermission",
            "contextExportPermission",
        ):
            try:
                normalized = _normalizePermission(getattr(self, fieldName), fieldName)
            except Exception as exc:
                raise AIAuthorizationPolicyInvalid(f"{fieldName} is invalid.") from exc
            object.__setattr__(self, fieldName, normalized)


class AuthorizationService:
    """Pure, in-memory Tenant authorization and permission filtering service."""

    def __init__(
        self,
        *,
        policy: AuthorizationPolicy | None = None,
        now: Callable[[], datetime] = utcNow,
    ) -> None:
        if policy is not None and not isinstance(policy, AuthorizationPolicy):
            raise AIAuthorizationPolicyInvalid("policy must be an AuthorizationPolicy.")
        if not callable(now):
            raise AIAuthorizationPolicyInvalid("now must be callable.")
        self.policy = policy or AuthorizationPolicy()
        self._now = now
        self._principals: dict[tuple[uuid.UUID, uuid.UUID], AuthorizationPrincipal] = {}
        self._grants: dict[tuple[uuid.UUID, uuid.UUID], PermissionGrant] = {}
        self._grantKeys: dict[tuple[Any, ...], uuid.UUID] = {}

    # ------------------------------------------------------------------
    # Principal and grant registration
    # ------------------------------------------------------------------
    def registerPrincipal(
        self,
        principal: AuthorizationPrincipal,
        *,
        replace: bool = False,
    ) -> PrincipalDescriptor:
        if not isinstance(principal, AuthorizationPrincipal):
            raise AIAuthorizationPrincipalInvalid("Principal must be an AuthorizationPrincipal.")
        key = (principal.tenantId, principal.subjectId)
        if key in self._principals and not replace:
            raise AIAuthorizationAlreadyRegistered(str(principal.subjectId))
        self._principals[key] = copy.deepcopy(principal)
        return self.describePrincipal(principal.tenantId, principal.subjectId)

    def registerGrant(
        self,
        grant: PermissionGrant,
        *,
        replace: bool = False,
    ) -> GrantDescriptor:
        if not isinstance(grant, PermissionGrant):
            raise AIAuthorizationGrantInvalid("Grant must be a PermissionGrant.")
        semanticKey = self._grantKey(grant)
        existingId = self._grantKeys.get(semanticKey)
        if existingId is not None and existingId != grant.grantId:
            raise AIAuthorizationAlreadyRegistered("Equivalent permission grant is already registered.")
        key = (grant.tenantId, grant.grantId)
        if key in self._grants and not replace:
            raise AIAuthorizationAlreadyRegistered(str(grant.grantId))
        if key in self._grants:
            oldKey = self._grantKey(self._grants[key])
            self._grantKeys.pop(oldKey, None)
        self._grants[key] = copy.deepcopy(grant)
        self._grantKeys[semanticKey] = grant.grantId
        return self.describeGrant(grant.tenantId, grant.grantId)

    def getPrincipal(
        self,
        tenantId: uuid.UUID | str,
        subjectId: uuid.UUID | str,
    ) -> AuthorizationPrincipal:
        tenant = requireUuid(tenantId, "tenantId")
        subject = requireUuid(subjectId, "subjectId")
        principal = self._principals.get((tenant, subject))
        if principal is None:
            raise AIAuthorizationNotFound(str(subject))
        return copy.deepcopy(principal)

    def getGrant(
        self,
        tenantId: uuid.UUID | str,
        grantId: uuid.UUID | str,
    ) -> PermissionGrant:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(grantId, "grantId")
        grant = self._grants.get((tenant, identifier))
        if grant is None:
            raise AIAuthorizationNotFound(str(identifier))
        return copy.deepcopy(grant)

    def describePrincipal(
        self,
        tenantId: uuid.UUID | str,
        subjectId: uuid.UUID | str,
    ) -> PrincipalDescriptor:
        principal = self.getPrincipal(tenantId, subjectId)
        return PrincipalDescriptor(
            tenantId=principal.tenantId,
            subjectId=principal.subjectId,
            subjectType=principal.subjectType,
            roles=principal.roles,
            directPermissionCount=len(principal.directPermissions),
            isActive=principal.isActive,
        )

    def describeGrant(
        self,
        tenantId: uuid.UUID | str,
        grantId: uuid.UUID | str,
    ) -> GrantDescriptor:
        grant = self.getGrant(tenantId, grantId)
        return GrantDescriptor(
            tenantId=grant.tenantId,
            grantId=grant.grantId,
            permissionCode=grant.permissionCode,
            effect=grant.effect,
            subjectId=grant.subjectId,
            roleCode=grant.roleCode,
            resourceType=grant.resourceType,
            resourceId=grant.resourceId,
            sourceDomain=grant.sourceDomain,
            sourceEntityType=grant.sourceEntityType,
            sourceEntityId=grant.sourceEntityId,
            allowedClassifications=grant.allowedClassifications,
            externalProvider=grant.externalProvider,
            priority=grant.priority,
            expiresAt=grant.expiresAt,
        )

    def listPrincipals(
        self,
        tenantId: uuid.UUID | str,
        *,
        activeOnly: bool = False,
    ) -> tuple[PrincipalDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        principals = [
            principal
            for (principalTenant, _), principal in self._principals.items()
            if principalTenant == tenant and (not activeOnly or principal.isActive)
        ]
        return tuple(
            PrincipalDescriptor(
                tenantId=principal.tenantId,
                subjectId=principal.subjectId,
                subjectType=principal.subjectType,
                roles=principal.roles,
                directPermissionCount=len(principal.directPermissions),
                isActive=principal.isActive,
            )
            for principal in sorted(principals, key=lambda item: str(item.subjectId))
        )

    def listGrants(
        self,
        tenantId: uuid.UUID | str,
        *,
        subjectId: uuid.UUID | str | None = None,
        roleCode: str | None = None,
        activeAt: datetime | None = None,
    ) -> tuple[GrantDescriptor, ...]:
        tenant = requireUuid(tenantId, "tenantId")
        subject = requireUuid(subjectId, "subjectId") if subjectId is not None else None
        role = _normalizeCode(roleCode, "roleCode") if roleCode else None
        moment = activeAt or self._now()
        grants = [
            grant
            for (grantTenant, _), grant in self._grants.items()
            if grantTenant == tenant
            and (subject is None or grant.subjectId == subject)
            and (role is None or grant.roleCode == role)
            and grant.isActiveAt(moment)
        ]
        return tuple(
            sorted(
                (self._grantDescriptor(grant) for grant in grants),
                key=lambda item: (item.priority * -1, str(item.grantId)),
            )
        )

    def revokeGrant(self, tenantId: uuid.UUID | str, grantId: uuid.UUID | str) -> None:
        tenant = requireUuid(tenantId, "tenantId")
        identifier = requireUuid(grantId, "grantId")
        key = (tenant, identifier)
        grant = self._grants.pop(key, None)
        if grant is None:
            raise AIAuthorizationNotFound(str(identifier))
        self._grantKeys.pop(self._grantKey(grant), None)

    # ------------------------------------------------------------------
    # Authorization decisions
    # ------------------------------------------------------------------
    def authorize(
        self,
        principal: AuthorizationPrincipal,
        action: str,
        resource: AuthorizationResource,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        subject = self._coercePrincipal(principal)
        permission = _normalizePermission(action, "action")
        if not isinstance(resource, AuthorizationResource):
            raise AIAuthorizationPolicyInvalid("resource must be an AuthorizationResource.")
        if subject.tenantId != resource.tenantId:
            raise AIAuthorizationTenantMismatch("Principal and resource belong to different Tenants.")
        if not subject.isActive:
            return self._decision(subject, permission, resource, False, "INACTIVE_PRINCIPAL", None, now)

        moment = now or self._now()
        matching = [
            grant
            for grant in self._grants.values()
            if grant.tenantId == subject.tenantId
            and grant.isActiveAt(moment)
            and self._matchesPrincipal(grant, subject)
            and _permissionMatches(grant.permissionCode, permission)
            and self._matchesResource(grant, resource)
        ]
        denies = [grant for grant in matching if grant.effect == "DENY"]
        allows = [grant for grant in matching if grant.effect == "ALLOW"]
        if denies and self.policy.denyOverridesAllow:
            selected = self._orderedGrant(denies)
            return self._decision(subject, permission, resource, False, "EXPLICIT_DENY", selected.grantId, moment)
        if allows:
            selected = self._orderedGrant(allows)
            return self._decision(subject, permission, resource, True, "EXPLICIT_ALLOW", selected.grantId, moment)
        if not denies and any(_permissionMatches(item, permission) for item in subject.directPermissions):
            return self._decision(subject, permission, resource, True, "DIRECT_PERMISSION", None, moment)
        if denies:
            selected = self._orderedGrant(denies)
            return self._decision(subject, permission, resource, False, "EXPLICIT_DENY", selected.grantId, moment)
        return self._decision(subject, permission, resource, False, "DEFAULT_DENY", None, moment)

    def requirePermission(
        self,
        principal: AuthorizationPrincipal,
        action: str,
        resource: AuthorizationResource,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        decision = self.authorize(principal, action, resource, now=now)
        if not decision.allowed:
            raise AIAuthorizationDenied(
                f"Permission denied for action {decision.action}."
            )
        return decision

    def require(
        self,
        principal: AuthorizationPrincipal,
        action: str,
        resource: AuthorizationResource,
        *,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.requirePermission(principal, action, resource, now=now)

    def can(
        self,
        principal: AuthorizationPrincipal,
        action: str,
        resource: AuthorizationResource,
        *,
        now: datetime | None = None,
    ) -> bool:
        return self.authorize(principal, action, resource, now=now).allowed

    def authorizeTenant(
        self,
        principal: AuthorizationPrincipal,
        tenantId: uuid.UUID | str,
    ) -> AuthorizationDecision:
        subject = self._coercePrincipal(principal)
        tenant = requireUuid(tenantId, "tenantId")
        if subject.tenantId != tenant:
            raise AIAuthorizationTenantMismatch("Principal is not scoped to the requested Tenant.")
        return self._decision(
            subject,
            "AI_TENANT_ACCESS",
            AuthorizationResource.tenant(tenant),
            True,
            "TENANT_SCOPE_MATCH",
            None,
            self._now(),
        )

    # ------------------------------------------------------------------
    # Source filtering and J integration
    # ------------------------------------------------------------------
    def filterContextSources(
        self,
        principal: AuthorizationPrincipal,
        sources: Iterable[ContextSourceCandidate],
        *,
        action: str | None = None,
        now: datetime | None = None,
    ) -> PermissionFilterResult:
        subject = self._coercePrincipal(principal)
        permission = _normalizePermission(action or self.policy.sourceReadPermission, "action")
        authorizedSources: list[ContextSourceCandidate] = []
        decisions: list[SourcePermissionDecision] = []
        sourceList = tuple(sources)
        moment = now or self._now()
        for source in sourceList:
            if not isinstance(source, ContextSourceCandidate):
                raise AIAuthorizationGrantInvalid(
                    "Context permission filtering requires Tenant-bound source candidates."
                )
            if source.tenantId != subject.tenantId:
                raise AIAuthorizationTenantMismatch("Context source belongs to another Tenant.")
            if not source.authorized:
                decision = self._decision(
                    subject,
                    permission,
                    AuthorizationResource.source(source),
                    False,
                    "SOURCE_NOT_AUTHORIZED",
                    None,
                    moment,
                )
            else:
                decision = self.authorize(
                    subject,
                    permission,
                    AuthorizationResource.source(source),
                    now=moment,
                )
            if decision.allowed:
                authorizedSources.append(source)
            decisions.append(
                SourcePermissionDecision(
                    sourceDomain=source.sourceDomain,
                    sourceEntityType=source.sourceEntityType,
                    sourceEntityId=source.sourceEntityId,
                    classification=source.classification,
                    allowed=decision.allowed,
                    reason=decision.reason,
                    authorizationDecisionId=decision.decisionId,
                )
            )
        return PermissionFilterResult(
            tenantId=subject.tenantId,
            subjectId=subject.subjectId,
            action=permission,
            requestedCount=len(sourceList),
            allowedCount=len(authorizedSources),
            deniedCount=len(sourceList) - len(authorizedSources),
            decisions=tuple(decisions),
            evaluatedAt=moment,
            authorizedSources=tuple(authorizedSources),
        )

    def filterSources(
        self,
        principal: AuthorizationPrincipal,
        sources: Iterable[ContextSourceCandidate],
        *,
        action: str | None = None,
        now: datetime | None = None,
    ) -> PermissionFilterResult:
        return self.filterContextSources(principal, sources, action=action, now=now)

    def buildAuthorizedContext(
        self,
        principal: AuthorizationPrincipal,
        requestId: uuid.UUID | str,
        sources: Iterable[ContextSourceCandidate],
        *,
        contextEngine: ContextEngine,
        policy: ContextPolicy | None = None,
        externalProvider: bool = False,
        contextId: uuid.UUID | str | None = None,
        now: datetime | None = None,
    ) -> ContextBuildResult:
        if not isinstance(contextEngine, ContextEngine):
            raise AIAuthorizationPolicyInvalid("contextEngine must be a ContextEngine.")
        subject = self._coercePrincipal(principal)
        request = requireUuid(requestId, "requestId")
        self.requirePermission(
            subject,
            self.policy.contextBuildPermission,
            AuthorizationResource.entity(subject.tenantId, "AI_REQUEST", request),
            now=now,
        )
        if externalProvider:
            self.requirePermission(
                subject,
                self.policy.contextExportPermission,
                AuthorizationResource.context(
                    subject.tenantId,
                    externalProvider=True,
                ),
                now=now,
            )
        filtered = self.filterContextSources(subject, sources, now=now)
        return contextEngine.buildContext(
            subject.tenantId,
            request,
            filtered.authorizedSources,
            policy,
            externalProvider=externalProvider,
            contextId=contextId,
        )

    buildContext = buildAuthorizedContext

    # ------------------------------------------------------------------
    # Typed resource authorization helpers
    # ------------------------------------------------------------------
    def authorizeEntity(
        self,
        principal: AuthorizationPrincipal,
        action: str,
        resourceType: str,
        resourceId: uuid.UUID | str = "",
        *,
        classification: str = "",
        externalProvider: bool = False,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorize(
            principal,
            action,
            AuthorizationResource.entity(
                self._coercePrincipal(principal).tenantId,
                resourceType,
                resourceId,
                classification=classification,
                externalProvider=externalProvider,
            ),
            now=now,
        )

    def authorizeContext(
        self,
        principal: AuthorizationPrincipal,
        contextId: uuid.UUID | str,
        *,
        action: str | None = None,
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        subject = self._coercePrincipal(principal)
        return self.authorize(
            subject,
            action or self.policy.contextReadPermission,
            AuthorizationResource.context(subject.tenantId, contextId),
            now=now,
        )

    def authorizeRequest(
        self,
        principal: AuthorizationPrincipal,
        requestId: uuid.UUID | str,
        *,
        action: str = "AI_REQUEST_READ",
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorizeEntity(principal, action, "AI_REQUEST", requestId, now=now)

    def authorizeResponse(
        self,
        principal: AuthorizationPrincipal,
        responseId: uuid.UUID | str,
        *,
        action: str = "AI_RESPONSE_READ",
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorizeEntity(principal, action, "AI_RESPONSE", responseId, now=now)

    def authorizePrompt(
        self,
        principal: AuthorizationPrincipal,
        promptId: uuid.UUID | str,
        *,
        action: str = "AI_PROMPT_READ",
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorizeEntity(principal, action, "AI_PROMPT", promptId, now=now)

    def authorizeModel(
        self,
        principal: AuthorizationPrincipal,
        modelId: uuid.UUID | str,
        *,
        action: str = "AI_MODEL_USE",
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorizeEntity(principal, action, "AI_MODEL", modelId, now=now)

    def authorizeProvider(
        self,
        principal: AuthorizationPrincipal,
        providerId: uuid.UUID | str,
        *,
        action: str = "AI_PROVIDER_USE",
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorizeEntity(principal, action, "AI_PROVIDER", providerId, now=now)

    def authorizeCapability(
        self,
        principal: AuthorizationPrincipal,
        capabilityId: uuid.UUID | str,
        *,
        action: str = "AI_CAPABILITY_USE",
        now: datetime | None = None,
    ) -> AuthorizationDecision:
        return self.authorizeEntity(principal, action, "AI_CAPABILITY", capabilityId, now=now)

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------
    def clear(self) -> None:
        self._principals.clear()
        self._grants.clear()
        self._grantKeys.clear()

    def _coercePrincipal(self, principal: AuthorizationPrincipal) -> AuthorizationPrincipal:
        if not isinstance(principal, AuthorizationPrincipal):
            raise AIAuthorizationPrincipalInvalid("Principal must be an AuthorizationPrincipal.")
        return principal

    @staticmethod
    def _matchesPrincipal(grant: PermissionGrant, principal: AuthorizationPrincipal) -> bool:
        return (grant.subjectId is not None and grant.subjectId == principal.subjectId) or (
            bool(grant.roleCode) and grant.roleCode in principal.roles
        )

    @staticmethod
    def _matchesResource(grant: PermissionGrant, resource: AuthorizationResource) -> bool:
        if grant.resourceType != "*" and grant.resourceType != resource.resourceType:
            return False
        if grant.resourceId and grant.resourceId != resource.resourceId:
            return False
        for grantValue, resourceValue in (
            (grant.sourceDomain, resource.sourceDomain),
            (grant.sourceEntityType, resource.sourceEntityType),
            (grant.sourceEntityId, resource.sourceEntityId),
        ):
            if grantValue and grantValue != resourceValue:
                return False
        if grant.allowedClassifications and resource.classification not in grant.allowedClassifications:
            return False
        if grant.externalProvider is not None and grant.externalProvider != resource.externalProvider:
            return False
        return True

    @staticmethod
    def _orderedGrant(grants: Iterable[PermissionGrant]) -> PermissionGrant:
        return sorted(grants, key=lambda grant: (-grant.priority, str(grant.grantId)))[0]

    @staticmethod
    def _grantKey(grant: PermissionGrant) -> tuple[Any, ...]:
        return (
            grant.tenantId,
            grant.permissionCode,
            grant.effect,
            grant.subjectId,
            grant.roleCode,
            grant.resourceType,
            grant.resourceId,
            grant.sourceDomain,
            grant.sourceEntityType,
            grant.sourceEntityId,
            grant.allowedClassifications,
            grant.externalProvider,
        )

    @staticmethod
    def _grantDescriptor(grant: PermissionGrant) -> GrantDescriptor:
        return GrantDescriptor(
            tenantId=grant.tenantId,
            grantId=grant.grantId,
            permissionCode=grant.permissionCode,
            effect=grant.effect,
            subjectId=grant.subjectId,
            roleCode=grant.roleCode,
            resourceType=grant.resourceType,
            resourceId=grant.resourceId,
            sourceDomain=grant.sourceDomain,
            sourceEntityType=grant.sourceEntityType,
            sourceEntityId=grant.sourceEntityId,
            allowedClassifications=grant.allowedClassifications,
            externalProvider=grant.externalProvider,
            priority=grant.priority,
            expiresAt=grant.expiresAt,
        )

    @staticmethod
    def _decision(
        principal: AuthorizationPrincipal,
        action: str,
        resource: AuthorizationResource,
        allowed: bool,
        reason: str,
        matchedGrantId: uuid.UUID | None,
        evaluatedAt: datetime | None,
    ) -> AuthorizationDecision:
        moment = evaluatedAt or utcNow()
        return AuthorizationDecision(
            decisionId=uuid.uuid4(),
            tenantId=principal.tenantId,
            subjectId=principal.subjectId,
            action=action,
            resourceType=resource.resourceType,
            resourceId=resource.resourceId,
            allowed=allowed,
            reason=reason,
            matchedGrantId=matchedGrantId,
            evaluatedAt=moment,
            decisionFingerprint=_fingerprint(
                principal.tenantId,
                principal.subjectId,
                action,
                resource,
                allowed,
                reason,
            ),
        )


class AuthorizedContextEngine:
    """Permission-aware facade over J's ContextEngine."""

    def __init__(
        self,
        authorization: AuthorizationService,
        contextEngine: ContextEngine,
    ) -> None:
        if not isinstance(authorization, AuthorizationService):
            raise AIAuthorizationPolicyInvalid("authorization must be an AuthorizationService.")
        if not isinstance(contextEngine, ContextEngine):
            raise AIAuthorizationPolicyInvalid("contextEngine must be a ContextEngine.")
        self.authorization = authorization
        self.contextEngine = contextEngine

    def buildContext(
        self,
        principal: AuthorizationPrincipal,
        requestId: uuid.UUID | str,
        sources: Iterable[ContextSourceCandidate],
        policy: ContextPolicy | None = None,
        *,
        externalProvider: bool = False,
        contextId: uuid.UUID | str | None = None,
    ) -> ContextBuildResult:
        return self.authorization.buildAuthorizedContext(
            principal,
            requestId,
            sources,
            contextEngine=self.contextEngine,
            policy=policy,
            externalProvider=externalProvider,
            contextId=contextId,
        )

    def getContext(
        self,
        principal: AuthorizationPrincipal,
        contextId: uuid.UUID | str,
    ) -> Any:
        self.authorization.requirePermission(
            principal,
            self.authorization.policy.contextReadPermission,
            AuthorizationResource.context(
                self.authorization._coercePrincipal(principal).tenantId,
                contextId,
            ),
        )
        subject = self.authorization._coercePrincipal(principal)
        return self.contextEngine.getContext(subject.tenantId, contextId)

    def getResult(
        self,
        principal: AuthorizationPrincipal,
        contextId: uuid.UUID | str,
    ) -> ContextBuildResult:
        self.authorization.requirePermission(
            principal,
            self.authorization.policy.contextReadPermission,
            AuthorizationResource.context(
                self.authorization._coercePrincipal(principal).tenantId,
                contextId,
            ),
        )
        subject = self.authorization._coercePrincipal(principal)
        return self.contextEngine.getResult(subject.tenantId, contextId)

    def describeContext(
        self,
        principal: AuthorizationPrincipal,
        contextId: uuid.UUID | str,
    ) -> Any:
        self.authorization.requirePermission(
            principal,
            self.authorization.policy.contextReadPermission,
            AuthorizationResource.context(
                self.authorization._coercePrincipal(principal).tenantId,
                contextId,
            ),
        )
        subject = self.authorization._coercePrincipal(principal)
        return self.contextEngine.describeContext(subject.tenantId, contextId)

    def listContexts(
        self,
        principal: AuthorizationPrincipal,
        *,
        requestId: uuid.UUID | str | None = None,
    ) -> tuple[Any, ...]:
        subject = self.authorization._coercePrincipal(principal)
        self.authorization.requirePermission(
            subject,
            self.authorization.policy.contextReadPermission,
            AuthorizationResource.entity(subject.tenantId, "AI_CONTEXT"),
        )
        return self.contextEngine.listContexts(subject.tenantId, requestId=requestId)


PermissionService = AuthorizationService
PermissionEngine = AuthorizationService
AuthorizationEngine = AuthorizationService
AIAuthorizationService = AuthorizationService
TenantAuthorizationService = AuthorizationService
InMemoryAuthorizationService = AuthorizationService
PermissionFilteringService = AuthorizationService
Permission = PermissionGrant
PermissionRule = PermissionGrant
Principal = AuthorizationPrincipal
ResourceReference = AuthorizationResource
AccessDecision = AuthorizationDecision
PermissionDecision = AuthorizationDecision
AuthorizationContext = AuthorizationResource
PermissionAwareContextEngine = AuthorizedContextEngine
AIContextAuthorizationEngine = AuthorizedContextEngine
AuthorizedContextBuilder = AuthorizedContextEngine

__all__ = [
    "AIContextAuthorizationEngine",
    "AIAuthorizationService",
    "AuthorizationDecision",
    "AuthorizationEngine",
    "PermissionEngine",
    "AuthorizationPolicy",
    "AuthorizationPrincipal",
    "AuthorizationResource",
    "AuthorizationService",
    "AuthorizationContext",
    "AccessDecision",
    "AuthorizedContextBuilder",
    "AuthorizedContextEngine",
    "GrantDescriptor",
    "InMemoryAuthorizationService",
    "PERMISSION_ACTIONS",
    "PERMISSION_EFFECTS",
    "PermissionAwareContextEngine",
    "PermissionDecision",
    "PermissionFilterResult",
    "PermissionFilteringService",
    "PermissionGrant",
    "Permission",
    "PermissionRule",
    "PermissionService",
    "Principal",
    "ResourceReference",
    "TenantAuthorizationService",
    "PrincipalDescriptor",
    "PRINCIPAL_TYPES",
    "RESOURCE_TYPES",
    "SourcePermissionDecision",
]
