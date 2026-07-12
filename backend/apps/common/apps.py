"""
TradeVision AI — Common application configuration.

This is the first app loaded in INSTALLED_APPS. Its ``ready()`` hook
initialises structlog immediately after Django finishes loading all apps,
ensuring that every subsequent log call (in other apps' ready() hooks,
management commands, and request handling) uses the structured renderer.
"""

import logging

from django.apps import AppConfig

logger = logging.getLogger(__name__)


class CommonConfig(AppConfig):
    """Configuration for the ``apps.common`` application."""

    name = "apps.common"
    verbose_name = "Common"
    default_auto_field = "django.db.models.BigAutoField"

    def ready(self) -> None:
        """
        Initialise cross-cutting infrastructure once Django is fully loaded.

        Called exactly once per process — not per request or per worker.
        Side effects here are intentional and expected:
        - Configures structlog with the correct renderer for the environment.
        """
        from django.conf import settings

        from core.logging import configure_structlog

        configure_structlog(development=settings.DEBUG)
        logger.info("common_app_ready", extra={"debug": settings.DEBUG})
