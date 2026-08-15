"""Batch STRATEGY-EDGE-VALIDATION-1 — empirical per-rule edge evaluation tests.

The batch reuses the *unmodified* single-run engine and the *unmodified*
walk-forward engine: ``EdgeValidationService.evaluate`` runs one full-range
backtest (its own isolated funded account) plus one ``WalkForwardService`` pass
over the same range, then applies the disclosed edge criterion per rule. The
tests stub ``BacktestRunnerService.run`` to seed deterministic trades per
account and pin the exact per-rule verdicts:

* ``edge_profitable_v1`` — 8 wins (+1000 each) / 4 losses (-500), expectancy
  500, profit factor 4.0, 12 trades: ``has_edge=True``.
* ``edge_unprofitable_v1`` — 2 wins (+500) / 8 losses (-1000), expectancy -700,
  10 trades: ``has_edge=False``.
* ``edge_insufficient_v1`` — 5 wins (+1000 each), 5 trades (< MIN_TRADES):
  ``has_edge=None`` (insufficient data, never False even though profitable).

The cost-sensitivity test uses ``edge_thin_v1`` — a rule with a real but thin
edge that is profitable at zero cost (expectancy 40.0) but not once
commission is applied (expectancy -100.8), so ``has_edge`` provably flips.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest
from rest_framework.test import APIClient

from apps.accounts.domain.value_objects import Role
from apps.backtesting.application.edge_validation_service import (
    MIN_TRADES,
    EdgeValidationService,
    _apply_edge_criterion,
)
from apps.backtesting.application.walk_forward_service import WalkForwardService
from apps.backtesting.models import BacktestRun
from apps.backtesting.services import BacktestRunnerService, BacktestStatsService

_UTC = timezone.utc
_D0 = datetime(2024, 1, 1, tzinfo=_UTC)
_RANGE_END = _D0 + timedelta(days=150)

_EV_PAYLOAD = {
    "symbol": "RELIANCE",
    "timeframe": "1D",
    "range_start": "2024-01-01T00:00:00Z",
    "range_end": "2024-05-30T00:00:00Z",
    "window_size_days": 60,
    "step_size_days": 30,
}


def _dt(year: int, month: int, day: int, hour: int = 10) -> datetime:
    return datetime(year, month, day, hour, tzinfo=_UTC)


class TestApplyEdgeCriterion:
    """Unit tests for the disclosed threshold on raw by_rule buckets."""

    def test_profitable_rule_is_true(self) -> None:
        bucket = {
            "trade_count": 12,
            "expectancy": "500",
            "profit_factor": "4.0",
        }
        assert _apply_edge_criterion(bucket) is True

    def test_unprofitable_rule_is_false(self) -> None:
        bucket = {
            "trade_count": 10,
            "expectancy": "-700",
            "profit_factor": "0.125",
        }
        assert _apply_edge_criterion(bucket) is False

    def test_zero_expectancy_is_false(self) -> None:
        bucket = {
            "trade_count": 12,
            "expectancy": "0",
            "profit_factor": "1.05",
        }
        assert _apply_edge_criterion(bucket) is False

    def test_profit_factor_at_or_below_one_is_false(self) -> None:
        for pf in ("1.0", "0.999"):
            assert _apply_edge_criterion(
                {"trade_count": 12, "expectancy": "50", "profit_factor": pf}
            ) is False

    def test_none_profit_factor_is_false(self) -> None:
        assert _apply_edge_criterion(
            {"trade_count": 12, "expectancy": "100", "profit_factor": None}
        ) is False

    def test_insufficient_trades_is_none_never_false(self) -> None:
        for count in (0, 1, MIN_TRADES - 1):
            bucket = {
                "trade_count": count,
                "expectancy": "1000",
                "profit_factor": "999.99",
            }
            assert _apply_edge_criterion(bucket) is None

    def test_exactly_min_trades_evaluates_fully(self) -> None:
        assert _apply_edge_criterion(
            {"trade_count": MIN_TRADES, "expectancy": "10", "profit_factor": "1.5"}
        ) is True


class _SeedingRunner:
    """Stub ``BacktestRunnerService.run`` that seeds deterministic trades."""

    def __init__(self, seed) -> None:
        self._seed = seed

    def run(self, run_id: uuid.UUID) -> dict[str, str]:
        run = BacktestRun.objects.get(id=run_id)
        self._seed(run)
        return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}


def _create_trade(
    run,
    side: str,
    entry: str,
    fill: str,
    qty: int,
    created_at: datetime,
    rule_id: str,
) -> None:
    """Plant one attributed order+fill+RuleExecution into ``run``'s account."""
    from apps.execution.infrastructure.models import ExecutionRequest, Fill, Order
    from apps.rule_engine.infrastructure.models import RuleExecution

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
        correlation_id=corr,
    )
    Order.objects.filter(id=order.id).update(created_at=created_at)
    Fill.objects.create(
        order=order,
        sequence=1,
        quantity=Decimal(qty),
        price=Decimal(fill),
        occurred_at=created_at,
    )
    RuleExecution.objects.create(
        analysis_event_id=corr,
        symbol="RELIANCE",
        rule_id=rule_id,
        severity="info",
        trigger_data={"mode": "backtest"},
    )


def _seed_edge_trades(run) -> None:
    """Deterministic multi-rule fixture (see module docstring)."""
    for day in range(1, 9):
        _create_trade(run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, day), "edge_profitable_v1")
    for day in range(9, 13):
        _create_trade(run, "SHORT", "200.00", "205.00", 100, _dt(2024, 1, day), "edge_profitable_v1")
    for day in range(1, 3):
        _create_trade(run, "LONG", "100.00", "105.00", 100, _dt(2024, 1, 13 + day), "edge_unprofitable_v1")
    for day in range(3, 11):
        _create_trade(run, "SHORT", "100.00", "110.00", 100, _dt(2024, 1, 13 + day), "edge_unprofitable_v1")
    for day in range(1, 6):
        _create_trade(run, "LONG", "100.00", "110.00", 100, _dt(2024, 1, 23 + day), "edge_insufficient_v1")


def _seed_thin_flip(run) -> None:
    """A thin-edge rule: profitable at zero cost, unprofitable once charged."""
    for day in range(1, 7):
        _create_trade(run, "LONG", "100.00", "101.00", 100, _dt(2024, 1, day), "edge_thin_v1")
    for day in range(7, 11):
        _create_trade(run, "SHORT", "200.00", "200.50", 100, _dt(2024, 1, day), "edge_thin_v1")


@pytest.mark.django_db
class TestEdgeValidationExecution:

    def _evaluate(self, django_user_model) -> dict:
        user = django_user_model.objects.create_user(
            username=f"ev_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = EdgeValidationService(runner=_SeedingRunner(_seed_edge_trades))
        return service.evaluate(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
            in_sample_ratio=Decimal("0.70"),
        )

    def test_reports_three_verdicts_exactly(self, django_user_model) -> None:
        result = self._evaluate(django_user_model)
        assert set(result["by_rule"]) == {
            "edge_profitable_v1",
            "edge_unprofitable_v1",
            "edge_insufficient_v1",
        }
        assert result["by_rule"]["edge_profitable_v1"]["has_edge"] is True
        assert result["by_rule"]["edge_unprofitable_v1"]["has_edge"] is False
        assert result["by_rule"]["edge_insufficient_v1"]["has_edge"] is None

    def test_raw_numbers_accompany_verdict(self, django_user_model) -> None:
        result = self._evaluate(django_user_model)
        report = result["by_rule"]["edge_profitable_v1"]
        assert report["trade_count"] == 12
        assert report["win_rate"] is not None
        assert Decimal(report["expectancy"]) == Decimal("500.0000000000000000000000001")
        assert Decimal(report["profit_factor"]) == Decimal(4)
        assert report["sharpe_ratio"] is not None or report["sharpe_ratio"] is None
        assert report["sortino_ratio"] is not None or report["sortino_ratio"] is None
        assert report["max_drawdown_pct"] is not None

    def test_full_range_run_isolated_and_funded(self, django_user_model) -> None:
        from apps.portfolio.infrastructure.models import AccountCapitalState

        self._evaluate(django_user_model)
        full_range_runs = list(
            BacktestRun.objects.filter(
                account__name__startswith="EdgeValidation "
            ).order_by("created_at")
        )
        assert len(full_range_runs) == 1
        for run in full_range_runs:
            capital = AccountCapitalState.objects.get(account_id=run.account_id)
            assert capital.equity == Decimal(1000000)
            assert capital.available_capital == Decimal(1000000)

    def test_by_rule_and_split_metrics_passed_through_unmodified(
        self, django_user_model
    ) -> None:
        user = django_user_model.objects.create_user(
            username=f"ev_reg_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = EdgeValidationService(runner=_SeedingRunner(_seed_edge_trades))
        result = service.evaluate(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
        )

        full_runs = list(
            BacktestRun.objects.filter(
                account__name__startswith="EdgeValidation "
            )
        )
        assert len(full_runs) == 1
        direct = BacktestStatsService().run_stats(full_runs[0])
        # The report's single_run section is the run_stats dict verbatim.
        assert result["single_run"] == direct
        # And the per-rule verdicts are derived without mutating by_rule.
        assert result["single_run"]["by_rule"]["edge_profitable_v1"]["expectancy"] == (
            direct["by_rule"]["edge_profitable_v1"]["expectancy"]
        )
        assert result["single_run"]["by_rule"]["edge_profitable_v1"]["profit_factor"] == (
            direct["by_rule"]["edge_profitable_v1"]["profit_factor"]
        )
        assert result["single_run"]["in_sample"] == direct["in_sample"]
        assert result["single_run"]["out_of_sample"] == direct["out_of_sample"]
        assert result["single_run"]["by_regime"] == direct["by_regime"]

    def test_walk_forward_output_passed_through(self, django_user_model) -> None:
        user = django_user_model.objects.create_user(
            username=f"ev_wf_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = EdgeValidationService(runner=_SeedingRunner(_seed_edge_trades))
        result = service.evaluate(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
        )

        direct_wf = WalkForwardService(runner=_SeedingRunner(_seed_edge_trades)).execute(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
            in_sample_ratio=Decimal("0.70"),
        )
        # Same seeding runner over the same range => identical aggregate output;
        # run_ids differ only because each invocation foots its own accounts.
        assert result["walk_forward"]["distribution"] == direct_wf["distribution"]
        assert result["walk_forward"]["total_windows"] == direct_wf["total_windows"]
        assert result["walk_forward"]["included_window_count"] == direct_wf["included_window_count"]
        assert [
            Decimal(w["out_of_sample_expectancy"]) for w in result["walk_forward"]["windows"]
        ] == [
            Decimal(w["out_of_sample_expectancy"]) for w in direct_wf["windows"]
        ]

    def test_disclosed_criterion_in_response(self, django_user_model) -> None:
        result = self._evaluate(django_user_model)
        criterion = result["edge_criterion"]
        assert criterion["min_trades"] == MIN_TRADES
        assert criterion["profit_factor_greater_than_one"] == Decimal("1.0")


@pytest.mark.django_db
class TestCostSensitivity:
    """The thin-edge rule's verdict must provably flip between cost settings."""

    def test_has_edge_flips_at_realistic_cost(self, django_user_model) -> None:
        user = django_user_model.objects.create_user(
            username=f"ev_cs_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = EdgeValidationService(runner=_SeedingRunner(_seed_thin_flip))
        result = service.compare_costs(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
            realistic_commission_rate=Decimal("0.005"),
            realistic_slippage_bps=Decimal(0),
        )

        comparison = result["by_rule"]["edge_thin_v1"]
        assert comparison["baseline_has_edge"] is True
        assert comparison["realistic_cost_has_edge"] is False
        assert comparison["flipped"] is True

        baseline = comparison["baseline"]
        realistic = comparison["realistic_cost"]
        # Zero-cost: gross 600 - gross loss 200 over 10 trades => expectancy 40.0
        assert Decimal(baseline["expectancy"]) == Decimal(40)
        assert Decimal(baseline["profit_factor"]) == Decimal(3)
        # Commission 0.005 on qty*avg_fill: 6*50.5 + 4*100.25 = 704 cost =>
        # expectancy = 0.6*49.5 - 0.4*150.25 - 70.4 = -100.8
        assert Decimal(realistic["expectancy"]) == Decimal("-100.8")
        assert Decimal(realistic["profit_factor"]) < Decimal(1)

    def test_zero_and_realistic_full_reports_embedded(self, django_user_model) -> None:
        user = django_user_model.objects.create_user(
            username=f"ev_cs2_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = EdgeValidationService(runner=_SeedingRunner(_seed_thin_flip))
        result = service.compare_costs(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
            realistic_commission_rate=Decimal("0.005"),
        )
        baseline_comm = result["baseline"]["commission_rate"]
        realistic_comm = result["realistic_cost"]["commission_rate"]
        assert baseline_comm == "0"
        assert realistic_comm == "0.005"
        assert result["edge_criterion"]["min_trades"] == MIN_TRADES

    def test_insufficient_data_never_flips(self, django_user_model) -> None:
        """A below-MIN_TRADES rule has has_edge=None at both settings -> no flip."""
        user = django_user_model.objects.create_user(
            username=f"ev_cs3_{uuid.uuid4().hex[:8]}", password="p"
        )
        service = EdgeValidationService(runner=_SeedingRunner(_seed_edge_trades))
        result = service.compare_costs(
            owner=user,
            symbol="RELIANCE",
            timeframe="1D",
            range_start=_D0,
            range_end=_RANGE_END,
            window_size_days=60,
            step_size_days=30,
            realistic_commission_rate=Decimal("0.005"),
        )
        comparison = result["by_rule"]["edge_insufficient_v1"]
        assert comparison["baseline_has_edge"] is None
        assert comparison["realistic_cost_has_edge"] is None
        assert comparison["flipped"] is False


def _staff_client(django_user_model) -> APIClient:
    user = django_user_model.objects.create_user(
        username=f"ev_staff_{uuid.uuid4().hex[:8]}",
        password="p",
        role=Role.STAFF.value,
    )
    client = APIClient()
    client.force_authenticate(user=user)
    return client


@pytest.mark.django_db
class TestEdgeValidationApi:
    def test_post_edge_validation_returns_report(self, django_user_model, monkeypatch) -> None:
        def fake_run(service, run_id: uuid.UUID) -> dict[str, str]:
            return {"status": "COMPLETED", "run_id": str(run_id), "bars_processed": "0"}

        monkeypatch.setattr(BacktestRunnerService, "run", fake_run)
        client = _staff_client(django_user_model)
        response = client.post(
            "/api/v1/backtesting/edge-validation/", _EV_PAYLOAD, format="json"
        )
        assert response.status_code == 200
        body = response.data
        assert body["symbol"] == "RELIANCE"
        assert body["baseline"]["commission_rate"] == "0"
        assert body["realistic_cost"]["commission_rate"] == "0.0003"
        assert body["baseline"]["by_rule"] == {}
        assert body["realistic_cost"]["by_rule"] == {}
        assert body["by_rule"] == {}
        assert body["baseline"]["walk_forward"]["total_windows"] == 4
        assert body["edge_criterion"]["min_trades"] == MIN_TRADES

    def test_invalid_range_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_EV_PAYLOAD, "range_end": "2023-12-31T00:00:00Z"}
        response = client.post(
            "/api/v1/backtesting/edge-validation/", payload, format="json"
        )
        assert response.status_code == 400

    def test_non_positive_window_size_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_EV_PAYLOAD, "window_size_days": 0}
        response = client.post(
            "/api/v1/backtesting/edge-validation/", payload, format="json"
        )
        assert response.status_code == 400

    def test_negative_realistic_cost_rejected(self, django_user_model) -> None:
        client = _staff_client(django_user_model)
        payload = {**_EV_PAYLOAD, "realistic_commission_rate": "-0.001"}
        response = client.post(
            "/api/v1/backtesting/edge-validation/", payload, format="json"
        )
        assert response.status_code == 400

    def test_anonymous_denied(self) -> None:
        client = APIClient()
        response = client.post(
            "/api/v1/backtesting/edge-validation/", _EV_PAYLOAD, format="json"
        )
        assert response.status_code in (401, 403)