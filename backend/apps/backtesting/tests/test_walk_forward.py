"""Batch WALKFORWARD-VALIDATION-1 — rolling walk-forward validation tests.

A walk-forward study runs the *unmodified* single-run engine
(``BacktestRunnerService`` + ``BacktestStatsService.run_stats``) once per
sliding date window, each window owning a dedicated isolated account so no
window's records leak into another. The tests stub ``BacktestRunnerService.run``
to seed deterministic orders per window (the pipeline replay itself is already
covered by the M3 pipeline tests) and pin the exact per-window IS/OOS values —
including the ``MIN_TRADES_FOR_DISTRIBUTION`` exclusion — plus the cross-window
OOS endowment distribution (min / max / median / count_positive).
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role
from apps.backtesting.application.walk_forward_service import (
    WalkForwardService,
    calculate_distribution,
    generate_windows,
)
from apps.backtesting.models import BacktestRun
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService

_UTC = timezone.utc
_W0 = datetime(2024, 1, 1, tzinfo=_UTC)
_W1 = datetime(2024, 1, 31, tzinfo=_UTC)
_W2 = datetime(2024, 3, 1, tzinfo=_UTC)
_W3 = datetime(2024, 3, 31, tzinfo=_UTC)
_WINDOW_SIZE = timedelta(days=60)
_STEP = timedelta(days=30)
_RANGE_END = _W0 + timedelta(days=150)


def _dt(year: int, month: int, day: int, hour: int = 10) -> datetime:
    return datetime(year, month, day, hour, tzinfo=_UTC)


_WF_PAYLOAD = {
    "symbol": "RELIANCE",
    "timeframe": "1D",
    "range_start": "2024-01-01T00:00:00Z",
    "range_end": "2024-05-30T00:00:00Z",
    "window_size_days": 60,
    "step_size_days": 30,
}


class TestGenerateWindows:
    def test_slides_four_full_size_windows(self) -> None:
        windows = generate_windows(_W0, _RANGE_END, _WINDOW_SIZE, _STEP)
        assert windows == [
            (_W0, datetime(2024, 3, 1, tzinfo=_UTC)),
            (_W1, datetime(2024, 3, 31, tzinfo=_UTC)),
            (_W2, datetime(2024, 4, 30, tzinfo=_UTC)),
            (_W3, datetime(2024, 5, 30, tzinfo=_UTC)),
        ]

    def test_every_window_fits_and_starts_are_unique(self) -> None:
        windows = generate_windows(_W0, _RANGE_END, _WINDOW_SIZE, _STEP)
        assert len(windows) == 4
        assert all(start >= _W0 and end <= _RANGE_END for start, end in windows)
        starts = [start for start, _ in windows]
        assert len(set(starts)) == len(starts)

    def test_single_window_when_step_exceeds_remaining_range(self) -> None:
        windows = generate_windows(_W0, _RANGE_END, _WINDOW_SIZE, timedelta(days=120))
        assert windows == [(_W0, _W0 + _WINDOW_SIZE)]

    def test_no_windows_when_range_shorter_than_window(self) -> None:
        assert generate_windows(_W0, _W0 + timedelta(days=40), _WINDOW_SIZE, _STEP) == []

    def test_zero_step_falls_back_to_window_step(self) -> None:
        assert generate_windows(_W0, _RANGE_END, _WINDOW_SIZE, timedelta(days=0)) == (
            generate_windows(_W0, _RANGE_END, _WINDOW_SIZE, _WINDOW_SIZE)
        )


class TestCalculateDistribution:
    def test_hand_computed_three_values(self) -> None:
        values = [Decimal("50"), Decimal("-75"), Decimal("200")]
        assert calculate_distribution(values) == {
            "count": 3,
            "min": "-75",
            "max": "200",
            "mean": str(sum(values) / Decimal(3)),
            "median": "50",
            "count_positive": 2,
        }

    def test_even_count_median_averages_middle_pair(self) -> None:
        dist = calculate_distribution([Decimal("1"), Decimal("2"), Decimal("3"), Decimal("4")])
        assert dist["median"] == "2.5"
        assert dist["count"] == 4

    def test_mean_matches_hand_computed_value(self) -> None:
        # REAL-DATA-BACKFILL-4: 'mean' must be present and exact — the edge
        # report's walk_forward_oos_expectancy_mean reads this key.
        dist = calculate_distribution([Decimal("-75"), Decimal("200")])
        assert dist["mean"] == str(Decimal("125") / Decimal(2))
        assert dist["mean"] == "62.5"

    def test_empty_input_returns_null_extrema(self) -> None:
        assert calculate_distribution([]) == {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
            "count_positive": 0,
        }


class _SeedingRunner:
    """Stub ``BacktestRunnerService.run`` that seeds deterministic trades."""

    def __init__(self, seed) -> None:
        self._seed = seed

    def run(self, run_id: uuid.UUID) -> dict[str, str]:
        run = BacktestRun.objects.get(id=run_id)
        self._seed(run)
        return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}


@pytest.mark.django_db
class TestWalkForwardExecution:
    def _create_trade(
        self,
        run,
        side: str,
        entry: str,
        fill: str,
        qty: int,
        created_at: datetime,
    ) -> None:
        from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order

        corr = uuid.uuid4()
        account_id = run.account_id
        req = ExecutionRequest.objects.create(
            idempotency_key=f"key-{corr}",
            account_id=account_id,
            symbol="RELIANCE",
            side=side,
            quantity=Decimal(qty),
            entry_price=Decimal(entry),
            stop_loss=Decimal("90.00"),
            correlation_id=corr,
            risk_approved_event_id=uuid.uuid4(),
            rule_id="long_momentum_v1",
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
            correlation_id=corr,
        )
        # auto_now_add ignores explicit values on save(); set it afterwards so
        # the IS/OOS partition is deterministic.
        Order.objects.filter(id=order.id).update(created_at=created_at)
        Fill.objects.create(
            order=order,
            sequence=1,
            quantity=Decimal(qty),
            price=Decimal(fill),
            occurred_at=created_at,
        )

    def _seed_trades(self, run) -> None:
        """Deterministic zero-cost trades for each window (see module docstring).

        in_sample_ratio=0.50 splits each window at its midpoint:
        * W0 [01-01, 03-01] split 01-31: IS +1000, -500 | OOS +200, -100 (kept)
        * W1 [01-31, 03-31] split 03-01: IS +500           | OOS -1000 (dropped)
        * W2 [03-01, 04-30] split 03-31: IS +500           | OOS -400, +250 (kept)
        * W3 [03-31, 05-30] split 04-30: IS +1500          | OOS +300, +100 (kept)
        """
        if run.range_start == _W0:
            self._create_trade(run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, 5))
            self._create_trade(run, "SHORT", "200.00", "205.00", 100, _dt(2024, 1, 20))
            self._create_trade(run, "LONG", "100.00", "102.00", 100, _dt(2024, 2, 10))
            self._create_trade(run, "SHORT", "100.00", "101.00", 100, _dt(2024, 2, 20))
        elif run.range_start == _W1:
            self._create_trade(run, "LONG", "100.00", "105.00", 100, _dt(2024, 2, 10))
            self._create_trade(run, "SHORT", "100.00", "110.00", 100, _dt(2024, 3, 10))
        elif run.range_start == _W2:
            self._create_trade(run, "LONG", "100.00", "105.00", 100, _dt(2024, 3, 10))
            self._create_trade(run, "SHORT", "200.00", "204.00", 100, _dt(2024, 4, 10))
            self._create_trade(run, "LONG", "100.00", "102.50", 100, _dt(2024, 4, 20))
        elif run.range_start == _W3:
            self._create_trade(run, "LONG", "100.00", "115.00", 100, _dt(2024, 4, 10))
            self._create_trade(run, "LONG", "100.00", "103.00", 100, _dt(2024, 5, 10))
            self._create_trade(run, "LONG", "100.00", "101.00", 100, _dt(2024, 5, 20))
        else:
            raise AssertionError(f"unexpected window start {run.range_start}")

    def _execute(self, django_user_model) -> dict:
        user = django_user_model.objects.create_user(
            username=f"wf_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = WalkForwardService(runner=_SeedingRunner(self._seed_trades))
        return service.execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_W0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
            in_sample_ratio=Decimal("0.50"),
            initial_capital=Decimal("1000000"),
            commission_rate=Decimal("0"),
            slippage_bps=Decimal("0"),
        )

    def test_execute_aggregates_oos_distribution(self, django_user_model) -> None:
        result = self._execute(django_user_model)
        assert result["symbol"] == "RELIANCE"
        assert result["total_windows"] == 4
        assert result["included_window_count"] == 3
        assert result["excluded_window_count"] == 1

        windows = result["windows"]
        assert [w["in_sample_trade_count"] for w in windows] == [2, 1, 1, 1]
        assert [w["out_of_sample_trade_count"] for w in windows] == [2, 1, 2, 2]
        assert [Decimal(w["out_of_sample_expectancy"]) for w in windows] == [
            Decimal("50"),
            Decimal("-1000"),
            Decimal("-75"),
            Decimal("200"),
        ]
        assert [Decimal(w["out_of_sample_win_rate"]) for w in windows] == [
            Decimal("0.5"),
            Decimal("0"),
            Decimal("0.5"),
            Decimal("1"),
        ]
        assert all(w["status"] == "COMPLETED" for w in windows)
        assert len({w["run_id"] for w in windows}) == 4
        assert len({w["account_id"] for w in windows}) == 4

        dist = result["distribution"]
        assert dist["out_of_sample_expectancy"]["count"] == 3
        assert dist["out_of_sample_expectancy"]["count_positive"] == 2
        assert Decimal(dist["out_of_sample_expectancy"]["min"]) == Decimal("-75")
        assert Decimal(dist["out_of_sample_expectancy"]["max"]) == Decimal("200")
        assert Decimal(dist["out_of_sample_expectancy"]["median"]) == Decimal("50")

        assert dist["out_of_sample_win_rate"]["count"] == 3
        assert dist["out_of_sample_win_rate"]["count_positive"] == 3
        assert Decimal(dist["out_of_sample_win_rate"]["min"]) == Decimal("0.5")
        assert Decimal(dist["out_of_sample_win_rate"]["max"]) == Decimal("1")
        assert Decimal(dist["out_of_sample_win_rate"]["median"]) == Decimal("0.5")

        assert dist["out_of_sample_sharpe_ratio"]["count"] == 3
        assert dist["out_of_sample_sharpe_ratio"]["count_positive"] == 2
        assert Decimal(dist["out_of_sample_sharpe_ratio"]["min"]) == Decimal("-2.5883")
        assert Decimal(dist["out_of_sample_sharpe_ratio"]["max"]) == Decimal("22.4449")
        assert Decimal(dist["out_of_sample_sharpe_ratio"]["median"]) == Decimal("3.7427")

    def test_per_window_values_identical_to_direct_run_stats(self, django_user_model) -> None:
        result = self._execute(django_user_model)
        for window in result["windows"]:
            run = BacktestRun.objects.get(id=window["run_id"])
            direct = BacktestStatsService().run_stats(run)
            oos = direct["out_of_sample"]
            assert oos["trade_count"] == window["out_of_sample_trade_count"]
            assert oos["expectancy"] == window["out_of_sample_expectancy"]
            assert oos["win_rate"] == window["out_of_sample_win_rate"]
            assert oos["sharpe_ratio"] == window["out_of_sample_sharpe_ratio"]

    def test_each_window_has_isolated_funded_account(self, django_user_model) -> None:
        from apps.portfolio.infrastructure.models import AccountCapitalState

        result = self._execute(django_user_model)
        runs = list(BacktestRun.objects.order_by("range_start"))
        assert len(runs) == 4
        assert len({run.account_id for run in runs}) == 4
        assert [run.range_start for run in runs] == [_W0, _W1, _W2, _W3]
        assert len(result["windows"]) == 4
        for run in runs:
            capital = AccountCapitalState.objects.get(account_id=run.account_id)
            assert capital.equity == Decimal("1000000")
            assert capital.available_capital == Decimal("1000000")

    def test_too_short_range_yields_empty_distribution(self, django_user_model) -> None:
        user = django_user_model.objects.create_user(
            username=f"wf_short_{uuid.uuid4().hex[:8]}", password="p"
        )
        result = WalkForwardService(runner=_SeedingRunner(self._seed_trades)).execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_W0,
            range_end=_W0 + timedelta(days=40),
            window_size_days=60,
            step_size_days=30,
            in_sample_ratio=Decimal("0.50"),
        )
        assert result["total_windows"] == 0
        assert result["windows"] == []
        assert result["distribution"]["out_of_sample_expectancy"]["count"] == 0


def _staff_client(django_user_model) -> APIClient:
    user = django_user_model.objects.create_user(
        username=f"wf_staff_{uuid.uuid4().hex[:8]}",
        password="p",
        role=Role.STAFF.value,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestWalkForwardApi:
    def test_post_walk_forward_returns_aggregate(self, django_user_model, monkeypatch) -> None:
        def fake_run(service, run_id: uuid.UUID) -> dict[str, str]:
            return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}

        monkeypatch.setattr(BacktestRunnerService, "run", fake_run)
        client = _staff_client(django_user_model)
        response = client.post(
            "/api/v1/backtesting/walk-forward/", _WF_PAYLOAD, format="json"
        )
        assert response.status_code == 200
        body = response.data
        assert body["total_windows"] == 4
        # No trades were seeded, so every window is excluded from the distribution.
        assert body["included_window_count"] == 0
        assert body["excluded_window_count"] == 4
        assert body["distribution"]["out_of_sample_expectancy"]["count"] == 0

    def test_invalid_range_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_WF_PAYLOAD, "range_end": "2023-12-31T00:00:00Z"}
        response = client.post(
            "/api/v1/backtesting/walk-forward/", payload, format="json"
        )
        assert response.status_code == 400

    def test_anonymous_denied(self) -> None:
        client = APIClient()
        response = client.post(
            "/api/v1/backtesting/walk-forward/", _WF_PAYLOAD, format="json"
        )
        assert response.status_code in (401, 403)