"""Backtest run API tests."""

from __future__ import annotations

import uuid
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role
from apps.accounts.infrastructure.models import Account
from apps.backtesting.models import BacktestRun
from apps.portfolio.infrastructure.models import AccountCapitalState

pytestmark = pytest.mark.django_db

_RUN_PAYLOAD = {
    "symbol": "RELIANCE",
    "timeframe": "1D",
    "range_start": "2024-06-09T00:00:00Z",
    "range_end": "2024-06-11T00:00:00Z",
    "initial_capital": "1000000",
}


def _staff_client(django_user_model) -> APIClient:
    user = django_user_model.objects.create_user(
        username=f"staff_{uuid.uuid4().hex[:8]}",
        password="p",
        role=Role.STAFF.value,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


class TestCreateRun:
    def test_create_run_creates_isolated_funded_account(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        response = client.post(
            "/api/v1/backtesting/runs/", _RUN_PAYLOAD, format="json"
        )
        assert response.status_code == 201
        body = response.data
        run = BacktestRun.objects.get(id=body["run_id"])
        assert run.symbol == "RELIANCE"
        assert run.timeframe == "1D"
        # Eager test env: the enqueued run already completed with zero bars.
        assert run.status == "COMPLETED"
        assert body["status"] == "PENDING"

        account = Account.objects.get(id=body["account_id"])
        assert account.is_default is False
        assert account.id == run.account_id
        capital = AccountCapitalState.objects.get(account_id=account.id)
        assert capital.equity == Decimal("1000000")
        assert capital.available_capital == Decimal("1000000")

    def test_create_run_enqueues_and_completes_eagerly(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        response = client.post(
            "/api/v1/backtesting/runs/", _RUN_PAYLOAD, format="json"
        )
        assert response.status_code == 201
        run = BacktestRun.objects.get(id=response.data["run_id"])
        assert run.status == "COMPLETED"
        assert run.completed_at is not None

    def test_default_capital_applied(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {k: v for k, v in _RUN_PAYLOAD.items() if k != "initial_capital"}
        response = client.post("/api/v1/backtesting/runs/", payload, format="json")
        assert response.status_code == 201
        capital = AccountCapitalState.objects.get(account_id=response.data["account_id"])
        assert capital.equity == Decimal("1000000")

    def test_invalid_range_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_RUN_PAYLOAD, "range_end": "2024-06-09T00:00:00Z"}
        response = client.post("/api/v1/backtesting/runs/", payload, format="json")
        assert response.status_code == 400

    def test_missing_symbol_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {k: v for k, v in _RUN_PAYLOAD.items() if k != "symbol"}
        response = client.post("/api/v1/backtesting/runs/", payload, format="json")
        assert response.status_code == 400


class TestReadRun:
    def test_get_run_status_and_stats(self, backtest_run, django_user_model) -> None:
        from decimal import Decimal

        client = _staff_client(django_user_model)
        response = client.get(f"/api/v1/backtesting/runs/{backtest_run.id}/")
        assert response.status_code == 200
        assert response.data["status"] == backtest_run.status
        assert response.data["account_id"] == str(backtest_run.account_id)
        assert response.data["stats"]["trade_count"] == 0
        assert Decimal(response.data["stats"]["equity_at_completion"]) == Decimal("1000000")

    def test_get_unknown_run_404(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        response = client.get(f"/api/v1/backtesting/runs/{uuid.uuid4()}/")
        assert response.status_code == 404


class TestAuth:
    def test_anonymous_denied(self) -> None:
        client = APIClient()
        assert client.post(
            "/api/v1/backtesting/runs/", _RUN_PAYLOAD, format="json"
        ).status_code in (401, 403)
        assert client.get("/api/v1/backtesting/runs/").status_code in (401, 403)
