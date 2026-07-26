from __future__ import annotations

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class IngestionConfig(AppConfig):
    """Django AppConfig for the ``ingestion`` app.

    ``ingestion`` is the single front door for external webhook payloads
    (TradingView alerts, Chartink scan results). It validates, persists,
    and publishes ``ingestion.RawAlertReceived`` and
    ``ingestion.ScanResultReceived`` events for downstream consumption.
    """

    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.ingestion"
    label = "ingestion"
    verbose_name = "Ingestion"

    def ready(self) -> None:
        """Validate configuration on startup.

        Does not register any event handlers — ``ingestion`` is a
        publisher-only app in this batch.
        """
        logger.debug("ingestion_app_ready")
