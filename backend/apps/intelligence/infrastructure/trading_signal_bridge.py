from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.infrastructure.market_context_cache import MarketContextCache
from apps.intelligence.models import PineOutput
from apps.intelligence.services import MarketContextService, SignalContextRef
from apps.macro_context.application.macro_context_builder import get_context_builder
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository
from core.clock import get_clock
from core.events.event_types import (
    BreadthContext,
    CircuitStatus,
    DataQuality,
    IntelligencePacket,
    NewsContext,
    PriceContext,
    TechnicalContext,
)

logger = logging.getLogger(__name__)

# Per-missing-source penalty applied to data_quality.quality_score. Mirrors the
# existing 0.3 discount used in apps/intelligence/domain/context_scoring.py
# (conf_signals -= 0.3 * min(len(dq.missing_sources), 3)). A local constant
# keeps the discount at the call site without a cross-layer import, and keeps
# this site consistent with ta_completed_handler.py.
NEWS_MISSING_QUALITY_PENALTY = 0.3


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return Decimal("0")


def _fetch_price_context(symbol: str) -> dict[str, Any]:
    repo = TASnapshotRepository()
    try:
        snapshots = repo.find_by_symbol(symbol, limit=1)
        if snapshots:
            snap = snapshots[0]
            raw = snap.raw_payload or {}
            return {
                "current_price": _to_decimal(raw.get("close") or raw.get("price")),
                "open_price": _to_decimal(raw.get("open")),
                "high": _to_decimal(raw.get("high")),
                "low": _to_decimal(raw.get("low")),
                "volume": int(raw.get("volume", 0)),
                "prev_close": _to_decimal(raw.get("prev_close")) if raw.get("prev_close") is not None else None,
                "change_pct": _to_decimal(raw.get("change_pct")) if raw.get("change_pct") is not None else None,
            }
    except Exception:
        logger.warning("signal_bridge_ta_fetch_failed", extra={"symbol": symbol})
    return {}


def _fetch_technical_context(symbol: str) -> dict[str, Any]:
    try:
        outputs = PineOutput.objects.filter(
            symbol=symbol,
            indicator_name="pine_composite",
        ).order_by("-detected_timestamp").first()
        if outputs and outputs.values:
            return dict(outputs.values)
    except Exception:
        logger.warning("signal_bridge_pine_fetch_failed", extra={"symbol": symbol})
    return {}


def _publish_market_context(context: Any, event: DomainEvent) -> None:
    try:
        bus = get_event_bus()
        mc_event = DomainEvent.create(
            event_type="intelligence.MarketContextBuilt",
            payload={
                "symbol": context.symbol,
                "market_regime": context.market_regime.value if hasattr(context.market_regime, "value") else str(context.market_regime),
                "regime_evidence": list(context.regime_evidence),
                "multi_timeframe_alignment": context.multi_timeframe_alignment.value if hasattr(context.multi_timeframe_alignment, "value") else str(context.multi_timeframe_alignment),
                "bullishness_score": context.bullishness_score,
                "bearishness_score": context.bearishness_score,
                "volatility_score": context.volatility_score,
                "trend_score": context.trend_score,
                "liquidity_score": context.liquidity_score,
                "momentum_score": context.momentum_score,
                "overall_context_confidence": context.overall_context_confidence,
                "pattern_alignment_note": context.pattern_alignment_note,
                "sector_context": context.sector_context,
                "data_quality_note": context.data_quality_note,
                "trading_signal_id": str(context.trading_signal.signal_id) if context.trading_signal else None,
            },
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )
        bus.publish(mc_event)
        cache = MarketContextCache()
        cache.set(context.symbol, context)
        logger.debug("market_context_published", extra={"symbol": context.symbol})
    except Exception as exc:
        logger.warning("market_context_publish_failed", extra={"symbol": context.symbol, "error": str(exc)})


def _fetch_breadth_context(indicators: dict[str, Any]) -> dict[str, Any]:
    return {
        "sector_index_change_pct": _to_decimal(indicators.get("sector_index_change_pct")),
        "sector_advance_decline": _to_decimal(indicators.get("sector_advance_decline")),
        "nifty_change_pct": _to_decimal(indicators.get("nifty_change_pct")),
        "sensex_change_pct": _to_decimal(indicators.get("sensex_change_pct")),
    }


def _build_macro_context() -> Any:
    """Build the point-in-time macro context as of the active clock.

    Defensive (additive-only contract): returns ``None`` when the provenance
    store is unavailable, so signal-driven packet assembly never fails because
    macro data could not be fetched. ``as_of`` always comes from
    ``get_clock().now()`` — the simulated-clock binding that makes backtest
    replay point-in-time safe.
    """
    try:
        return get_context_builder().build(as_of=get_clock().now())
    except Exception as exc:
        logger.warning("macro_context_build_failed", extra={"error": str(exc)})
        return None


def handle_signal_created(event: DomainEvent) -> None:
    payload = event.payload
    symbol = payload.get("symbol", "")
    if not symbol:
        logger.warning("signal_created_missing_symbol", extra={"event_id": str(event.event_id)})
        return

    price_data = _fetch_price_context(symbol)
    tech_data = _fetch_technical_context(symbol)
    breadth_data = _fetch_breadth_context(tech_data)

    service = MarketContextService()

    # No real news source is wired up yet (the news_feed app is an intentionally
    # empty scaffold pending NSE/BSE/Moneycontrol ToS review), so the packet uses
    # the unchecked NewsContext() default. Tag that absence explicitly so "no
    # news found" is distinguishable from "never checked", and reflect the same
    # per-source penalty used at the ta_completed_handler assembly site.
    missing: list[str] = []
    missing.append("news")

    packet = IntelligencePacket(
        symbol=symbol,
        timestamp=event.occurred_at,
        freshness_validated=True,
        price_context=PriceContext(
            current_price=price_data.get("current_price", Decimal("0")),
            open_price=price_data.get("open_price", Decimal("0")),
            high=price_data.get("high", Decimal("0")),
            low=price_data.get("low", Decimal("0")),
            prev_close=price_data.get("prev_close"),
            change_pct=price_data.get("change_pct"),
            volume=price_data.get("volume", 0),
            avg_volume_20d=0,
            circuit_status=CircuitStatus.NORMAL,
        ),
        technical_context=TechnicalContext(
            rsi_14=_to_decimal(tech_data.get("rsi_14")) if tech_data.get("rsi_14") is not None else None,
            macd=_to_decimal(tech_data.get("macd")) if tech_data.get("macd") is not None else None,
            bb_upper=_to_decimal(tech_data.get("bb_upper")) if tech_data.get("bb_upper") is not None else None,
            bb_lower=_to_decimal(tech_data.get("bb_lower")) if tech_data.get("bb_lower") is not None else None,
            ema_20=_to_decimal(tech_data.get("ema_20")) if tech_data.get("ema_20") is not None else None,
            ema_50=_to_decimal(tech_data.get("ema_50")) if tech_data.get("ema_50") is not None else None,
            ema_200=_to_decimal(tech_data.get("ema_200")) if tech_data.get("ema_200") is not None else None,
            vwap=_to_decimal(tech_data.get("vwap")) if tech_data.get("vwap") is not None else None,
        ),
        breadth_context=BreadthContext(
            sector_index_change_pct=breadth_data.get("sector_index_change_pct", Decimal("0")),
            sector_advance_decline=breadth_data.get("sector_advance_decline", Decimal("0")),
            nifty_change_pct=breadth_data.get("nifty_change_pct", Decimal("0")),
            sensex_change_pct=breadth_data.get("sensex_change_pct", Decimal("0")),
        ),
        news_context=NewsContext(),
        macro_context=_build_macro_context(),
        data_quality=DataQuality(
            quality_score=1.0 - (NEWS_MISSING_QUALITY_PENALTY * len(missing)),
            missing_sources=tuple(missing),
            stale_sources=(),
        ),
    )

    signal_ref = None
    signal_id_str = payload.get("signal_id")
    if signal_id_str:
        signal_ref = SignalContextRef(
            signal_id=uuid.UUID(signal_id_str),
            direction=payload.get("direction", "WAIT"),
            confidence_hint=float(payload.get("confidence_hint", 0.0)),
        )

    context = service.build_signal_context(
        symbol=symbol,
        packet=packet,
        trading_signal=signal_ref,
    )

    _publish_market_context(context, event)

    logger.info(
        "signal_context_triggered_by_bridge",
        extra={
            "signal_id": payload.get("signal_id"),
            "symbol": symbol,
            "direction": payload.get("direction"),
        },
    )
    return context
