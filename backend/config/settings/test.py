from __future__ import annotations

from .base import *

DEBUG = False

SECRET_KEY = "test-secret-key-not-for-production"

DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.postgresql",
        "NAME": os.environ.get("POSTGRES_DB", "test_tradevision_db"),
        "USER": os.environ.get("POSTGRES_USER", "tradevision"),
        "PASSWORD": os.environ.get("POSTGRES_PASSWORD", ""),
        "HOST": os.environ.get("POSTGRES_HOST", "localhost"),
        "PORT": os.environ.get("POSTGRES_PORT", "5432"),
    }
}

CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.dummy.DummyCache",
    }
}

PASSWORD_HASHERS = [
    "django.contrib.auth.hashers.MD5PasswordHasher",
]

CELERY_TASK_ALWAYS_EAGER = True
CELERY_TASK_EAGER_PROPAGATES = True

EVENT_BUS_IMPLEMENTATION = "fake"

LOGGING["root"]["level"] = "CRITICAL"
LOGGING["handlers"]["console"]["class"] = "logging.NullHandler"

EMAIL_BACKEND = "django.core.mail.backends.locmem.EmailBackend"
