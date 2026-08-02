from __future__ import annotations

import uuid
from decimal import Decimal

import pytest

from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.application.portfolio_query_service import PortfolioQueryService
from apps.portfolio.domain.exceptions import InvalidFillError
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.infrastructure.models import (
    AccountCapitalState,
    Position,
    PositionFillExecution,
)
from apps.portfolio.infrastructure.repositories import PositionRepository
from apps.portfolio.tests.unit.helpers import FakePriceSource, published_events_of_type

pytestmark = pytest.mark.django_db


def make_ledger(prices: dict[str, str] | None = None) -> PositionLedgerService:
    price_source = FakePriceSource(
        {k: Decimal(v) for k, v in (prices or {}).items()}
    )
    query = PortfolioQueryService(price_source=price_source)
    return PositionLedgerService(query_service=query)


def fund(account, amount: str = "1000000") -> None:
    CapitalService().deposit(account.id, Decimal(amount))


def _fill(
    ledger: PositionLedgerService,
    account,
    *,
    symbol: str = "RELIANCE",
    side: Side = Side.LONG,
    quantity: str = "100",
    price: str = "100.00",
    source_fill_id: uuid.UUID | None = None,
    correlation_id: uuid.UUID | None = None,
    causation_id: uuid.UUID | None = None,
):
    return ledger.record_fill(
        account.id,
        symbol,
        side,
        Decimal(quantity),
        Decimal(price),
        source_fill_id=source_fill_id,
        correlation_id=correlation_id,
        causation_id=causation_id,
    )


class TestOpenPosition:
    def test_open_long_position(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        position = _fill(make_ledger(), account)

        assert position is not None
        assert position.symbol == "RELIANCE"
        assert position.side == "LONG"
        assert position.quantity == Decimal(100)
        assert position.avg_entry_price == Decimal("100.00")

        opened = published_events_of_type(bus.published_events, "positions.PositionOpened")
        assert len(opened) == 1
        payload = opened[0].payload
        assert payload["account_id"] == str(account.id)
        assert payload["position_id"] == str(position.id)
        assert payload["symbol"] == "RELIANCE"
        assert payload["side"] == "LONG"
        assert payload["quantity"] == "100"
        assert payload["entry_price"] == "100"

    def test_open_short_position(self, account) -> None:
        fund(account)
        position = _fill(make_ledger(), account, side=Side.SHORT, price="200.00")
        assert position.side == "SHORT"
        assert position.quantity == Decimal(100)

    def test_opening_reserves_margin(self, account) -> None:
        fund(account)
        _fill(make_ledger(), account, quantity="100", price="100.00")
        state = AccountCapitalState.objects.get(account=account)
        assert state.margin_used == Decimal("10000")
        assert state.available_capital == Decimal("990000")


class TestSameSideAdd:
    def test_weighted_average_entry_price(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        position = _fill(ledger, account, quantity="100", price="110.00")

        assert position.quantity == Decimal(200)
        assert position.avg_entry_price == Decimal("105.00")

    def test_add_publishes_quantity_changed(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        position = _fill(ledger, account, quantity="100", price="110.00")

        changed = published_events_of_type(
            bus.published_events, "positions.PositionQuantityChanged"
        )
        assert len(changed) == 1
        assert changed[0].payload["quantity"] == "200"
        assert changed[0].payload["entry_price"] == "105"
        assert changed[0].payload["position_id"] == str(position.id)


class TestClose:
    def test_partial_close_realizes_proportional_pnl(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        position = _fill(ledger, account, side=Side.SHORT, quantity="40", price="120.00")

        assert position.quantity == Decimal(60)
        assert position.avg_entry_price == Decimal("100.00")
        state = AccountCapitalState.objects.get(account=account)
        # realized = (120 - 100) x 40 x (+1) = 800
        assert state.realized_pnl_today == Decimal(800)
        assert state.cash == Decimal("1000800")
        # released margin = 40 x 100 = 4000
        assert state.margin_used == Decimal("6000")

    def test_full_close_realizes_pnl_and_removes_row(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        bus = get_event_bus()
        result = _fill(ledger, account, side=Side.SHORT, quantity="100", price="120.00")

        assert result is None
        assert PositionRepository().get_open(account.id, "RELIANCE") is None
        state = AccountCapitalState.objects.get(account=account)
        assert state.realized_pnl_today == Decimal(2000)
        assert state.cash == Decimal("1002000")
        assert state.margin_used == Decimal(0)
        assert state.available_capital == Decimal("1002000")

        closed = published_events_of_type(bus.published_events, "positions.PositionClosed")
        assert len(closed) == 1
        assert closed[0].payload["account_id"] == str(account.id)
        assert "position_id" in closed[0].payload

    def test_short_profit_sign_convention(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, side=Side.SHORT, quantity="100", price="100.00")
        _fill(ledger, account, side=Side.LONG, quantity="100", price="90.00")
        state = AccountCapitalState.objects.get(account=account)
        # short 100 @ 100, cover @ 90 -> realized (90-100)*100*(-1) = +1000
        assert state.realized_pnl_today == Decimal(1000)

    def test_short_loss_sign_convention(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, side=Side.SHORT, quantity="100", price="100.00")
        _fill(ledger, account, side=Side.LONG, quantity="100", price="110.00")
        state = AccountCapitalState.objects.get(account=account)
        # short 100 @ 100, cover @ 110 -> realized (110-100)*100*(-1) = -1000
        assert state.realized_pnl_today == Decimal("-1000")

    def test_over_offset_flips_to_opposite_side(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = make_ledger()
        _fill(ledger, account, side=Side.LONG, quantity="100", price="100.00")
        position = _fill(ledger, account, side=Side.SHORT, quantity="150", price="100.00")

        # 100 LONG closed (realized 0), 50 SHORT opened
        assert position is not None
        assert position.side == "SHORT"
        assert position.quantity == Decimal(50)
        assert position.avg_entry_price == Decimal("100.00")

        event_types = [e.event_type for e in bus.published_events]
        assert event_types.count("positions.PositionClosed") == 1
        assert event_types.count("positions.PositionOpened") == 2

    def test_close_position_helper(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        result = ledger.close_position(account.id, "RELIANCE", Decimal("105.00"))
        assert result is None
        assert PositionRepository().get_open(account.id, "RELIANCE") is None
        state = AccountCapitalState.objects.get(account=account)
        assert state.realized_pnl_today == Decimal(500)

    def test_close_position_with_no_position_returns_none(self, account) -> None:
        fund(account)
        result = make_ledger().close_position(account.id, "RELIANCE", Decimal("105.00"))
        assert result is None


class TestAdjustQuantity:
    def test_scale_in(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        position = ledger.adjust_quantity(
            account.id, "RELIANCE", Side.LONG, Decimal(200), Decimal("110.00")
        )
        assert position.quantity == Decimal(200)
        assert position.avg_entry_price == Decimal("105.00")

    def test_scale_out(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")
        position = ledger.adjust_quantity(
            account.id, "RELIANCE", Side.LONG, Decimal(60), Decimal("110.00")
        )
        assert position.quantity == Decimal(60)
        state = AccountCapitalState.objects.get(account=account)
        assert state.realized_pnl_today == Decimal(400)


class TestIdempotency:
    def test_duplicate_fill_is_skipped(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = make_ledger()
        fill_id = uuid.uuid4()
        first = _fill(ledger, account, quantity="100", price="100.00", source_fill_id=fill_id)
        second = _fill(ledger, account, quantity="100", price="100.00", source_fill_id=fill_id)

        assert first is not None
        assert second is None
        assert PositionFillExecution.objects.filter(source_fill_id=fill_id).count() == 1
        assert Position.objects.filter(account_id=account.id).count() == 1
        assert published_events_of_type(bus.published_events, "positions.PositionOpened")[0].event_id is not None
        opened = published_events_of_type(bus.published_events, "positions.PositionOpened")
        assert len(opened) == 1

    def test_duplicate_close_is_skipped(self, account) -> None:
        fund(account)
        ledger = make_ledger()
        fill_id = uuid.uuid4()
        _fill(ledger, account, quantity="100", price="100.00")
        close_fill = uuid.uuid4()
        ledger.close_position(
            account.id, "RELIANCE", Decimal("110.00"),
            source_fill_id=close_fill,
        )
        again = ledger.close_position(
            account.id, "RELIANCE", Decimal("110.00"),
            source_fill_id=close_fill,
        )
        # second close is a duplicate fill (no open position anyway) -> None
        assert again is None
        assert Position.objects.filter(account_id=account.id).count() == 0


class TestValidation:
    def test_zero_quantity_rejected(self, account) -> None:
        fund(account)
        with pytest.raises(InvalidFillError):
            make_ledger().record_fill(
                account.id, "RELIANCE", Side.LONG, Decimal(0), Decimal("100")
            )

    def test_negative_quantity_rejected(self, account) -> None:
        fund(account)
        with pytest.raises(InvalidFillError):
            make_ledger().record_fill(
                account.id, "RELIANCE", Side.LONG, Decimal("-10"), Decimal("100")
            )

    def test_zero_price_rejected(self, account) -> None:
        fund(account)
        with pytest.raises(InvalidFillError):
            make_ledger().record_fill(
                account.id, "RELIANCE", Side.LONG, Decimal(10), Decimal(0)
            )

    def test_negative_price_rejected(self, account) -> None:
        fund(account)
        with pytest.raises(InvalidFillError):
            make_ledger().record_fill(
                account.id, "RELIANCE", Side.LONG, Decimal(10), Decimal("-1")
            )

    def test_empty_symbol_rejected(self, account) -> None:
        fund(account)
        with pytest.raises(InvalidFillError):
            make_ledger().record_fill(
                account.id, "", Side.LONG, Decimal(10), Decimal("100")
            )

    def test_insufficient_capital_rejected(self, account) -> None:
        fund(account, amount="100")
        # reserving 100 x 200 = 20,000 > available 100 -> rejected
        from apps.portfolio.domain.exceptions import (
            InsufficientAvailableCapitalError,
        )

        with pytest.raises(InsufficientAvailableCapitalError):
            make_ledger().record_fill(
                account.id, "RELIANCE", Side.LONG, Decimal(100), Decimal("200")
            )


class TestEvents:
    def test_five_approved_event_types_published(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        correlation = uuid.uuid4()
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00", correlation_id=correlation)

        event_types = {e.event_type for e in bus.published_events}
        assert event_types == {
            "positions.PositionOpened",
            "portfolio.AccountCapitalChanged",  # deposit
            "portfolio.ExposureChanged",
        }

    def test_correlation_id_propagates_to_all_events(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        baseline = len(bus.published_events)
        correlation = uuid.uuid4()
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00", correlation_id=correlation)

        for event in bus.published_events[baseline:]:
            assert event.correlation_id == correlation

    def test_causation_id_propagates(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = make_ledger()
        cause = uuid.uuid4()
        _fill(ledger, account, quantity="100", price="100.00", causation_id=cause)

        opened = published_events_of_type(bus.published_events, "positions.PositionOpened")
        assert opened[0].causation_id == cause
        capital_events = published_events_of_type(
            bus.published_events, "portfolio.AccountCapitalChanged"
        )
        # deposit has no causation; the fill's margin reserve does
        reserve = [e for e in capital_events if e.payload["reason"] == "MARGIN_RESERVED"]
        assert reserve[0].causation_id == cause

    def test_exposure_changed_reports_position_notional(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = make_ledger()
        _fill(ledger, account, quantity="100", price="100.00")

        exposure_events = published_events_of_type(
            bus.published_events, "portfolio.ExposureChanged"
        )
        assert len(exposure_events) == 1
        assert exposure_events[0].payload["exposure"] == "10000"
        assert exposure_events[0].payload["account_id"] == str(account.id)
