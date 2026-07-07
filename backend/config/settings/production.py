"""
TradeVision AI — Production settings.

See development.py for the wildcard import justification.
"""

# ruff: noqa: F401, F403
from .base import *  # noqa: F401, F403

import sentry_sdk
from decouple import config
from sentry_sdk.integrations.celery import CeleryIntegration
from sentry_sdk.integrations.django import DjangoIntegration
from sentry_sdk.integrations.redis import RedisIntegration

# ---------------------------------------------------------------------------
# Core — enforce safe production defaults
# ---------------------------------------------------------------------------
DEBUG = False

# ---------------------------------------------------------------------------
# Security hardening
# ---------------------------------------------------------------------------
SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
SECURE_SSL_REDIRECT = True
SECURE_HSTS_SECONDS = 63072000
SECURE_HSTS_INCLUDE_SUBDOMAINS = True
SECURE_HSTS_PRELOAD = True
SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_BROWSER_XSS_FILTER = True
SESSION_COOKIE_SECURE = True
CSRF_COOKIE_SECURE = True
SESSION_COOKIE_SAMESITE = "Strict"

# ---------------------------------------------------------------------------
# Email — configure real backend in environment
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.smtp.EmailBackend"
EMAIL_HOST = config("EMAIL_HOST", default="")
EMAIL_PORT = config("EMAIL_PORT", default=587, cast=int)
EMAIL_HOST_USER = config("EMAIL_HOST_USER", default="")
EMAIL_HOST_PASSWORD = config("EMAIL_HOST_PASSWORD", default="")
EMAIL_USE_TLS = config("EMAIL_USE_TLS", default=True, cast=bool)
DEFAULT_FROM_EMAIL = config("DEFAULT_FROM_EMAIL", default="noreply@tradevision.ai")

# ---------------------------------------------------------------------------
# Sentry — error tracking and performance monitoring
# ---------------------------------------------------------------------------
_sentry_dsn: str = config("SENTRY_DSN", default="")
if _sentry_dsn:
    sentry_sdk.init(
        dsn=_sentry_dsn,
        environment=config("SENTRY_ENVIRONMENT", default="production"),
        traces_sample_rate=config("SENTRY_TRACES_SAMPLE_RATE", default=0.1, cast=float),
        integrations=[
            DjangoIntegration(transaction_style="url"),
            CeleryIntegration(monitor_beat_tasks=True),
            RedisIntegration(),
        ],
        send_default_pii=False,
    )

# ---------------------------------------------------------------------------
# Logging — WARNING level in production; errors go to Sentry
# ---------------------------------------------------------------------------
LOG_LEVEL = "WARNING"

LOGGING = {  # type: ignore[name-defined]  # noqa: F405
    **LOGGING,  # type: ignore[name-defined]
    "root": {
        "handlers": ["console"],
        "level": "WARNING",
    },
}
