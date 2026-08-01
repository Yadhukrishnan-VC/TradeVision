from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.events.event_types import (
    AnnouncementContext,
    BreadthContext,
    CircuitStatus,
    DataQuality,
    GlobalContext,
    InstitutionalContext,
    IntelligencePacket,
    MarketTrend,
    NewsContext,
    OptionsContext,
    PriceContext,
    TechnicalContext,
)


def _to_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _to_decimal_zero(value: Any) -> Decimal:
    result = _to_decimal(value)
    return result if result is not None else Decimal(0)


def _to_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def _trend(value: Any) -> MarketTrend:
    try:
        return MarketTrend(str(value).upper())
    except (ValueError, TypeError):
        return MarketTrend.SIDEWAYS


def _circuit(value: Any) -> CircuitStatus:
    try:
        return CircuitStatus(str(value).upper())
    except (ValueError, TypeError):
        return CircuitStatus.NORMAL


def _ts(value: Any, fallback: datetime | None = None) -> datetime:
    if value is None:
        if fallback is not None:
            return fallback
        return datetime.now(timezone.utc)
    try:
        ts = datetime.fromisoformat(str(value))
    except (ValueError, TypeError):
        if fallback is not None:
            return fallback
        return datetime.now(timezone.utc)
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=timezone.utc)
    return ts


def deserialize_packet(
    data: dict[str, Any], *, fallback_ts: datetime | None = None
) -> IntelligencePacket:
    """Rehydrate an ``IntelligencePacket`` from serialized ``packet_data``.

    Mirrors the deserialization approach used by the rule engine
    (``apps.rule_engine.infrastructure.event_handlers``) and tolerates
    missing optional context blocks by leaving them ``None``.
    """
    price_raw = data.get("price_context", {})
    tech_raw = data.get("technical_context", {})
    breadth_raw = data.get("breadth_context", {})
    dq_raw = data.get("data_quality", {})
    options_raw = data.get("options_context")
    global_raw = data.get("global_context")
    ann_raw = data.get("announcement_context")
    inst_raw = data.get("institutional_context")

    price_ctx = PriceContext(
        current_price=_to_decimal_zero(price_raw.get("current_price")),
        open_price=_to_decimal_zero(price_raw.get("open_price")),
        high=_to_decimal_zero(price_raw.get("high")),
        low=_to_decimal_zero(price_raw.get("low")),
        volume=_to_int(price_raw.get("volume")),
        avg_volume_20d=_to_int(price_raw.get("avg_volume_20d")),
        circuit_status=_circuit(price_raw.get("circuit_status")),
        prev_close=_to_decimal(price_raw.get("prev_close")),
        change_pct=_to_decimal(price_raw.get("change_pct")),
    )

    tech_ctx = TechnicalContext(
        trend=_trend(tech_raw.get("trend")),
        rsi_14=_to_decimal(tech_raw.get("rsi_14")),
        macd=_to_decimal(tech_raw.get("macd")),
        macd_signal=_to_decimal(tech_raw.get("macd_signal")),
        macd_histogram=_to_decimal(tech_raw.get("macd_histogram")),
        bb_upper=_to_decimal(tech_raw.get("bb_upper")),
        bb_lower=_to_decimal(tech_raw.get("bb_lower")),
        bb_width=_to_decimal(tech_raw.get("bb_width")),
        vwap=_to_decimal(tech_raw.get("vwap")),
        atr_14=_to_decimal(tech_raw.get("atr_14")),
        ema_20=_to_decimal(tech_raw.get("ema_20")),
        ema_50=_to_decimal(tech_raw.get("ema_50")),
        ema_200=_to_decimal(tech_raw.get("ema_200")),
    )

    breadth_ctx = BreadthContext(
        sector_index_change_pct=_to_decimal_zero(
            breadth_raw.get("sector_index_change_pct")
        ),
        sector_advance_decline=_to_decimal_zero(
            breadth_raw.get("sector_advance_decline")
        ),
        nifty_change_pct=_to_decimal_zero(breadth_raw.get("nifty_change_pct")),
        sensex_change_pct=_to_decimal_zero(breadth_raw.get("sensex_change_pct")),
    )

    news_ctx = NewsContext()

    dq_ctx = DataQuality(
        quality_score=float(dq_raw.get("quality_score", 1.0)),
    )

    options_ctx = None
    if options_raw:
        options_ctx = OptionsContext(
            pcr=_to_decimal_zero(options_raw.get("pcr")),
            max_pain=_to_decimal_zero(options_raw.get("max_pain")),
            atm_iv=_to_decimal_zero(options_raw.get("atm_iv")),
            oi_change_pct=_to_decimal_zero(options_raw.get("oi_change_pct")),
            unusual_activity=bool(options_raw.get("unusual_activity", False)),
        )

    global_ctx = None
    if global_raw:
        global_ctx = GlobalContext(
            dow_futures_pct=_to_decimal_zero(global_raw.get("dow_futures_pct")),
            sgx_nifty_pct=_to_decimal_zero(global_raw.get("sgx_nifty_pct")),
            crude_oil_pct=_to_decimal_zero(global_raw.get("crude_oil_pct")),
            usd_inr_change_pct=_to_decimal_zero(global_raw.get("usd_inr_change_pct")),
            vix=_to_decimal_zero(global_raw.get("vix")),
            india_vix=_to_decimal_zero(global_raw.get("india_vix")),
            fii_net_flow_cr=_to_decimal_zero(global_raw.get("fii_net_flow_cr")),
        )

    announcement_ctx = AnnouncementContext() if ann_raw else None
    institutional_ctx = InstitutionalContext() if inst_raw else None

    ts = _ts(data.get("timestamp"), fallback=fallback_ts)

    return IntelligencePacket(
        symbol=str(data.get("symbol", "")),
        timestamp=ts,
        freshness_validated=bool(data.get("freshness_validated", True)),
        price_context=price_ctx,
        technical_context=tech_ctx,
        breadth_context=breadth_ctx,
        news_context=news_ctx,
        data_quality=dq_ctx,
        options_context=options_ctx,
        announcement_context=announcement_ctx,
        global_context=global_ctx,
        institutional_context=institutional_ctx,
    )


__all__ = ["deserialize_packet"]
