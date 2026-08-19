from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import uuid4

import pytest

from apps.risk_management.application.risk_config import RiskConfig
from apps.risk_management.domain.rules.base_risk_check import (
    RiskCheckContext,
)
from apps.risk_management.domain.rules.portfolio_concentration import (
    PortfolioConcentrationCheck,
)
from apps.risk_management.domain.value_objects import (
    PortfolioPosition,
    RejectionReason,
)
from apps.risk_management.tests.unit.helpers import (
    FakeCapitalGateway,
    FakeMarketGateway,
    FakePortfolioGateway,
    build_service,
    make_payload,
)


def _ctx(
    *,
    symbol: str = "RELIANCE",
    rule_id: str = "long_momentum_v1",
    entry_price: Decimal = Decimal("103.00"),
    proposed_quantity: int = 100,
    available_capital: Decimal = Decimal("1000000"),
    instrument_sector: str | None = "Energy",
    positions: tuple = (),
    max_sector_exposure_pct: Decimal | None = None,
    correlated_trigger_max_multiple: Decimal | None = None,
) -> RiskCheckContext:
    return RiskCheckContext(
        symbol=symbol,
        rule_id=rule_id,
        event_type="BREAKOUT",
        analysis_event_id=uuid4(),
        occurred_at=datetime.now(timezone.utc),
        entry_price=entry_price,
        stop_loss=Decimal("101.00"),
        direction="long",
        available_capital=available_capital,
        proposed_quantity=proposed_quantity,
        portfolio_positions=positions,
        instrument_sector=instrument_sector,
        max_sector_exposure_pct=max_sector_exposure_pct,
        correlated_trigger_max_multiple=correlated_trigger_max_multiple,
    )


class TestPortfolioConcentrationCheck:
    def test_passes_when_no_thresholds_configured(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(positions=(PortfolioPosition(symbol="RELIANCE", sector="Energy", notional=Decimal("50000")),))
        assert check.evaluate(ctx) is None

    def test_rejects_for_sector_concentration(self) -> None:
        check = PortfolioConcentrationCheck()
        # Existing same-sector position (Energy) + proposed 10300 notional
        # => 50300 > 5% of 1,000,000 (50000) -> reject.
        ctx = _ctx(
            positions=(
                PortfolioPosition(
                    symbol="ONGC",
                    sector="Energy",
                    notional=Decimal("40000"),
                    trigger_rule="long_momentum_v1",
                ),
            ),
            max_sector_exposure_pct=Decimal("0.05"),
        )
        result = check.evaluate(ctx)
        assert result is not None
        assert result.reason is RejectionReason.SECTOR_CONCENTRATION_EXCEEDED

    def test_passes_when_within_sector_cap(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(
            positions=(
                PortfolioPosition(
                    symbol="ONGC",
                    sector="Energy",
                    notional=Decimal("10000"),
                    trigger_rule="long_momentum_v1",
                ),
            ),
            max_sector_exposure_pct=Decimal("0.05"),
        )
        assert check.evaluate(ctx) is None

    def test_rejects_for_correlated_trigger_exposure(self) -> None:
        check = PortfolioConcentrationCheck()
        # Same rule already holds 40000 notional; proposed adds 10300 => 50300
        # > 3 x single-position risk (3 x 10000 = 30000) -> reject.
        ctx = _ctx(
            positions=(
                PortfolioPosition(
                    symbol="TCS",
                    sector="IT",
                    notional=Decimal("40000"),
                    trigger_rule="long_momentum_v1",
                ),
            ),
            correlated_trigger_max_multiple=Decimal("3"),
        )
        result = check.evaluate(ctx)
        assert result is not None
        assert result.reason is RejectionReason.CORRELATED_EXPOSURE_EXCEEDED

    def test_passes_within_correlated_trigger_cap(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(
            positions=(
                PortfolioPosition(
                    symbol="TCS",
                    sector="IT",
                    notional=Decimal("10000"),
                    trigger_rule="long_momentum_v1",
                ),
            ),
            correlated_trigger_max_multiple=Decimal("3"),
        )
        assert check.evaluate(ctx) is None

    def test_fails_closed_when_proposed_sector_missing(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(
            instrument_sector=None,
            max_sector_exposure_pct=Decimal("0.05"),
        )
        result = check.evaluate(ctx)
        assert result is not None
        assert result.reason is RejectionReason.MISSING_SECTOR_DATA

    def test_fails_closed_when_open_position_sector_missing(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(
            positions=(
                PortfolioPosition(symbol="HDFC", sector=None, notional=Decimal("10000")),
            ),
            max_sector_exposure_pct=Decimal("0.05"),
        )
        result = check.evaluate(ctx)
        assert result is not None
        assert result.reason is RejectionReason.MISSING_SECTOR_DATA

    def test_fails_closed_when_correlated_attribution_missing(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(
            positions=(
                PortfolioPosition(symbol="TCS", sector="IT", notional=Decimal("10000")),
            ),
            correlated_trigger_max_multiple=Decimal("3"),
        )
        result = check.evaluate(ctx)
        assert result is not None
        assert result.reason is RejectionReason.MISSING_SECTOR_DATA

    def test_fails_closed_when_capital_missing(self) -> None:
        check = PortfolioConcentrationCheck()
        ctx = _ctx(available_capital=None, max_sector_exposure_pct=Decimal("0.05"))
        result = check.evaluate(ctx)
        assert result is not None
        assert result.reason is RejectionReason.MISSING_ACCOUNT_STATE


@pytest.mark.django_db
class TestConcentrationWiredIntoEvaluation:
    """End-to-end wiring: the check runs inside RiskEvaluationService and its
    rejections surface as the decision's rejection code."""

    def _build(self, config: RiskConfig) -> tuple:
        capital = FakeCapitalGateway(available_capital=Decimal("1000000"))
        portfolio = FakePortfolioGateway(
            sector_by_symbol={"RELIANCE": "Energy", "ONGC": "Energy"},
            portfolio_positions=(
                PortfolioPosition(
                    symbol="ONGC",
                    sector="Energy",
                    notional=Decimal("40000"),
                    trigger_rule="long_momentum_v1",
                ),
            ),
        )
        market = FakeMarketGateway()
        service = build_service(config=config, capital=capital, portfolio=portfolio, market=market)
        return service, make_payload()

    def test_evaluation_rejects_on_sector_concentration(self) -> None:
        config = RiskConfig(max_sector_exposure_pct=Decimal("0.05"))
        service, payload = self._build(config)
        decision = service.evaluate_rule_firing(payload)
        assert decision.status.value == "REJECTED"
        assert decision.rejection.code is RejectionReason.SECTOR_CONCENTRATION_EXCEEDED

    def test_evaluation_rejects_fail_closed_on_missing_sector(self) -> None:
        config = RiskConfig(max_sector_exposure_pct=Decimal("0.05"))
        capital = FakeCapitalGateway(available_capital=Decimal("1000000"))
        portfolio = FakePortfolioGateway()  # no sector_by_symbol -> sector unknown
        market = FakeMarketGateway()
        service = build_service(config=config, capital=capital, portfolio=portfolio, market=market)
        decision = service.evaluate_rule_firing(make_payload())
        assert decision.status.value == "REJECTED"
        assert decision.rejection.code is RejectionReason.MISSING_SECTOR_DATA

    def test_evaluation_passes_when_concentration_ok(self) -> None:
        config = RiskConfig(max_sector_exposure_pct=Decimal("0.6"))
        service, payload = self._build(config)
        decision = service.evaluate_rule_firing(payload)
        assert decision.status.value == "APPROVED"