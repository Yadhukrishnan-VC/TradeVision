from __future__ import annotations

import logging
import time
from datetime import datetime
from decimal import Decimal
from typing import Any, ClassVar

import requests

from core.config import config
from core.exceptions import DataProviderError
from core.market_data.base_provider import (
    BaseMarketDataProvider,
    MarketDataRequest,
    MarketDataResponse,
    OHLCVBar,
)
from core.utils import get_now, to_utc

logger = logging.getLogger(__name__)

_ZERODHA_API_BASE = "https://api.kite.trade"
_ZERODHA_HISTORICAL_ENDPOINT = "/instruments/historical/{instrument_token}/{interval}"


class ZerodhaMarketDataProvider(BaseMarketDataProvider):
    """Zerodha Kite Connect market data provider.

    Provides OHLCV data via Zerodha's REST API. Requires a valid Kite
    Connect API key and access token configured in Django settings.

    Implements every abstract method of ``BaseMarketDataProvider``
    without breaking the existing contract.
    """

    provider_name: ClassVar[str] = "zerodha"

    def __init__(self) -> None:
        self._api_key: str = config.zerodha_api_key
        self._access_token: str = config.zerodha_access_token
        self._session: requests.Session | None = None

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "X-Kite-Version": "3",
            "Authorization": f"token {self._api_key}:{self._access_token}",
        }

    def validate_connection(self) -> bool:
        """Verify connectivity by calling the Kite Connect user profile endpoint.

        Returns:
            ``True`` if the credentials are valid and the API is reachable.

        Raises:
            DataProviderError: If the connection cannot be established.
        """
        try:
            response = requests.get(
                f"{_ZERODHA_API_BASE}/user/profile",
                headers=self._headers,
                timeout=10,
            )
            response.raise_for_status()
            return True
        except requests.RequestException as exc:
            raise DataProviderError(
                f"Zerodha connection failed: {exc}"
            ) from exc

    def health_check(self) -> dict[str, Any]:
        """Return current health status for this provider.

        Returns:
            Health dict with ``status``, ``provider``, ``latency_ms``.
        """
        start = time.monotonic()
        try:
            ok = self.validate_connection()
            latency = round((time.monotonic() - start) * 1000, 2)
            return {
                "status": "healthy" if ok else "unhealthy",
                "provider": self.provider_name,
                "latency_ms": latency,
            }
        except DataProviderError:
            latency = round((time.monotonic() - start) * 1000, 2)
            return {
                "status": "unhealthy",
                "provider": self.provider_name,
                "latency_ms": latency,
                "error": "Connection validation failed",
            }

    def fetch(self, request: MarketDataRequest) -> MarketDataResponse:
        """Retrieve OHLCV bars from Zerodha Kite Connect historical API.

        The Kite Connect historical endpoint requires the numeric
        ``instrument_token`` in the URL path, not the trading symbol. The
        token is resolved locally from the ``Instrument`` table (the same
        lookup ``HistoricalSyncService`` uses); if no matching instrument
        row exists yet (instrument sync has not run), a
        ``DataProviderError`` is raised instead of sending a malformed
        request.

        Args:
            request: A populated ``MarketDataRequest``.

        Returns:
            ``MarketDataResponse`` with the requested OHLCV bars.

        Raises:
            DataProviderError: On API errors or unexpected responses, or
                when the instrument token cannot be resolved.
        """
        session = self._get_session()
        start = time.monotonic()

        instrument_token = self._resolve_instrument_token(request.symbol)
        kite_interval = self._map_interval(request.interval)
        from_str = request.from_timestamp.strftime("%Y-%m-%d %H:%M:%S")
        to_str = request.to_timestamp.strftime("%Y-%m-%d %H:%M:%S")

        url = f"{_ZERODHA_API_BASE}/instruments/historical/{instrument_token}/{kite_interval}"
        params = {"from": from_str, "to": to_str}

        try:
            resp = session.get(url, params=params, timeout=30)
            resp.raise_for_status()
            data = resp.json()
        except requests.RequestException as exc:
            raise DataProviderError(
                f"Zerodha historical fetch failed for {request.symbol}: {exc}"
            ) from exc

        if data.get("status") != "success" or "data" not in data:
            raise DataProviderError(
                f"Zerodha returned error for {request.symbol}: {data.get('error', 'unknown')}"
            )

        bars: list[OHLCVBar] = []
        for item in data["data"].get("candles", []):
            if len(item) < 6:
                continue
            try:
                ts = datetime.fromisoformat(item[0])
                bars.append(OHLCVBar(
                    timestamp=ts,
                    open_price=Decimal(str(item[1])),
                    high=Decimal(str(item[2])),
                    low=Decimal(str(item[3])),
                    close_price=Decimal(str(item[4])),
                    volume=int(item[5]),
                ))
            except (ValueError, TypeError) as exc:
                logger.warning(
                    "zerodha_parse_error",
                    extra={"symbol": request.symbol, "error": str(exc)},
                )
                continue

        latency = round((time.monotonic() - start) * 1000, 2)

        return MarketDataResponse(
            request_id=request.request_id or "",
            symbol=request.symbol,
            interval=request.interval,
            bars=tuple(bars),
            provider=self.provider_name,
            fetched_at=get_now(),
            is_complete=True,
            meta={"latency_ms": latency, "bar_count": len(bars)},
        )

    def fetch_instruments(self) -> list[dict[str, Any]]:
        """Retrieve the full instrument master from Zerodha.

        This is a concrete method not present on ``BaseMarketDataProvider``;
        it is called by ``InstrumentSyncService`` when available.

        Returns:
            List of instrument dicts with keys: ``instrument_token``,
            ``exchange``, ``tradingsymbol``, ``name``, ``segment``,
            ``lot_size``, ``tick_size``, ``instrument_type``, ``expiry``.

        Raises:
            DataProviderError: If the API call fails.
        """
        session = self._get_session()
        url = f"{_ZERODHA_API_BASE}/instruments"

        try:
            resp = session.get(url, timeout=60)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as exc:
            raise DataProviderError(
                f"Zerodha instrument fetch failed: {exc}"
            ) from exc

    def close(self) -> None:
        """Close the HTTP session and release resources."""
        if self._session is not None:
            self._session.close()
            self._session = None
        logger.debug("zerodha_provider_closed")

    def _get_session(self) -> requests.Session:
        if self._session is None:
            self._session = requests.Session()
            self._session.headers.update(self._headers)
        return self._session

    @staticmethod
    def _resolve_instrument_token(tradingsymbol: str) -> int:
        """Resolve the numeric Kite Connect instrument token for a trading symbol.

        The historical API requires the numeric ``instrument_token`` in the
        URL path, not the trading symbol. The token is looked up from the
        locally synced ``Instrument`` table (populated by
        ``InstrumentSyncService``).

        Args:
            tradingsymbol: The exchange trading symbol (e.g. ``"RELIANCE"``).

        Returns:
            The numeric instrument token.

        Raises:
            DataProviderError: If no ``Instrument`` row exists for the symbol,
                i.e. instrument sync has not run yet.
        """
        from apps.common.domain.value_objects import Symbol
        from apps.market_data.infrastructure.repositories import InstrumentRepository

        instrument = InstrumentRepository().find_by_symbol(
            Symbol(exchange=config.default_exchange, tradingsymbol=tradingsymbol)
        )
        if instrument is None:
            raise DataProviderError(
                f"Cannot resolve instrument token for '{tradingsymbol}': "
                "instrument not found in local table. Run instrument sync "
                "(InstrumentSyncService.sync or sync_instrument_master) first."
            )
        return instrument.instrument_token

    @staticmethod
    def _map_interval(interval: str) -> str:
        """Map TradeVision interval strings to Kite Connect interval format."""
        mapping = {
            "1min": "minute",
            "3min": "3minute",
            "5min": "5minute",
            "10min": "10minute",
            "15min": "15minute",
            "30min": "30minute",
            "1hr": "60minute",
            "1D": "day",
            "1W": "week",
            "1M": "month",
        }
        result = mapping.get(interval)
        if result is None:
            raise DataProviderError(f"Unsupported interval for Zerodha: {interval}")
        return result
