from __future__ import annotations

import pytest

from apps.execution.domain.entities import OrderState
from apps.execution.domain.exceptions import InvalidOrderTransition
from apps.execution.domain.value_objects import OrderStatus


class TestOrderStateMachine:
    def test_happy_path_creates_to_filled(self) -> None:
        path = [
            (OrderStatus.CREATED, OrderStatus.SUBMITTED),
            (OrderStatus.SUBMITTED, OrderStatus.ACKNOWLEDGED),
            (OrderStatus.ACKNOWLEDGED, OrderStatus.PARTIALLY_FILLED),
            (OrderStatus.PARTIALLY_FILLED, OrderStatus.PARTIALLY_FILLED),
            (OrderStatus.PARTIALLY_FILLED, OrderStatus.FILLED),
        ]
        current = OrderStatus.CREATED
        for current, next_status in path:
            assert OrderState.can_transition(current, next_status)
            assert OrderState.transition(current, next_status) is next_status

    def test_rejected_from_submitted_and_acknowledged(self) -> None:
        assert OrderState.can_transition(OrderStatus.SUBMITTED, OrderStatus.REJECTED)
        assert OrderState.can_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.REJECTED)

    def test_cancel_and_expire_paths(self) -> None:
        assert OrderState.can_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.CANCEL_REQUESTED)
        assert OrderState.can_transition(OrderStatus.CANCEL_REQUESTED, OrderStatus.CANCELLED)
        assert OrderState.can_transition(OrderStatus.ACKNOWLEDGED, OrderStatus.EXPIRED)
        assert OrderState.can_transition(OrderStatus.PARTIALLY_FILLED, OrderStatus.EXPIRED)

    def test_any_pre_terminal_can_fail(self) -> None:
        for pre_terminal in (
            OrderStatus.CREATED,
            OrderStatus.SUBMITTED,
            OrderStatus.ACKNOWLEDGED,
            OrderStatus.PARTIALLY_FILLED,
            OrderStatus.CANCEL_REQUESTED,
        ):
            assert OrderState.can_transition(pre_terminal, OrderStatus.FAILED)

    def test_terminal_statuses_are_terminal(self) -> None:
        for terminal in (OrderStatus.FILLED, OrderStatus.REJECTED, OrderStatus.CANCELLED,
                         OrderStatus.EXPIRED, OrderStatus.FAILED):
            assert OrderState.is_terminal(terminal)
        assert not OrderState.is_terminal(OrderStatus.ACKNOWLEDGED)
        assert not OrderState.is_terminal(OrderStatus.CREATED)

    def test_invalid_transition_raises(self) -> None:
        with pytest.raises(InvalidOrderTransition):
            OrderState.transition(OrderStatus.CREATED, OrderStatus.FILLED)

    def test_terminal_order_cannot_reopen(self) -> None:
        assert not OrderState.can_transition(OrderStatus.FILLED, OrderStatus.CREATED)
        assert not OrderState.can_transition(OrderStatus.REJECTED, OrderStatus.SUBMITTED)
