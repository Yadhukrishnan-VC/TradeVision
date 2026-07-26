from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class MarketDataConfig(AppConfig):
    """Django AppConfig for the ``market_data`` app.

    On ``ready()``, registers event handlers on the process-wide event
    bus so that ``market_data`` can publish and consume domain events.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.market_data"
    label = "market_data"
    verbose_name = "Market Data"

    def ready(self) -> None:
        """Perform application initialisation when Django starts.

        - Registers ``market_data`` event handlers on the event bus.
        - Does *not* automatically start the WebSocket tick manager
          — that is controlled by the Celery beat ``reconnect_websocket_watchdog``
          task or an explicit management command.
        """
        try:
            from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

            event_bus = get_event_bus()
            from apps.market_data.infrastructure.event_handlers import register_handlers

            register_handlers(event_bus)
            logger.info("market_data_event_handlers_registered")
        except Exception as exc:
            logger.warning(
                "market_data_ready_handler_registration_failed",
                extra={"error": str(exc)},
            )
