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

from pathlib import Path

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
    "apps.learning",
    "apps.projectIntelligence",
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
    # Phase 15 notification abuse/provider controls.
    "notification:search": (120, 60),
    "notification:create": (60, 60),
    "notification:bulk": (10, 60),
    "notification:device": (20, 60),
    "notification:webhook": (300, 60),
    "notification:admin": (30, 60),
    # Phase 16 Self-Learning Platform controls.
    "learning:observe": (300, 60),
    "learning:manage": (30, 60),
    "learning:run": (10, 60),
    "learning:action": (20, 60),
    "learning:feedback": (120, 60),
    "learning:monitor": (300, 60),
    "project-intelligence:snapshot": (10, 60),
    "project-intelligence:analyze": (10, 60),
    "project-intelligence:context": (30, 60),
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

# Phase 13-Z public agent runtime and release gate. Production remains
# fail-closed until an explicit provider/model pair is selected. The fake
# provider can only be enabled deliberately (testing.py does so).
AI_AGENT_DEFAULT_PROVIDER = str(env("aiAgentDefaultProvider", default="") or "").upper()
AI_AGENT_DEFAULT_MODEL = str(env("aiAgentDefaultModel", default="") or "")
AI_AGENT_ALLOW_DETERMINISTIC_PROVIDER = env.bool("aiAgentAllowDeterministicProvider", default=False)

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
# AI PROVIDER RESILIENCE (Phase 13-M)
# ---------------------------------------------------------------------------
# Retry / fallback / timeout tuning consumed by
# apps.ai.infrastructure.providers.resilienceWiring, which validates them.
# NOTE (Phase 13-Q corrective amendment): this block was delivered by
# Phase 13-M (commit 0df22be) and removed by the Phase 13-N commit
# (fd9b289) — see Phase13-Q-ExecutionReport.md §5. It is restored here
# unchanged so `resilienceWiring.buildResilientExecutor` reads real
# configuration again instead of falling back to an empty mapping.
AI_RESILIENCE: dict[str, object] = {
    # Total attempts for one provider step (1 = no retry).
    "aiRetryMaxAttempts": int(env("aiRetryMaxAttempts", default="3") or 3),
    # Initial backoff before the first retry, in seconds.
    "aiRetryInitialBackoffSeconds": float(
        env("aiRetryInitialBackoffSeconds", default="0.25") or 0.25
    ),
    # Geometric growth factor applied to the backoff after each retry.
    "aiRetryBackoffMultiplier": float(env("aiRetryBackoffMultiplier", default="2.0") or 2.0),
    # Ceiling for a single backoff wait, in seconds.
    "aiRetryMaxBackoffSeconds": float(env("aiRetryMaxBackoffSeconds", default="5.0") or 5.0),
    # Wall-clock budget for the whole call including fallbacks, in seconds.
    "aiProviderTimeoutBudgetSeconds": float(
        env("aiProviderTimeoutBudgetSeconds", default="60") or 60
    ),
    # Ordered fallback chain: primary first, then secondaries, then local.
    "aiProviderFallbackChain": env("aiProviderFallbackChain", default=""),
}

# ---------------------------------------------------------------------------
# AI EMBEDDING FOUNDATION (Phase 13-Q)
# ---------------------------------------------------------------------------
# Configuration-driven embedding defaults (Master Specification §42): the
# fail-closed switch, provider batch and input ceilings, the default vector
# space geometry applied when a space is registered without one, the
# fingerprint cache switch, the brute-force candidate scan ceiling, and the
# vector retention horizon. Camel-case env names per ADR-001/ADR-009.
AI_EMBEDDING_ENABLED = env.bool("aiEmbeddingEnabled", default=True)
AI_EMBEDDING_MAX_BATCH_SIZE = int(env("aiEmbeddingMaxBatchSize", default="32") or 32)
AI_EMBEDDING_MAX_INPUT_TOKENS = int(env("aiEmbeddingMaxInputTokens", default="8192") or 8192)
AI_EMBEDDING_DEFAULT_METRIC = str(
    env("aiEmbeddingDefaultMetric", default="COSINE") or "COSINE"
).upper()
AI_EMBEDDING_DEFAULT_NORMALIZATION = str(
    env("aiEmbeddingDefaultNormalization", default="L2") or "L2"
).upper()
AI_EMBEDDING_CACHE_ENABLED = env.bool("aiEmbeddingCacheEnabled", default=True)
AI_EMBEDDING_SEARCH_CANDIDATE_LIMIT = int(
    env("aiEmbeddingSearchCandidateLimit", default="1000") or 1000
)
AI_EMBEDDING_RETENTION_DAYS = int(env("aiEmbeddingRetentionDays", default="365") or 365)

# ---------------------------------------------------------------------------
# AI KNOWLEDGE PLATFORM (Phase 13-R)
# ---------------------------------------------------------------------------
# Configuration-driven ingestion defaults (Master Specification §42): the
# fail-closed switch, the default chunking policy (strategy, budget,
# overlap, minimum tail), whether new chunks are embedded automatically
# through Phase 13-Q, the embed batch size, the per-source chunk ceiling,
# and the retention horizon for archived sources.
# Camel-case env names per ADR-001/ADR-009.
AI_KNOWLEDGE_ENABLED = env.bool("aiKnowledgeEnabled", default=True)
AI_KNOWLEDGE_CHUNK_STRATEGY = str(
    env("aiKnowledgeChunkStrategy", default="PARAGRAPH") or "PARAGRAPH"
).upper()
AI_KNOWLEDGE_CHUNK_TOKENS = int(env("aiKnowledgeChunkTokens", default="512") or 512)
AI_KNOWLEDGE_CHUNK_OVERLAP_TOKENS = int(env("aiKnowledgeChunkOverlapTokens", default="64") or 64)
AI_KNOWLEDGE_MIN_CHUNK_TOKENS = int(env("aiKnowledgeMinChunkTokens", default="32") or 32)
AI_KNOWLEDGE_AUTO_EMBED = env.bool("aiKnowledgeAutoEmbed", default=True)
AI_KNOWLEDGE_EMBED_BATCH_SIZE = int(env("aiKnowledgeEmbedBatchSize", default="32") or 32)
AI_KNOWLEDGE_MAX_CHUNKS_PER_SOURCE = int(env("aiKnowledgeMaxChunksPerSource", default="500") or 500)
AI_KNOWLEDGE_RETENTION_DAYS = int(env("aiKnowledgeRetentionDays", default="730") or 730)

# ---------------------------------------------------------------------------
# AI RETRIEVAL, RAG & RERANKING (Phase 13-S)
# ---------------------------------------------------------------------------
# Configuration-driven read defaults (Master Specification §42): the
# fail-closed switch, the candidate strategy and its ceilings, the rerank
# strategy and its weights, the context budget, and the grounding rule that
# decides whether an answer may be produced without authorized evidence.
# An empty aiRetrievalMinScore means "no floor".
# Camel-case env names per ADR-001/ADR-009.
AI_RETRIEVAL_ENABLED = env.bool("aiRetrievalEnabled", default=True)
AI_RETRIEVAL_STRATEGY = str(env("aiRetrievalStrategy", default="HYBRID") or "HYBRID").upper()
AI_RETRIEVAL_TOP_K = int(env("aiRetrievalTopK", default="5") or 5)
AI_RETRIEVAL_CANDIDATE_LIMIT = int(env("aiRetrievalCandidateLimit", default="200") or 200)
AI_RETRIEVAL_MIN_SCORE = str(env("aiRetrievalMinScore", default="") or "")
AI_RETRIEVAL_RERANK = str(
    env("aiRetrievalRerank", default="LEXICAL_BOOST") or "LEXICAL_BOOST"
).upper()
AI_RETRIEVAL_LEXICAL_WEIGHT = float(env("aiRetrievalLexicalWeight", default="0.3") or 0.3)
AI_RETRIEVAL_MMR_LAMBDA = float(env("aiRetrievalMmrLambda", default="0.7") or 0.7)
AI_RETRIEVAL_MAX_CONTEXT_TOKENS = int(env("aiRetrievalMaxContextTokens", default="4000") or 4000)
AI_RETRIEVAL_MAX_CONTEXT_SOURCES = int(env("aiRetrievalMaxContextSources", default="10") or 10)
AI_RETRIEVAL_LEXICAL_SCAN_LIMIT = int(env("aiRetrievalLexicalScanLimit", default="500") or 500)
AI_RAG_REQUIRE_GROUNDING = env.bool("aiRagRequireGrounding", default=True)
AI_RAG_ANSWER_MODEL = str(env("aiRagAnswerModel", default="") or "")

# ---------------------------------------------------------------------------
# AI MEMORY (Phase 13-T)
# ---------------------------------------------------------------------------
# Configuration-driven memory ceilings (Master Specification §42) — this
# block closes Open Question #8 from Phase 13-A: nothing is unbounded.
# Per-scope platform defaults apply unless aiMemoryUseScopeDefaults is
# false; configuration may only narrow them, never widen them. A zero TTL
# means "no expiry for scopes that do not define one".
AI_MEMORY_ENABLED = env.bool("aiMemoryEnabled", default=True)
AI_MEMORY_MAX_ENTRIES_PER_SCOPE = int(env("aiMemoryMaxEntriesPerScope", default="200") or 200)
AI_MEMORY_DEFAULT_TTL_SECONDS = int(env("aiMemoryDefaultTtlSeconds", default="0") or 0)
AI_MEMORY_MAX_VALUE_BYTES = int(env("aiMemoryMaxValueBytes", default="32768") or 32768)
AI_MEMORY_EVICTION = str(env("aiMemoryEviction", default="OLDEST_FIRST") or "OLDEST_FIRST").upper()
AI_MEMORY_CONTEXT_MAX_ENTRIES = int(env("aiMemoryContextMaxEntries", default="10") or 10)
AI_MEMORY_CONTEXT_MAX_TOKENS = int(env("aiMemoryContextMaxTokens", default="1000") or 1000)
AI_MEMORY_RETENTION_DAYS = int(env("aiMemoryRetentionDays", default="365") or 365)
AI_MEMORY_USE_SCOPE_DEFAULTS = env.bool("aiMemoryUseScopeDefaults", default=True)

# ---------------------------------------------------------------------------
# AI EVALUATION (Phase 13-U)
# ---------------------------------------------------------------------------
# Configuration-driven acceptance criteria (Master Specification §42) —
# this block closes Open Question #9 from Phase 13-A: what counts as an
# acceptable AI answer is data, not folklore. Groundedness and safety stay
# mandatory metrics; configuration tunes their bands and the run-level
# limits. aiEvaluationForbiddenTerms is a comma-separated deny list applied
# to every suite on top of each case's own list.
AI_EVALUATION_ENABLED = env.bool("aiEvaluationEnabled", default=True)
AI_EVALUATION_MIN_OVERALL_SCORE = float(env("aiEvaluationMinOverallScore", default="0.7") or 0.7)
AI_EVALUATION_MAX_FAILED_CASES = int(env("aiEvaluationMaxFailedCases", default="0") or 0)
AI_EVALUATION_MAX_WARN_RATIO = float(env("aiEvaluationMaxWarnRatio", default="0.3") or 0.3)
AI_EVALUATION_REGRESSION_TOLERANCE = float(
    env("aiEvaluationRegressionTolerance", default="0.02") or 0.02
)
AI_EVALUATION_GROUNDEDNESS_FAIL_BELOW = float(
    env("aiEvaluationGroundednessFailBelow", default="0.5") or 0.5
)
AI_EVALUATION_GROUNDEDNESS_WARN_BELOW = float(
    env("aiEvaluationGroundednessWarnBelow", default="0.75") or 0.75
)
AI_EVALUATION_MAX_CASES_PER_RUN = int(env("aiEvaluationMaxCasesPerRun", default="200") or 200)
AI_EVALUATION_RETENTION_DAYS = int(env("aiEvaluationRetentionDays", default="365") or 365)
AI_EVALUATION_FORBIDDEN_TERMS = str(env("aiEvaluationForbiddenTerms", default="") or "")

# ---------------------------------------------------------------------------
# AI FEEDBACK (Phase 13-V)
# ---------------------------------------------------------------------------
# Configuration-driven feedback policy (Master Specification §42): when a
# complaint becomes a Phase 13-U golden case, what counts as a negative
# rating, the satisfaction bar, and the trend window. Promotion is manual
# by default: turning a complaint into a permanent quality gate is a
# decision, and aiFeedbackAutoPromote must be set deliberately.
AI_FEEDBACK_ENABLED = env.bool("aiFeedbackEnabled", default=True)
AI_FEEDBACK_PROMOTION_THRESHOLD = int(env("aiFeedbackPromotionThreshold", default="2") or 2)
AI_FEEDBACK_REQUIRE_CORRECTION = env.bool("aiFeedbackRequireCorrection", default=True)
AI_FEEDBACK_REQUIRE_REASON = env.bool("aiFeedbackRequireReason", default=True)
AI_FEEDBACK_NEGATIVE_RATING_CEILING = int(env("aiFeedbackNegativeRatingCeiling", default="2") or 2)
AI_FEEDBACK_MIN_SATISFACTION = float(env("aiFeedbackMinSatisfaction", default="0.6") or 0.6)
AI_FEEDBACK_TREND_TOLERANCE = float(env("aiFeedbackTrendTolerance", default="0.05") or 0.05)
AI_FEEDBACK_TREND_WINDOW_DAYS = int(env("aiFeedbackTrendWindowDays", default="7") or 7)
AI_FEEDBACK_AUTO_PROMOTE = env.bool("aiFeedbackAutoPromote", default=False)
AI_FEEDBACK_GOLDEN_SUITE = str(
    env("aiFeedbackGoldenSuite", default="FEEDBACK_GOLDEN") or "FEEDBACK_GOLDEN"
).upper()
AI_FEEDBACK_RETENTION_DAYS = int(env("aiFeedbackRetentionDays", default="730") or 730)

# ---------------------------------------------------------------------------
# AI OBSERVABILITY & ALERTING (Phase 13-W)
# ---------------------------------------------------------------------------
# Configuration-driven monitoring defaults (Master Specification §42 and
# §34): the collection window, the alert thresholds for the four failures
# that actually hurt, and the retention of snapshots and alerts. Metric
# labels are allow-listed in code, not here: they leave the tenant
# boundary and must never carry free-form text (§47).
AI_OBSERVABILITY_ENABLED = env.bool("aiObservabilityEnabled", default=True)
AI_OBSERVABILITY_WINDOW_MINUTES = int(env("aiObservabilityWindowMinutes", default="60") or 60)
AI_OBSERVABILITY_MAX_WINDOW_HOURS = int(env("aiObservabilityMaxWindowHours", default="24") or 24)
AI_OBSERVABILITY_SNAPSHOT_RETENTION_DAYS = int(
    env("aiObservabilitySnapshotRetentionDays", default="90") or 90
)
AI_OBSERVABILITY_ALERT_RETENTION_DAYS = int(
    env("aiObservabilityAlertRetentionDays", default="365") or 365
)
AI_ALERTING_ENABLED = env.bool("aiAlertingEnabled", default=True)
AI_ALERT_ERROR_RATIO = float(env("aiAlertErrorRatio", default="0.1") or 0.1)
AI_ALERT_LATENCY_P95_MS = int(env("aiAlertLatencyP95Ms", default="15000") or 15000)
AI_ALERT_QUEUE_DEPTH = int(env("aiAlertQueueDepth", default="100") or 100)
AI_ALERT_FEEDBACK_SCORE = float(env("aiAlertFeedbackScore", default="0.5") or 0.5)
AI_ALERT_EVALUATION_SCORE = float(env("aiAlertEvaluationScore", default="0.6") or 0.6)

# ---------------------------------------------------------------------------
# AI TOOL REGISTRY & EXECUTION (Phase 13-X)
# ---------------------------------------------------------------------------
# Configuration-driven tool policy (Master Specification §30 and §42) —
# this block closes Open Question #10: which risk level needs a human, and
# which needs two. A tool may declare a stricter approval mode than these
# thresholds require; it can never declare a looser one.
AI_TOOL_ENABLED = env.bool("aiToolEnabled", default=True)
AI_TOOL_AUTOMATIC_BELOW_RISK = str(
    env("aiToolAutomaticBelowRisk", default="HIGH") or "HIGH"
).upper()
AI_TOOL_DUAL_CONTROL_AT_RISK = str(
    env("aiToolDualControlAtRisk", default="CRITICAL") or "CRITICAL"
).upper()
AI_TOOL_MAX_CALLS_PER_REQUEST = int(env("aiToolMaxCallsPerRequest", default="10") or 10)
AI_TOOL_MAX_REPEATS_PER_REQUEST = int(env("aiToolMaxRepeatsPerRequest", default="2") or 2)
AI_TOOL_TIMEOUT_SECONDS = int(env("aiToolTimeoutSeconds", default="30") or 30)
AI_TOOL_MAX_ARGUMENT_BYTES = int(env("aiToolMaxArgumentBytes", default="16384") or 16384)
AI_TOOL_APPROVAL_TTL_SECONDS = int(env("aiToolApprovalTtlSeconds", default="3600") or 3600)
AI_TOOL_RETENTION_DAYS = int(env("aiToolRetentionDays", default="365") or 365)

# ---------------------------------------------------------------------------
# Configuration-driven agent policy (Master Specification §31 and §42) —
# this block closes Open Question #11: the agent's access level is
# structural (its versioned definition), and these thresholds decide which
# risk level needs a human, and which needs two, before a run may start.
# An agent may declare a stricter approval mode than these thresholds
# require; it can never declare a looser one.
AI_AGENT_ENABLED = env.bool("aiAgentEnabled", default=True)
AI_AGENT_AUTOMATIC_BELOW_RISK = str(
    env("aiAgentAutomaticBelowRisk", default="HIGH") or "HIGH"
).upper()
AI_AGENT_DUAL_CONTROL_AT_RISK = str(
    env("aiAgentDualControlAtRisk", default="CRITICAL") or "CRITICAL"
).upper()
AI_AGENT_MAX_STEPS_PER_RUN = int(env("aiAgentMaxStepsPerRun", default="10") or 10)
AI_AGENT_MAX_TOOL_CALLS_PER_RUN = int(env("aiAgentMaxToolCallsPerRun", default="20") or 20)
AI_AGENT_MAX_REPEATS_PER_RUN = int(env("aiAgentMaxRepeatsPerRun", default="2") or 2)
AI_AGENT_MAX_DURATION_SECONDS = int(env("aiAgentMaxDurationSeconds", default="120") or 120)
AI_AGENT_MAX_CONTEXT_TOKENS = int(env("aiAgentMaxContextTokens", default="16000") or 16_000)
AI_AGENT_MAX_INSTRUCTIONS_BYTES = int(env("aiAgentMaxInstructionsBytes", default="16384") or 16_384)
AI_AGENT_MAX_INPUT_BYTES = int(env("aiAgentMaxInputBytes", default="65536") or 65_536)
AI_AGENT_APPROVAL_TTL_SECONDS = int(env("aiAgentApprovalTtlSeconds", default="3600") or 3600)
AI_AGENT_RETENTION_DAYS = int(env("aiAgentRetentionDays", default="365") or 365)

# Phase 14 — attachment intake and physical communication retention are
# operational policy, not domain constants.
COMMUNICATION_MAX_ATTACHMENT_BYTES = int(
    env("communicationMaxAttachmentBytes", default=str(25 * 1024 * 1024)) or 25 * 1024 * 1024
)
COMMUNICATION_ALLOWED_ATTACHMENT_TYPES = tuple(
    env.list(
        "communicationAllowedAttachmentTypes",
        default=[
            "application/pdf",
            "image/jpeg",
            "image/png",
            "text/plain",
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        ],
    )
)
COMMUNICATION_REQUIRE_CLEAN_SCAN = env.bool("communicationRequireCleanScan", default=True)
COMMUNICATION_RETENTION_DAYS = int(env("communicationRetentionDays", default="2555") or 2555)

# Phase 15 — durable notification jobs, callback replay protection and cleanup.
NOTIFICATION_RETENTION_DAYS = int(env("notificationRetentionDays", default="365") or 365)
NOTIFICATION_WEBHOOK_TOLERANCE_SECONDS = int(
    env("notificationWebhookToleranceSeconds", default="300") or 300
)
# Provider secrets are injected by deployment/secret-manager integrations.
# Keys may be PROVIDER or "<tenant UUID>:PROVIDER"; values are never returned.
NOTIFICATION_WEBHOOK_SECRETS: dict[str, str] = env.json("notificationWebhookSecrets", default={})
CELERY_BROKER_URL = env("notificationCeleryBrokerUrl", default="redis://127.0.0.1:6379/2")
CELERY_RESULT_BACKEND = env("notificationCeleryResultBackend", default="redis://127.0.0.1:6379/3")
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_ACKS_LATE = True
CELERY_TASK_REJECT_ON_WORKER_LOST = True
CELERY_WORKER_PREFETCH_MULTIPLIER = 1
CELERY_TASK_ROUTES = {
    "notifications.dispatch": {"queue": "notifications.normal"},
    "notifications.workerTick": {"queue": "notifications.maintenance"},
    "learning.processJob": {"queue": "learning.training"},
    "learning.monitorDeployments": {"queue": "learning.monitoring"},
    "projectIntelligence.processJob": {"queue": "project-intelligence.analysis"},
}
CELERY_BEAT_SCHEDULE = {
    "notification-worker-tick": {
        "task": "notifications.workerTick",
        "schedule": 10.0,
        "args": (200,),
    },
    "learning-monitor-heartbeat": {
        "task": "learning.monitorDeployments",
        "schedule": 60.0,
    },
}

LEARNING_ARTIFACT_ROOT = BASE_DIR / "var" / "learningArtifacts"
LEARNING_ENGINE_IMPL = (
    "apps.learning.infrastructure.learning.deterministicEngine.DeterministicLearningEngine"
)
LEARNING_EVALUATION_IMPL = (
    "apps.learning.infrastructure.evaluation.deterministicEvaluation.DeterministicEvaluationEngine"
)
LEARNING_QUEUE_IMPL = "apps.learning.infrastructure.queue.learningQueue.CeleryLearningJobQueue"

PROJECT_INTELLIGENCE_WORKSPACE_ROOT = Path(
    env("projectIntelligenceWorkspaceRoot", default=str(BASE_DIR.parent))
).resolve()
PROJECT_INTELLIGENCE_ARTIFACT_ROOT = BASE_DIR / "var" / "projectIntelligenceArtifacts"
PROJECT_INTELLIGENCE_MAX_FILES = int(env("projectIntelligenceMaxFiles", default="50000") or 50000)
PROJECT_INTELLIGENCE_MAX_FILE_BYTES = int(
    env("projectIntelligenceMaxFileBytes", default="2000000") or 2000000
)
PROJECT_INTELLIGENCE_CACHE_TTL_SECONDS = int(
    env("projectIntelligenceCacheTtlSeconds", default="86400") or 86400
)

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
    "learning": "apps.learning.infrastructure.migrations",
    "projectIntelligence": "apps.projectIntelligence.infrastructure.migrations",
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
