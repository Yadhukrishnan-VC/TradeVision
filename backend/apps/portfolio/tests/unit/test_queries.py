from __future__ import annotations

from decimal import Decimal

import pytest

from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.entities import AccountCapital, Position
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.infrastructure.models import AccountCapitalState
from apps.portfolio.tests.unit.helpers import FakePriceSource

pytestmark = pytest.mark.django_db


def _query(prices: dict[str, str] | None = None) -> PortfolioQueryService:
    return PortfolioQueryService(
        price_source=FakePriceSource({k: Decimal(v) for k, v in (prices or {}).items()})
    )


def _fund(account, amount: str = "1000000") -> None:
    CapitalService().deposit(account.id, Decimal(amount))


def _open_position(
    account,
    ledger: PositionLedgerService,
    symbol: str,
    side: Side,
    quantity: str,
    price: str,
) -> None:
    ledger.record_fill(
        account.id, symbol, side, Decimal(quantity), Decimal(price)
    )


class TestExposure:
    def test_single_position_exposure_at_market_price(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.LONG, "100", "100")
        assert _query({"RELIANCE": "120"}).get_exposure(account.id) == Decimal("12000")

    def test_short_position_exposure_is_absolute(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.SHORT, "50", "100")
        assert _query({"RELIANCE": "80"}).get_exposure(account.id) == Decimal("4000")

    def test_exposure_aggregates_multiple_positions(self, account) -> None:
        _fund(account)
        ledger = PositionLedgerService(query_service=_query())
        _open_position(account, ledger, "RELIANCE", Side.LONG, "100", "100")
        _open_position(account, ledger, "TATA", Side.LONG, "200", "50")
        exposure = _query({"RELIANCE": "120", "TATA": "55"}).get_exposure(account.id)
        assert exposure == Decimal("12000") + Decimal("11000")  # 120*100 + 55*200

    def test_exposure_falls_back_to_average_entry(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.LONG, "100", "100")
        # no price known -> exposure = 100 x 100 = 10000
        assert _query().get_exposure(account.id) == Decimal("10000")


class TestUnrealizedPnl:
    def test_long_unrealized_at_market(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.LONG, "100", "100")
        assert _query({"RELIANCE": "120"}).get_unrealized_pnl(account.id) == Decimal("2000")

    def test_short_unrealized_at_market(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.SHORT, "100", "100")
        assert _query({"RELIANCE": "90"}).get_unrealized_pnl(account.id) == Decimal("1000")

    def test_unrealized_falls_back_to_zero_when_price_unknown(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.LONG, "100", "100")
        assert _query().get_unrealized_pnl(account.id) == Decimal(0)

    def test_reconcile_persists_unrealized_and_equity(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.LONG, "100", "100")
        capital = _query({"RELIANCE": "120"}).reconcile_unrealized(account.id)
        assert isinstance(capital, AccountCapital)
        assert capital.unrealized_pnl_today == Decimal("2000")
        state = AccountCapitalState.objects.get(account=account)
        assert state.unrealized_pnl_today == Decimal("2000")
        assert state.equity == Decimal("1000000") + Decimal("2000")


class TestDailyLoss:
    def test_daily_loss_magnitude_from_realized_and_unrealized(self, account) -> None:
        _fund(account)
        ledger = PositionLedgerService(query_service=_query())
        _open_position(account, ledger, "RELIANCE", Side.LONG, "100", "100")
        # close at a loss: (90 - 100) x 100 = -1000 realized
        ledger.record_fill(account.id, "RELIANCE", Side.SHORT, Decimal(100), Decimal("90"))
        # remaining: none; unrealized zero -> daily loss = 1000 (magnitude)
        assert _query().get_daily_loss(account.id) == Decimal("1000")

    def test_daily_loss_zero_when_no_state(self, account) -> None:
        assert _query().get_daily_loss(account.id) == Decimal(0)

    def test_daily_loss_ignores_gains(self, account) -> None:
        _fund(account)
        CapitalService().record_realized_pnl(account.id, Decimal("5000"))
        assert _query().get_daily_loss(account.id) == Decimal(0)


class TestCapitalReads:
    def test_account_capital_mapping(self, account) -> None:
        _fund(account, amount="500000")
        capital = _query().get_account_capital(account.id)
        assert isinstance(capital, AccountCapital)
        assert capital.account_id == account.id
        assert capital.cash == Decimal("500000")
        assert capital.available_capital == Decimal("500000")
        assert capital.equity == Decimal("500000")

    def test_missing_account_state_returns_none(self) -> None:
        import uuid

        assert _query().get_account_capital(uuid.uuid4()) is None

    def test_open_positions_list(self, account) -> None:
        _fund(account)
        _open_position(account, PositionLedgerService(query_service=_query()), "RELIANCE", Side.LONG, "100", "100")
        positions = _query().get_open_positions(account.id)
        assert len(positions) == 1
        assert isinstance(positions[0], Position)
        assert positions[0].side == Side.LONG
        assert positions[0].quantity == Decimal(100)
