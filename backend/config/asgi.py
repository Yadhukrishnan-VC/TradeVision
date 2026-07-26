from __future__ import annotations

import os

from channels.auth import AuthMiddlewareStack
from channels.routing import ProtocolTypeRouter, URLRouter
from django.core.asgi import get_asgi_application

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings.dev")

django_asgi_app = get_asgi_application()

from apps.dashboard.interfaces.websocket.trading_core.routing import websocket_urlpatterns as trading_core_ws  # noqa: E402
from apps.dashboard.interfaces.websocket.analytics_risk.routing import websocket_urlpatterns as analytics_risk_ws  # noqa: E402

combined_ws = trading_core_ws + analytics_risk_ws

application = ProtocolTypeRouter({
    "http": django_asgi_app,
    "websocket": AuthMiddlewareStack(
        URLRouter(combined_ws)
    ),
})
