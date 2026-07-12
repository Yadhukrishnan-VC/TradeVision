"""
TradeVision AI — Base Django settings.

All environment-sensitive values are read via python-decouple.
This module must never be used as DJANGO_SETTINGS_MODULE directly;
use environment-specific overrides: development | production | testing.
"""

from datetime import timedelta
from pathlib import Path

from decouple import Csv, config

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
APPS_DIR: Path = BASE_DIR / "apps"

# ---------------------------------------------------------------------------
# Core Django
# ---------------------------------------------------------------------------
SECRET_KEY: str = config("DJANGO_SECRET_KEY")
DEBUG: bool = config("DJANGO_DEBUG", default=False, cast=bool)
ALLOWED_HOSTS: list[str] = config(
    "DJANGO_ALLOWED_HOSTS",
    default="localhost,127.0.0.1,backend",
    cast=Csv(),
)

ROOT_URLCONF: str = "config.urls"
WSGI_APPLICATION: str = "config.wsgi.application"
ASGI_APPLICATION: str = "config.asgi.application"

# All domain models inherit from apps.common.models.BaseModel, which defines a
# UUIDField primary key. BigAutoField is the fallback only for third-party apps.
DEFAULT_AUTO_FIELD: str = "django.db.models.BigAutoField"

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
]

THIRD_PARTY_APPS: list[str] = [
    "rest_framework",
    "rest_framework_simplejwt",
    "rest_framework_simplejwt.token_blacklist",
    "corsheaders",
    "channels",
    "django_filters",
    "django_celery_beat",
    "django_celery_results",
    "django_prometheus",
]

# Populated progressively as app modules are scaffolded in Batches 4-8.
# Each batch patches this list via str_replace without regenerating this file.
LOCAL_APPS: list[str] = []

INSTALLED_APPS: list[str] = DJANGO_APPS + THIRD_PARTY_APPS + LOCAL_APPS

# ---------------------------------------------------------------------------
# Middleware
# ---------------------------------------------------------------------------
MIDDLEWARE: list[str] = [
    "django_prometheus.middleware.PrometheusBeforeMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "corsheaders.middleware.CorsMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "core.middleware.CorrelationIDMiddleware",
    "core.middleware.RequestLoggingMiddleware",
    "django_prometheus.middleware.PrometheusAfterMiddleware",
]

# ---------------------------------------------------------------------------
# Templates
# ---------------------------------------------------------------------------
TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [BASE_DIR / "templates"],
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

# ---------------------------------------------------------------------------
# Database
# Application connects through pgbouncer (transaction pool mode).
# CONN_MAX_AGE must be 0 in transaction pool mode — persistent connections
# are managed by pgbouncer, not Django.
# ---------------------------------------------------------------------------
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": config("POSTGRES_DB"),
        "USER": config("POSTGRES_USER"),
        "PASSWORD": config("POSTGRES_PASSWORD"),
        "HOST": config("POSTGRES_HOST", default="pgbouncer"),
        "PORT": config("POSTGRES_PORT", default="6432", cast=int),
        "CONN_MAX_AGE": 0,
        "OPTIONS": {
            "connect_timeout": 10,
            "options": "-c statement_timeout=30000",
        },
        "TEST": {
            "NAME": config("POSTGRES_TEST_DB", default="tradevision_test"),
        },
    }
}

# ---------------------------------------------------------------------------
# Cache — Redis with index isolation per purpose
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.redis.RedisCache",
        "LOCATION": config("REDIS_CACHE_URL", default="redis://redis:6379/1"),
        "KEY_PREFIX": "tv",
        "TIMEOUT": 300,
    }
}

# ---------------------------------------------------------------------------
# Django Channels — ASGI WebSocket layer
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels_redis.core.RedisChannelLayer",
        "CONFIG": {
            "hosts": [config("REDIS_CHANNELS_URL", default="redis://redis:6379/2")],
            "capacity": 1500,
            "expiry": 10,
        },
    }
}

# ---------------------------------------------------------------------------
# Celery — task queue configuration
# Named queues are declared in config/celery.py alongside the Celery app.
# ---------------------------------------------------------------------------
CELERY_BROKER_URL: str = config("CELERY_BROKER_URL", default="redis://redis:6379/0")
CELERY_RESULT_BACKEND: str = config("CELERY_RESULT_BACKEND", default="redis://redis:6379/0")
CELERY_ACCEPT_CONTENT: list[str] = ["json"]
CELERY_TASK_SERIALIZER: str = "json"
CELERY_RESULT_SERIALIZER: str = "json"
CELERY_TIMEZONE: str = "Asia/Kolkata"
CELERY_ENABLE_UTC: bool = True
CELERY_TASK_TRACK_STARTED: bool = True
CELERY_TASK_ACKS_LATE: bool = True
CELERY_WORKER_PREFETCH_MULTIPLIER: int = 1
CELERY_RESULT_EXPIRES: int = 3600
CELERY_BEAT_SCHEDULER: str = "django_celery_beat.schedulers:DatabaseScheduler"

# ---------------------------------------------------------------------------
# Django REST Framework
# ---------------------------------------------------------------------------
REST_FRAMEWORK: dict = {
    "DEFAULT_AUTHENTICATION_CLASSES": [
        "rest_framework_simplejwt.authentication.JWTAuthentication",
    ],
    "DEFAULT_PERMISSION_CLASSES": [
        "rest_framework.permissions.IsAuthenticated",
    ],
    "DEFAULT_PAGINATION_CLASS": "core.pagination.StandardResultsPagination",
    "PAGE_SIZE": 20,
    "DEFAULT_FILTER_BACKENDS": [
        "django_filters.rest_framework.DjangoFilterBackend",
        "rest_framework.filters.SearchFilter",
        "rest_framework.filters.OrderingFilter",
    ],
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
    ],
    "DEFAULT_THROTTLE_CLASSES": [
        "rest_framework.throttling.AnonRateThrottle",
        "rest_framework.throttling.UserRateThrottle",
    ],
    "DEFAULT_THROTTLE_RATES": {
        "anon": "60/minute",
        "user": "600/minute",
    },
    "EXCEPTION_HANDLER": "core.exceptions.custom_exception_handler",
}

# ---------------------------------------------------------------------------
# Simple JWT — short-lived access tokens, rotating refresh tokens
# ---------------------------------------------------------------------------
SIMPLE_JWT: dict = {
    "ACCESS_TOKEN_LIFETIME": timedelta(
        minutes=config("JWT_ACCESS_TOKEN_LIFETIME_MINUTES", default=15, cast=int)
    ),
    "REFRESH_TOKEN_LIFETIME": timedelta(
        days=config("JWT_REFRESH_TOKEN_LIFETIME_DAYS", default=7, cast=int)
    ),
    "ROTATE_REFRESH_TOKENS": True,
    "BLACKLIST_AFTER_ROTATION": True,
    "UPDATE_LAST_LOGIN": True,
    "ALGORITHM": config("JWT_ALGORITHM", default="HS256"),
    "SIGNING_KEY": config("JWT_SECRET_KEY", default=SECRET_KEY),
    "AUTH_HEADER_TYPES": ("Bearer",),
    "AUTH_HEADER_NAME": "HTTP_AUTHORIZATION",
    "USER_ID_FIELD": "id",
    "USER_ID_CLAIM": "user_id",
}

# ---------------------------------------------------------------------------
# CORS
# ---------------------------------------------------------------------------
CORS_ALLOWED_ORIGINS: list[str] = config(
    "CORS_ALLOWED_ORIGINS",
    default="http://localhost,http://localhost:5173",
    cast=Csv(),
)
CORS_ALLOW_CREDENTIALS: bool = True

# ---------------------------------------------------------------------------
# Internationalisation and timezone
# USE_TZ must remain True. All datetimes are UTC-stored, IST-displayed.
# ---------------------------------------------------------------------------
LANGUAGE_CODE: str = "en-us"
TIME_ZONE: str = "Asia/Kolkata"
USE_I18N: bool = True
USE_TZ: bool = True

# ---------------------------------------------------------------------------
# Static and media files
# ---------------------------------------------------------------------------
STATIC_URL: str = "/static/"
STATIC_ROOT: Path = BASE_DIR / "staticfiles"
MEDIA_URL: str = "/media/"
MEDIA_ROOT: Path = BASE_DIR / "mediafiles"

# ---------------------------------------------------------------------------
# Security — baseline values; hardened further in production.py
# ---------------------------------------------------------------------------
SESSION_COOKIE_HTTPONLY: bool = True
SESSION_COOKIE_SAMESITE: str = "Lax"
CSRF_COOKIE_HTTPONLY: bool = True
X_FRAME_OPTIONS: str = "DENY"

AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator"},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

# ---------------------------------------------------------------------------
# Logging — structured JSON via python-json-logger.
# structlog is configured separately in core.logging and initialised by
# apps.common.apps.CommonConfig.ready() once apps are scaffolded.
# ---------------------------------------------------------------------------
LOG_LEVEL: str = config("LOG_LEVEL", default="INFO")

LOGGING: dict = {
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "()": "pythonjsonlogger.jsonlogger.JsonFormatter",
            "fmt": "%(asctime)s %(name)s %(levelname)s %(message)s",
            "datefmt": "%Y-%m-%dT%H:%M:%SZ",
        },
    },
    "handlers": {
        "console": {
            "class": "logging.StreamHandler",
            "formatter": "json",
            "stream": "ext://sys.stdout",
        },
    },
    "root": {
        "handlers": ["console"],
        "level": LOG_LEVEL,
    },
    "loggers": {
        "django": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "django.db.backends": {"handlers": ["console"], "level": "WARNING", "propagate": False},
        "celery": {"handlers": ["console"], "level": "INFO", "propagate": False},
        "channels": {"handlers": ["console"], "level": "WARNING", "propagate": False},
    },
}

# ---------------------------------------------------------------------------
# Prometheus
# ---------------------------------------------------------------------------
PROMETHEUS_METRICS_ENABLED: bool = config(
    "PROMETHEUS_METRICS_ENABLED", default=True, cast=bool
)

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

# ---------------------------------------------------------------------------
# Market data provider
# ---------------------------------------------------------------------------
MARKET_DATA_PROVIDER: str = config("MARKET_DATA_PROVIDER", default="mock")
