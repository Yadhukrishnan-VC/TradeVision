from __future__ import annotations

from .base import *

DEBUG = True

ALLOWED_HOSTS = ["*"]

SECRET_KEY = "dev-secret-key-not-for-production"

INSTALLED_APPS += [
    "debug_toolbar",
]

MIDDLEWARE = ["debug_toolbar.middleware.DebugToolbarMiddleware"] + MIDDLEWARE

INTERNAL_IPS = ["127.0.0.1"]

REST_FRAMEWORK["DEFAULT_RENDERER_CLASSES"] = (
    "rest_framework.renderers.JSONRenderer",
    "rest_framework.renderers.BrowsableAPIRenderer",
)

LOGGING["root"]["level"] = "DEBUG"

EVENT_BUS_IMPLEMENTATION = "redis"

CELERY_TASK_ALWAYS_EAGER = False

EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"
