"""E2E paper-trading pipeline integration test.

Publishes a real ``technical_analysis.TechnicalAnalysisCompleted`` event
through the FakeEventBus and proves the genuine event-driven cascade:

    TechnicalAnalysisCompleted
    -> intelligence.PacketBuilt
    -> rule_engine.RuleFired (long_momentum_v1)
    -> risk_management.RiskApproved
    -> ExecutionRequest -> Order -> Fill (paper broker)

Every consumer is the real production handler registered explicitly on the
bus (intelligence, rule_engine, risk_management). The AI branch is
deliberately NOT registered, so it is inert for this flow. No provider, no
real broker, no network — everything runs through FakeEventBus + eager
Celery + PaperBroker.

Correlation traceability note: the PacketBuilt hop carries the original TA
correlation id. From RuleFired onward the stable trace key is the PacketBuilt
``event_id`` — ``RuleEvaluationService.publish_rule_firing`` sets
``correlation_id=analysis_event_id`` (the PacketBuilt event id) and the risk/
execution hops thread that same key plus ``causation_id``=the immediately
preceding event id. The test asserts the values the running code produces.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

pytestmark = pytest.mark.django_db


def _ta_payload(symbol: str = "RELIANCE") -> dict:
    """A real TA payload on which LongMomentumRule legitimately fires.

    - opening 15m candle: open == low == 100.00 (from seeded market_data)
    - current price 103.00 is >2% above the session open (100.00)
    - volume 1,000,000 > avg_volume_10d (100,000) * 3
    - vwap 101.50 and ema_20 102.00 both below the current price
    """
    return {
        "symbol": symbol,
        "snapshot_id": str(uuid.uuid4()),
        "exchange": "NSE",
        "timeframe": "1D",
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "indicators": {
            "vwap": "101.50",
            "ema_20": "102.00",
        },
        "price": {
            "close": "103.00",
            "open": "100.00",
            "high": "104.00",
            "low": "99.00",
            "volume": 1_000_000,
            "avg_volume_10d": 100_000,
        },
        "pine_id": "e2e_paper",
        "pine_version": "5",
    }


def _ta_short_breakdown_payload(symbol: str = "RELIANCE") -> dict:
    """A real TA payload on which VolatilityBreakoutRule fires short.

    - prev-day candle low 108.00 (seeded by the test) with a wide range
    - current price 103.00 < prev-day low -> direction "short"
    - session range (104.00 - 99.00 = 5.00) >= 1.5 x ATR (3.00)
    - Supertrend(10,2) value 104.50 > entry -> decision-grade stop for a short
    - volume far below every average-volume threshold, so no other rule fires
    """
    return {
        "symbol": symbol,
        "snapshot_id": str(uuid.uuid4()),
        "exchange": "NSE",
        "timeframe": "1D",
        "snapshot_timestamp": datetime.now(timezone.utc).isoformat(),
        "indicators": {
            "atr_14": "3.00",
            "supertrend_value": "104.50",
            "supertrend_direction": "down",
            "vwap": "105.00",
            "ema_20": "104.00",
        },
        "price": {
            "close": "103.00",
            "open": "103.50",
            "high": "104.00",
            "low": "99.00",
            "volume": 100_000,
            "avg_volume_10d": 1_000_000,
        },
        "pine_id": "e2e_paper",
        "pine_version": "5",
    }


def _seed_previous_day_candle(monkeypatch) -> None:
    """Create the previous trading day's 1D candle (high/low for the VS rule).

    The session-facts enrichment fills ``prev_day_high``/``prev_day_low``
    from persisted candles; without a previous-day candle the
    VolatilityBreakoutRule cannot fire. Uses the same IST/UTC and
    always-trading-day conventions as ``seed_session_facts``.
    """
    from datetime import datetime, time, timedelta, timezone
    from decimal import Decimal
    from zoneinfo import ZoneInfo

    from apps.market_data.infrastructure.models import Candle
    from core.market_calendar import MarketCalendar

    _IST = ZoneInfo("Asia/Kolkata")
    monkeypatch.setattr(MarketCalendar, "is_trading_day", lambda self, day: True)

    session_day = datetime.now(timezone.utc).astimezone(_IST).date()
    prev_day = session_day - timedelta(days=1)
    prev_start_utc = datetime.combine(
        prev_day, time(0, 0), tzinfo=_IST
    ).astimezone(timezone.utc)

    Candle.objects.create(
        instrument_id=1002,
        timeframe="1D",
        timestamp=prev_start_utc,
        open=Decimal("112.00"),
        high=Decimal("112.00"),
        low=Decimal("108.00"),
        close=Decimal("110.00"),
        volume=1_000_000,
    )


def _register_pipeline(bus, *handler_fixtures) -> None:
    for register in handler_fixtures:
        register(bus)


def _publish_ta_event(bus, *, correlation_id: uuid.UUID | None = None) -> DomainEvent:
    event = DomainEvent.create(
        event_type="technical_analysis.TechnicalAnalysisCompleted",
        payload=_ta_payload(),
        correlation_id=correlation_id or uuid.uuid4(),
    )
    bus.publish(event)
    return event


def _publish_ta_short_breakdown_event(
    bus, *, correlation_id: uuid.UUID | None = None
) -> DomainEvent:
    event = DomainEvent.create(
        event_type="technical_analysis.TechnicalAnalysisCompleted",
        payload=_ta_short_breakdown_payload(),
        correlation_id=correlation_id or uuid.uuid4(),
    )
    bus.publish(event)
    return event


class TestE2EPaperTradingPipeline:
    def test_ta_event_drives_paper_order_to_fill(
        self,
        account,
        register_intelligence_handlers,
        register_rule_engine_handlers,
        register_risk_handlers,
        seed_session_facts,
    ) -> None:
        from apps.execution.domain.value_objects import side_for_rule
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.intelligence.models import PineOutput
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.rule_engine.infrastructure.models import RuleExecution

        bus = get_event_bus()
        _register_pipeline(
            bus,
            register_intelligence_handlers,
            register_rule_engine_handlers,
            register_risk_handlers,
        )

        correlation_id = uuid.uuid4()
        ta_event = _publish_ta_event(bus, correlation_id=correlation_id)

        # ------------------------------------------------------------------
        # Stage 1: Intelligence persists the Pine output and builds PacketBuilt
        # ------------------------------------------------------------------
        packet_events = [
            e for e in bus.published_events
            if e.event_type == "intelligence.PacketBuilt"
        ]
        assert len(packet_events) == 1
        packet_event = packet_events[0]
        assert packet_event.correlation_id == correlation_id
        assert packet_event.causation_id == ta_event.event_id

        assert PineOutput.objects.filter(
            symbol="RELIANCE",
            timeframe="1D",
            indicator_name="pine_composite",
        ).exists()

        # Real values survived into the packet (non-placeholder, matching input).
        packet_data = packet_event.payload["packet_data"]
        price_ctx = packet_data["price_context"]
        tech_ctx = packet_data["technical_context"]
        assert Decimal(price_ctx["current_price"]) == Decimal("103.00")
        assert Decimal(price_ctx["open_price"]) == Decimal("100.00")
        assert price_ctx["volume"] == 1_000_000
        assert price_ctx["avg_volume_10d"] == 100_000
        assert Decimal(tech_ctx["vwap"]) == Decimal("101.50")
        assert Decimal(tech_ctx["ema_20"]) == Decimal("102.00")
        assert Decimal(tech_ctx["opening_15m_open"]) == Decimal("100.00")
        assert Decimal(tech_ctx["opening_15m_low"]) == Decimal("100.00")

        # ------------------------------------------------------------------
        # Stage 2: Rule Engine evaluates and LongMomentumRule fires once
        # ------------------------------------------------------------------
        fired_events = [
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
        ]
        assert len(fired_events) == 1
        fired_event = fired_events[0]
        assert fired_event.payload["rule_id"] == "long_momentum_v1"
        assert fired_event.payload["symbol"] == "RELIANCE"
        assert fired_event.payload["trigger_data"]["entry_price"] == "103.00"
        assert Decimal(fired_event.payload["trigger_data"]["stop_loss"]) == Decimal("100.00")

        analysis_event_id = uuid.UUID(fired_event.payload["analysis_event_id"])
        assert analysis_event_id == packet_event.event_id

        execution = RuleExecution.objects.get(
            analysis_event_id=analysis_event_id,
            rule_id="long_momentum_v1",
        )
        assert execution.symbol == "RELIANCE"
        assert execution.published_event_id == fired_event.event_id
        assert execution.trigger_data["entry_price"] == "103.00"
        assert Decimal(execution.trigger_data["stop_loss"]) == Decimal("100.00")

        # ------------------------------------------------------------------
        # Stage 3: Risk Management evaluates and approves
        # ------------------------------------------------------------------
        approved_events = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved_events) == 1
        approved_event = approved_events[0]
        assert approved_event.payload["symbol"] == "RELIANCE"
        assert approved_event.payload["rule_id"] == "long_momentum_v1"
        assert approved_event.payload["entry_price"] == "103.00"
        assert Decimal(approved_event.payload["stop_loss"]) == Decimal("100.00")

        decision = RiskDecisionExecution.objects.get(
            analysis_event_id=analysis_event_id,
            rule_id="long_momentum_v1",
        )
        assert decision.status == "APPROVED"
        assert decision.published_event_id == approved_event.event_id
        assert decision.entry_price == "103.00"
        assert Decimal(decision.stop_loss) == Decimal("100.00")
        assert decision.position_size > 0

        # ------------------------------------------------------------------
        # Stage 4: Execution intakes and the paper broker fills the order
        # ------------------------------------------------------------------
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

        request = ExecutionRequest.objects.get()
        order = Order.objects.get()

        assert request.status == "ORDER_CREATED"
        assert request.symbol == "RELIANCE"
        assert request.rule_id == "long_momentum_v1"
        assert request.risk_approved_event_id == approved_event.event_id
        assert request.account_id == account.id
        assert request.quantity == order.quantity
        assert request.quantity > 0

        assert order.status == "FILLED"
        assert order.symbol == "RELIANCE"
        assert order.side == side_for_rule("long_momentum_v1").value
        assert order.order_type == "market"
        assert order.filled_quantity == order.quantity
        assert order.avg_fill_price == Decimal("103.00")
        assert order.entry_price == Decimal("103.00")
        assert order.stop_loss == Decimal("100.00")

        assert Fill.objects.count() >= 1
        fill = Fill.objects.get(order=order, sequence=1)
        assert fill.quantity == order.quantity
        assert fill.price == Decimal("103.00")

        money_fields = [
            order.entry_price,
            order.stop_loss,
            order.avg_fill_price,
            order.filled_quantity,
            fill.price,
            fill.quantity,
        ]
        assert all(v is not None and v != Decimal(0) for v in money_fields)

        # ------------------------------------------------------------------
        # Correlation / causation traceability
        # ------------------------------------------------------------------
        assert packet_event.correlation_id == correlation_id
        assert packet_event.causation_id == ta_event.event_id
        assert fired_event.correlation_id == packet_event.event_id
        assert approved_event.correlation_id == packet_event.event_id
        assert approved_event.causation_id == fired_event.event_id
        assert request.correlation_id == approved_event.correlation_id
        assert request.causation_id == approved_event.causation_id
        assert order.correlation_id == request.correlation_id

        # ------------------------------------------------------------------
        # Broker lifecycle events published; AI and Pattern branches inert
        # ------------------------------------------------------------------
        assert [e for e in bus.published_events if e.event_type == "orders.OrderPlaced"]
        assert [e for e in bus.published_events if e.event_type == "orders.OrderFilled"]
        assert not [e for e in bus.published_events
                    if e.event_type == "ai_engine.RecommendationIssued"]
        assert not [e for e in bus.published_events
                    if e.event_type.startswith("pattern_engine.")]

    def test_short_breakdown_drives_short_order_to_fill(
        self,
        account,
        monkeypatch,
        register_intelligence_handlers,
        register_rule_engine_handlers,
        register_risk_handlers,
        seed_session_facts,
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.rule_engine.infrastructure.models import RuleExecution

        _seed_previous_day_candle(monkeypatch)

        bus = get_event_bus()
        _register_pipeline(
            bus,
            register_intelligence_handlers,
            register_rule_engine_handlers,
            register_risk_handlers,
        )

        correlation_id = uuid.uuid4()
        _publish_ta_short_breakdown_event(bus, correlation_id=correlation_id)

        # ------------------------------------------------------------------
        # Stage 1: VolatilityBreakoutRule fires the short breakdown once
        # ------------------------------------------------------------------
        fired_events = [
            e for e in bus.published_events
            if e.event_type == "rule_engine.RuleFired"
        ]
        assert len(fired_events) == 1
        fired_event = fired_events[0]
        assert fired_event.payload["rule_id"] == "volatility_breakout_v1"
        assert fired_event.payload["event_type"] == "breakdown"
        assert fired_event.payload["trigger_data"]["direction"] == "short"
        assert Decimal(fired_event.payload["trigger_data"]["entry_price"]) == Decimal("103.00")
        assert fired_event.payload["trigger_data"]["stop_loss"] == "104.50"

        analysis_event_id = uuid.UUID(fired_event.payload["analysis_event_id"])
        execution = RuleExecution.objects.get(
            analysis_event_id=analysis_event_id,
            rule_id="volatility_breakout_v1",
        )
        assert execution.trigger_data["direction"] == "short"

        # ------------------------------------------------------------------
        # Stage 2: Risk Management approves with direction short
        # ------------------------------------------------------------------
        approved_events = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved_events) == 1
        approved_event = approved_events[0]
        assert approved_event.payload["rule_id"] == "volatility_breakout_v1"
        assert approved_event.payload["event_type"] == "breakdown"
        assert approved_event.payload["direction"] == "short"
        assert approved_event.payload["entry_price"] == "103.00"

        decision = RiskDecisionExecution.objects.get(
            analysis_event_id=analysis_event_id,
            rule_id="volatility_breakout_v1",
        )
        assert decision.status == "APPROVED"
        assert decision.position_size > 0

        # ------------------------------------------------------------------
        # Stage 3: Execution opens a SHORT order filled by the paper broker
        # ------------------------------------------------------------------
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

        request = ExecutionRequest.objects.get()
        order = Order.objects.get()

        assert request.status == "ORDER_CREATED"
        assert request.risk_approved_event_id == approved_event.event_id
        assert request.rule_id == "volatility_breakout_v1"
        assert request.side == "SHORT"

        assert order.status == "FILLED"
        assert order.symbol == "RELIANCE"
        assert order.side == "SHORT"
        assert order.order_type == "market"
        assert order.filled_quantity == order.quantity
        assert order.avg_fill_price == Decimal("103.00")
        assert order.entry_price == Decimal("103.00")
        assert order.stop_loss == Decimal("104.50")

        assert Fill.objects.count() >= 1

        # ------------------------------------------------------------------
        # Correlation traceability through the short chain
        # ------------------------------------------------------------------
        packet_event = next(
            e for e in bus.published_events if e.event_type == "intelligence.PacketBuilt"
        )
        assert fired_event.correlation_id == packet_event.event_id
        assert approved_event.causation_id == fired_event.event_id
        assert request.correlation_id == approved_event.correlation_id

    def test_rule_and_risk_layers_are_idempotent_on_redelivery(
        self,
        account,
        register_intelligence_handlers,
        register_rule_engine_handlers,
        register_risk_handlers,
        seed_session_facts,
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.risk_management.infrastructure.event_handlers import (
            handle_rule_fired,
        )
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.rule_engine.infrastructure.models import RuleExecution
        from apps.rule_engine.infrastructure.tasks import evaluate_packet

        bus = get_event_bus()
        _register_pipeline(
            bus,
            register_intelligence_handlers,
            register_rule_engine_handlers,
            register_risk_handlers,
        )

        ta_event = _publish_ta_event(bus)

        packet_event = next(
            e for e in bus.published_events if e.event_type == "intelligence.PacketBuilt"
        )
        fired_event = next(
            e for e in bus.published_events if e.event_type == "rule_engine.RuleFired"
        )
        analysis_event_id = uuid.UUID(fired_event.payload["analysis_event_id"])

        assert RuleExecution.objects.filter(
            analysis_event_id=analysis_event_id,
            rule_id="long_momentum_v1",
        ).count() == 1
        assert RiskDecisionExecution.objects.count() == 1
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1
        assert ta_event.event_id == packet_event.causation_id

        # RuleExecution dedup: re-evaluating the same analysis_event_id is a no-op.
        evaluate_packet.run(
            {"packet": packet_event.payload["packet_data"]},
            analysis_event_id=str(analysis_event_id),
        )
        assert RuleExecution.objects.filter(
            analysis_event_id=analysis_event_id,
            rule_id="long_momentum_v1",
        ).count() == 1

        # RiskDecisionExecution dedup: redelivering the same RuleFired is skipped.
        handle_rule_fired(fired_event)
        assert RiskDecisionExecution.objects.count() == 1
        approved = [
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        ]
        assert len(approved) == 1
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

    def test_execution_intake_is_idempotent_on_same_approval(
        self,
        account,
        register_intelligence_handlers,
        register_rule_engine_handlers,
        register_risk_handlers,
        seed_session_facts,
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.execution.infrastructure.tasks import handle_risk_approved

        bus = get_event_bus()
        _register_pipeline(
            bus,
            register_intelligence_handlers,
            register_rule_engine_handlers,
            register_risk_handlers,
        )

        _publish_ta_event(bus)

        approved_event = next(
            e for e in bus.published_events
            if e.event_type == "risk_management.RiskApproved"
        )

        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

        # Redelivered approval: intake dedups on risk_approved_event_id.
        result = handle_risk_approved.run(
            payload=approved_event.payload,
            correlation_id=str(approved_event.correlation_id),
            causation_id=str(approved_event.causation_id or ""),
            risk_approved_event_id=str(approved_event.event_id),
        )
        assert result["outcome"] == "DUPLICATE"
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

    def test_second_ta_event_with_new_id_creates_new_chain(
        self,
        account,
        register_intelligence_handlers,
        register_rule_engine_handlers,
        register_risk_handlers,
        seed_session_facts,
    ) -> None:
        """Document the intended absence of dedup at the TA layer.

        A distinct TechnicalAnalysisCompleted (new event id) legitimately
        produces a second chain; idempotency lives at the rule/risk/execution
        layers, not at the TA ingestion layer.
        """
        from apps.execution.infrastructure.models import ExecutionRequest, Order
        from apps.risk_management.infrastructure.models import RiskDecisionExecution
        from apps.rule_engine.infrastructure.models import RuleExecution

        bus = get_event_bus()
        _register_pipeline(
            bus,
            register_intelligence_handlers,
            register_rule_engine_handlers,
            register_risk_handlers,
        )

        correlation_id = uuid.uuid4()
        _publish_ta_event(bus, correlation_id=correlation_id)
        _publish_ta_event(bus, correlation_id=correlation_id)

        assert len([e for e in bus.published_events
                    if e.event_type == "intelligence.PacketBuilt"]) == 2
        assert len([e for e in bus.published_events
                    if e.event_type == "rule_engine.RuleFired"]) == 2
        assert len([e for e in bus.published_events
                    if e.event_type == "risk_management.RiskApproved"]) == 2
        assert RuleExecution.objects.count() == 2
        assert RiskDecisionExecution.objects.count() == 2
        assert ExecutionRequest.objects.count() == 2
        assert Order.objects.count() == 2
