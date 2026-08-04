from __future__ import annotations

import uuid
from decimal import Decimal
from unittest import mock

import pytest
from django.test import override_settings

from apps.execution.infrastructure import tasks as execution_tasks
from apps.execution.infrastructure.models import ExecutionRequest, Order

pytestmark = pytest.mark.django_db


def _approved_payload(**overrides: object) -> dict:
    from apps.risk_management.domain.events import RiskApproved

    base = RiskApproved(
        symbol="RELIANCE",
        rule_id="long_momentum_v1",
        event_type="BREAKOUT",
        entry_price=Decimal("103.00"),
        stop_loss=Decimal("101.00"),
        position_size=5000,
        risk_amount=Decimal("10000"),
        risk_pct_of_capital=Decimal("0.01"),
        risk_reward_ratio=Decimal("3.5"),
        portfolio_gateway_impl="portfolio_v1",
    )
    payload = base.to_payload()
    payload.update({k: v for k, v in overrides.items()})
    return payload


def _task_kwargs(**overrides: object) -> dict:
    kwargs = {
        "payload": _approved_payload(),
        "correlation_id": str(uuid.uuid4()),
        "causation_id": str(uuid.uuid4()),
        "risk_approved_event_id": str(uuid.uuid4()),
    }
    kwargs.update(overrides)
    return kwargs


class TestExecutionEngineGate:
    def test_disabled_produces_zero_execution_side_effects(self) -> None:
        with (
            override_settings(EXECUTION_ENGINE_ENABLED=False),
            mock.patch.object(execution_tasks, "ExecutionRequestService") as service_cls,
            mock.patch.object(execution_tasks, "process_order") as process_order,
        ):
            result = execution_tasks.handle_risk_approved.run(**_task_kwargs())

        assert result["outcome"] == "EXECUTION_DISABLED"
        assert result["order_id"] == ""
        assert result["request_id"] == ""
        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0
        service_cls.return_value.intake.assert_not_called()
        process_order.delay.assert_not_called()

    def test_disabled_returns_before_intake_uses_spy(self) -> None:
        with (
            override_settings(EXECUTION_ENGINE_ENABLED=False),
            mock.patch.object(execution_tasks, "ExecutionRequestService") as service_cls,
        ):
            execution_tasks.handle_risk_approved.run(**_task_kwargs())
            service_cls.assert_not_called()

        assert ExecutionRequest.objects.count() == 0
        assert Order.objects.count() == 0

    def test_enabled_creates_order_and_enqueues_process_order(self) -> None:
        kwargs = _task_kwargs()
        with (
            override_settings(EXECUTION_ENGINE_ENABLED=True),
            mock.patch.object(execution_tasks, "process_order") as process_order,
        ):
            result = execution_tasks.handle_risk_approved.run(**kwargs)

        assert result["outcome"] == "CREATED"
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1
        order = Order.objects.get()
        assert result["order_id"] == str(order.id)
        assert order.status == "CREATED"
        process_order.delay.assert_called_once()
        call_args = process_order.delay.call_args
        assert call_args[0][0] == str(order.id)
        assert call_args[1]["correlation_id"] == kwargs["correlation_id"]

    def test_enabled_outcome_matches_intake_contract(self) -> None:
        with (
            override_settings(EXECUTION_ENGINE_ENABLED=True),
            mock.patch.object(execution_tasks, "process_order"),
        ):
            result = execution_tasks.handle_risk_approved.run(**_task_kwargs())

        assert result["outcome"] == "CREATED"
        assert result["request_id"]
        assert result["order_id"]

    def test_idempotency_duplicate_unchanged_when_enabled(self) -> None:
        event_id = str(uuid.uuid4())
        kwargs = _task_kwargs(risk_approved_event_id=event_id)
        with (
            override_settings(EXECUTION_ENGINE_ENABLED=True),
            mock.patch.object(execution_tasks, "process_order"),
        ):
            first = execution_tasks.handle_risk_approved.run(**kwargs)
            second = execution_tasks.handle_risk_approved.run(**kwargs)

        assert first["outcome"] == "CREATED"
        assert second["outcome"] == "DUPLICATE"
        assert ExecutionRequest.objects.count() == 1
        assert Order.objects.count() == 1

    def test_risk_approved_subscription_still_dispatches(
        self, register_risk_handlers
    ) -> None:
        from apps.eventbus.domain.events import DomainEvent
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus

        bus = get_event_bus()
        register_risk_handlers(bus)

        correlation_id = uuid.uuid4()
        event = DomainEvent.create(
            event_type="risk_management.RiskApproved",
            payload=_approved_payload(),
            correlation_id=correlation_id,
            causation_id=uuid.uuid4(),
        )

        with mock.patch.object(execution_tasks.handle_risk_approved, "delay") as delay:
            bus.publish(event)
            delay.assert_called_once()

        _, kwargs = delay.call_args
        assert kwargs["risk_approved_event_id"] == str(event.event_id)
        assert kwargs["correlation_id"] == str(correlation_id)
        assert kwargs["payload"]["symbol"] == "RELIANCE"
