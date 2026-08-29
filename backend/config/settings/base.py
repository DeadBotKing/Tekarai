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
# APPLICATIONS (Phase 01 — framework foundation only, no business apps)
# ---------------------------------------------------------------------------
INSTALLED_APPS = [
    "django.contrib.contenttypes",
    "django.contrib.auth",
    "rest_framework",
    "corsheaders",
]

MIDDLEWARE = [
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
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
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "standard",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
}

# ---------------------------------------------------------------------------
# GUARDS
# ---------------------------------------------------------------------------
if environment not in {"development", "testing", "production"}:
    raise ImproperlyConfigured(
        f"Configuration value 'environment' must be one of "
        f"development|testing|production. Got '{environment}'."
    )
