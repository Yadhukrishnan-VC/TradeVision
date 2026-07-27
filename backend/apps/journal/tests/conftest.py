from __future__ import annotations

import uuid

import pytest

from apps.eventbus.domain.events import DomainEvent


@pytest.fixture
def correlation_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def account_id() -> uuid.UUID:
    return uuid.uuid4()


@pytest.fixture
def position_id() -> uuid.UUID:
    return uuid.uuid4()


def make_event(
    event_type: str,
    correlation_id: uuid.UUID,
    account_id: uuid.UUID,
    extra_payload: dict | None = None,
) -> DomainEvent:
    payload = {"account_id": str(account_id)}
    if extra_payload:
        payload.update(extra_payload)
    return DomainEvent.create(
        event_type=event_type,
        payload=payload,
        correlation_id=correlation_id,
    )


@pytest.fixture
def signal_created_event(correlation_id: uuid.UUID, account_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "signals.SignalCreated",
        correlation_id,
        account_id,
        extra_payload={
            "symbol": "RELIANCE",
            "signal_type": "buy",
            "confidence": 0.85,
        },
    )


@pytest.fixture
def decision_made_event(correlation_id: uuid.UUID, account_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "decisions.TradeDecisionMade",
        correlation_id,
        account_id,
        extra_payload={
            "symbol": "RELIANCE",
            "decision": "enter_long",
            "quantity": 100,
        },
    )


@pytest.fixture
def order_placed_event(correlation_id: uuid.UUID, account_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "orders.OrderPlaced",
        correlation_id,
        account_id,
        extra_payload={
            "order_id": str(uuid.uuid4()),
            "symbol": "RELIANCE",
            "side": "buy",
            "quantity": 100,
        },
    )


@pytest.fixture
def order_filled_event(correlation_id: uuid.UUID, account_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "orders.OrderFilled",
        correlation_id,
        account_id,
        extra_payload={
            "order_id": str(uuid.uuid4()),
            "symbol": "RELIANCE",
            "side": "buy",
            "quantity": 100,
            "fill_price": 2500.00,
        },
    )


@pytest.fixture
def position_opened_event(correlation_id: uuid.UUID, account_id: uuid.UUID, position_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "positions.PositionOpened",
        correlation_id,
        account_id,
        extra_payload={
            "position_id": str(position_id),
            "symbol": "RELIANCE",
            "quantity": 100,
            "entry_price": 2500.00,
        },
    )


@pytest.fixture
def position_closed_event(correlation_id: uuid.UUID, account_id: uuid.UUID, position_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "positions.PositionClosed",
        correlation_id,
        account_id,
        extra_payload={
            "position_id": str(position_id),
            "symbol": "RELIANCE",
            "realized_pnl": 5000.00,
        },
    )


@pytest.fixture
def position_closed_losing_event(correlation_id: uuid.UUID, account_id: uuid.UUID, position_id: uuid.UUID) -> DomainEvent:
    return make_event(
        "positions.PositionClosed",
        correlation_id,
        account_id,
        extra_payload={
            "position_id": str(position_id),
            "symbol": "RELIANCE",
            "realized_pnl": -2500.00,
        },
    )
