from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.dashboard.infrastructure.trading_core.event_consumers import register_handlers
from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.tests.unit.helpers import FakePriceSource

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def _register_dashboard_projectors() -> None:
    """Wire the *unmodified* dashboard projection handlers onto the fake bus."""
    from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus

    reset_event_bus()
    bus = get_event_bus()
    register_handlers(bus)
    yield
    reset_event_bus()


@pytest.fixture(autouse=True)
def _market_open(monkeypatch) -> None:
    """Deterministic market/freshness state regardless of wall-clock time."""
    from apps.risk_management.gateways.market_calendar_status_gateway import (
        MarketCalendarStatusGateway,
    )

    monkeypatch.setattr(MarketCalendarStatusGateway, "is_market_open", lambda self, dt: True)
    monkeypatch.setattr(MarketCalendarStatusGateway, "is_fresh", lambda self, a, r: True)


def _ledger(prices: dict[str, str] | None = None) -> PositionLedgerService:
    return PositionLedgerService(
        query_service=PortfolioQueryService(
            price_source=FakePriceSource(
                {k: Decimal(v) for k, v in (prices or {}).items()}
            )
        )
    )


class TestPositionEventDrivesDashboardProjection:
    """ADR-028 §20: ``positions.*`` events feed the *unmodified* dashboard."""

    def test_record_fill_opens_dashboard_snapshot(self, account) -> None:
        CapitalService().deposit(account.id, Decimal("1000000"))
        position = _ledger().record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal(100), Decimal("100.00")
        )

        snapshots = PositionSnapshot.objects.filter(position_id=position.id)
        assert snapshots.count() == 1
        snapshot = snapshots.get()
        assert snapshot.account_id == account.id
        assert snapshot.symbol == "RELIANCE"
        assert snapshot.side == "LONG"
        assert snapshot.quantity == Decimal("100.00")
        assert snapshot.entry_price == Decimal("100.00")
        assert snapshot.is_open is True

    def test_close_marks_dashboard_snapshot_closed(self, account) -> None:
        CapitalService().deposit(account.id, Decimal("1000000"))
        ledger = _ledger()
        position = ledger.record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal(100), Decimal("100.00")
        )

        ledger.record_fill(
            account.id, "RELIANCE", Side.SHORT, Decimal(100), Decimal("105.00")
        )

        snapshot = PositionSnapshot.objects.get(position_id=position.id)
        assert snapshot.is_open is False
        assert snapshot.closed_at is not None

    def test_scale_in_updates_dashboard_snapshot(self, account) -> None:
        CapitalService().deposit(account.id, Decimal("1000000"))
        ledger = _ledger()
        position = ledger.record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal(100), Decimal("100.00")
        )

        updated = ledger.adjust_quantity(
            account.id, "RELIANCE", Side.LONG, Decimal(200), Decimal("110.00")
        )

        snapshot = PositionSnapshot.objects.get(position_id=position.id)
        assert snapshot.quantity == Decimal("200.00")
        assert snapshot.entry_price == Decimal("105.00")


class TestRiskGatewayIntegration:
    """ADR-028 §2.9: the risk chain now reads the real portfolio gateway."""

    def _evaluate(self, account) -> dict:
        from apps.risk_management.application.risk_config import (
            risk_config_from_settings,
        )
        from apps.risk_management.application.risk_evaluation_service import (
            RiskEvaluationService,
        )
        from apps.risk_management.gateways.market_calendar_status_gateway import (
            MarketCalendarStatusGateway,
        )
        from apps.portfolio.gateways.real_capital_gateway import RealCapitalGateway
        from apps.portfolio.gateways.real_portfolio_state_gateway import (
            RealPortfolioStateGateway,
        )

        query = PortfolioQueryService(price_source=FakePriceSource({"RELIANCE": Decimal("103")}))
        service = RiskEvaluationService(
            capital_gateway=RealCapitalGateway(query_service=query, account_id=account.id),
            portfolio_gateway=RealPortfolioStateGateway(
                query_service=query, account_id=account.id
            ),
            market_gateway=MarketCalendarStatusGateway(),
            config=risk_config_from_settings(),
        )
        return service.evaluate_rule_firing(
            {
                "symbol": "RELIANCE",
                "rule_id": "long_momentum_v1",
                "event_type": "BREAKOUT",
                "trigger_data": {
                    "entry_price": "103.00",
                    "stop_loss": "101.00",
                    "target_price": "110.00",
                },
                "analysis_event_id": str(uuid.uuid4()),
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    def test_approved_uses_portfolio_v1_gateway(self, account) -> None:
        CapitalService().deposit(account.id, Decimal("1000000"))
        decision = self._evaluate(account)

        assert decision.status.value == "APPROVED"
        assert decision.portfolio_gateway_impl == "portfolio_v1"

    def test_insufficient_capital_rejects_via_real_gateway(self, account) -> None:
        decision = self._evaluate(account)

        assert decision.status.value == "REJECTED"
        assert decision.rejection.code.value == "ZERO_CAPITAL"
        assert decision.portfolio_gateway_impl == "portfolio_v1"

    def test_exposure_and_daily_loss_read_from_portfolio(self, account) -> None:
        from apps.portfolio.gateways.real_portfolio_state_gateway import (
            RealPortfolioStateGateway,
        )

        CapitalService().deposit(account.id, Decimal("1000000"))
        query = PortfolioQueryService(price_source=FakePriceSource({"RELIANCE": Decimal("120")}))
        _ledger({"RELIANCE": "120"}).record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal(100), Decimal("100.00")
        )
        state = query.reconcile_unrealized(account.id)
        assert state.unrealized_pnl_today == Decimal("2000.00000000")

        gateway = RealPortfolioStateGateway(
            query_service=query, account_id=account.id
        )
        assert gateway.get_current_exposure() == Decimal("12000")
        assert gateway.get_daily_loss() == Decimal("0")

    def test_risk_approved_correlates_to_fill_via_event_bus(self, account) -> None:
        from apps.risk_management.application.risk_config import (
            risk_config_from_settings,
        )
        from apps.risk_management.application.risk_evaluation_service import (
            RiskEvaluationService,
        )
        from apps.risk_management.gateways.market_calendar_status_gateway import (
            MarketCalendarStatusGateway,
        )
        from apps.portfolio.gateways.real_capital_gateway import RealCapitalGateway
        from apps.portfolio.gateways.real_portfolio_state_gateway import (
            RealPortfolioStateGateway,
        )

        CapitalService().deposit(account.id, Decimal("1000000"))
        bus = get_event_bus()
        baseline = len(bus.published_events)
        correlation = uuid.uuid4()
        query = PortfolioQueryService(price_source=FakePriceSource({"RELIANCE": Decimal("103")}))
        _ledger().record_fill(
            account.id,
            "RELIANCE",
            Side.LONG,
            Decimal(100),
            Decimal("100.00"),
            correlation_id=correlation,
        )

        service = RiskEvaluationService(
            capital_gateway=RealCapitalGateway(query_service=query, account_id=account.id),
            portfolio_gateway=RealPortfolioStateGateway(
                query_service=query, account_id=account.id
            ),
            market_gateway=MarketCalendarStatusGateway(),
            config=risk_config_from_settings(),
        )
        decision = service.evaluate_rule_firing(
            {
                "symbol": "RELIANCE",
                "rule_id": "long_momentum_v1",
                "event_type": "BREAKOUT",
                "trigger_data": {
                    "entry_price": "103.00",
                    "stop_loss": "101.00",
                    "target_price": "110.00",
                },
                "analysis_event_id": str(uuid.uuid4()),
                "occurred_at": datetime.now(timezone.utc).isoformat(),
            },
            reference_dt=datetime.now(timezone.utc),
        )
        assert decision.status.value == "APPROVED"
        assert decision.portfolio_gateway_impl == "portfolio_v1"
        assert all(e.correlation_id == correlation for e in bus.published_events[baseline:])
