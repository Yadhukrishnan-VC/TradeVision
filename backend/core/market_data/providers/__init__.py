"""
TradeVision AI — Market data provider implementations package.

Available providers:
    mock  — Deterministic placeholder data, no network I/O (Phase 0, testing)

Phase 1 will add:
    nse   — NSE/BSE vendor API integration

Import via the factory, not directly::

    from core.market_data.provider_factory import MarketDataProviderFactory
    provider = MarketDataProviderFactory.get_provider()
"""
