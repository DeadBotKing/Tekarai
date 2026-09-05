"""Base settings shared by every Tekarai environment.

Rules enforced here (Phase 01 · docs/Phases/Phase1.md §5, §14, §15):
- Environment-specific values come from environment variables (never hard-coded).
- No secret has a real default in this file.
- SQL Server is the system of record; SQLite is an offline development/test
  exception recorded in docs/adr/ADR-011.md.
- No business application or business model exists in Phase 01.

Per-environment modules: ``development.py`` · ``testing.py`` · ``production.py``.
"""

from __future__ import annotations

import environ
from django.core.exceptions import ImproperlyConfigured

from config.environment import BASE_DIR, buildDatabaseConfig

env = environ.Env(
    DEBUG=(bool, False),
    ALLOWED_HOSTS=(list, []),
    TIME_ZONE=(str, "UTC"),
    LANGUAGE_CODE=(str, "en-us"),
    corsAllowedOrigins=(list, []),
    csrfTrustedOrigins=(list, []),
    logLevel=(str, "INFO"),
)

# Read backend/.env when present (the real .env is never committed).
envFile = BASE_DIR / ".env"
if envFile.exists():
    environ.Env.read_env(envFile)

# ---------------------------------------------------------------------------
# APPLICATION
# ---------------------------------------------------------------------------
environment = env("environment", default="development")
TIME_ZONE = env("TIME_ZONE")
LANGUAGE_CODE = env("LANGUAGE_CODE")
USE_I18N = True
USE_TZ = True

# ---------------------------------------------------------------------------
# DJANGO / SECURITY (framework-level values)
# ---------------------------------------------------------------------------
DEBUG = env("DEBUG")
ALLOWED_HOSTS = env("ALLOWED_HOSTS")
SECRET_KEY = env("SECRET_KEY", default="")  # each environment module decides policy

CSRF_TRUSTED_ORIGINS = env("csrfTrustedOrigins")

# Security headers — safe defaults everywhere (Phase 01 §14).
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"
SESSION_COOKIE_HTTPONLY = True
CSRF_COOKIE_HTTPONLY = True

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS = env("corsAllowedOrigins")
CORS_ALLOW_CREDENTIALS = True

# ---------------------------------------------------------------------------
# DATABASE (Phase 01 §15 — configuration only, no business entities)
# ---------------------------------------------------------------------------
DATABASES = {
    "default": buildDatabaseConfig(
        dbEngine=env("dbEngine", default="sqlite"),
        dbName=env("dbName", default=""),
        dbUser=env("dbUser", default=""),
        dbPassword=env("dbPassword", default=""),
        dbHost=env("dbHost", default=""),
        dbPort=env("dbPort", default="1433"),
        dbConnTimeout=env("dbConnTimeout", default="30"),
        dbEncrypt=env("dbEncrypt", default="true"),
        odbcDriver=env("odbcDriver", default="ODBC Driver 18 for SQL Server"),
        connMaxAge=env("dbConnMaxAge", default="60"),
    )
}
DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# ---------------------------------------------------------------------------
# APPLICATIONS (Phase 06 §27/§32 — layered contexts under apps/)
# Shared kernel + the first two bounded contexts (Tenancy, Identity).
# ---------------------------------------------------------------------------
# ``daphne`` MUST stay first so ``runserver`` serves the ASGI application
# (Phase 08 §30 — REST and WS share one process in development).
INSTALLED_APPS = [
    "daphne",
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
    "apps.sharedKernel",
    "apps.tenancy",
    "apps.identity",
    "apps.communication",
    "apps.notifications",
    "apps.ai",
]

# --------------------------------------------------------------------------- #
# CHANNELS — real-time transport (Phase 08 §8/§30)                              #
# --------------------------------------------------------------------------- #

ASGI_APPLICATION = "config.asgi.application"

# In-memory layer works for single-process development and tests; production
# settings override this with channels-redis (see production.py).
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    },
}

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    # Correlation/request context before anything else observes the request
    # (Phase 06 §25–§26).
    "apps.sharedKernel.presentation.api.middleware.CorrelationContextMiddleware",
    "django.middleware.common.CommonMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

# ---------------------------------------------------------------------------
# STATIC / MEDIA / STORAGE
# ---------------------------------------------------------------------------
STATIC_URL = "static/"
STATIC_ROOT = env("staticRoot", default=str(BASE_DIR / "staticRoot"))
MEDIA_URL = "media/"
MEDIA_ROOT = env("mediaRoot", default=str(BASE_DIR / "mediaRoot"))

# ---------------------------------------------------------------------------
# LOGGING
# ---------------------------------------------------------------------------
LOG_LEVEL = env("logLevel").upper()
LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "standard": {
            "format": "{levelname} {asctime} {name} :: {message}",
            "style": "{",
        },
        # Structured logging (Phase 06 §30) — JSON with the §30 field set.
        "tekaraiJson": {
            "()": "apps.sharedKernel.infrastructure.loggingSetup.TekaraiJsonFormatter",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "tekaraiJson",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}

# ---------------------------------------------------------------------------
# API LAYER (Phase 06 §12–§25)
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "apps.identity.presentation.api.authentication.apiKeyAuthentication.ApiKeyAuthentication",
        "apps.sharedKernel.presentation.api.authentication.BearerSessionAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "apps.sharedKernel.presentation.api.permissions.IsAuthenticated",
    ],
    "EXCEPTION_HANDLER": (
        "apps.sharedKernel.presentation.api.exceptionHandler.tekraiExceptionHandler"
    ),
    "DEFAULT_PAGINATION_CLASS": (
        "apps.sharedKernel.presentation.api.pagination.TekaraiPagePagination"
    ),
    "PAGE_SIZE": 50,
    "UNAUTHENTICATED_USER": None,
}

# Port bindings for the composition root (Phase 06 §34); defaults live in
# apps.sharedKernel.infrastructure.wiring — override per environment here.
SHARED_KERNEL_PROVIDERS: dict[str, str] = {}

# Rate-limit policies (§23): scope → (limit, windowSeconds). Sensitive
# classes: login/refresh now; OTP, password reset, AI, uploads land with
# their phases.
API_RATE_LIMIT_POLICIES: dict[str, tuple[int, int]] = {
    "auth:login": (5, 60),
    "auth:refresh": (30, 60),
    # Phase 10 communication scopes (docs/Phases/Phase10.md §68) —
    # (limit per window, window seconds). Send/presence are generous;
    # call/meeting/conversation creation tighter. Overridable via env if a
    # deployment tunes them; defaults match DEFAULT_RATE_LIMITS in
    # domain/valueObjects/phase10Types.py.
    "communication:sendMessage": (30, 60),
    "communication:createConversation": (20, 300),
    "communication:callStart": (10, 60),
    "communication:meetingCreate": (20, 300),
    "communication:wsConnection": (30, 60),
    "communication:presenceUpdate": (120, 60),
}

# Session lifetime (ADR-019 opaque tokens; refresh rotates within this TTL).
SESSION_TTL_MINUTES = 480

# ---------------------------------------------------------------------------
# AI PROVIDER ADAPTERS (Phase 13-L)
# ---------------------------------------------------------------------------
# Configuration-driven provider wiring (Master Specification §42): values come
# exclusively from the environment, secrets never have a real default, and an
# entry is instantiated only when its configuration is complete
# (apps.ai.infrastructure.providers.providerWiring.buildConfiguredProviderAdapters).
# Camel-case env names per ADR-001/ADR-009.
aiProviderTimeoutSeconds = float(env("aiProviderTimeoutSeconds", default="30") or 30)

AI_PROVIDER_ADAPTERS: dict[str, dict[str, object]] = {
    "OPENAI": {
        "baseUrl": env("aiProviderOpenAiBaseUrl", default="https://api.openai.com/v1"),
        "apiKey": env("aiProviderOpenAiApiKey", default=""),
        "timeoutSeconds": aiProviderTimeoutSeconds,
    },
    "AZURE_OPENAI": {
        "baseUrl": env("aiProviderAzureOpenAiBaseUrl", default=""),
        "apiKey": env("aiProviderAzureOpenAiApiKey", default=""),
        "apiVersion": env("aiProviderAzureOpenAiApiVersion", default="2024-10-21"),
        "timeoutSeconds": aiProviderTimeoutSeconds,
    },
    "OLLAMA": {
        "baseUrl": env("aiProviderOllamaBaseUrl", default="http://127.0.0.1:11434"),
        "apiKey": env("aiProviderOllamaApiKey", default=""),
        "timeoutSeconds": aiProviderTimeoutSeconds,
    },
    "ANTHROPIC": {
        "baseUrl": env("aiProviderAnthropicBaseUrl", default="https://api.anthropic.com"),
        "apiKey": env("aiProviderAnthropicApiKey", default=""),
        "anthropicVersion": env("aiProviderAnthropicVersion", default="2023-06-01"),
        "timeoutSeconds": aiProviderTimeoutSeconds,
    },
    "LOCAL": {
        "baseUrl": env("aiProviderLocalBaseUrl", default=""),
        "apiKey": env("aiProviderLocalApiKey", default=""),
        "supportsEmbedding": env.bool("aiProviderLocalSupportsEmbedding", default=False),
        "timeoutSeconds": aiProviderTimeoutSeconds,
    },
}

# ---------------------------------------------------------------------------
# AI USAGE METERING (Phase 13-N)
# ---------------------------------------------------------------------------
# Configuration-driven metering defaults (Master Specification §42): token
# and cost caps plus the metering currency and retention horizon. A zero
# token/cost limit means "unlimited" — explicit per-tenant quota policies
# (aiQuotaPolicies) always take precedence over these platform defaults.
# Camel-case env names per ADR-001/ADR-009.
AI_USAGE_ENABLED = env.bool("aiUsageEnabled", default=True)
AI_USAGE_DEFAULT_TOKEN_LIMIT = int(env("aiUsageDefaultTokenLimit", default="0") or 0)
AI_USAGE_DEFAULT_COST_LIMIT = str(env("aiUsageDefaultCostLimit", default="0") or "0")
AI_USAGE_DEFAULT_CURRENCY = str(env("aiUsageDefaultCurrency", default="USD") or "USD").upper()
AI_USAGE_RETENTION_DAYS = int(env("aiUsageRetentionDays", default="90") or 90)

# ---------------------------------------------------------------------------
# AI AUDIT & GOVERNANCE (Phase 13-O)
# ---------------------------------------------------------------------------
# Configuration-driven audit/governance defaults (Master Specification §42):
# ledger switch and retention horizon, the restricted-detail opt-in (§47),
# the governance switch, and the platform-default daily cost budget applied
# when a tenant defines no governance policy of its own (§48). A zero
# budget means "unlimited" — an explicit per-tenant governance policy
# always takes precedence over these platform defaults.
# Camel-case env names per ADR-001/ADR-009.
AI_AUDIT_ENABLED = env.bool("aiAuditEnabled", default=True)
AI_AUDIT_RETENTION_DAYS = int(env("aiAuditRetentionDays", default="365") or 365)
AI_AUDIT_INCLUDE_RESTRICTED_DETAIL = env.bool("aiAuditIncludeRestrictedDetail", default=False)
AI_GOVERNANCE_ENABLED = env.bool("aiGovernanceEnabled", default=True)
AI_GOVERNANCE_DEFAULT_MAX_COST_PER_DAY = str(
    env("aiGovernanceDefaultMaxCostPerDay", default="0") or "0"
)
AI_GOVERNANCE_DEFAULT_CURRENCY = str(
    env("aiGovernanceDefaultCurrency", default="USD") or "USD"
).upper()

# Phase 13-P async execution: the DB-backed job ledger, lease claiming,
# exponential retry backoff, and the worker loop
# (docs/Phases/Phase13/Phase13-P.md). Fail-closed: a disabled queue refuses
# submissions instead of silently dropping them.
AI_QUEUE_ENABLED = env.bool("aiQueueEnabled", default=True)
AI_QUEUE_RETENTION_DAYS = int(env("aiQueueRetentionDays", default="30") or 30)
AI_QUEUE_DEFAULT_MAX_ATTEMPTS = int(env("aiQueueDefaultMaxAttempts", default="3") or 3)
AI_QUEUE_CLAIM_LIMIT = int(env("aiQueueClaimLimit", default="10") or 10)
AI_WORKER_ID = str(env("aiWorkerId", default="aiWorker") or "aiWorker")
AI_WORKER_LEASE_SECONDS = int(env("aiWorkerLeaseSeconds", default="120") or 120)
AI_WORKER_RETRY_BASE_SECONDS = int(env("aiWorkerRetryBaseSeconds", default="30") or 30)
AI_WORKER_RETRY_MULTIPLIER = float(env("aiWorkerRetryMultiplier", default="2.0") or 2.0)
AI_WORKER_RETRY_MAX_SECONDS = int(env("aiWorkerRetryMaxSeconds", default="600") or 600)
AI_WORKER_IDLE_SLEEP_SECONDS = int(env("aiWorkerIdleSleepSeconds", default="5") or 5)

# ---------------------------------------------------------------------------
# GUARDS
# ---------------------------------------------------------------------------
if environment not in {"development", "testing", "production"}:
    raise ImproperlyConfigured(
        f"Configuration value 'environment' must be one of "
        f"development|testing|production. Got '{environment}'."
    )

# Migrations live inside each context's infrastructure layer (§27).
MIGRATION_MODULES = {
    "sharedKernel": "apps.sharedKernel.infrastructure.migrations",
    "tenancy": "apps.tenancy.infrastructure.migrations",
    "identity": "apps.identity.infrastructure.migrations",
    "communication": "apps.communication.infrastructure.migrations",
    "notifications": "apps.notifications.infrastructure.migrations",
    "ai": "apps.ai.infrastructure.migrations",
}

# Phase 07 §7/§8 — JWT configuration (ADR-022: in-house HS256, stdlib only).
JWT_AUTH = {
    "issuer": env("jwtIssuer", default="tekarai"),
    "audience": env("jwtAudience", default="tekarai-api"),
    "accessTtlMinutes": int(env("jwtAccessTtlMinutes", default="15") or 15),
    "challengeTtlMinutes": int(env("jwtChallengeTtlMinutes", default="5") or 5),
    # Dedicated key recommended; empty falls back to SECRET_KEY (ADR-022).
    "signingKey": env("jwtSigningKey", default=""),
}

# Phase 07 §23 — password policy (expiration NOT forced by default).
PASSWORD_POLICY = {
    "minLength": 12,
    "requireComplexity": True,
    "historyLimit": 5,
    "maxFailedAttempts": 5,
    "lockMinutes": 15,
    "enforceExpiration": False,
    "expirationDays": 0,
}

# Phase 07 §24 — MFA policy (per system/tenant/user, default off).
MFA_POLICY = {
    "required": False,
    "allowedFactors": ["totp"],
    "recoveryCodeCount": 8,
    "challengeTtlMinutes": 5,
}

# Phase 07 §25/§26 — token lifetimes (minutes).
VERIFICATION_POLICY = {
    "emailTtlMinutes": 60,
    "phoneTtlMinutes": 60,
    "resetTtlMinutes": 30,
    "maxAttempts": 5,
}
