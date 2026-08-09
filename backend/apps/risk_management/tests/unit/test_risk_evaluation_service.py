from __future__ import annotations

from decimal import Decimal

from apps.risk_management.application.risk_config import RiskConfig
from apps.risk_management.domain.value_objects import RejectionReason
from apps.risk_management.tests.unit.helpers import (
    FakeCapitalGateway,
    FakeKillSwitchService,
    FakeMarketGateway,
    FakePortfolioGateway,
    build_service,
    make_payload,
)


class TestRiskDecisionOutcomes:
    def test_approved_when_all_checks_pass(self) -> None:
        decision = build_service().evaluate_rule_firing(make_payload())
        assert decision.status.value == "APPROVED"
        assert decision.rejection is None
        # risk_amount = 1,000,000 x 0.01 = 10,000; risk_per_unit = |103 - 101| = 2
        # raw = floor(10000/2) = 5000; capital = floor(1,000,000/103) = 9708
        # position_size = min(5000, 1_000_000, 9708, None) = 5000
        assert decision.position_size == 5000
        assert decision.risk_amount == Decimal(10000)
        assert decision.risk_reward_ratio == Decimal("3.5")  # (110-103)/2

    def test_stop_equals_entry_rejected(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(entry_price="103.00", stop_loss="103.00")
        )
        assert decision.status.value == "REJECTED"
        assert decision.rejection.code == RejectionReason.STOP_EQUALS_ENTRY

    def test_stop_wrong_side_for_long_rejected(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(entry_price="103.00", stop_loss="105.00")
        )
        assert decision.rejection.code == RejectionReason.STOP_WRONG_SIDE

    def test_missing_stop_loss_rejected(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(entry_price="103.00", stop_loss=None)
        )
        assert decision.rejection.code == RejectionReason.MISSING_STOP_LOSS

    def test_missing_entry_price_rejected(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(entry_price=None, stop_loss="101.00")
        )
        assert decision.rejection.code == RejectionReason.MISSING_ENTRY_PRICE

    def test_zero_risk_distance_rejected(self) -> None:
        # ZERO_RISK_DISTANCE is a defensive fail-closed emitted by the sizing
        # check when |entry - stop| <= 0. Through the service the StopDirection
        # check catches stop==entry first, so we assert it at the check level.
        from datetime import datetime, timezone
        from decimal import Decimal as D
        from uuid import uuid4

        from apps.risk_management.domain.rules import (
            PositionSizingCheck,
            RiskCheckContext,
        )
        from apps.risk_management.domain.value_objects import RejectionReason

        ctx = RiskCheckContext(
            symbol="RELIANCE",
            rule_id="long_momentum_v1",
            event_type="BREAKOUT",
            analysis_event_id=uuid4(),
            occurred_at=datetime.now(timezone.utc),
            entry_price=D("103.00"),
            stop_loss=D("103.00"),
            available_capital=D(1000000),
            risk_pct=D("0.01"),
        )
        result = PositionSizingCheck().evaluate(ctx)
        assert result is not None
        assert result.reason == RejectionReason.ZERO_RISK_DISTANCE

    def test_zero_capital_rejected(self) -> None:
        decision = build_service(
            capital=FakeCapitalGateway(available_capital=Decimal(0))
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.ZERO_CAPITAL

    def test_missing_account_state_rejected(self) -> None:
        decision = build_service(
            capital=FakeCapitalGateway(available_capital=None)
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.MISSING_ACCOUNT_STATE

    def test_insufficient_capital_rejected(self) -> None:
        decision = build_service(
            capital=FakeCapitalGateway(available_capital=Decimal(10))
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.INSUFFICIENT_CAPITAL

    def test_position_size_zero_rejected(self) -> None:
        decision = build_service(
            capital=FakeCapitalGateway(available_capital=Decimal(10))
        ).evaluate_rule_firing(
            make_payload(entry_price="103.00", stop_loss="102.00", target_price=None)
        )
        assert decision.status.value == "REJECTED"
        assert decision.rejection.code == RejectionReason.INSUFFICIENT_CAPITAL

    def test_exposure_cap_exceeded_rejected(self) -> None:
        decision = build_service(
            portfolio=FakePortfolioGateway(current_exposure=Decimal(999999)),
            config=RiskConfig(max_exposure_cap=Decimal(1000000)),
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.MAX_EXPOSURE_EXCEEDED

    def test_daily_loss_limit_rejected(self) -> None:
        decision = build_service(
            portfolio=FakePortfolioGateway(daily_loss=Decimal(50000)),
            config=RiskConfig(daily_loss_limit=Decimal(50000)),
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.DAILY_LOSS_LIMIT_EXCEEDED

    def test_risk_reward_below_minimum_rejected(self) -> None:
        decision = build_service(
            config=RiskConfig(min_risk_reward=Decimal("2.0"))
        ).evaluate_rule_firing(make_payload(target_price="106.00"))
        # (106-103)/2 = 1.5 < 2.0
        assert decision.rejection.code == RejectionReason.RISK_REWARD_BELOW_MINIMUM

    def test_stale_data_rejected(self) -> None:
        decision = build_service(
            market=FakeMarketGateway(freshness=False)
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.STALE_DATA

    def test_market_closed_rejected(self) -> None:
        decision = build_service(
            market=FakeMarketGateway(is_open=False)
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.MARKET_CLOSED

    def test_invalid_instrument_rejected(self) -> None:
        decision = build_service(
            config=RiskConfig(tradable_symbols=frozenset({"TCS"}))
        ).evaluate_rule_firing(make_payload(symbol="RELIANCE"))
        assert decision.rejection.code == RejectionReason.INVALID_INSTRUMENT

    def test_kill_switch_active_rejected_first(self) -> None:
        # Kill switch + stale data: kill switch wins (evaluated first).
        decision = build_service(
            market=FakeMarketGateway(freshness=False),
            kill_switch=FakeKillSwitchService(blocked=True),
        ).evaluate_rule_firing(make_payload())
        assert decision.rejection.code == RejectionReason.KILL_SWITCH_ACTIVE


class TestDecisionDirection:
    def test_decision_carries_long_direction_for_long_rule(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(rule_id="long_momentum_v1", direction="long")
        )
        assert decision.status.value == "APPROVED"
        assert decision.direction == "long"

    def test_decision_carries_short_direction_from_trigger_data(self) -> None:
        # The bidirectional volatility rule derives its direction from the
        # explicit trigger_data direction (short-breakdown case).
        decision = build_service().evaluate_rule_firing(
            make_payload(
                rule_id="volatility_breakout_v1",
                direction="short",
                stop_loss="105.00",  # above entry -> correct side for a short
            )
        )
        assert decision.status.value == "APPROVED"
        assert decision.direction == "short"

    def test_direction_defaults_to_long_when_payload_omits_it(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(direction=None)
        )
        assert decision.status.value == "APPROVED"
        assert decision.direction == "long"

    def test_short_direction_survives_a_rejected_decision(self) -> None:
        decision = build_service().evaluate_rule_firing(
            make_payload(
                rule_id="volatility_breakout_v1",
                direction="short",
                stop_loss="101.00",  # below entry -> wrong side for a short
            )
        )
        assert decision.status.value == "REJECTED"
        assert decision.direction == "short"


class TestRiskApprovedDirectionPayload:
    def test_published_payload_contains_direction(self) -> None:
        from apps.risk_management.domain.events import RiskApproved

        decision = build_service().evaluate_rule_firing(
            make_payload(rule_id="volatility_breakout_v1", direction="short")
        )
        payload = RiskApproved.from_decision(decision).to_payload()
        assert payload["direction"] == "short"

    def test_published_payload_defaults_direction_to_long(self) -> None:
        from apps.risk_management.domain.events import RiskApproved

        decision = build_service().evaluate_rule_firing(
            make_payload(direction=None)
        )
        payload = RiskApproved.from_decision(decision).to_payload()
        assert payload["direction"] == "long"


class TestSizingPrecision:
    def test_position_size_uses_decimal_floor_not_float(self) -> None:
        decision = build_service(
            capital=FakeCapitalGateway(available_capital=Decimal(1000000))
        ).evaluate_rule_firing(
            make_payload(entry_price="99.99", stop_loss="99.98", target_price="110.00")
        )
        # risk_amount = 10,000; risk_per_unit = 0.01; raw = 1,000,000
        # capital = floor(1,000,000/99.99) = 10001
        assert decision.position_size == 10001
        assert isinstance(decision.position_size, int)
