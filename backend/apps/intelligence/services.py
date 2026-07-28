"""
TradeVision AI — Market Context Service.

Assembles the SignalContext from IntelligencePacket, PineScript outputs,
portfolio state, risk state, and trading history. This is the input to the
AI Brain's ContextBuilder.

The service performs deterministic enrichment only — no AI calls.
"""

from __future__ import annotations

import dataclasses
import json
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from django.utils import timezone

from apps.intelligence.domain.market_regime import (
    MarketRegime,
    MultiTimeframeAlignment,
    RegimeInput,
    RegimeOutput,
    detect_mtf_alignment,
    detect_regime,
)
from core.events.event_bus import EventBus, EventChannel
from core.events.event_types import IntelligencePacket

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class SignalContextRef:
    """Lightweight reference to a Trading Core signal that triggered context assembly."""

    signal_id: uuid.UUID
    direction: str
    confidence_hint: float


@dataclass(frozen=True)
class SignalContext:
    """Complete signal context assembled for the AI Brain.

    This is the Intelligence Domain's input to the AI. It includes all
    signal sources that the AI reasons about.
    """

    symbol: str
    timestamp: datetime
    market_regime: MarketRegime
    regime_evidence: tuple[str, ...] = ()
    multi_timeframe_alignment: MultiTimeframeAlignment = MultiTimeframeAlignment.NEUTRAL

    pine_outputs: dict[str, dict[str, Any]] = field(default_factory=dict)
    news_headlines: list[dict[str, Any]] = field(default_factory=list)
    sector_context: str = ""
    event_data: dict[str, Any] = field(default_factory=dict)
    data_quality_note: str = ""
    trading_signal: SignalContextRef | None = None


@dataclass(frozen=True)
class PortfolioState:
    """Current portfolio state relevant to AI reasoning."""

    has_position: bool = False
    position_size_pct: float = 0.0
    unrealized_pnl_pct: float = 0.0
    days_in_position: int = 0
    entry_price: float | None = None
    current_price: float | None = None
    stop_loss: float | None = None
    target_price: float | None = None


@dataclass(frozen=True)
class RiskState:
    """Current risk metrics relevant to AI reasoning."""

    portfolio_drawdown_pct: float = 0.0
    india_vix: float = 15.0
    portfolio_beta: float = 1.0
    concentration_risk: str = "LOW"
    var_95_pct: float = 0.0


class IntelligenceService:
    """Publishes the base IntelligencePacket for enrichment and downstream consumption.

    ``build_packet()`` publishes to ``EventChannel.INTELLIGENCE_PACKET_READY``.
    Portfolio/risk enrichment is handled asynchronously by
    ``PortfolioRiskContextBuilder``, which consumes the ready event and
    republishes to ``EventChannel.INTELLIGENCE_PACKET_ENRICHED``.
    """

    def __init__(self, event_bus: EventBus | None = None) -> None:
        self._bus = event_bus

    def build_packet(self, packet: IntelligencePacket) -> str:
        """Publish a base IntelligencePacket to the enrichment pipeline.

        Args:
            packet: Fully assembled base packet (must include regime, pine
                    outputs, news, sector context, and data quality).

        Returns:
            The EventBus stream entry ID.

        Raises:
            EventBusError: If publication fails.
        """
        bus = self._bus or EventBus.from_settings()
        payload = dataclasses.asdict(packet)
        from core.events.event_bus import _EventEncoder

        return bus.publish_raw(
            EventChannel.INTELLIGENCE_PACKET_READY,
            {"packet": json.loads(json.dumps(payload, cls=_EventEncoder))},
        )


class MarketContextService:
    """Builds the SignalContext from the IntelligencePacket and enrichments.

    Portfolio/risk enrichment was previously handled via direct-call
    ``enrich_with_portfolio()`` / ``enrich_with_risk()`` stubs (both removed).
    Enrichment now flows through the event pipeline:
    ``INTELLIGENCE_PACKET_READY`` → ``PortfolioRiskContextBuilder`` →
    ``INTELLIGENCE_PACKET_ENRICHED``.
    """

    def build_signal_context(
        self,
        symbol: str,
        packet: IntelligencePacket,
        timeframes: list[str] | None = None,
        trading_signal: SignalContextRef | None = None,
    ) -> SignalContext:
        """Build the base SignalContext from an IntelligencePacket.

        Args:
            symbol: NSE/BSE stock symbol.
            packet: The assembled IntelligencePacket.
            timeframes: Timeframes to query for Pine output (default: 1D, 4h, 1h).

        Returns:
            A populated SignalContext.
        """
        if timeframes is None:
            timeframes = ["1D", "4h", "1h"]

        pine_outputs = self._get_pine_outputs(symbol, timeframes)
        regime = self._detect_regime(packet, pine_outputs)

        mtf = self._detect_mtf(pine_outputs)

        news = [
            {
                "title": item.title,
                "source": item.source,
                "sentiment": item.sentiment.value if hasattr(item.sentiment, "value") else str(item.sentiment),
                "materiality": item.materiality.value if hasattr(item.materiality, "value") else str(item.materiality),
                "age_minutes": item.age_minutes,
            }
            for item in packet.news_context.headlines
        ]

        sector_change = float(packet.breadth_context.sector_index_change_pct)
        sector_direction = "up" if sector_change > 0 else "down" if sector_change < 0 else "flat"
        sector_context = (
            f"Sector change: {sector_change:+.2f}% ({sector_direction}). "
            f"Nifty: {float(packet.breadth_context.nifty_change_pct):+.2f}%. "
            f"Sensex: {float(packet.breadth_context.sensex_change_pct):+.2f}%."
        )

        dq = packet.data_quality
        dq_notes = []
        if dq.missing_sources:
            dq_notes.append(f"Missing sources: {', '.join(dq.missing_sources)}")
        if dq.stale_sources:
            dq_notes.append(f"Stale sources: {', '.join(dq.stale_sources)}")
        if dq.quality_score < 0.8:
            dq_notes.append(f"Quality score: {dq.quality_score:.2f}")

        event_data = {
            "current_price": float(packet.price_context.current_price),
            "change_pct": float(packet.price_context.change_pct) if packet.price_context.change_pct is not None else 0.0,
            "volume": packet.price_context.volume,
            "volume_ratio": (
                packet.price_context.volume / packet.price_context.avg_volume_20d
                if packet.price_context.avg_volume_20d > 0
                else 0
            ),
            "circuit_status": packet.price_context.circuit_status.value,
            "open": float(packet.price_context.open_price),
            "high": float(packet.price_context.high),
            "low": float(packet.price_context.low),
            "prev_close": float(packet.price_context.prev_close) if packet.price_context.prev_close is not None else 0.0,
        }

        logger.info(
            "signal_context_built",
            extra={
                "symbol": symbol,
                "regime": regime.regime.value,
                "mtf": mtf.value,
                "quality_score": dq.quality_score,
            },
        )

        return SignalContext(
            symbol=symbol,
            timestamp=timezone.now(),
            market_regime=regime.regime,
            regime_evidence=regime.supporting_evidence,
            multi_timeframe_alignment=mtf,
            pine_outputs=pine_outputs,
            news_headlines=news,
            sector_context=sector_context,
            event_data=event_data,
            data_quality_note="; ".join(dq_notes) if dq_notes else "All sources fresh and available.",
            trading_signal=trading_signal,
        )

    def _get_pine_outputs(
        self, symbol: str, timeframes: list[str]
    ) -> dict[str, dict[str, Any]]:
        """Query Pine Script outputs from the database.

        Returns a dict keyed by timeframe, each containing the latest
        indicator values for that timeframe.  Populated by signals_engine;
        no longer a stub.
        """
        from apps.intelligence.models import PineOutput

        rows = PineOutput.objects.filter(
            symbol=symbol,
            timeframe__in=timeframes,
            indicator_name="pine_composite",
        )
        outputs: dict[str, dict[str, Any]] = {}
        for row in rows:
            outputs[row.timeframe] = dict(row.values) if row.values else {}
        for tf in timeframes:
            if tf not in outputs:
                outputs[tf] = {}
        return outputs

    def _detect_regime(
        self,
        packet: IntelligencePacket,
        pine_outputs: dict[str, dict[str, Any]],
    ) -> RegimeOutput:
        """Detect market regime from the IntelligencePacket and Pine outputs."""
        daily = pine_outputs.get("1D", {})

        regime_input = RegimeInput(
            current_price=packet.price_context.current_price,
            ema_20=self._to_decimal(daily.get("ema_20")),
            ema_50=self._to_decimal(daily.get("ema_50")),
            ema_200=self._to_decimal(daily.get("ema_200")),
            rsi_14=self._to_decimal(daily.get("rsi_14")),
            macd=self._to_decimal(daily.get("macd")),
            macd_histogram=self._to_decimal(daily.get("macd_histogram")),
            bb_upper=self._to_decimal(daily.get("bb_upper")),
            bb_lower=self._to_decimal(daily.get("bb_lower")),
            atr_14=self._to_decimal(daily.get("atr_14")),
            avg_atr_20d=self._to_decimal(daily.get("avg_atr_20d")),
            volume_ratio=float(packet.price_context.volume) / float(packet.price_context.avg_volume_20d)
            if packet.price_context.avg_volume_20d > 0
            else 1.0,
            india_vix=self._to_decimal(daily.get("india_vix"))
            if packet.global_context is None
            else packet.global_context.india_vix,
            sector_change_pct=packet.breadth_context.sector_index_change_pct,
            support_levels=packet.technical_context.support_levels,
            resistance_levels=packet.technical_context.resistance_levels,
        )
        return detect_regime(regime_input)

    def _detect_mtf(
        self, pine_outputs: dict[str, dict[str, Any]]
    ) -> MultiTimeframeAlignment:
        """Detect multi-timeframe alignment."""
        trends: dict[str, str] = {}
        for tf in ["1D", "4h", "1h"]:
            data = pine_outputs.get(tf, {})
            trend = data.get("trend", "SIDEWAYS")
            trend_str = str(trend).upper()
            if "UP" in trend_str:
                trends[tf] = "UP"
            elif "DOWN" in trend_str:
                trends[tf] = "DOWN"
            else:
                trends[tf] = "SIDEWAYS"

        return detect_mtf_alignment(
            daily_trend=trends.get("1D", "SIDEWAYS"),
            hourly_trend=trends.get("1h", "SIDEWAYS"),
            four_hour_trend=trends.get("4h", "SIDEWAYS"),
        )

    @staticmethod
    def _to_decimal(value: Any) -> Any:
        """Convert a value to Decimal if it's not None."""
        if value is None:
            return None
        from decimal import Decimal
        return Decimal(str(value))
