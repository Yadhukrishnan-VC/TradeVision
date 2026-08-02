"""
TradeVision AI — Market data provider factory.

Implements the singleton pattern for market data provider instances.
Provider selection is driven by ``TradeVisionConfig.market_data_provider``.

Usage::

    from core.market_data.provider_factory import MarketDataProviderFactory

    provider = MarketDataProviderFactory.get_provider()
    response = provider.fetch(request)
"""

import logging
import threading
from typing import ClassVar

from core.exceptions import DataProviderError
from core.market_data.base_provider import BaseMarketDataProvider

logger = logging.getLogger(__name__)


class MarketDataProviderFactory:
    """
    Singleton factory for market data provider instances.

    Only one provider instance exists per process. ``reset()`` destroys
    the current instance and forces re-creation on the next ``get_provider()``
    call — used for test isolation and provider switching.

    Currently supported providers:
        ``mock``    — Deterministic fake data, no network I/O (Phase 0)
        ``paper``   — Seeded simulated OHLCV, no network I/O (dev/testing)
        ``zerodha`` — Real Kite Connect historical + instrument data
    """

    _instance: ClassVar[BaseMarketDataProvider | None] = None
    _lock: ClassVar[threading.Lock] = threading.Lock()

    @classmethod
    def get_provider(cls) -> BaseMarketDataProvider:
        """
        Return the active market data provider singleton.

        Creates the provider on first call using ``TradeVisionConfig``.
        Thread-safe via double-checked locking.

        Returns:
            The configured ``BaseMarketDataProvider`` instance.

        Raises:
            DataProviderError: If the configured provider name is unknown.
        """
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls._create_provider()
        return cls._instance

    @classmethod
    def reset(cls) -> None:
        """
        Destroy the current singleton and release its resources.

        The next call to ``get_provider()`` creates a fresh instance.
        Intended for test isolation.
        """
        with cls._lock:
            if cls._instance is not None:
                try:
                    cls._instance.close()
                except Exception as exc:
                    logger.warning(
                        "market_data_provider_close_error_during_reset",
                        extra={"error": str(exc)},
                    )
            cls._instance = None
            logger.debug("market_data_provider_factory_reset")

    @classmethod
    def _create_provider(cls) -> BaseMarketDataProvider:
        """
        Instantiate and return the correct provider for the current configuration.

        Returns:
            A freshly instantiated ``BaseMarketDataProvider``.

        Raises:
            DataProviderError: If the provider name is not recognised.
        """
        from core.config import config
        from core.market_data.providers.mock_provider import MockMarketDataProvider
        from apps.market_data.infrastructure.providers.paper_provider import PaperMarketDataProvider
        from apps.market_data.infrastructure.providers.zerodha_provider import ZerodhaMarketDataProvider

        provider_name: str = config.market_data_provider

        provider_map: dict[str, type[BaseMarketDataProvider]] = {
            "mock": MockMarketDataProvider,
            "paper": PaperMarketDataProvider,
            "zerodha": ZerodhaMarketDataProvider,
        }

        if provider_name not in provider_map:
            raise DataProviderError(
                f"Unknown market data provider: '{provider_name}'. "
                f"Supported providers: {sorted(provider_map.keys())}. "
                "Update settings.MARKET_DATA_PROVIDER to a supported value."
            )

        instance: BaseMarketDataProvider = provider_map[provider_name]()
        logger.info(
            "market_data_provider_created",
            extra={
                "provider": provider_name,
                "class": type(instance).__name__,
            },
        )
        return instance
