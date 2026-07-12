"""
TradeVision AI — Centralised typed configuration.

Provides ``TradeVisionConfig`` — a thin, typed wrapper around Django settings
that gives the rest of the codebase a single, testable access point for all
TradeVision-specific configuration values. Providers and core modules should
import ``config`` from this module rather than reaching into
``django.conf.settings`` directly.

Usage::

    from core.config import config

    provider_name = config.ai_provider
    gemini_key = config.gemini_api_key
"""

from typing import Any


class TradeVisionConfig:
    """
    Typed, centralised access to all TradeVision settings.

    Reads values lazily from ``django.conf.settings`` on first access,
    caching them for the lifetime of the process. This avoids import-time
    coupling to Django settings while keeping access convenient.
    """

    def __getattr__(self, name: str) -> Any:
        """Proxy attribute access to Django settings."""
        from django.conf import settings

        return getattr(settings, name)


# Module-level singleton — import and use directly
config = TradeVisionConfig()
