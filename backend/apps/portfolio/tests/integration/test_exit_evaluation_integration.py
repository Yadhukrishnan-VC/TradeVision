"""Batch M3.6 — integration tests for the stop-loss exit path.

Covers: record_fill stop-loss threading (open sets it, pyramiding keeps it),
the triggered close via the real ``PositionLedgerService.close_position()``
(event + realized P&L + correlation chaining), safe no-ops, and idempotency
under duplicate delivery.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.portfolio.application.capital_service import CapitalService
from apps.portfolio.application.exit_evaluation_service import ExitEvaluationService
from apps.portfolio.application.position_ledger_service import PositionLedgerService
from apps.portfolio.domain.value_objects import Side
from apps.portfolio.infrastructure.event_handlers import handle_ta_completed
from apps.portfolio.infrastructure.models import (
    AccountCapitalState,
    Position,
    PositionFillExecution,
)
from apps.portfolio.tests.unit.helpers import published_events_of_type

pytestmark = pytest.mark.django_db


def fund(account, amount: str = "1000000") -> None:
    CapitalService().deposit(account.id, Decimal(amount))


def _open_position(
    ledger: PositionLedgerService,
    account,
    *,
    side: Side = Side.LONG,
    price: str = "100.00",
    stop_loss: str = "95.00",
    opened_at: datetime | None = None,
) -> Position:
    position = ledger.record_fill(
        account.id,
        "RELIANCE",
        side,
        Decimal("100"),
        Decimal(price),
        occurred_at=opened_at or datetime(2024, 6, 10, 6, 0, 0, tzinfo=timezone.utc),
        stop_loss=Decimal(stop_loss),
        source_fill_id=uuid.uuid4(),
    )
    assert position is not None
    return position


def _ta_event(
    *,
    symbol: str = "RELIANCE",
    high: str = "103.00",
    low: str = "94.00",
    snapshot_timestamp: str = "2024-06-10T07:00:00+00:00",
    correlation_id: uuid.UUID | None = None,
) -> DomainEvent:
    payload = {
        "snapshot_id": str(uuid.uuid4()),
        "symbol": symbol,
        "exchange": "NSE",
        "timeframe": "1D",
        "snapshot_timestamp": snapshot_timestamp,
        "indicators": {},
        "price": {"high": high, "low": low},
    }
    return DomainEvent.create(
        event_type="technical_analysis.TechnicalAnalysisCompleted",
        payload=payload,
        correlation_id=correlation_id or uuid.uuid4(),
    )


class TestRecordFillStopLossThreading:
    def test_open_position_persists_stop_loss(self, account) -> None:
        fund(account)
        position = _open_position(PositionLedgerService(), account)
        assert position.stop_loss == Decimal("95.00")

    def test_open_position_without_stop_loss_is_null(self, account) -> None:
        fund(account)
        position = PositionLedgerService().record_fill(
            account.id,
            "RELIANCE",
            Side.LONG,
            Decimal("100"),
            Decimal("100.00"),
        )
        assert position.stop_loss is None

    def test_pyramid_add_does_not_overwrite_stop_loss(self, account) -> None:
        fund(account)
        ledger = PositionLedgerService()
        position = _open_position(ledger, account)
        assert position.stop_loss == Decimal("95.00")

        # Same-direction add-on fill carries a different stop -> must NOT
        # overwrite the original entry's stop (§4 semantics).
        added = ledger.record_fill(
            account.id,
            "RELIANCE",
            Side.LONG,
            Decimal("50"),
            Decimal("105.00"),
            stop_loss=Decimal("90.00"),
            source_fill_id=uuid.uuid4(),
        )
        assert added.quantity == Decimal("150")
        assert added.stop_loss == Decimal("95.00")


class TestCloseOnStopTriggered:
    def test_long_stop_hit_closes_with_realized_pnl_and_event(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = PositionLedgerService()
        _open_position(ledger, account, stop_loss="95.00")

        correlation_id = uuid.uuid4()
        event = _ta_event(low="94.00", correlation_id=correlation_id)
        closed = ExitEvaluationService(ledger=ledger).evaluate_ta_completed(event)

        assert closed is not None
        assert Position.objects.filter(account_id=account.id).count() == 0

        # Exactly one PositionClosed; gap-through fill at the worse price.
        closed_events = published_events_of_type(
            bus.published_events, "positions.PositionClosed"
        )
        assert len(closed_events) == 1
        payload = closed_events[0].payload
        assert payload["symbol"] == "RELIANCE"
        assert payload["side"] == "LONG"
        assert payload["exit_price"] == "94"
        assert Decimal(payload["realized_pnl"]) == Decimal("-600")

        state = AccountCapitalState.objects.get(account=account)
        assert state.realized_pnl_today == Decimal("-600")

        # Correlation chain inherited from the triggering TA event.
        assert closed_events[0].correlation_id == correlation_id
        assert closed_events[0].causation_id == event.event_id

    def test_short_stop_hit_realizes_loss(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        ledger = PositionLedgerService()
        _open_position(
            ledger, account, side=Side.SHORT, price="100.00", stop_loss="102.00"
        )

        # High gaps above the stop -> SHORT realized = (entry - exit) * qty.
        event = _ta_event(high="112.00", low="109.00")
        closed = ExitEvaluationService(ledger=ledger).evaluate_ta_completed(event)
        assert closed is not None

        closed_events = published_events_of_type(
            bus.published_events, "positions.PositionClosed"
        )
        assert len(closed_events) == 1
        assert closed_events[0].payload["exit_price"] == "112"
        realized = Decimal(closed_events[0].payload["realized_pnl"])
        assert realized == (Decimal("100") - Decimal("112")) * Decimal("100")


class TestSafeNoOps:
    def test_position_without_stop_loss_is_no_op(self, account) -> None:
        fund(account)
        bus = get_event_bus()
        PositionLedgerService().record_fill(
            account.id,
            "RELIANCE",
            Side.LONG,
            Decimal("100"),
            Decimal("100.00"),
        )
        handle_ta_completed(_ta_event(low="50.00"))
        assert Position.objects.filter(account_id=account.id).count() == 1
        closed_events = published_events_of_type(
            bus.published_events, "positions.PositionClosed"
        )
        assert len(closed_events) == 0  # stop is None -> never closed

    def test_no_open_position_is_no_op(self, account) -> None:
        bus = get_event_bus()
        handle_ta_completed(_ta_event())
        assert len(bus.published_events) == 0

    def test_missing_price_extremes_is_no_op(self, account) -> None:
        fund(account)
        _open_position(PositionLedgerService(), account)
        bus = get_event_bus()
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={"symbol": "RELIANCE", "price": {"high": "103.00"}},
            correlation_id=uuid.uuid4(),
        )
        handle_ta_completed(event)
        assert Position.objects.filter(account_id=account.id).count() == 1


class TestDecisionBOrderIndependence:
    def test_same_bar_position_is_never_stop_closed(self, account) -> None:
        """Decision B: order-independent ``opened_at`` guard.

        A position whose ``opened_at`` is at/after the current bar's
        timestamp (i.e. a same-bar re-entry) must not be stop-closed by the
        very bar that opened it, regardless of EventBus dispatch ordering.
        """
        fund(account)
        bus = get_event_bus()
        ledger = PositionLedgerService()
        bar_time = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)
        _open_position(ledger, account, stop_loss="95.00", opened_at=bar_time)

        # Bar timestamp == opened_at, low far below the stop: guard must win.
        event = _ta_event(
            snapshot_timestamp="2024-06-10T07:00:00+00:00", low="50.00"
        )
        closed = ExitEvaluationService(ledger=ledger).evaluate_ta_completed(event)
        assert closed is None
        assert Position.objects.filter(account_id=account.id).count() == 1
        closed_events = published_events_of_type(
            bus.published_events, "positions.PositionClosed"
        )
        assert len(closed_events) == 0


class TestIdempotencyDuplicateDelivery:
    def test_same_bar_twice_does_not_double_close(self, account) -> None:
        fund(account)
        ledger = PositionLedgerService()
        _open_position(ledger, account)

        event = _ta_event(low="94.00")
        service = ExitEvaluationService(ledger=ledger)

        first = service.evaluate_ta_completed(event)
        second = service.evaluate_ta_completed(event)

        assert first is not None
        assert second is None  # position already closed -> no second close
        closed_events = published_events_of_type(
            get_event_bus().published_events, "positions.PositionClosed"
        )
        assert len(closed_events) == 1
        assert AccountCapitalState.objects.get(account=account).realized_pnl_today == Decimal("-600")
