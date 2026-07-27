"""
TradeVision AI — Development settings.

Wildcard import from base is the accepted Django convention for settings
inheritance. This is the only file in the codebase where `import *` is
permitted. All other Python files must use explicit imports.
"""

# ruff: noqa: F401, F403
from .base import *  # noqa: F401, F403

from datetime import timedelta

# ---------------------------------------------------------------------------
# Core overrides
# ---------------------------------------------------------------------------
DEBUG = True

# In development, accept any host so Docker service names work
ALLOWED_HOSTS = ["*"]

import importlib.util

DEV_APPS = []
if importlib.util.find_spec("debug_toolbar"):
    DEV_APPS.append("debug_toolbar")
if importlib.util.find_spec("django_extensions"):
    DEV_APPS.append("django_extensions")

INSTALLED_APPS = [
    *INSTALLED_APPS,  # type: ignore[name-defined]  # noqa: F405
    *DEV_APPS,
]

# ---------------------------------------------------------------------------
# Debug Toolbar middleware — inserted before CommonMiddleware
# ---------------------------------------------------------------------------
if "debug_toolbar" in INSTALLED_APPS:
    _common_idx = MIDDLEWARE.index(  # type: ignore[name-defined]  # noqa: F405
        "django.middleware.common.CommonMiddleware"
    )
    MIDDLEWARE = [  # noqa: F405
        *MIDDLEWARE[:_common_idx],  # type: ignore[name-defined]
        "debug_toolbar.middleware.DebugToolbarMiddleware",
        *MIDDLEWARE[_common_idx:],  # type: ignore[name-defined]
    ]

INTERNAL_IPS = ["127.0.0.1", "::1"]

DEBUG_TOOLBAR_CONFIG = {
    "SHOW_TOOLBAR_CALLBACK": lambda _request: DEBUG,
}

# ---------------------------------------------------------------------------
# DRF — add Browsable API renderer in development
# ---------------------------------------------------------------------------
REST_FRAMEWORK = {  # type: ignore[name-defined]  # noqa: F405
    **REST_FRAMEWORK,  # type: ignore[name-defined]
    "DEFAULT_RENDERER_CLASSES": [
        "rest_framework.renderers.JSONRenderer",
        "rest_framework.renderers.BrowsableAPIRenderer",
    ],
}

# ---------------------------------------------------------------------------
# JWT — longer lifetime for development convenience
# ---------------------------------------------------------------------------
SIMPLE_JWT = {  # type: ignore[name-defined]  # noqa: F405
    **SIMPLE_JWT,  # type: ignore[name-defined]
    "ACCESS_TOKEN_LIFETIME": timedelta(days=1),
}

# ---------------------------------------------------------------------------
# Email — print to console instead of sending
# ---------------------------------------------------------------------------
EMAIL_BACKEND = "django.core.mail.backends.console.EmailBackend"

# ---------------------------------------------------------------------------
# CORS — allow all origins in development
# ---------------------------------------------------------------------------
CORS_ALLOW_ALL_ORIGINS = True

# ---------------------------------------------------------------------------
# Market data provider — use mock in development
# ---------------------------------------------------------------------------
MARKET_DATA_PROVIDER = "mock"

# ---------------------------------------------------------------------------
# Logging — verbose in development
# ---------------------------------------------------------------------------
LOG_LEVEL = "DEBUG"

LOGGING = {  # type: ignore[name-defined]  # noqa: F405
    **LOGGING,  # type: ignore[name-defined]
    "root": {
        "handlers": ["console"],
        "level": "DEBUG",
    },
    "loggers": {
        **LOGGING.get("loggers", {}),  # type: ignore[name-defined]
        "django.db.backends": {
            "handlers": ["console"],
            "level": "DEBUG",
            "propagate": False,
        },
    },
}
