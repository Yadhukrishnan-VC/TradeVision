from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.gateways.real_capital_gateway import RealCapitalGateway
from apps.portfolio.gateways.real_portfolio_state_gateway import RealPortfolioStateGateway
from apps.portfolio.tests.unit.helpers import FakePriceSource

pytestmark = pytest.mark.django_db


def _gateways(account, prices: dict[str, str] | None = None) -> tuple:
    query = PortfolioQueryService(
        price_source=FakePriceSource({k: Decimal(v) for k, v in (prices or {}).items()})
    )
    return (
        RealCapitalGateway(query_service=query, account_id=account.id),
        RealPortfolioStateGateway(query_service=query, account_id=account.id),
    )


class TestCapitalGateway:
    def test_implementation_name_is_portfolio_v1(self, account) -> None:
        capital, _ = _gateways(account)
        assert capital.implementation_name == "portfolio_v1"

    def test_get_available_capital_from_real_state(self, account) -> None:
        CapitalService().deposit(account.id, Decimal("1000000"))
        capital, _ = _gateways(account)
        assert capital.get_available_capital() == Decimal("1000000")

    def test_get_max_position_size_is_config_driven(self, account) -> None:
        capital, _ = _gateways(account)
        assert capital.get_max_position_size() == 1_000_000

    def test_no_account_returns_none(self) -> None:
        query = PortfolioQueryService(price_source=FakePriceSource())
        gateway = RealCapitalGateway(query_service=query)
        assert gateway.get_available_capital() is None


class TestPortfolioStateGateway:
    def test_implementation_name_is_portfolio_v1(self, account) -> None:
        _, gateway = _gateways(account)
        assert gateway.implementation_name == "portfolio_v1"

    def test_get_current_exposure_from_positions(self, account) -> None:
        from apps.portfolio.application.position_ledger_service import PositionLedgerService

        CapitalService().deposit(account.id, Decimal("1000000"))
        query = PortfolioQueryService(price_source=FakePriceSource({"RELIANCE": Decimal("120")}))
        PositionLedgerService(query_service=query).record_fill(
            account.id, "RELIANCE", Side.LONG, Decimal(100), Decimal("100")
        )
        _, gateway = _gateways(account, prices={"RELIANCE": "120"})
        assert gateway.get_current_exposure() == Decimal("12000")

    def test_get_daily_loss_from_capital_state(self, account) -> None:
        service = CapitalService()
        service.deposit(account.id, Decimal("1000000"))
        service.record_realized_pnl(account.id, Decimal("-2500"))
        _, gateway = _gateways(account)
        assert gateway.get_daily_loss() == Decimal("2500")

    def test_get_instrument_max_qty_is_config_driven(self, account) -> None:
        _, gateway = _gateways(account)
        assert gateway.get_instrument_max_qty("RELIANCE") is None

    def test_get_tradable_symbols_is_config_driven(self, account) -> None:
        _, gateway = _gateways(account)
        assert gateway.get_tradable_symbols() == frozenset()

    def test_no_account_returns_zero(self) -> None:
        query = PortfolioQueryService(price_source=FakePriceSource())
        gateway = RealPortfolioStateGateway(query_service=query)
        assert gateway.get_current_exposure() == Decimal(0)
        assert gateway.get_daily_loss() == Decimal(0)

    def test_protocol_contract_without_constructor_kwargs(self, account) -> None:
        """The gateway satisfies the M3 Protocol when used with defaults.

        The M3 ports are non-runtime-checkable ``Protocol``s, so conformance
        is asserted structurally: every member the port declares is present
        and callable on the gateway.
        """
        from apps.risk_management.application.ports import (
            CapitalGateway,
            PortfolioStateGateway,
        )

        CapitalService().deposit(account.id, Decimal("1000000"))
        capital = RealCapitalGateway(account_id=account.id)
        state = RealPortfolioStateGateway(account_id=account.id)
        for port in (CapitalGateway, PortfolioStateGateway):
            for member in getattr(port, "__annotations__", {}):
                assert hasattr(state, member) or hasattr(capital, member), member
        for member, expected in (
            ("get_available_capital", capital),
            ("get_max_position_size", capital),
            ("get_current_exposure", state),
            ("get_daily_loss", state),
            ("get_instrument_max_qty", state),
            ("get_tradable_symbols", state),
        ):
            assert callable(getattr(expected, member)), member
        assert isinstance(state.implementation_name, str)
        assert state.implementation_name == "portfolio_v1"
