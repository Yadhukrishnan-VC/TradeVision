"""
TradeVision AI — Intelligence pipeline event consumers.

PortfolioRiskContextBuilder
    Subscribes to ``intelligence:packet_ready``, reads the latest
    ``PositionSnapshot`` and ``RiskStateSnapshot`` from the EventBus at-or-before
    the packet's timestamp, attaches them, and republishes the enriched packet
    to ``intelligence:enriched``.

    This consumer is asset-agnostic — it never imports ``apps.portfolio`` or any
    ``PortfolioService``. All portfolio/risk data enters the EventBus via their
    respective services publishing to ``intelligence:position_snapshot`` and
    ``intelligence:risk_snapshot``.
"""

from __future__ import annotations

import dataclasses
import json
import logging
from datetime import datetime
from typing import Any

from core.events.event_bus import EventBus, EventChannel
from core.events.event_types import (
    EnrichedIntelligencePacket,
    IntelligencePacket,
    PositionSnapshot,
    RiskStateSnapshot,
)

logger = logging.getLogger(__name__)


_SNAPSHOT_TIMEOUT_MS: int = 5000
"""Max milliseconds to wait for a snapshot read response."""


class PortfolioRiskContextBuilder:
    """Event-driven portfolio/risk enrichment for IntelligencePackets.

    Run in a dedicated Celery worker or management command. Example::

        bus = EventBus.from_settings()
        builder = PortfolioRiskContextBuilder(bus)
        for msg in bus.subscribe_stream(
            EventChannel.INTELLIGENCE_PACKET_READY,
            consumer_group="intelligence-enrichment",
            consumer_name="worker-1",
        ):
            builder.handle(msg)
            bus.ack_event(msg.stream, "intelligence-enrichment", msg.entry_id)
    """

    def __init__(self, event_bus: EventBus) -> None:
        self._bus = event_bus

    def handle(self, message: Any) -> None:
        """Process a single ``INTELLIGENCE_PACKET_READY`` message.

        Args:
            message: A ``StreamMessage`` whose ``.data`` dict contains a
                     serialised ``IntelligencePacket`` under the ``"packet"`` key.

        Raises:
            ValueError: If the message payload is malformed.
        """
        raw = message.data
        if not isinstance(raw, dict):
            logger.warning("enrichment_skipped_malformed", extra={"payload": raw})
            return

        packet_data = raw.get("packet")
        if not packet_data:
            logger.warning(
                "enrichment_skipped_no_packet",
                extra={"stream": message.stream, "entry_id": message.entry_id},
            )
            return

        try:
            packet = self._deserialise_packet(packet_data)
        except (TypeError, ValueError, KeyError) as exc:
            logger.error(
                "enrichment_packet_deserialisation_failed",
                extra={"error": str(exc)},
            )
            return

        ts = packet.timestamp
        position = self._latest_snapshot(
            EventChannel.POSITION_SNAPSHOT,
            PositionSnapshot,
            ts,
        )
        risk = self._latest_snapshot(
            EventChannel.RISK_SNAPSHOT,
            RiskStateSnapshot,
            ts,
        )

        enriched = EnrichedIntelligencePacket(
            packet=packet,
            portfolio_context=position,
            risk_context=risk,
        )

        from core.events.event_bus import _EventEncoder

        enriched_payload = json.loads(
            json.dumps(dataclasses.asdict(enriched), cls=_EventEncoder)
        )
        self._bus.publish_raw(
            EventChannel.INTELLIGENCE_PACKET_ENRICHED,
            {"enriched_packet": enriched_payload},
        )

        logger.info(
            "packet_enriched",
            extra={
                "symbol": packet.symbol,
                "has_position": position is not None,
                "has_risk": risk is not None,
            },
        )

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _deserialise_packet(self, data: dict[str, Any]) -> IntelligencePacket:
        """Reconstruct an ``IntelligencePacket`` from a dict.

        The dict is expected to have come from ``dataclasses.asdict()``
        serialised via ``_EventEncoder`` (all fields are plain JSON types:
        strings for Decimal/UUID/Enum, ISO-8601 for datetime).
        """
        from core.events.event_types import (
            AggregateSentiment,
            AnnouncementContext,
            AnnouncementItem,
            BreadthContext,
            CircuitStatus,
            DataQuality,
            Deal,
            GlobalContext,
            InstitutionalContext,
            MarketTrend,
            MaterialityLevel,
            NewsContext,
            NewsItem,
            OptionsContext,
            PatternContext,
            PatternMatch,
            PendingEvent,
            PriceContext,
            TechnicalContext,
        )

        def _d(v: Any) -> Any:
            from decimal import Decimal
            if isinstance(v, str):
                try:
                    return Decimal(v)
                except Exception:
                    return v
            return v

        def _news_item(item: dict[str, Any]) -> NewsItem:
            return NewsItem(
                title=item["title"],
                source=item["source"],
                sentiment=AggregateSentiment(item["sentiment"]),
                materiality=MaterialityLevel(item["materiality"]),
                age_minutes=item["age_minutes"],
                url=item.get("url", ""),
            )

        def _announcement_item(item: dict[str, Any]) -> AnnouncementItem:
            return AnnouncementItem(
                announcement_type=item["announcement_type"],
                title=item["title"],
                materiality=MaterialityLevel(item["materiality"]),
                age_hours=item["age_hours"],
            )

        def _pending_event(ev: dict[str, Any]) -> PendingEvent:
            return PendingEvent(
                event_type=ev["event_type"],
                scheduled_at=datetime.fromisoformat(ev["scheduled_at"]),
            )

        def _deal(d: dict[str, Any]) -> Deal:
            return Deal(
                entity=d["entity"],
                quantity=d["quantity"],
                price=_d(d["price"]),
                side=d["side"],
            )

        def _pattern_match(pm: dict[str, Any]) -> PatternMatch:
            return PatternMatch(
                date_str=pm["date_str"],
                similarity_score=_d(pm["similarity_score"]),
                outcome_summary=pm["outcome_summary"],
            )

        pc = data.get("price_context", {})
        tc = data.get("technical_context", {})
        bc = data.get("breadth_context", {})
        nc = data.get("news_context", {})
        dq = data.get("data_quality", {})

        headlines = tuple(
            _news_item(h) for h in nc.get("headlines", ())
        )
        agg_sent = AggregateSentiment(
            nc.get("aggregate_sentiment", AggregateSentiment.NEUTRAL.value)
        )

        def _optional_ctx(key: str, builder: Any) -> Any:
            raw = data.get(key)
            if raw is None:
                return None
            return builder(raw)

        parsed = {
            "symbol": data["symbol"],
            "timestamp": datetime.fromisoformat(data["timestamp"]),
            "freshness_validated": data["freshness_validated"],
            "price_context": PriceContext(
                current_price=_d(pc["current_price"]),
                open_price=_d(pc.get("open_price", 0)),
                high=_d(pc.get("high", 0)),
                low=_d(pc.get("low", 0)),
                prev_close=_d(pc.get("prev_close")),
                change_pct=_d(pc.get("change_pct")),
                volume=pc["volume"],
                avg_volume_20d=pc["avg_volume_20d"],
                circuit_status=CircuitStatus(pc["circuit_status"]),
            ),
            "technical_context": TechnicalContext(
                trend=MarketTrend(tc.get("trend", MarketTrend.SIDEWAYS.value)),
                rsi_14=_d(tc.get("rsi_14")),
                macd=_d(tc.get("macd")),
                macd_signal=_d(tc.get("macd_signal")),
                macd_histogram=_d(tc.get("macd_histogram")),
                bb_upper=_d(tc.get("bb_upper")),
                bb_lower=_d(tc.get("bb_lower")),
                bb_width=_d(tc.get("bb_width")),
                vwap=_d(tc.get("vwap")),
                atr_14=_d(tc.get("atr_14")),
                ema_20=_d(tc.get("ema_20")),
                ema_50=_d(tc.get("ema_50")),
                ema_200=_d(tc.get("ema_200")),
                support_levels=tuple(_d(s) for s in tc.get("support_levels", [])),
                resistance_levels=tuple(_d(r) for r in tc.get("resistance_levels", [])),
            ),
            "breadth_context": BreadthContext(
                sector_index_change_pct=_d(bc["sector_index_change_pct"]),
                sector_advance_decline=_d(bc["sector_advance_decline"]),
                nifty_change_pct=_d(bc["nifty_change_pct"]),
                sensex_change_pct=_d(bc["sensex_change_pct"]),
            ),
            "news_context": NewsContext(
                headlines=headlines,
                aggregate_sentiment=agg_sent,
            ),
            "data_quality": DataQuality(
                quality_score=dq.get("quality_score", 1.0),
                missing_sources=tuple(dq.get("missing_sources", ())),
                stale_sources=tuple(dq.get("stale_sources", ())),
            ),
            "options_context": _optional_ctx("options_context", lambda r: OptionsContext(
                pcr=_d(r["pcr"]),
                max_pain=_d(r["max_pain"]),
                atm_iv=_d(r["atm_iv"]),
                oi_change_pct=_d(r["oi_change_pct"]),
                unusual_activity=r.get("unusual_activity", False),
            )),
            "announcement_context": _optional_ctx("announcement_context", lambda r: AnnouncementContext(
                recent_announcements=tuple(
                    _announcement_item(a) for a in r.get("recent_announcements", ())
                ),
                pending_events=tuple(
                    _pending_event(e) for e in r.get("pending_events", ())
                ),
            )),
            "global_context": _optional_ctx("global_context", lambda r: GlobalContext(
                dow_futures_pct=_d(r["dow_futures_pct"]),
                sgx_nifty_pct=_d(r["sgx_nifty_pct"]),
                crude_oil_pct=_d(r["crude_oil_pct"]),
                usd_inr_change_pct=_d(r["usd_inr_change_pct"]),
                vix=_d(r["vix"]),
                india_vix=_d(r["india_vix"]),
                fii_net_flow_cr=_d(r["fii_net_flow_cr"]),
            )),
            "institutional_context": _optional_ctx("institutional_context", lambda r: InstitutionalContext(
                bulk_deals=tuple(_deal(d) for d in r.get("bulk_deals", ())),
                block_deals=tuple(_deal(d) for d in r.get("block_deals", ())),
            )),
            "pattern_context": _optional_ctx("pattern_context", lambda r: PatternContext(
                similar_dates=tuple(
                    _pattern_match(pm) for pm in r.get("similar_dates", ())
                ),
                top_analogue_summary=r.get("top_analogue_summary", ""),
            )),
        }
        return IntelligencePacket(**parsed)

    def _latest_snapshot(
        self,
        stream: str,
        cls: type[PositionSnapshot | RiskStateSnapshot],
        at_or_before: datetime,
    ) -> PositionSnapshot | RiskStateSnapshot | None:
        """Return the most recent snapshot from *stream* at-or-before *at_or_before*.

        Uses ``XREVRANGE`` with a timestamp-based upper bound to find the
        closest preceding snapshot entry.  Returns ``None`` when no snapshot
        exists for the given time window.
        """
        ts_ms = int(at_or_before.timestamp() * 1000)
        max_id = f"{ts_ms}-0"
        min_id = "0-0"

        try:
            redis = self._bus._redis
            entries = redis.xrevrange(stream, max=max_id, min=min_id, count=1)
        except Exception as exc:
            logger.error(
                "snapshot_read_failed",
                extra={"stream": stream, "error": str(exc)},
            )
            return None

        if not entries:
            return None

        _entry_id, raw = entries[0]
        payload_raw = raw.get("payload", "{}")
        try:
            data = json.loads(payload_raw)
        except json.JSONDecodeError:
            logger.warning("snapshot_malformed", extra={"stream": stream})
            return None

        return self._deserialise_snapshot(cls, data)

    @staticmethod
    def _deserialise_snapshot(
        cls: type[PositionSnapshot | RiskStateSnapshot],
        data: dict[str, Any],
    ) -> PositionSnapshot | RiskStateSnapshot | None:
        """Reconstruct a snapshot dataclass from a serialised dict."""
        from decimal import Decimal

        def _d(v: Any) -> Any:
            if isinstance(v, str):
                try:
                    return Decimal(v)
                except Exception:
                    return v
            return v

        try:
            if cls is PositionSnapshot:
                return PositionSnapshot(
                    symbol=data["symbol"],
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    has_position=data["has_position"],
                    quantity=data.get("quantity", 0),
                    entry_price=_d(data.get("entry_price")),
                    current_price=_d(data.get("current_price")),
                    unrealized_pnl_pct=_d(data.get("unrealized_pnl_pct")),
                    days_in_position=data.get("days_in_position", 0),
                    stop_loss=_d(data.get("stop_loss")),
                    target_price=_d(data.get("target_price")),
                )
            if cls is RiskStateSnapshot:
                return RiskStateSnapshot(
                    timestamp=datetime.fromisoformat(data["timestamp"]),
                    portfolio_drawdown_pct=_d(data.get("portfolio_drawdown_pct")),
                    portfolio_beta=_d(data.get("portfolio_beta")),
                    concentration_risk=data.get("concentration_risk", "LOW"),
                    var_95_pct=_d(data.get("var_95_pct")),
                    india_vix=_d(data.get("india_vix")),
                )
        except (KeyError, TypeError, ValueError) as exc:
            logger.warning(
                "snapshot_deserialisation_failed",
                extra={"snapshot_type": cls.__name__, "error": str(exc)},
            )
            return None

        return None
