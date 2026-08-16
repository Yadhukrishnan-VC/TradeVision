from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.models import PineOutput
from apps.macro_context.application.macro_context_builder import get_context_builder
from apps.technical_analysis.application.services import CANONICAL_FIELD_MAP
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
# (conf_signals -= 0.3 * min(len(dq.missing_sources), 3)), so packet assembly
# and context scoring agree on the cost of a missing source. A local constant
# keeps the discount at the call site without a cross-layer import.
NEWS_MISSING_QUALITY_PENALTY = 0.3


def handle_ta_completed(event: DomainEvent) -> None:
    payload = event.payload
    symbol = payload.get("symbol", "")
    if not symbol:
        logger.warning("ta_completed_missing_symbol", extra={"event_id": str(event.event_id)})
        return

    _save_pine_outputs(payload)

    packet = _build_packet(payload, event.occurred_at)

    try:
        bus = get_event_bus()
        ts = payload.get("snapshot_timestamp", event.occurred_at.isoformat())
        indicators = payload.get("indicators", {})

        sys_packet = DomainEvent.create(
            event_type="intelligence.PacketBuilt",
            payload={
                "symbol": symbol,
                "snapshot_id": payload.get("snapshot_id", ""),
                "exchange": payload.get("exchange", ""),
                "timeframe": payload.get("timeframe", ""),
                "snapshot_timestamp": ts,
                "indicators": indicators,
                "price": payload.get("price", {}),
                "pine_id": payload.get("pine_id", ""),
                "pine_version": payload.get("pine_version", ""),
                "packet_data": _serialize_packet(packet),
            },
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )
        bus.publish(sys_packet)

        logger.info(
            "ta_completed_processed",
            extra={
                "symbol": symbol,
                "snapshot_id": payload.get("snapshot_id"),
                "correlation_id": str(event.correlation_id),
            },
        )
    except Exception as exc:
        logger.exception(
            "ta_completed_processing_failed",
            extra={"symbol": symbol, "error": str(exc)},
        )


def _save_pine_outputs(payload: dict[str, Any]) -> None:
    symbol = payload.get("symbol", "")
    timeframe = payload.get("timeframe", "")
    raw_indicators: dict[str, Any] = payload.get("indicators", {})
    raw_price: dict[str, Any] = payload.get("price", {})
    try:
        ts_str = payload.get("snapshot_timestamp", "")
        if ts_str:
            detected_ts = datetime.fromisoformat(ts_str)
        else:
            detected_ts = datetime.now(timezone.utc)
    except (ValueError, TypeError):
        detected_ts = datetime.now(timezone.utc)

    indicators: dict[str, Any] = dict(raw_indicators)
    indicators["current_price"] = raw_price.get("close", "0")

    try:
        PineOutput.objects.update_or_create(
            symbol=symbol,
            timeframe=timeframe,
            indicator_name="pine_composite",
            defaults={
                "values": indicators,
                "detected_timestamp": detected_ts,
                "source": "pine_script",
            },
        )
    except Exception as exc:
        logger.warning(
            "pine_output_save_failed",
            extra={"symbol": symbol, "error": str(exc)},
        )


def _to_decimal(value: Any) -> Decimal | None:
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _optional_decimal(value: Any) -> Decimal | None:
    if value is None:
        return None
    try:
        return Decimal(str(value))
    except (ValueError, TypeError, ArithmeticError):
        return None


def _optional_int(value: Any) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (ValueError, TypeError, ArithmeticError):
        return None


def _optional_levels(value: Any) -> tuple[Decimal, ...]:
    """Parse a payload list (or scalar) of levels into a tuple of Decimals."""
    if value is None:
        return ()
    items = value if isinstance(value, (list, tuple)) else [value]
    parsed: list[Decimal] = []
    for item in items:
        dec = _optional_decimal(item)
        if dec is not None:
            parsed.append(dec)
    return tuple(parsed)


def _optional_direction(value: Any) -> str | None:
    """Validate a Supertrend direction string (``up``/``down``), else None."""
    if not isinstance(value, str):
        return None
    lowered = value.strip().lower()
    return lowered if lowered in ("up", "down") else None


def _get_prev_close(symbol: str, price_data: dict[str, Any]) -> Decimal | None:
    prev_close_raw = price_data.get("prev_close")
    if prev_close_raw is not None:
        try:
            return Decimal(str(prev_close_raw))
        except (ValueError, TypeError, ArithmeticError):
            return None

    try:
        repo = TASnapshotRepository()
        snapshots = repo.find_by_symbol(symbol, limit=2)
        if len(snapshots) >= 2:
            prev = snapshots[1]
            for raw_key, raw_value in prev.raw_payload.items():
                canonical = CANONICAL_FIELD_MAP.get(str(raw_key).lower().strip(), str(raw_key).lower().strip())
                if canonical == "close":
                    return Decimal(str(raw_value))
    except Exception:
        pass
    return None


def _detect_regime_value(
    indicators: dict[str, Any], price_data: dict[str, Any]
) -> str | None:
    """Detect the deterministic market regime from the payload's pine values.

    Reuses the frozen ``detect_regime`` classifier (``apps.intelligence.domain.
    market_regime``) with the same inputs ``MarketContextService`` feeds it.
    Returns the regime string (e.g. ``"BULLISH"``) or ``None`` when the
    classifier inputs are unavailable. Additive and defensive — never raises.
    """
    from apps.intelligence.domain.market_regime import RegimeInput, detect_regime

    volume = _optional_int(price_data.get("volume")) or 0
    avg_volume_20d = _optional_int(price_data.get("avg_volume_20d")) or 0
    volume_ratio = float(volume) / float(avg_volume_20d) if avg_volume_20d > 0 else 1.0

    try:
        regime_input = RegimeInput(
            current_price=_optional_decimal(price_data.get("close")) or Decimal("0"),
            ema_20=_optional_decimal(indicators.get("ema_20")),
            ema_50=_optional_decimal(indicators.get("ema_50")),
            ema_200=_optional_decimal(indicators.get("ema_200")),
            rsi_14=_optional_decimal(indicators.get("rsi_14")),
            macd=_optional_decimal(indicators.get("macd")),
            macd_histogram=_optional_decimal(indicators.get("macd_histogram")),
            bb_upper=_optional_decimal(indicators.get("bb_upper")),
            bb_lower=_optional_decimal(indicators.get("bb_lower")),
            atr_14=_optional_decimal(indicators.get("atr_14")),
            avg_atr_20d=_optional_decimal(indicators.get("avg_atr_20d")),
            volume_ratio=volume_ratio,
            india_vix=_optional_decimal(indicators.get("india_vix")),
            sector_change_pct=_optional_decimal(indicators.get("sector_index_change_pct")),
            support_levels=_optional_levels(indicators.get("support_levels")),
            resistance_levels=_optional_levels(indicators.get("resistance_levels")),
        )
        return detect_regime(regime_input).regime.value
    except Exception:
        return None


def _build_macro_context() -> Any:
    """Build the point-in-time macro context as of the active clock.

    Defensive (additive-only contract): returns ``None`` when the provenance
    store is unavailable, so packet assembly never fails because macro data
    could not be fetched. ``as_of`` always comes from ``get_clock().now()`` —
    the simulated-clock binding that makes backtest replay point-in-time safe.
    """
    try:
        return get_context_builder().build(as_of=get_clock().now())
    except Exception as exc:
        logger.warning("macro_context_build_failed", extra={"error": str(exc)})
        return None


def _build_packet(payload: dict[str, Any], occurred_at: datetime) -> IntelligencePacket:
    symbol = payload.get("symbol", "UNKNOWN")
    indicators: dict[str, Any] = payload.get("indicators", {})
    price_data: dict[str, Any] = payload.get("price", {})

    current_price = _to_decimal(price_data.get("close")) or Decimal("0")
    open_price = _to_decimal(price_data.get("open")) or Decimal("0")
    high = _to_decimal(price_data.get("high")) or Decimal("0")
    low = _to_decimal(price_data.get("low")) or Decimal("0")

    change_pct_raw = price_data.get("change_pct")
    if change_pct_raw is not None:
        change_pct = _optional_decimal(change_pct_raw)
        prev_close = _get_prev_close(symbol, price_data)
    else:
        prev_close = _get_prev_close(symbol, price_data)
        if prev_close is not None and prev_close != Decimal("0"):
            change_pct = ((current_price - prev_close) / prev_close) * Decimal("100")
        else:
            change_pct = None

    price_ctx = PriceContext(
        current_price=current_price,
        open_price=open_price,
        high=high,
        low=low,
        prev_close=prev_close,
        change_pct=change_pct,
        volume=int(price_data.get("volume", 0)),
        avg_volume_20d=_optional_int(price_data.get("avg_volume_20d")) or 0,
        avg_volume_10d=_optional_int(price_data.get("avg_volume_10d")),
        circuit_status=CircuitStatus.NORMAL,
    )

    tech_ctx = TechnicalContext(
        rsi_14=_optional_decimal(indicators.get("rsi_14")),
        macd=_optional_decimal(indicators.get("macd")),
        macd_signal=_optional_decimal(indicators.get("macd_signal")),
        bb_upper=_optional_decimal(indicators.get("bb_upper")),
        bb_lower=_optional_decimal(indicators.get("bb_lower")),
        bb_width=_optional_decimal(indicators.get("bb_width")),
        vwap=_optional_decimal(indicators.get("vwap")),
        atr_14=_optional_decimal(indicators.get("atr_14")),
        ema_20=_optional_decimal(indicators.get("ema_20")),
        ema_50=_optional_decimal(indicators.get("ema_50")),
        ema_200=_optional_decimal(indicators.get("ema_200")),
        support_levels=_optional_levels(indicators.get("support_levels")),
        resistance_levels=_optional_levels(indicators.get("resistance_levels")),
        supertrend_value=_optional_decimal(indicators.get("supertrend_value")),
        supertrend_direction=_optional_direction(indicators.get("supertrend_direction")),
    )

    breadth_ctx = BreadthContext(
        sector_index_change_pct=_to_decimal(indicators.get("sector_index_change_pct")) or Decimal("0"),
        sector_advance_decline=_to_decimal(indicators.get("sector_advance_decline")) or Decimal("0"),
        nifty_change_pct=_to_decimal(indicators.get("nifty_change_pct")) or Decimal("0"),
        sensex_change_pct=_to_decimal(indicators.get("sensex_change_pct")) or Decimal("0"),
    )

    # No real news source is wired up yet (the news_feed app is an intentionally
    # empty scaffold pending NSE/BSE/Moneycontrol ToS review), so every packet
    # assembled here uses the unchecked NewsContext() default. Tag that absence
    # explicitly so "no news found" is distinguishable from "never checked".
    missing: list[str] = []
    missing.append("news")
    dq = DataQuality(
        quality_score=1.0 - (NEWS_MISSING_QUALITY_PENALTY * len(missing)),
        missing_sources=tuple(missing),
        stale_sources=(),
    )

    packet = IntelligencePacket(
        symbol=symbol,
        timestamp=occurred_at,
        freshness_validated=True,
        price_context=price_ctx,
        technical_context=tech_ctx,
        breadth_context=breadth_ctx,
        news_context=NewsContext(),
        macro_context=_build_macro_context(),
        data_quality=dq,
        regime=_detect_regime_value(indicators, price_data),
    )
    return _enrich_with_session_facts(packet)


def _enrich_with_session_facts(packet: IntelligencePacket) -> IntelligencePacket:
    """Fill session-fact fields (opening 15m candle, prev-day H/L, avg volume).

    These facts are derived from already-persisted ``market_data`` candles via
    ``SessionFactsService`` (read-only). The enrichment is additive and fully
    defensive: if the instrument cannot be resolved or the DB is unavailable,
    the packet is returned unchanged and the optional fields stay ``None``
    (rules then fail safe per the missing-data contract).
    """
    from dataclasses import replace

    from apps.market_data.application.session_facts_service import SessionFactsService
    from apps.market_data.infrastructure.repositories import InstrumentRepository
    from apps.common.domain.value_objects import Symbol
    from core.config import config

    try:
        instrument = InstrumentRepository().find_by_symbol(
            Symbol(exchange=config.default_exchange, tradingsymbol=packet.symbol)
        )
        if instrument is None:
            return packet

        facts = SessionFactsService()
        opening = facts.get_opening_15m_candle(
            instrument.instrument_token, packet.timestamp
        )
        prev_high, prev_low = facts.get_previous_day_ohlc(
            instrument.instrument_token, packet.timestamp
        )
        avg_volume_5d = facts.get_avg_daily_volume(
            instrument.instrument_token, packet.timestamp, days=5
        )
        avg_volume_10d = facts.get_avg_daily_volume(
            instrument.instrument_token, packet.timestamp, days=10
        )
        avg_volume_20d = facts.get_avg_daily_volume(
            instrument.instrument_token, packet.timestamp, days=20
        )
        opening_avg_volume = facts.get_avg_opening_15m_volume(
            instrument.instrument_token, packet.timestamp, days=10
        )
    except Exception:
        logger.debug("session_facts_unavailable", extra={"symbol": packet.symbol})
        return packet

    price = packet.price_context
    tech = packet.technical_context

    new_price = replace(
        price,
        avg_volume_5d=price.avg_volume_5d or avg_volume_5d,
        avg_volume_10d=price.avg_volume_10d or avg_volume_10d,
        avg_volume_20d=price.avg_volume_20d or (avg_volume_20d or 0),
    )
    new_tech = replace(
        tech,
        opening_15m_open=opening.open if opening else None,
        opening_15m_high=opening.high if opening else None,
        opening_15m_low=opening.low if opening else None,
        opening_15m_close=opening.close if opening else None,
        opening_15m_volume=opening.volume if opening else None,
        opening_15m_avg_volume=opening_avg_volume,
        prev_day_high=prev_high,
        prev_day_low=prev_low,
    )
    return replace(packet, price_context=new_price, technical_context=new_tech)


def _serialize_packet(packet: IntelligencePacket) -> dict[str, Any]:
    from dataclasses import asdict
    from core.events.event_bus import _EventEncoder
    import json
    return json.loads(json.dumps(asdict(packet), cls=_EventEncoder))
