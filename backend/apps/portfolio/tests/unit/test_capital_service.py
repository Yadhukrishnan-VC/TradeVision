from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.domain.exceptions import (
    InsufficientAvailableCapitalError,
    InsufficientCashError,
    PortfolioDomainError,
)
from apps.portfolio.infrastructure.models import AccountCapitalState
from apps.portfolio.tests.unit.helpers import published_events_of_type

pytestmark = pytest.mark.django_db


def _service() -> CapitalService:
    return CapitalService()


class TestAccountCreation:
    def test_account_creation_creates_zero_balance_capital_state(
        self, account
    ) -> None:
        state = AccountCapitalState.objects.get(account=account)
        assert state.cash == Decimal(0)
        assert state.margin_used == Decimal(0)
        assert state.equity == Decimal(0)
        assert state.available_capital == Decimal(0)
        assert state.realized_pnl_today == Decimal(0)
        assert state.unrealized_pnl_today == Decimal(0)


class TestCashOperations:
    def test_deposit_updates_cash_and_equity(self, account) -> None:
        state = _service().deposit(account.id, Decimal("1000000"))
        assert state.cash == Decimal("1000000")
        assert state.equity == Decimal("1000000")
        assert state.available_capital == Decimal("1000000")

    def test_withdraw_reduces_cash(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000000"))
        state = service.withdraw(account.id, Decimal("250000"))
        assert state.cash == Decimal("750000")
        assert state.available_capital == Decimal("750000")

    def test_withdraw_beyond_cash_rejected(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000"))
        with pytest.raises(InsufficientCashError):
            service.withdraw(account.id, Decimal("1001"))

    def test_zero_amount_rejected(self, account) -> None:
        with pytest.raises(PortfolioDomainError):
            _service().deposit(account.id, Decimal(0))
        with pytest.raises(PortfolioDomainError):
            _service().withdraw(account.id, Decimal("-5"))

    def test_decimal_precision_is_8_places(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("0.00000001"))
        state = service.get_state(account.id)
        assert state.cash == Decimal("0.00000001")


class TestMargin:
    def test_reserve_margin_reduces_available(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000000"))
        state = service.reserve_margin(account.id, Decimal("10000"))
        assert state.margin_used == Decimal("10000")
        assert state.available_capital == Decimal("990000")
        assert state.equity == Decimal("1000000")  # cash unchanged

    def test_reserve_margin_beyond_available_rejected(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("10000"))
        with pytest.raises(InsufficientAvailableCapitalError):
            service.reserve_margin(account.id, Decimal("10000.01"))

    def test_release_margin_restores_available(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000000"))
        service.reserve_margin(account.id, Decimal("10000"))
        state = service.release_margin(account.id, Decimal("10000"))
        assert state.margin_used == Decimal(0)
        assert state.available_capital == Decimal("1000000")

    def test_release_margin_beyond_reserved_rejected(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000000"))
        with pytest.raises(PortfolioDomainError):
            service.release_margin(account.id, Decimal("1"))


class TestRealizedPnl:
    def test_record_realized_pnl_updates_cash_and_equity(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000000"))
        state = service.record_realized_pnl(account.id, Decimal("5000"))
        assert state.cash == Decimal("1005000")
        assert state.realized_pnl_today == Decimal("5000")
        assert state.equity == Decimal("1005000")

    def test_record_realized_loss_reduces_cash(self, account) -> None:
        service = _service()
        service.deposit(account.id, Decimal("1000000"))
        state = service.record_realized_pnl(account.id, Decimal("-2000"))
        assert state.cash == Decimal("998000")
        assert state.realized_pnl_today == Decimal("-2000")
        assert state.equity == Decimal("998000")


class TestEvents:
    def test_account_capital_changed_published_with_reason(self, account) -> None:
        bus = get_event_bus()
        _service().deposit(
            account.id,
            Decimal("1000000"),
            correlation_id=uuid.uuid4(),
        )
        events = published_events_of_type(bus.published_events, "portfolio.AccountCapitalChanged")
        assert len(events) == 1
        payload = events[0].payload
        assert payload["account_id"] == str(account.id)
        assert payload["reason"] == "DEPOSIT"
        assert payload["cash"] == "1000000"
        assert "available_capital" in payload
        assert "equity" in payload
        assert "occurred_at" in payload

    def test_correlation_id_propagates_to_event(self, account) -> None:
        bus = get_event_bus()
        correlation = uuid.uuid4()
        _service().deposit(
            account.id,
            Decimal("100"),
            correlation_id=correlation,
        )
        event = published_events_of_type(
            bus.published_events, "portfolio.AccountCapitalChanged"
        )[0]
        assert event.correlation_id == correlation
