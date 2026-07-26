from __future__ import annotations

import logging

from rest_framework import status
from rest_framework.generics import GenericAPIView, ListAPIView
from rest_framework.permissions import IsAuthenticated
from rest_framework.request import Request
from rest_framework.response import Response

from apps.common.domain.value_objects import Symbol
from apps.market_data.application.market_data_service import get_market_data_service
from apps.market_data.domain.value_objects import Timeframe
from apps.market_data.infrastructure.models import Instrument
from apps.market_data.infrastructure.repositories import InstrumentRepository
from apps.market_data.interfaces.api.serializers import (
    CandleQuerySerializer,
    CandleSerializer,
    InstrumentQuerySerializer,
    InstrumentSerializer,
    SessionStatusSerializer,
)

logger = logging.getLogger(__name__)


class InstrumentSearchView(ListAPIView):
    """Search for tradeable instruments by symbol or name.

    GET /api/v1/market-data/instruments/?q=RELIANCE&exchange=NSE

    Responses:
        ``200``: Paginated list of matching instruments.
        ``401``: Authentication required.
    """

    serializer_class = InstrumentSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        query_ser = InstrumentQuerySerializer(data=self.request.query_params)
        query_ser.is_valid(raise_exception=True)

        q = query_ser.validated_data.get("q", "")
        exchange = query_ser.validated_data.get("exchange")

        repo = InstrumentRepository()
        if q:
            tokens = [inst.instrument_token for inst in repo.search(q, exchange=exchange)]
            return Instrument.objects.filter(instrument_token__in=tokens, is_active=True)
        elif exchange:
            return Instrument.objects.filter(exchange__iexact=exchange, is_active=True)
        else:
            return Instrument.objects.filter(is_active=True)


class CandleListView(GenericAPIView):
    """Return aggregated OHLCV candles for a given symbol.

    GET /api/v1/market-data/candles/{symbol}/?timeframe=15min&lookback=50

    Responses:
        ``200``: List of candles (chronological order).
        ``400``: Invalid timeframe or lookback value.
        ``404``: Unknown instrument symbol.
        ``401``: Authentication required.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request, symbol: str) -> Response:
        query_ser = CandleQuerySerializer(data=request.query_params)
        query_ser.is_valid(raise_exception=True)

        timeframe_str = query_ser.validated_data["timeframe"]
        lookback = query_ser.validated_data["lookback"]

        try:
            timeframe = Timeframe.from_string(timeframe_str)
        except ValueError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_400_BAD_REQUEST,
            )

        # Parse symbol as exchange:tradingsymbol
        parts = symbol.split(":", 1)
        if len(parts) == 2:
            exchange, tradingsymbol = parts
        else:
            exchange = "NSE"
            tradingsymbol = parts[0]

        symbol_obj = Symbol(exchange=exchange, tradingsymbol=tradingsymbol)

        service = get_market_data_service()
        try:
            candles = service.get_candles(symbol=symbol_obj, timeframe=timeframe, lookback=lookback)
        except LookupError as exc:
            return Response(
                {"error": str(exc)},
                status=status.HTTP_404_NOT_FOUND,
            )

        serializer = CandleSerializer(candles, many=True)
        return Response(serializer.data)


class MarketSessionView(GenericAPIView):
    """Return the current NSE market session.

    GET /api/v1/market-data/session/

    Responses:
        ``200``: ``{"status": "market_hours"}``
        ``401``: Authentication required.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        service = get_market_data_service()
        session = service.get_market_session()
        serializer = SessionStatusSerializer({"status": session.value})
        return Response(serializer.data)


class MarketDataHealthView(GenericAPIView):
    """Return the health status of the market data subsystem.

    GET /api/v1/market-data/health/

    Responses:
        ``200``: Health status including provider, cache, and WebSocket state.
        ``401``: Authentication required.
    """

    permission_classes = [IsAuthenticated]

    def get(self, request: Request) -> Response:
        from core.market_data.provider_factory import MarketDataProviderFactory
        from core.redis_client import get_redis_client

        service = get_market_data_service()
        session = service.get_market_session()

        provider_status: dict = {}
        try:
            provider = MarketDataProviderFactory.get_provider()
            provider_status = provider.health_check()
        except Exception as exc:
            provider_status = {
                "status": "unhealthy",
                "error": str(exc),
            }

        cache_status: str = "unknown"
        try:
            redis_client = get_redis_client()
            redis_client.ping()
            cache_status = "healthy"
        except Exception:
            cache_status = "unhealthy"

        websocket_state: str = "unknown"
        try:
            from core.redis_client import get_redis_client as _get_redis_client
            r = _get_redis_client()
            ws_state = r.get("market_data:websocket:state")
            websocket_state = ws_state if ws_state else "disconnected"
        except Exception:
            websocket_state = "unknown"

        return Response({
            "market_session": session.value,
            "provider": provider_status,
            "cache": cache_status,
            "websocket_state": websocket_state,
        })
