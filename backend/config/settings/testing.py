"""
TradeVision AI — Testing settings.

Optimised for fast, isolated test runs. Celery tasks execute synchronously;
password hashing uses a fast algorithm; logging is silenced.

pytest-django selects this module via pytest.ini:
    DJANGO_SETTINGS_MODULE = config.settings.testing
"""

# ruff: noqa: F401, F403
from .base import *  # noqa: F401, F403

# ---------------------------------------------------------------------------
# Security — minimal values for test isolation
# ---------------------------------------------------------------------------
SECRET_KEY = "test-secret-key-not-used-in-production-ever"  # noqa: S105
DEBUG = False

# ---------------------------------------------------------------------------
# Password hashing — MD5 for speed; security irrelevant in tests
# ---------------------------------------------------------------------------
PASSWORD_HASHERS = ["django.contrib.auth.hashers.MD5PasswordHasher"]

# ---------------------------------------------------------------------------
# Database — real PostgreSQL via the test DB alias
# Tests run against a dedicated database created by pytest-django.
# Never use SQLite — TimescaleDB behaviour cannot be reproduced with it.
# ---------------------------------------------------------------------------
DATABASES = {  # type: ignore[name-defined]  # noqa: F405
    "default": {
        **DATABASES["default"],  # type: ignore[name-defined]
        "NAME": "tradevision_test",
    }
}

# ---------------------------------------------------------------------------
# Celery — synchronous execution so tests do not need a running broker
# ---------------------------------------------------------------------------
CELERY_TASK_ALWAYS_EAGER: bool = True
CELERY_TASK_EAGER_PROPAGATES: bool = True

# ---------------------------------------------------------------------------
# Cache — in-memory dummy cache for test isolation
# ---------------------------------------------------------------------------
CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

# ---------------------------------------------------------------------------
# Channels — in-memory layer removes Redis dependency in unit tests
# ---------------------------------------------------------------------------
CHANNEL_LAYERS = {
    "default": {
        "BACKEND": "channels.layers.InMemoryChannelLayer",
    }
}

# ---------------------------------------------------------------------------
# Email — discard all outbound email in tests
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"

# ---------------------------------------------------------------------------
# Logging — silence during test runs to keep output clean
# ---------------------------------------------------------------------------
LOGGING = {  # type: ignore[name-defined]  # noqa: F405
    "version": 1,
    "disable_existing_loggers": True,
    "handlers": {"null": {"class": "logging.NullHandler"}},
    "root": {"handlers": ["null"]},
}

# ---------------------------------------------------------------------------
# Media — use tmp directory for file upload tests
# ---------------------------------------------------------------------------
import tempfile  # noqa: E402

MEDIA_ROOT = tempfile.mkdtemp()
