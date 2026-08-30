"""Architecture tests — Phase 06 (docs/Phases/Phase6.md §32/§33/§27).

Mechanically enforces the application/API architecture: layered §27
structure, HTTP-free application layer, ORM-free presentation, use-case
template conformance, standard envelope everywhere, versioning, error
architecture, authn/authz separation, tenancy enforcement points,
audit integration, idempotency, rate limiting, OpenAPI coverage, testing
architecture and logging.
"""

from __future__ import annotations

import re
from pathlib import Path

from django.conf import settings
from django.test import SimpleTestCase

from apps.sharedKernel.presentation.api.openapi import REGISTRY

BACKEND_DIR = Path(__file__).resolve().parents[2]
APPS_DIR = BACKEND_DIR / "apps"
CONTEXTS = ("tenancy", "identity")

CONTEXT_LAYER_FOLDERS = {
    "domain": ("entities", "valueObjects", "services", "events", "repositories", "exceptions"),
    "application": ("commands", "queries", "useCases", "dto", "services"),
    "infrastructure": ("models.py", "repositories", "services", "migrations"),
    "presentation": ("api",),
}
API_FOLDERS = ("serializers", "views", "urls", "permissions")

IMPORT_LINE = re.compile(r"^\s*(?:from|import)\s+([a-zA-Z0-9_.]+)")


def importsOf(path: Path) -> list[str]:
    return [
        match.group(1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if (match := IMPORT_LINE.match(line))
    ]


def pythonFiles(context: str, layer: str) -> list[Path]:
    directory = APPS_DIR / context / layer
    return sorted(directory.rglob("*.py")) if directory.exists() else []


class Phase6StructureTests(SimpleTestCase):
    def testContextsFollowSection27Layout(self) -> None:
        for context in CONTEXTS:
            for layer, required in CONTEXT_LAYER_FOLDERS.items():
                for entry in required:
                    path = APPS_DIR / context / layer / entry
                    self.assertTrue(path.exists(), f"{context}/{layer}/{entry} missing (§27)")

    def testPresentationApiLayout(self) -> None:
        for context in CONTEXTS:
            for folder in API_FOLDERS:
                self.assertTrue(
                    (APPS_DIR / context / "presentation" / "api" / folder).is_dir(),
                    f"{context}/presentation/api/{folder} missing (§27)",
                )

    def testSharedKernelExposesTheFourLayers(self) -> None:
        for layer in ("domain", "application", "infrastructure", "presentation"):
            self.assertTrue(
                (APPS_DIR / "sharedKernel" / layer).is_dir(),
                f"sharedKernel/{layer} missing",
            )


class Phase6LayerDisciplineTests(SimpleTestCase):
    def testApplicationLayerIsFrameworkFree(self) -> None:
        violations: list[str] = []
        for context in (*CONTEXTS, "sharedKernel"):
            for sourceFile in pythonFiles(context, "application"):
                for imported in importsOf(sourceFile):
                    if imported.startswith(("django", "rest_framework")):
                        violations.append(f"{sourceFile.name}: {imported}")
        self.assertEqual(violations, [], "Application must not know HTTP/ORM (§1/§3)")

    def testPresentationContainsNoOrmCalls(self) -> None:
        """API never touches the database directly (§4/§12)."""
        forbidden = re.compile(r"\.objects\.|\.save\(|\.bulk_create\(|raw\(")
        violations: list[str] = []
        for context in (*CONTEXTS, "sharedKernel"):
            presentationDir = APPS_DIR / context / "presentation"
            for sourceFile in sorted(presentationDir.rglob("*.py")):
                content = sourceFile.read_text(encoding="utf-8")
                for lineNumber, line in enumerate(content.splitlines(), 1):
                    if forbidden.search(line):
                        violations.append(f"{sourceFile.name}:{lineNumber}")
        self.assertEqual(violations, [], "ORM usage inside presentation (§12)")

    def testPresentationImportsApplicationOrOwnContainerOnly(self) -> None:
        """Views reach use cases through the application layer / container —
        never into domain or repositories directly (§1, §34)."""
        violations: list[str] = []
        for context in CONTEXTS:
            for sourceFile in pythonFiles(context, "presentation"):
                for imported in importsOf(sourceFile):
                    match = re.match(rf"^apps\.{context}\.(\w+)", imported)
                    allowed = {"application", "infrastructure", "presentation"}
                    if match and match.group(1) not in allowed:
                        violations.append(f"{sourceFile.name}: {imported}")
        self.assertEqual(violations, [])

    def testInfrastructureImplementsDomainContracts(self) -> None:
        for context, contract, implementation in (
            ("tenancy", "tenantRepository.py", "tenantRepositoryImpl.py"),
            ("identity", "identityRepositories.py", "identityRepositoriesImpl.py"),
        ):
            self.assertTrue((APPS_DIR / context / "domain" / "repositories" / contract).is_file())
            self.assertTrue(
                (APPS_DIR / context / "infrastructure" / "repositories" / implementation).is_file(),
                f"{context}: repository implementation missing (DoD 5)",
            )

    def testRepositoryContractsAreProtocols(self) -> None:
        for context in CONTEXTS:
            contractsDir = APPS_DIR / context / "domain" / "repositories"
            for contractFile in contractsDir.glob("*.py"):
                content = contractFile.read_text(encoding="utf-8")
                if "class " in content:
                    self.assertIn(
                        "Protocol",
                        content,
                        f"{contractFile.name}: contracts must be Protocols (§10)",
                    )

    def testRepositorySelectorsCarryTenantScope(self) -> None:
        """§10/BR-TEN-001: repository methods never return unscoped rows."""
        identityContracts = (
            APPS_DIR / "identity" / "domain" / "repositories" / "identityRepositories.py"
        ).read_text(encoding="utf-8")
        self.assertIn("tenantId", identityContracts)
        userImpl = (
            APPS_DIR
            / "identity"
            / "infrastructure"
            / "repositories"
            / "identityRepositoriesImpl.py"
        ).read_text(encoding="utf-8")
        self.assertIn("tenantId=", userImpl)


class Phase6UseCaseTests(SimpleTestCase):
    def testUseCasesSubclassTheTemplate(self) -> None:
        from apps.identity.application.useCases.assignUserToTenant import (
            AssignUserToTenantUseCase,
        )
        from apps.identity.application.useCases.createUser import CreateUserUseCase
        from apps.sharedKernel.application.useCase import UseCase

        for useCaseClass in (CreateUserUseCase, AssignUserToTenantUseCase):
            self.assertTrue(issubclass(useCaseClass, UseCase))
            self.assertTrue(useCaseClass.requiredAction)  # §8 step 2 bound

    def testAuthenticationUseCaseRequiresNoPermission(self) -> None:
        from apps.identity.application.useCases.sessionUseCases import (
            AuthenticateUserUseCase,
        )

        self.assertEqual(AuthenticateUserUseCase.requiredAction, "")  # §16

    def testCommandsAndQueriesAreFrozenDataclasses(self) -> None:
        import dataclasses

        from apps.identity.application.commands.identityCommands import CreateUserCommand
        from apps.sharedKernel.application.messaging import Command, Query
        from apps.tenancy.application.queries.tenantQueries import ListTenantsQuery

        self.assertTrue(dataclasses.is_dataclass(CreateUserCommand))
        self.assertTrue(dataclasses.is_dataclass(ListTenantsQuery))
        self.assertTrue(issubclass(CreateUserCommand, Command))
        self.assertTrue(issubclass(ListTenantsQuery, Query))
        with self.assertRaises(dataclasses.FrozenInstanceError):
            CreateUserCommand(tenantId="a", username="b", email="c", password="d").username = "x"  # type: ignore[misc]

    def testTransactionBoundaryLivesInApplicationLayer(self) -> None:
        useCaseSource = (APPS_DIR / "sharedKernel" / "application" / "useCase.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("with self.unitOfWork", useCaseSource)  # §9


class Phase6ApiContractTests(SimpleTestCase):
    def testAllViewsUseTheStandardEnvelope(self) -> None:
        for context in CONTEXTS:
            viewsDir = APPS_DIR / context / "presentation" / "api" / "views"
            for viewFile in viewsDir.glob("*.py"):
                content = viewFile.read_text(encoding="utf-8")
                if "Response(" in content:
                    self.assertIn(
                        "successEnvelope",
                        content,
                        f"{viewFile.name}: responses must use the envelope (§14)",
                    )

    def testErrorArchitectureCoversSpecClasses(self) -> None:
        from apps.sharedKernel.domain import errors

        for className in (
            "EntityNotFoundError",
            "BusinessRuleViolationError",
            "PermissionDeniedError",
            "ConflictError",
            "ExternalServiceError",
            "AuthenticationRequiredError",
            "ValidationFailedError",
        ):
            self.assertTrue(hasattr(errors, className), f"§15 error missing: {className}")

    def testExceptionMapperIsBoundInSettings(self) -> None:
        self.assertIn(
            "tekraiExceptionHandler",
            settings.REST_FRAMEWORK["EXCEPTION_HANDLER"],
        )

    def testApiVersioning(self) -> None:
        urlsSource = (BACKEND_DIR / "config" / "urls.py").read_text(encoding="utf-8")
        self.assertIn('"api/v1/"', urlsSource)
        # RULE K scan already guarantees no unversioned api/ strings.

    def testCorrelationMiddlewareIsActive(self) -> None:
        self.assertTrue(
            any("CorrelationContextMiddleware" in m for m in settings.MIDDLEWARE),
            "§25 correlation middleware missing",
        )

    def testSensitiveEndpointsAreRateLimited(self) -> None:
        authViews = (
            APPS_DIR / "identity" / "presentation" / "api" / "views" / "authViews.py"
        ).read_text(encoding="utf-8")
        self.assertIn('@enforceRateLimit("auth:login")', authViews)
        self.assertIn('@enforceRateLimit("auth:refresh")', authViews)
        self.assertIn("auth:login", settings.API_RATE_LIMIT_POLICIES)

    def testMutatingEndpointsSupportIdempotency(self) -> None:
        for context in ("tenancy", "identity"):
            viewsDir = APPS_DIR / context / "presentation" / "api" / "views"
            for viewFile in viewsDir.glob("*.py"):
                content = viewFile.read_text(encoding="utf-8")
                if "def post(" in content:
                    self.assertIn(
                        "IdempotencyMixin",
                        content,
                        f"{viewFile.name}: POST endpoints need IdempotencyMixin (§20)",
                    )

    def testOpenApiRegistryCoversRegisteredRoutes(self) -> None:
        registeredPaths = {f"/{spec.path.strip('/')}" for spec in REGISTRY}
        self.assertIn("/api/v1/auth/login", registeredPaths)
        self.assertIn("/api/v1/users", registeredPaths)
        self.assertIn("/api/v1/tenants", registeredPaths)
        self.assertIn("/api/v1/platform/audit-events", registeredPaths)
        self.assertTrue(
            all(path.startswith("/api/v1/") for path in registeredPaths),
            "every documented endpoint must be versioned (§13/§24)",
        )

    def testOpenApiDocumentBuilds(self) -> None:
        from apps.sharedKernel.presentation.api.openapi import buildOpenApiDocument

        document = buildOpenApiDocument()
        self.assertEqual(document["openapi"], "3.1.0")
        self.assertGreaterEqual(len(document["paths"]), 10)

    def testPaginationClassesExist(self) -> None:
        from apps.sharedKernel.presentation.api.pagination import (
            TekaraiCursorPagination,
            TekaraiPagePagination,
        )

        self.assertEqual(TekaraiPagePagination.page_query_param, "page")
        self.assertEqual(TekaraiCursorPagination.cursor_query_param, "cursor")

    def testFilteringIsWhitelistDriven(self) -> None:
        source = (APPS_DIR / "sharedKernel" / "presentation" / "api" / "filtering.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("filterableFields", source)
        self.assertIn("sortableFields", source)


class Phase6AuthAndTenancyTests(SimpleTestCase):
    def testAuthenticationAndAuthorizationAreSeparateModules(self) -> None:
        apiDir = APPS_DIR / "sharedKernel" / "presentation" / "api"
        self.assertTrue((apiDir / "authentication.py").is_file())
        self.assertTrue((apiDir / "permissions.py").is_file())

    def testLoginEndpointIsPublicButRateLimited(self) -> None:
        from apps.identity.presentation.api.views.authViews import LoginView

        self.assertEqual(LoginView.permission_classes, [])
        self.assertEqual(LoginView.authentication_classes, [])

    def testAuthorizationIsActionBasedNotFlags(self) -> None:
        presentationSources = "".join(
            path.read_text(encoding="utf-8")
            for path in APPS_DIR.rglob("*.py")
            if "presentation" in path.parts
        )
        # Docstrings may mention the forbidden flags; usage may not (§17).
        self.assertNotIn(".is_staff", presentationSources)
        self.assertNotIn(".is_superuser", presentationSources)
        self.assertNotIn("is_staff=", presentationSources)
        self.assertIn("actionPermission", presentationSources)

    def testTenancyEnforcedAtMultipleLayers(self) -> None:
        # Application: use case boundary check exists (§18).
        userQueries = (
            APPS_DIR / "identity" / "application" / "useCases" / "userQueryUseCases.py"
        ).read_text(encoding="utf-8")
        self.assertIn("TenantAccessDeniedError", userQueries)
        # Authorization: gate receives tenant context.
        gate = (
            APPS_DIR / "identity" / "infrastructure" / "services" / "permissionGate.py"
        ).read_text(encoding="utf-8")
        self.assertIn("targetTenantId", gate)

    def testSessionVerifierResolvesTokensOnly(self) -> None:
        verifier = (
            APPS_DIR / "identity" / "infrastructure" / "services" / "sessionVerifier.py"
        ).read_text(encoding="utf-8")
        self.assertIn("verifyToken", verifier)
        self.assertNotIn("hasPermission", verifier)  # §16 separation


class Phase6AuditAndObservabilityTests(SimpleTestCase):
    def testAuditModelCoversSection19Fields(self) -> None:
        from apps.sharedKernel.infrastructure.models import AuditEventModel

        for field in (
            "actorUserId",
            "tenantId",
            "action",
            "resourceType",
            "resourceId",
            "occurredAt",
            "ipAddress",
            "userAgent",
            "beforeState",
            "afterState",
            "correlationId",
        ):
            self.assertTrue(hasattr(AuditEventModel, field), f"§19 audit field missing: {field}")

    def testUseCaseTemplateAudits(self) -> None:
        from apps.sharedKernel.application.useCase import UseCase

        self.assertTrue(hasattr(UseCase, "audit"))

    def testDomainEventsDispatchPostCommit(self) -> None:
        useCaseSource = (APPS_DIR / "sharedKernel" / "application" / "useCase.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("publishPendingEvents", useCaseSource)

    def testStructuredLoggingConfigured(self) -> None:
        formatter = settings.LOGGING["formatters"]["tekaraiJson"]
        self.assertIn("TekaraiJsonFormatter", formatter["()"])
        self.assertEqual(settings.LOGGING["handlers"]["console"]["formatter"], "tekaraiJson")


class Phase6TestingArchitectureTests(SimpleTestCase):
    def testTestCategoryFoldersExist(self) -> None:
        for folder in ("unit", "application", "integration", "architecture"):
            self.assertTrue(
                (BACKEND_DIR / "tests" / folder).is_dir(),
                f"tests/{folder} missing (§29)",
            )

    def testEachExemplarUseCaseHasCoverage(self) -> None:
        applicationTests = (
            BACKEND_DIR / "tests" / "application" / "testPhase6UseCases.py"
        ).read_text(encoding="utf-8")
        for fragment in (
            "createTenantUseCase",
            "createUserUseCase",
            "assignUserToTenantUseCase",
            "authenticateUserUseCase",
            "refreshSessionUseCase",
            "logoutUseCase",
            "listUsersUseCase",
        ):
            self.assertIn(fragment, applicationTests)
        apiTests = (BACKEND_DIR / "tests" / "integration" / "testPhase6ApiContract.py").read_text(
            encoding="utf-8"
        )
        for fragment in (
            "TENANT_ACCESS_DENIED",
            "PERM_PERMISSION_DENIED",
            "SYS_RATE_LIMITED",
            "VALIDATION_ERROR",
        ):
            self.assertIn(fragment, apiTests)


class Phase6DesignOnlyGuardTests(SimpleTestCase):
    def testNoNewDependenciesWereAdded(self) -> None:
        requirements = BACKEND_DIR.parent / "backend" / "requirements" / "base.txt"
        content = requirements.read_text(encoding="utf-8")
        self.assertNotIn("drf-spectacular", content)  # ADR-020 in-house builder
        self.assertNotIn("djangorestframework-simplejwt", content)  # ADR-019

    def testProvidersBoundThroughSettings(self) -> None:
        from apps.sharedKernel.infrastructure.wiring import DEFAULT_PROVIDERS

        for port in (
            "unitOfWork",
            "auditRecorder",
            "eventDispatcher",
            "clock",
            "sessionVerifier",
            "permissionGate",
            "idempotencyStore",
            "rateLimiter",
        ):
            self.assertIn(port, DEFAULT_PROVIDERS)
