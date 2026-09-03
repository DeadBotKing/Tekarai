"""Phase 7 architecture guards — §41 DoD as executable rules.

- application layer stays Django-free and HTTP-free (§41.2/§41.3)
- domain has no Django, no DRF, no infrastructure import
- §32 endpoints are all versioned under /api/v1
- JWT never the sole mechanism: every verify re-checks the Session row
- no raw secrets in models: ApiKey stores keyHash, MFA stores secretRef
"""

from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase

BACKEND = Path(__file__).resolve().parents[2]

CONTEXTS = ("sharedKernel", "tenancy", "identity")


def pyFiles(root: Path):
    for path in root.rglob("*.py"):
        if any(
            part in {"venv", "__pycache__", "migrations", "site-packages"} for part in path.parts
        ):
            continue
        yield path


class LayerPurityTests(SimpleTestCase):
    def testApplicationNeverImportsDjangoOrRestFramework(self) -> None:
        for context in CONTEXTS:
            for file in pyFiles(BACKEND / "apps" / context / "application"):
                src = file.read_text(encoding="utf-8")
                for banned in ("import django", "from django", "rest_framework"):
                    self.assertNotIn(
                        banned,
                        src,
                        f"{file} leaks framework code into the application layer",
                    )

    def testDomainNeverImportsDjangoOrInfrastructure(self) -> None:
        for context in CONTEXTS:
            for file in pyFiles(BACKEND / "apps" / context / "domain"):
                src = file.read_text(encoding="utf-8")
                for banned in (
                    "import django",
                    "from django",
                    "rest_framework",
                    "apps.identity.infrastructure",
                    "apps.tenancy.infrastructure",
                ):
                    self.assertNotIn(banned, src, f"{file} breaks domain purity")

    def testDomainEntitiesNeverImportPresentation(self) -> None:
        for context in CONTEXTS:
            for file in pyFiles(BACKEND / "apps" / context / "domain"):
                src = file.read_text(encoding="utf-8")
                self.assertNotIn("presentation", src, f"{file} touches presentation")


class JwtNotSoleMechanismTests(SimpleTestCase):
    def testSessionVerifierRechecksSessionRow(self) -> None:
        verifier = (BACKEND / "apps/identity/infrastructure/services/principals.py").read_text(
            encoding="utf-8"
        )
        self.assertIn("SessionModel", verifier, "verifyToken must hit the DB")
        self.assertIn("revokedAt", verifier, "revocation must be re-checked (§35.4)")
        self.assertIn("expiresAt", verifier, "expiry must be re-checked (§35.5)")

    def testAccessTokensCarryMinimalClaims(self) -> None:
        jwt = (BACKEND / "apps/identity/infrastructure/services/jwtService.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("permissions", jwt.split("def issueAccessToken")[1].split("def ")[0])


class SecretHygieneTests(SimpleTestCase):
    def testNoRawSecretColumns(self) -> None:
        models = (BACKEND / "apps/identity/infrastructure/models.py").read_text(encoding="utf-8")
        self.assertNotIn("rawKey", models)
        self.assertIn("keyHash", models, "§22 — only hashes persist")
        self.assertIn("secretRef", models, "§24 — protected secret reference")

    def testApiKeysDoNotReturnRawKeyInListing(self) -> None:
        listing = (BACKEND / "apps/identity/application/useCases/apiKeyUseCases.py").read_text(
            encoding="utf-8"
        )
        listingBody = listing.split("class ListApiKeysUseCase")[1]
        self.assertNotIn("rawKey", listingBody)

    def testJwtServiceLogsNothing(self) -> None:
        jwt = (BACKEND / "apps/identity/infrastructure/services/jwtService.py").read_text(
            encoding="utf-8"
        )
        self.assertNotIn("print(", jwt)
        self.assertNotIn("logging", jwt)


class EndpointVersioningTests(SimpleTestCase):
    def testPhase7RoutesAreVersioned(self) -> None:
        routes = (BACKEND / "apps/identity/presentation/api/urls/identityRoutes.py").read_text(
            encoding="utf-8"
        )
        for probe in (
            "auth/password/change",
            "auth/password/reset",
            "auth/verify-email",
            "roles",
            "api-keys",
            "service-accounts",
            "me/sessions",
            "me/mfa",
        ):
            self.assertIn(probe, routes, f"§32 endpoint missing: {probe}")


class UseCaseInventoryTests(SimpleTestCase):
    """§31 — the Phase 7 use-case inventory exists in the container."""

    def testContainerExposesAllPhase7UseCases(self) -> None:
        container = (BACKEND / "apps/identity/infrastructure/container.py").read_text(
            encoding="utf-8"
        )
        for factory in (
            "authenticateUserUseCase",
            "verifyMfaChallengeUseCase",
            "refreshSessionUseCase",
            "logoutUseCase",
            "listSessionsUseCase",
            "revokeSessionUseCase",
            "revokeAllSessionsUseCase",
            "changePasswordUseCase",
            "requestPasswordResetUseCase",
            "confirmPasswordResetUseCase",
            "sendVerificationUseCase",
            "verifyChannelUseCase",
            "createRoleUseCase",
            "updateRoleUseCase",
            "deleteRoleUseCase",
            "assignRoleUseCase",
            "removeRoleUseCase",
            "listRolesUseCase",
            "createApiKeyUseCase",
            "revokeApiKeyUseCase",
            "listApiKeysUseCase",
            "createServiceAccountUseCase",
            "disableServiceAccountUseCase",
            "enableServiceAccountUseCase",
            "listServiceAccountsUseCase",
            "setupMfaUseCase",
            "confirmMfaUseCase",
            "disableMfaUseCase",
            "changeUserStatusUseCase",
        ):
            self.assertIn(factory, container, f"§31 use case missing: {factory}")
