from __future__ import annotations

import os
from pathlib import Path

from decouple import config

BASE_DIR = Path(__file__).resolve().parent.parent.parent

SECRET_KEY = os.environ.get("DJANGO_SECRET_KEY", "insecure-dev-key-change-in-production")

DEBUG = False

ALLOWED_HOSTS: list[str] = []

# Custom user model — email-only auth, UUID pk, role-based RBAC.
# This replaces Django's default auth.User and activates the model defined
# in apps/accounts/models.py. Must be set before the first makemigrations run.
AUTH_USER_MODEL: str = "accounts.User"

# ---------------------------------------------------------------------------
# Installed applications
# ---------------------------------------------------------------------------
DJANGO_APPS: list[str] = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    # Third-party
    "rest_framework",
    "django_celery_beat",
    "django_celery_results",
    # Project apps
    "apps.common",
    "apps.eventbus",
    "apps.accounts",
]

# Populated progressively as app modules are scaffolded in Batches 4-8.
# Each batch patches this list via str_replace without regenerating this file.
# Remediation R1.a — every implemented app under apps/ with real models or views.
# Order matters: common first (provides BaseModel used by other apps),
# accounts second (provides AUTH_USER_MODEL), health last (no models).
LOCAL_APPS: list[str] = [
    "apps.common",
    "apps.accounts",
    "apps.health",
]

THIRD_PARTY_APPS = []

INSTALLED_APPS: list[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE: list[str] = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "apps.common.infrastructure.middleware.CorrelationIdMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.debug",
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"
ASGI_APPLICATION = "config.asgi.application"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "tradevision_db"),
        "USER": os.environ.get("POSTGRES_USER", "tradevision"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
        "ATOMIC_REQUESTS": True,
    }
}

import dj_database_url  # noqa: E402
db_url = os.environ.get("DATABASE_URL")
if db_url:
    DATABASES["default"] = dj_database_url.parse(db_url, conn_max_age=600)

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": os.environ.get("REDIS_CACHE_URL", "redis://localhost:6379/3"),
    }
}

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "en-us"
TIME_ZONE = "Asia/Kolkata"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

REST_FRAMEWORK = {
    "DEFAULT_RENDERER_CLASSES": ("rest_framework.renderers.JSONRenderer",),
    "DEFAULT_AUTHENTICATION_CLASSES": [],
    "DEFAULT_PARSER_CLASSES": ("rest_framework.parsers.JSONParser",),
    "DEFAULT_PERMISSION_CLASSES": ("rest_framework.permissions.IsAuthenticated",),
    "EXCEPTION_HANDLER": "apps.common.infrastructure.drf_exception_handler.custom_exception_handler",
    "DEFAULT_PAGINATION_CLASS": "rest_framework.pagination.PageNumberPagination",
    "PAGE_SIZE": 20,
}

from datetime import timedelta  # noqa: E402

SIMPLE_JWT = {
    "ACCESS_TOKEN_LIFETIME": timedelta(minutes=int(os.environ.get("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", "15"))),
    "REFRESH_TOKEN_LIFETIME": timedelta(days=int(os.environ.get("JWT_REFRESH_TOKEN_LIFETIME_DAYS", "7"))),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "ALGORITHM": os.environ.get("JWT_ALGORITHM", "HS256"),
    "SIGNING_KEY": os.environ.get("JWT_SECRET_KEY", SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

CELERY_APP = "config.celery"
CELERY_BROKER_URL = os.environ.get("CELERY_BROKER_URL", "redis://localhost:6379/0")
CELERY_RESULT_BACKEND = os.environ.get("CELERY_RESULT_BACKEND", "redis://localhost:6379/0")
CELERY_ACCEPT_CONTENT = ["json"]
CELERY_TASK_SERIALIZER = "json"
CELERY_RESULT_SERIALIZER = "json"
CELERY_TIMEZONE = "Asia/Kolkata"
CELERY_TASK_TRACK_STARTED = True
CELERY_TASK_TIME_LIMIT = 60
CELERY_TASK_SOFT_TIME_LIMIT = 30
CELERY_BEAT_SCHEDULER = "django_celery_beat.schedulers:DatabaseScheduler"

CELERY_TASK_ROUTES = {
    "apps.eventbus.infrastructure.tasks.dispatch_event_to_handler": {"queue": "maintenance"},
    "apps.eventbus.infrastructure.tasks.poll_event_streams": {"queue": "maintenance"},
    "apps.eventbus.infrastructure.tasks.replay_unpublished_events": {"queue": "maintenance"},
    "apps.accounts.infrastructure.tasks.purge_expired_tokens": {"queue": "maintenance"},
}

CELERY_TASK_QUEUES = [
    "webhooks",
    "signals",
    "analysis",
    "ai_reasoning",
    "decisions",
    "execution",
    "monitoring",
    "portfolio",
    "analytics",
    "notifications",
    "maintenance",
]

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "filters": {
        "correlation_id": {
            "()": "apps.common.infrastructure.logging_context.CorrelationIdFilter",
        },
    },
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s %(correlation_id)s",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "filters": ["correlation_id"],
        },
    },
    "root": {
        "handlers": ["console"],
        "level": os.environ.get("LOG_LEVEL", "INFO"),
    },
}

FIELD_ENCRYPTION_KEY = os.environ.get("FIELD_ENCRYPTION_KEY", "")

EVENT_BUS_IMPLEMENTATION = os.environ.get("EVENT_BUS_IMPLEMENTATION", "redis")
# ---------------------------------------------------------------------------
# Market calendar
# ---------------------------------------------------------------------------
MARKET_TIMEZONE: str = config("MARKET_TIMEZONE", default="Asia/Kolkata")
MARKET_EXCHANGE: str = config("MARKET_EXCHANGE", default="NSE")

# ---------------------------------------------------------------------------
# Data quality thresholds (seconds)
# ---------------------------------------------------------------------------
TICK_FRESHNESS_THRESHOLD_SECONDS: int = config(
    "TICK_FRESHNESS_THRESHOLD_SECONDS", default=120, cast=int
)
INDICATOR_FRESHNESS_THRESHOLD_SECONDS: int = config(
    "INDICATOR_FRESHNESS_THRESHOLD_SECONDS", default=300, cast=int
)
INTELLIGENCE_MIN_QUALITY_SCORE: float = config(
    "INTELLIGENCE_MIN_QUALITY_SCORE", default=0.60, cast=float
)

# ---------------------------------------------------------------------------
# AI governance
# ---------------------------------------------------------------------------
AI_PROVIDER: str = config("AI_PROVIDER", default="gemini")
AI_CONFIDENCE_FLOOR: float = config("AI_CONFIDENCE_FLOOR", default=0.55, cast=float)
AI_DAILY_BUDGET_USD: float = config("AI_DAILY_BUDGET_USD", default=10.00, cast=float)
AI_DEDUP_WINDOW_SECONDS: int = config("AI_DEDUP_WINDOW_SECONDS", default=300, cast=int)
AI_MAX_TOKENS: int = config("AI_MAX_TOKENS", default=4096, cast=int)

GEMINI_API_KEY: str = config("GEMINI_API_KEY", default="")
GEMINI_MODEL: str = config("GEMINI_MODEL", default="gemini-1.5-pro")

OPENAI_API_KEY: str = config("OPENAI_API_KEY", default="")
OPENAI_MODEL: str = config("OPENAI_MODEL", default="gpt-4o")

ANTHROPIC_API_KEY: str = config("ANTHROPIC_API_KEY", default="")
ANTHROPIC_MODEL: str = config("ANTHROPIC_MODEL", default="claude-3-5-sonnet-20241022")

OLLAMA_BASE_URL: str = config("OLLAMA_BASE_URL", default="http://localhost:11434")
OLLAMA_MODEL: str = config("OLLAMA_MODEL", default="llama3.2")

# ---------------------------------------------------------------------------
# Circuit breaker defaults
# ---------------------------------------------------------------------------
CIRCUIT_BREAKER_FAILURE_THRESHOLD: int = config(
    "CIRCUIT_BREAKER_FAILURE_THRESHOLD", default=5, cast=int
)
CIRCUIT_BREAKER_RECOVERY_TIMEOUT: int = config(
    "CIRCUIT_BREAKER_RECOVERY_TIMEOUT", default=60, cast=int
)

# ---------------------------------------------------------------------------
# Redis direct URL — for use outside the Django cache framework
# ---------------------------------------------------------------------------
REDIS_URL: str = config("REDIS_URL", default="redis://redis:6379/0")
REDIS_MAX_CONNECTIONS: int = config("REDIS_MAX_CONNECTIONS", default=50, cast=int)

# ---------------------------------------------------------------------------
# EventBus — Redis Streams (AnalysisEvent transport)
# ---------------------------------------------------------------------------
EVENT_STREAM_MAXLEN: int = config("EVENT_STREAM_MAXLEN", default=10000, cast=int)
EVENT_STREAM_CONSUMER_GROUP_PREFIX: str = config(
    "EVENT_STREAM_CONSUMER_GROUP_PREFIX", default="tradevision"
)

# ---------------------------------------------------------------------------
# Market data provider
# ---------------------------------------------------------------------------
MARKET_DATA_PROVIDER: str = config("MARKET_DATA_PROVIDER", default="mock")
