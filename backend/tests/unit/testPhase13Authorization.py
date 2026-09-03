"""Phase 13-K Tenant Authorization and Permission Filtering tests."""

from __future__ import annotations

import unittest
import uuid
from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta
from pathlib import Path

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
from apps.ai.domain.services.authorizationService import (
    AIContextAuthorizationEngine,
    AIAuthorizationService,
    AuthorizationDecision,
    AuthorizationPolicy,
    AuthorizationPrincipal,
    AuthorizationResource,
    AuthorizationService,
    AuthorizedContextEngine,
    GrantDescriptor,
    PermissionAwareContextEngine,
    PermissionFilterResult,
    PermissionGrant,
    PermissionService,
)
from apps.ai.domain.services.contextEngine import ContextEngine, ContextSourceCandidate


class Phase13KAuthorizationTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tenantId = uuid.uuid4()
        self.otherTenantId = uuid.uuid4()
        self.subjectId = uuid.uuid4()
        self.otherSubjectId = uuid.uuid4()
        self.requestId = uuid.uuid4()
        self.clock = datetime(2026, 3, 4, 5, 6, 7, tzinfo=UTC)
        self.service = AuthorizationService(now=lambda: self.clock)
        self.principal = AuthorizationPrincipal(
            self.tenantId,
            self.subjectId,
            roles=("ANALYST",),
        )
        self.service.registerPrincipal(self.principal)

    def grant(
        self,
        permission: str,
        *,
        effect: str = "ALLOW",
        subjectId: uuid.UUID | None = None,
        roleCode: str = "ANALYST",
        **selectors: object,
    ) -> PermissionGrant:
        return PermissionGrant(
            tenantId=self.tenantId,
            permissionCode=permission,
            effect=effect,
            subjectId=subjectId,
            roleCode="" if subjectId is not None else roleCode,
            **selectors,
        )

    def source(
        self,
        entityId: str,
        content: str,
        *,
        tenantId: uuid.UUID | None = None,
        classification: str = "INTERNAL",
        authorized: bool = True,
    ) -> ContextSourceCandidate:
        return ContextSourceCandidate(
            tenantId=tenantId or self.tenantId,
            sourceDomain="projects",
            sourceEntityType="document",
            sourceEntityId=entityId,
            content=content,
            classification=classification,
            authorized=authorized,
        )

    def testPrincipalAndResourceContractsNormalizeAndRejectInvalidScope(self) -> None:
        principal = AuthorizationPrincipal(
            str(self.tenantId),
            str(self.subjectId),
            subjectType="user",
            roles=("analyst", "ANALYST"),
            directPermissions=("ai_context_read", "AI_CONTEXT_READ"),
        )
        self.assertEqual(principal.subjectType, "USER")
        self.assertEqual(principal.roles, ("ANALYST",))
        self.assertEqual(principal.directPermissions, ("AI_CONTEXT_READ",))
        resource = AuthorizationResource.entity(self.tenantId, "ai_request", self.requestId)
        self.assertEqual(resource.resourceType, "AI_REQUEST")
        self.assertEqual(resource.resourceId, str(self.requestId))
        with self.assertRaises(AIAuthorizationPrincipalInvalid):
            AuthorizationPrincipal(self.tenantId, self.subjectId, subjectType="ADMIN")
        with self.assertRaises(AIAuthorizationGrantInvalid):
            AuthorizationResource(self.tenantId, "*")
        with self.assertRaises(AIAuthorizationTenantMismatch):
            self.service.authorize(
                self.principal,
                "AI_REQUEST_READ",
                AuthorizationResource.entity(self.otherTenantId, "AI_REQUEST", self.requestId),
            )

    def testDefaultDenyExplicitAllowAndSafeDecisionFingerprint(self) -> None:
        resource = AuthorizationResource.entity(self.tenantId, "AI_REQUEST", self.requestId)
        denied = self.service.authorize(self.principal, "AI_REQUEST_READ", resource)
        self.assertIsInstance(denied, AuthorizationDecision)
        self.assertFalse(denied.allowed)
        self.assertEqual(denied.reason, "DEFAULT_DENY")
        self.assertIsNone(denied.matchedGrantId)
        self.assertTrue(denied.decisionFingerprint)
        self.service.registerGrant(self.grant("AI_REQUEST_READ", resourceType="AI_REQUEST"))
        allowed = self.service.authorize(self.principal, "AI_REQUEST_READ", resource)
        self.assertTrue(allowed.allowed)
        self.assertEqual(allowed.reason, "EXPLICIT_ALLOW")
        self.assertTrue(allowed.matchedGrantId)
        with self.assertRaises(AIAuthorizationDenied):
            self.service.requirePermission(
                AuthorizationPrincipal(self.tenantId, self.otherSubjectId),
                "AI_REQUEST_READ",
                resource,
            )

    def testExplicitDenyWinsAndWildcardPermissionMatchesOnlyItsPrefix(self) -> None:
        resource = AuthorizationResource.entity(self.tenantId, "AI_CONTEXT", "context-1")
        allow = self.service.registerGrant(self.grant("AI_CONTEXT_*", resourceType="AI_CONTEXT"))
        deny = self.service.registerGrant(
            self.grant(
                "AI_CONTEXT_READ",
                effect="DENY",
                resourceType="AI_CONTEXT",
                resourceId="context-1",
                priority=20,
            )
        )
        decision = self.service.authorize(self.principal, "AI_CONTEXT_READ", resource)
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.reason, "EXPLICIT_DENY")
        self.assertEqual(decision.matchedGrantId, deny.grantId)
        other = self.service.authorize(
            self.principal,
            "AI_CONTEXT_BUILD",
            AuthorizationResource.entity(self.tenantId, "AI_CONTEXT", "context-1"),
        )
        self.assertTrue(other.allowed)
        self.assertEqual(other.matchedGrantId, allow.grantId)
        unrelated = self.service.authorize(
            self.principal,
            "AI_REQUEST_READ",
            AuthorizationResource.entity(self.tenantId, "AI_REQUEST", "request-1"),
        )
        self.assertFalse(unrelated.allowed)

    def testRoleSubjectResourceClassificationExternalAndExpirySelectorsAreEnforced(self) -> None:
        restricted = AuthorizationResource.entity(
            self.tenantId,
            "CONTEXT_SOURCE",
            "doc-1",
            classification="RESTRICTED",
        )
        self.service.registerGrant(
            self.grant(
                "AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                allowedClassifications=("INTERNAL",),
            )
        )
        self.assertFalse(self.service.can(self.principal, "AI_CONTEXT_SOURCE_READ", restricted))
        internal = AuthorizationResource.entity(
            self.tenantId,
            "CONTEXT_SOURCE",
            "doc-1",
            classification="INTERNAL",
        )
        self.assertTrue(self.service.can(self.principal, "AI_CONTEXT_SOURCE_READ", internal))
        external = AuthorizationResource.entity(
            self.tenantId,
            "AI_CONTEXT",
            "ctx-1",
            externalProvider=True,
        )
        self.service.registerGrant(
            self.grant(
                "AI_CONTEXT_EXPORT",
                resourceType="AI_CONTEXT",
                externalProvider=True,
            )
        )
        self.assertTrue(self.service.can(self.principal, "AI_CONTEXT_EXPORT", external))
        self.assertFalse(
            self.service.can(
                self.principal,
                "AI_CONTEXT_EXPORT",
                AuthorizationResource.entity(self.tenantId, "AI_CONTEXT", "ctx-1"),
            )
        )
        expired = self.grant(
            "AI_MODEL_USE",
            resourceType="AI_MODEL",
            expiresAt=self.clock - timedelta(seconds=1),
        )
        self.service.registerGrant(expired)
        self.assertFalse(
            self.service.can(
                self.principal,
                "AI_MODEL_USE",
                AuthorizationResource.entity(self.tenantId, "AI_MODEL", "model-1"),
            )
        )

    def testGrantRegistrationIsTenantScopedDuplicateProtectedAndSnapshotSafe(self) -> None:
        grant = self.grant("AI_PROMPT_READ", resourceType="AI_PROMPT")
        descriptor = self.service.registerGrant(grant)
        self.assertIsInstance(descriptor, GrantDescriptor)
        self.assertEqual(self.service.getGrant(self.tenantId, grant.grantId).grantId, grant.grantId)
        with self.assertRaises(AIAuthorizationAlreadyRegistered):
            self.service.registerGrant(grant)
        with self.assertRaises(AIAuthorizationAlreadyRegistered):
            self.service.registerGrant(self.grant("AI_PROMPT_READ", resourceType="AI_PROMPT"))
        with self.assertRaises(AIAuthorizationNotFound):
            self.service.getGrant(self.otherTenantId, grant.grantId)
        self.assertNotIn("content", repr(descriptor).lower())
        with self.assertRaises(FrozenInstanceError):
            descriptor.permissionCode = "AI_MODEL_USE"
        self.service.revokeGrant(self.tenantId, grant.grantId)
        with self.assertRaises(AIAuthorizationNotFound):
            self.service.getGrant(self.tenantId, grant.grantId)

    def testFilterContextSourcesIsFailClosedAndDoesNotExposeDeniedPayload(self) -> None:
        self.service.registerGrant(
            self.grant(
                "AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                sourceDomain="projects",
                sourceEntityType="document",
                sourceEntityId="allowed",
            )
        )
        result = self.service.filterContextSources(
            self.principal,
            [
                self.source("allowed", "visible"),
                self.source("denied", "private payload"),
                self.source("not-authorized", "blocked", authorized=False),
            ],
        )
        self.assertIsInstance(result, PermissionFilterResult)
        self.assertEqual(result.requestedCount, 3)
        self.assertEqual(result.allowedCount, 1)
        self.assertEqual(result.deniedCount, 2)
        self.assertEqual(tuple(item.sourceEntityId for item in result.authorizedSources), ("allowed",))
        reasons = {item.sourceEntityId: item.reason for item in result.decisions}
        self.assertEqual(reasons["denied"], "DEFAULT_DENY")
        self.assertEqual(reasons["not-authorized"], "SOURCE_NOT_AUTHORIZED")
        self.assertNotIn("private payload", repr(result))
        self.assertNotIn("blocked", repr(result))
        with self.assertRaises(AIAuthorizationTenantMismatch):
            self.service.filterContextSources(
                self.principal,
                [self.source("foreign", "cross tenant", tenantId=self.otherTenantId)],
            )

    def testBuildAuthorizedContextRequiresBuildAndSourcePermissionsBeforeJAssembly(self) -> None:
        contextEngine = ContextEngine(now=lambda: self.clock)
        with self.assertRaises(AIAuthorizationDenied):
            self.service.buildAuthorizedContext(
                self.principal,
                self.requestId,
                [self.source("doc", "must not pass")],
                contextEngine=contextEngine,
            )
        self.service.registerGrant(self.grant("AI_CONTEXT_BUILD", resourceType="AI_REQUEST"))
        self.service.registerGrant(
            self.grant(
                "AI_CONTEXT_SOURCE_READ",
                resourceType="CONTEXT_SOURCE",
                sourceEntityId="allowed",
            )
        )
        result = self.service.buildAuthorizedContext(
            self.principal,
            self.requestId,
            [self.source("allowed", "authorized"), self.source("denied", "not authorized")],
            contextEngine=contextEngine,
        )
        self.assertEqual(result.context.content, "authorized")
        self.assertEqual(result.descriptor.sourceCount, 1)

    def testExternalContextRequiresSeparateExportPermissionAndPolicy(self) -> None:
        contextEngine = ContextEngine(now=lambda: self.clock)
        self.service.registerGrant(self.grant("AI_CONTEXT_BUILD", resourceType="AI_REQUEST"))
        self.service.registerGrant(self.grant("AI_CONTEXT_SOURCE_READ", resourceType="CONTEXT_SOURCE"))
        with self.assertRaises(AIAuthorizationDenied):
            self.service.buildAuthorizedContext(
                self.principal,
                self.requestId,
                [self.source("doc", "external")],
                contextEngine=contextEngine,
                policy=ContextPolicy(allowExternalProvider=True),
                externalProvider=True,
            )
        self.service.registerGrant(
            self.grant("AI_CONTEXT_EXPORT", resourceType="AI_CONTEXT", externalProvider=True)
        )
        result = self.service.buildAuthorizedContext(
            self.principal,
            self.requestId,
            [self.source("doc", "external")],
            contextEngine=contextEngine,
            policy=ContextPolicy(allowExternalProvider=True),
            externalProvider=True,
        )
        self.assertEqual(result.context.content, "external")
        self.assertTrue(result.descriptor.externalProvider)

    def testPermissionAwareContextEngineProtectsBuildReadListAndTenantScope(self) -> None:
        contextEngine = ContextEngine(now=lambda: self.clock)
        self.service.registerGrant(self.grant("AI_CONTEXT_BUILD", resourceType="AI_REQUEST"))
        self.service.registerGrant(self.grant("AI_CONTEXT_SOURCE_READ", resourceType="CONTEXT_SOURCE"))
        self.service.registerGrant(self.grant("AI_CONTEXT_READ", resourceType="AI_CONTEXT"))
        facade = AuthorizedContextEngine(self.service, contextEngine)
        result = facade.buildContext(self.principal, self.requestId, [self.source("doc", "payload")])
        self.assertEqual(facade.getContext(self.principal, result.context.id).content, "payload")
        self.assertEqual(facade.describeContext(self.principal, result.context.id).contextId, result.context.id)
        self.assertEqual(len(facade.listContexts(self.principal)), 1)
        other = AuthorizationPrincipal(self.otherTenantId, self.otherSubjectId)
        with self.assertRaises(AIAuthorizationDenied):
            facade.getContext(other, result.context.id)
        with self.assertRaises(AIAuthorizationDenied):
            facade.listContexts(AuthorizationPrincipal(self.tenantId, self.otherSubjectId))

    def testTypedAuthorizationHelpersAndTenantAccessAreExplicit(self) -> None:
        self.service.registerGrant(self.grant("AI_RESPONSE_READ", resourceType="AI_RESPONSE"))
        self.service.registerGrant(self.grant("AI_MODEL_USE", resourceType="AI_MODEL"))
        self.assertTrue(self.service.authorizeResponse(self.principal, uuid.uuid4()).allowed)
        self.assertTrue(self.service.authorizeModel(self.principal, uuid.uuid4()).allowed)
        self.assertFalse(self.service.authorizeProvider(self.principal, uuid.uuid4()).allowed)
        tenantDecision = self.service.authorizeTenant(self.principal, self.tenantId)
        self.assertTrue(tenantDecision.allowed)
        self.assertEqual(tenantDecision.reason, "TENANT_SCOPE_MATCH")
        with self.assertRaises(AIAuthorizationTenantMismatch):
            self.service.authorizeTenant(self.principal, self.otherTenantId)

    def testPolicyIsImmutableFailClosedAndAliasesAreStable(self) -> None:
        policy = AuthorizationPolicy()
        with self.assertRaises(FrozenInstanceError):
            policy.defaultDeny = False
        with self.assertRaises(AIAuthorizationPolicyInvalid):
            AuthorizationPolicy(defaultDeny=False)
        with self.assertRaises(AIAuthorizationPolicyInvalid):
            AuthorizationService(policy="not-a-policy")
        self.assertIs(PermissionService, AuthorizationService)
        self.assertIs(AIAuthorizationService, AuthorizationService)
        self.assertIs(PermissionAwareContextEngine, AuthorizedContextEngine)
        self.assertIs(AIContextAuthorizationEngine, AuthorizedContextEngine)
        source = (Path(__file__).resolve().parents[2] / "apps/ai/domain/services/authorizationService.py").read_text(
            encoding="utf-8"
        )
        for forbidden in (
            "django",
            "rest_framework",
            "redis",
            "requests",
            "httpx",
            "openai",
            "ollama",
            "azure",
            "anthropic",
            "boto3",
        ):
            self.assertNotIn(f"import {forbidden}", source.lower())
        self.assertNotIn("sk-", source.lower())
        self.assertNotIn("bearer ", source.lower())


if __name__ == "__main__":
    unittest.main()
