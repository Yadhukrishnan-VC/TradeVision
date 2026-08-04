from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role
from apps.execution.application.execution_request_service import ExecutionRequestService
from apps.execution.infrastructure.models import Order

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


def _staff_client(django_user_model) -> APIClient:
    user = django_user_model.objects.create_user(
        username=f"staff_{uuid.uuid4().hex[:8]}",
        password="p",
        role=Role.STAFF.value,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestExecutionAPI:
    def test_order_and_request_endpoints_are_read_only(
        self, account, django_user_model
    ) -> None:
        service = ExecutionRequestService()
        result = service.intake(
            payload=_approved_payload(),
            correlation_id=uuid.uuid4(),
            causation_id=None,
            risk_approved_event_id=uuid.uuid4(),
        )
        assert result.outcome == "CREATED"
        order = Order.objects.get(id=result.order_id)

        client = _staff_client(django_user_model)

        orders_resp = client.get("/api/v1/execution/orders/")
        assert orders_resp.status_code == 200
        assert orders_resp.data["count"] == 1
        assert orders_resp.data["results"][0]["id"] == str(order.id)

        detail_resp = client.get(f"/api/v1/execution/orders/{order.id}/")
        assert detail_resp.status_code == 200
        assert detail_resp.data["status"] == "CREATED"
        assert detail_resp.data["order_type"] == "market"

        requests_resp = client.get("/api/v1/execution/requests/")
        assert requests_resp.status_code == 200
        assert requests_resp.data["count"] == 1
        assert requests_resp.data["results"][0]["status"] == "ORDER_CREATED"

    def test_anonymous_user_denied(self) -> None:
        client = APIClient()
        assert client.get("/api/v1/execution/orders/").status_code in (401, 403)

    def test_order_filters(self, account, django_user_model) -> None:
        service = ExecutionRequestService()
        service.intake(
            payload=_approved_payload(),
            correlation_id=uuid.uuid4(),
            causation_id=None,
            risk_approved_event_id=uuid.uuid4(),
        )

        client = _staff_client(django_user_model)
        resp = client.get("/api/v1/execution/orders/?symbol=RELIANCE&status=CREATED")
        assert resp.status_code == 200
        assert resp.data["count"] == 1

        resp = client.get("/api/v1/execution/orders/?symbol=NOPE")
        assert resp.status_code == 200
        assert resp.data["count"] == 0
