"""
TradeVision AI — ASGI application.

Protocol routing:
    HTTP  → Django (via get_asgi_application)
    WS    → Django Channels (URLRouter populated progressively from Phase 5)

Django must be fully initialised before importing Channels components;
the ordering of statements in this module is deliberate.
"""

import os

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.development")

from django.core.asgi import get_asgi_application  # noqa: E402

# Initialise Django before importing any Channels components so that all
# installed apps and settings are available to the routing layer.
_django_asgi_app = get_asgi_application()

from channels.auth import AuthMiddlewareStack  # noqa: E402
from channels.routing import ProtocolTypeRouter, URLRouter  # noqa: E402
from channels.security.websocket import AllowedHostsOriginValidator  # noqa: E402

application = ProtocolTypeRouter(
    {
        "http": _django_asgi_app,
        # WebSocket consumers are registered here as each Phase introduces them.
        # AllowedHostsOriginValidator enforces the ALLOWED_HOSTS whitelist.
        # AuthMiddlewareStack populates request.user from the session / JWT.
        "websocket": AllowedHostsOriginValidator(
            AuthMiddlewareStack(
                URLRouter(
                    []  # Populated in Phase 5 — Notifications & WebSocket
                )
            )
        ),
    }
)
