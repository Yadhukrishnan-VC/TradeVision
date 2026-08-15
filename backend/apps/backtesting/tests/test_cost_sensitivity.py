"""Batch COST-SENSITIVITY-1 — per-rule cost-breakeven analysis tests.

A cost sweep runs the *unmodified* single-run engine once per grid point in a
``(commission_rate, slippage_bps)`` grid, each point owning a dedicated
isolated funded account so no point's records leak into another (exactly like
WALKFORWARD-VALIDATION-1). The tests stub ``BacktestRunnerService.run`` to seed
deterministic orders + rule attributions per point, and pin the exact per-rule
expectancy series and breakeven values against the seed fixture:

* ``long_momentum_v1`` — 2 wins (+1000, +500) and 1 loss (-500) at zero cost;
  expectancy decays 333.33... -> -226.66... across the grid, crossing zero
  between the 0.010 and 0.015 commission points (BREAKEVEN_FOUND).
* ``always_win_v1`` — 3 wins (+1000 each); stays positive for the whole grid
  (SURVIVES_FULL_RANGE).
* ``never_profitable_v1`` — 1 loss (-1000); never becomes positive
  (NEVER_PROFITABLE).
"""

from __future__ import annotations

import itertools
import uuid
from datetime import datetime, timezone
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role
from apps.accounts.infrastructure.models import Account
from apps.backtesting.application.cost_sensitivity_service import (
    CostSensitivityService,
    cost_level,
    find_breakeven,
    generate_cost_grid,
)
from apps.backtesting.models import BacktestRun
from apps.backtesting.services import BacktestRunnerService

_UTC = timezone.utc
_D0 = datetime(2024, 1, 1, tzinfo=_UTC)
_D1 = datetime(2024, 3, 1, tzinfo=_UTC)

_COMMISSION_GRID = ["0", "0.005", "0.010", "0.015", "0.020"]

_LONG_SERIES = [
    "333.3333333333333333333333334",
    "193.3333333333333333333333334",
    "53.3333333333333333333333334",
    "-86.6666666666666666666666666",
    "-226.6666666666666666666666666",
]

_ALWAYS_WIN_SERIES = [
    "1000.0000000000000000",
    "890.0000000000000000000",
    "780.000000000000000000",
    "670.0000000000000000000",
    "560.000000000000000000",
]

_NEVER_SERIES = [
    "-1000.0000000000000000",
    "-1110.0000000000000000000",
    "-1220.000000000000000000",
    "-1330.0000000000000000000",
    "-1440.000000000000000000",
]


def _dt(year: int, month: int, day: int, hour: int = 10) -> datetime:
    return datetime(year, month, day, hour, tzinfo=_UTC)


class TestGenerateCostGrid:
    def test_cartesian_product_commissions_fastest(self) -> None:
        grid = generate_cost_grid(
            (Decimal(0), Decimal("0.0002")),
            Decimal("0.0001"),
            (Decimal(0), Decimal(2)),
            Decimal(2),
        )
        assert grid == [
            (Decimal(0), Decimal(0)),
            (Decimal(0), Decimal(2)),
            (Decimal("0.0001"), Decimal(0)),
            (Decimal("0.0001"), Decimal(2)),
            (Decimal("0.0002"), Decimal(0)),
            (Decimal("0.0002"), Decimal(2)),
        ]

    def test_single_point_when_ranges_are_zero_width(self) -> None:
        grid = generate_cost_grid(
            (Decimal("0.001"), Decimal("0.001")),
            Decimal("0.001"),
            (Decimal(0), Decimal(0)),
            Decimal(1),
        )
        assert grid == [(Decimal("0.001"), Decimal(0))]

    def test_non_positive_commission_step_rejected(self) -> None:
        with pytest.raises(ValueError):
            generate_cost_grid(
                (Decimal(0), Decimal(1)),
                Decimal(0),
                (Decimal(0), Decimal(1)),
                Decimal(1),
            )

    def test_non_positive_slippage_step_rejected(self) -> None:
        with pytest.raises(ValueError):
            generate_cost_grid(
                (Decimal(0), Decimal(1)),
                Decimal("0.1"),
                (Decimal(0), Decimal(1)),
                Decimal(-1),
            )

    def test_inverted_commission_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            generate_cost_grid(
                (Decimal("0.01"), Decimal(0)),
                Decimal("0.1"),
                (Decimal(0), Decimal(1)),
                Decimal(1),
            )

    def test_inverted_slippage_range_rejected(self) -> None:
        with pytest.raises(ValueError):
            generate_cost_grid(
                (Decimal(0), Decimal(1)),
                Decimal("0.1"),
                (Decimal(2), Decimal(1)),
                Decimal(1),
            )


class TestCostLevel:
    def test_combines_commission_and_slippage_impact(self) -> None:
        assert cost_level(Decimal("0.001"), Decimal(10)) == Decimal("0.002")

    def test_slippage_converted_from_bps(self) -> None:
        assert cost_level(Decimal(0), Decimal(5)) == Decimal("0.0005")

    def test_zero_costs_give_zero_level(self) -> None:
        assert cost_level(Decimal(0), Decimal(0)) == Decimal(0)


class TestFindBreakeven:
    def test_interpolates_downward_crossing(self) -> None:
        rows = [
            {"cost_level": Decimal(0), "expectancy": Decimal(20)},
            {"cost_level": Decimal("0.01"), "expectancy": Decimal(-40)},
        ]
        expected = (Decimal("0.01") - Decimal(0)) * (
            Decimal(-20) / (Decimal(-40) - Decimal(20))
        )
        assert find_breakeven(rows) == expected

    def test_interpolates_upward_crossing(self) -> None:
        rows = [
            {"cost_level": Decimal(0), "expectancy": Decimal(-20)},
            {"cost_level": Decimal("0.01"), "expectancy": Decimal(40)},
        ]
        expected = (Decimal("0.01") - Decimal(0)) * (
            Decimal(20) / (Decimal(40) - Decimal(-20))
        )
        assert find_breakeven(rows) == expected

    def test_exact_zero_expectancy_returns_its_own_level(self) -> None:
        rows = [
            {"cost_level": Decimal("0.001"), "expectancy": Decimal(0)},
            {"cost_level": Decimal("0.003"), "expectancy": Decimal(-1)},
        ]
        assert find_breakeven(rows) == Decimal("0.001")

    def test_no_crossing_returns_none(self) -> None:
        rows = [
            {"cost_level": Decimal(0), "expectancy": Decimal(10)},
            {"cost_level": Decimal("0.01"), "expectancy": Decimal(5)},
        ]
        assert find_breakeven(rows) is None

    def test_all_negative_returns_none(self) -> None:
        rows = [
            {"cost_level": Decimal(0), "expectancy": Decimal(-10)},
            {"cost_level": Decimal("0.01"), "expectancy": Decimal(-5)},
        ]
        assert find_breakeven(rows) is None

    def test_empty_series_returns_none(self) -> None:
        assert find_breakeven([]) is None

    def test_unsorted_input_is_sorted_first(self) -> None:
        rows = [
            {"cost_level": Decimal("0.01"), "expectancy": Decimal(-40)},
            {"cost_level": Decimal(0), "expectancy": Decimal(20)},
        ]
        expected = find_breakeven(
            [
                {"cost_level": Decimal(0), "expectancy": Decimal(20)},
                {"cost_level": Decimal("0.01"), "expectancy": Decimal(-40)},
            ]
        )
        assert find_breakeven(rows) == expected


class _SeedingRunner:
    """Stub ``BacktestRunnerService.run`` that seeds deterministic trades."""

    def __init__(self, seed) -> None:
        self._seed = seed

    def run(self, run_id: uuid.UUID) -> dict[str, str]:
        run = BacktestRun.objects.get(id=run_id)
        self._seed(run)
        return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}


@pytest.mark.django_db
class TestCostSensitivityExecution:

    def _create_trade(
        self,
        run,
        side: str,
        entry: str,
        fill: str,
        qty: int,
        created_at: datetime,
        rule_id: str,
        correlation_id,
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
        from apps.rule_engine.infrastructure.models import RuleExecution

        account_id = run.account_id
        req = ExecutionRequest.objects.create(
            idempotency_key=f"key-{correlation_id}",
            account_id=account_id,
            symbol="RELIANCE",
            side=side,
            quantity=Decimal(qty),
            entry_price=Decimal(entry),
            stop_loss=Decimal("90.00"),
            correlation_id=correlation_id,
            risk_approved_event_id=uuid.uuid4(),
            rule_id=rule_id,
            event_type="BREAKOUT",
            status="FILLED",
        )
        order = Order.objects.create(
            execution_request=req,
            account_id=account_id,
            symbol="RELIANCE",
            side=side,
            quantity=Decimal(qty),
            status="FILLED",
            filled_quantity=Decimal(qty),
            avg_fill_price=Decimal(fill),
            entry_price=Decimal(entry),
            stop_loss=Decimal("90.00"),
            correlation_id=correlation_id,
        )
        Order.objects.filter(id=order.id).update(created_at=created_at)
        Fill.objects.create(
            order=order,
            sequence=1,
            quantity=Decimal(qty),
            price=Decimal(fill),
            occurred_at=created_at,
        )
        # Rule attribution: Order.correlation_id -> RuleExecution.analysis_event_id
        RuleExecution.objects.create(
            analysis_event_id=correlation_id,
            symbol="RELIANCE",
            rule_id=rule_id,
            severity="info",
            trigger_data={"mode": "backtest"},
        )

    def _seed_trades(self, run) -> None:
        """The module-docstring fixture, burned into every grid point.

        Cost-free at zero commission/slippage; ``run_stats`` applies the point's
        own commission/slippage to the same orders each run, so expectancy decays
        deterministically with the combined cost rate.
        """
        self._create_trade(
            run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, 20),
            "long_momentum_v1", correlation_id=uuid.uuid4(),
        )
        self._create_trade(
            run, "LONG", "100.00", "105.00", 100, _dt(2024, 1, 21),
            "long_momentum_v1", correlation_id=uuid.uuid4(),
        )
        self._create_trade(
            run, "SHORT", "200.00", "205.00", 100, _dt(2024, 1, 22),
            "long_momentum_v1", correlation_id=uuid.uuid4(),
        )
        self._create_trade(
            run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, 24),
            "always_win_v1", correlation_id=uuid.uuid4(),
        )
        self._create_trade(
            run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, 25),
            "always_win_v1", correlation_id=uuid.uuid4(),
        )
        self._create_trade(
            run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, 26),
            "always_win_v1", correlation_id=uuid.uuid4(),
        )
        self._create_trade(
            run, "SHORT", "100.00", "110.00", 100, _dt(2024, 1, 23),
            "never_profitable_v1", correlation_id=uuid.uuid4(),
        )

    def _execute(self, django_user_model) -> dict:
        user = django_user_model.objects.create_user(
            username=f"cs_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = CostSensitivityService(runner=_SeedingRunner(self._seed_trades))
        return service.execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_D1,
            commission_range=(Decimal(0), Decimal("0.02")),
            commission_step=Decimal("0.005"),
            slippage_range=(Decimal(0), Decimal(0)),
            slippage_step=Decimal(1),
            initial_capital=Decimal(1000000),
        )

    def test_execute_reports_all_three_classifications(self, django_user_model) -> None:
        result = self._execute(django_user_model)
        assert result["grid_points_run"] == 5
        assert set(result["by_rule"]) == {
            "long_momentum_v1",
            "always_win_v1",
            "never_profitable_v1",
        }

    def _series_assertions(
        self,
        rule_key: str,
        result: dict,
        expected: list[str],
        trade_counts: list[int] | None = None,
    ) -> None:
        report = result["by_rule"][rule_key]
        series = report["series"]
        assert len(series) == 5
        assert [point["cost_level"] for point in series] == _COMMISSION_GRID
        if trade_counts is not None:
            assert [point["trade_count"] for point in series] == trade_counts
        # Compare numerically: ``run_stats`` scales each expectancy's precision
        # to the grid point's own commission/slippage, so exact strings vary.
        assert [
            Decimal(point["expectancy"]) for point in series
        ] == [Decimal(value) for value in expected]
        # Cost never improves a rule: expectancy must be monotone non-increasing.
        expectancies = [Decimal(point["expectancy"]) for point in series]
        assert all(
            earlier >= later
            for earlier, later in itertools.pairwise(expectancies)
        )

    def test_long_momentum_interpolates_breakeven(self, django_user_model) -> None:
        result = self._execute(django_user_model)
        self._series_assertions(
            "long_momentum_v1", result, _LONG_SERIES, [3, 3, 3, 3, 3]
        )
        report = result["by_rule"]["long_momentum_v1"]
        assert report["classification"] == "BREAKEVEN_FOUND"
        assert Decimal(report["breakeven_commission_rate"]) == Decimal(
            "0.01190476190476190476190476191"
        )
        assert Decimal(report["breakeven_slippage_bps"]) == Decimal(
            "119.0476190476190476190476191"
        )
        assert Decimal(report["expectancy_at_min_cost"]) == Decimal(
            "333.3333333333333333333333334"
        )
        assert Decimal(report["expectancy_at_max_cost"]) == Decimal(
            "-226.6666666666666666666666666"
        )

    def test_always_win_survives_full_range(self, django_user_model) -> None:
        result = self._execute(django_user_model)
        self._series_assertions(
            "always_win_v1", result, _ALWAYS_WIN_SERIES, [3, 3, 3, 3, 3]
        )
        report = result["by_rule"]["always_win_v1"]
        assert report["classification"] == "SURVIVES_FULL_RANGE"
        assert Decimal(report["breakeven_commission_rate"]) == Decimal("0.02")
        assert Decimal(report["breakeven_slippage_bps"]) == Decimal(200)

    def test_never_profitable_has_no_breakeven(self, django_user_model) -> None:
        result = self._execute(django_user_model)
        self._series_assertions(
            "never_profitable_v1", result, _NEVER_SERIES, [1, 1, 1, 1, 1]
        )
        report = result["by_rule"]["never_profitable_v1"]
        assert report["classification"] == "NEVER_PROFITABLE"
        assert report["breakeven_commission_rate"] is None
        assert report["breakeven_slippage_bps"] is None

    def test_each_grid_point_has_isolated_funded_account(
        self, django_user_model
    ) -> None:
        from apps.execution.infrastructure.models import Order
        from apps.portfolio.infrastructure.models import AccountCapitalState

        self._execute(django_user_model)
        runs = list(BacktestRun.objects.order_by("created_at"))
        assert len(runs) == 5
        assert len({run.account_id for run in runs}) == 5
        for run in runs:
            capital = AccountCapitalState.objects.get(account_id=run.account_id)
            assert capital.equity == Decimal(1000000)
            assert capital.available_capital == Decimal(1000000)
            orders = list(Order.objects.filter(account_id=run.account_id))
            assert len(orders) == 7
        # Grid points never reuse records from another point.
        assert len(Account.objects.filter(is_default=False)) == 5

    def test_grid_point_failure_is_isolated_and_reported(
        self, django_user_model
    ) -> None:
        def failing_seed(run) -> None:
            run.refresh_from_db()
            if run.commission_rate == Decimal("0.01"):
                raise RuntimeError("simulated engine failure")

        class _Runner:
            def __init__(self, seed) -> None:
                self._seed = seed

            def run(self, run_id) -> dict[str, str]:
                run = BacktestRun.objects.get(id=run_id)
                self._seed(run)
                return {
                    "status": "COMPLETED",
                    "run_id": str(run_id),
                    "bars_processed": "0",
                }

        user = django_user_model.objects.create_user(
            username=f"cs_fail_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = CostSensitivityService(runner=_Runner(failing_seed))
        result = service.execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_D1,
            commission_range=(Decimal(0), Decimal("0.02")),
            commission_step=Decimal("0.005"),
            slippage_range=(Decimal(0), Decimal(0)),
            slippage_step=Decimal(1),
        )
        assert result["grid_points_run"] == 4
        for report in result["by_rule"].values():
            assert len(report["series"]) == 4
            assert "0.010" not in [point["cost_level"] for point in report["series"]]

    def test_oversized_grid_rejected(self, django_user_model) -> None:
        user = django_user_model.objects.create_user(
            username=f"cs_big_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = CostSensitivityService(runner=_SeedingRunner(self._seed_trades))
        with pytest.raises(ValueError):
            service.execute(
                owner=user,
                symbol="RELIANCE",
                range_start=_D0,
                range_end=_D1,
                commission_range=(Decimal(0), Decimal("0.005")),
                commission_step=Decimal("0.0001"),
                slippage_range=(Decimal(0), Decimal(0)),
                slippage_step=Decimal(1),
            )


def _staff_client(django_user_model) -> APIClient:
    user = django_user_model.objects.create_user(
        username=f"cs_staff_{uuid.uuid4().hex[:8]}",
        password="p",
        role=Role.STAFF.value,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


_CS_PAYLOAD = {
    "symbol": "RELIANCE",
    "timeframe": "1D",
    "range_start": "2024-01-01T00:00:00Z",
    "range_end": "2024-03-01T00:00:00Z",
    "commission_start": "0.0",
    "commission_end": "0.02",
    "commission_step": "0.005",
    "slippage_start": "0.0",
    "slippage_end": "0.0",
    "slippage_step": "1.0",
}


@pytest.mark.django_db
class TestCostSensitivityApi:
    def test_post_cost_sensitivity_returns_report(self, django_user_model, monkeypatch) -> None:
        def fake_run(service, run_id) -> dict[str, str]:
            return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}

        monkeypatch.setattr(BacktestRunnerService, "run", fake_run)
        client = _staff_client(django_user_model)
        response = client.post(
            "/api/v1/backtesting/cost-sensitivity/", _CS_PAYLOAD, format="json"
        )
        assert response.status_code == 200
        body = response.data
        assert body["grid_points_run"] == 5
        assert body["by_rule"] == {}

    def test_invalid_range_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_CS_PAYLOAD, "range_end": "2023-12-31T00:00:00Z"}
        response = client.post(
            "/api/v1/backtesting/cost-sensitivity/", payload, format="json"
        )
        assert response.status_code == 400

    def test_non_positive_step_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_CS_PAYLOAD, "commission_step": "0.0"}
        response = client.post(
            "/api/v1/backtesting/cost-sensitivity/", payload, format="json"
        )
        assert response.status_code == 400

    def test_inverted_commission_range_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {
            **_CS_PAYLOAD,
            "commission_start": "0.02",
            "commission_end": "0.0",
        }
        response = client.post(
            "/api/v1/backtesting/cost-sensitivity/", payload, format="json"
        )
        assert response.status_code == 400

    def test_oversized_grid_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_CS_PAYLOAD, "commission_step": "0.0001"}
        response = client.post(
            "/api/v1/backtesting/cost-sensitivity/", payload, format="json"
        )
        assert response.status_code == 400

    def test_anonymous_denied(self) -> None:
        client = APIClient()
        response = client.post(
            "/api/v1/backtesting/cost-sensitivity/", _CS_PAYLOAD, format="json"
        )
        assert response.status_code in (401, 403)