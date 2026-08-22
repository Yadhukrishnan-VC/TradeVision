"""LIVE-PAPER-DRESS-REHEARSAL-1 — drift monitor unit tests.

Covers the alert decision table end to end with real ORM rows:
sign-flip, relative-threshold, insufficient-trades, healthy, same-day dedup,
and symbol scoping of the live window.
"""

from __future__ import annotations

from decimal import Decimal
from typing import Any

import pytest

from apps.accounts.infrastructure.models import Account
from apps.execution.infrastructure.models import ExecutionRequest, Order
from apps.live_drift.application.drift_monitor import (
    DEFAULT_MIN_TRADES,
    compute_live_stats,
    evaluate_observation,
)
from apps.live_drift.infrastructure.models import DriftAlert, ObservedRule
from apps.rule_engine.infrastructure.models import RuleExecution

pytestmark = pytest.mark.django_db


def _make_observed(**kwargs: Any) -> ObservedRule:
    params: dict[str, Any] = {
        "rule_id": "price_movement_v1",
        "regime": "RANGING",
        "symbol": "",
        "baseline_expectancy": Decimal("100"),
        "enabled": True,
    }
    params.update(kwargs)
    return ObservedRule.objects.create(**params)


@pytest.fixture
def paper_account(db) -> Account:
    from django.contrib.auth import get_user_model

    User = get_user_model()
    owner = User.objects.create_user(username="drift-owner", password="irrelevant")
    return Account.objects.create(name="DriftPaper", owner=owner, is_default=False)


def _seed_trade(
    *,
    account: Account,
    analysis_event_id,
    net_direction: str = "win",
    symbol: str = "TCS",
) -> None:
    """One RuleExecution + FILLED order whose net P&L sign matches direction."""
    RuleExecution.objects.create(
        rule_id="price_movement_v1",
        symbol=symbol,
        severity="info",
        trigger_data={"regime": "RANGING"},
        analysis_event_id=analysis_event_id,
    )
    entry = Decimal("100")
    fill = Decimal("110") if net_direction == "win" else Decimal("95")
    ExecutionRequest.objects.create(
        idempotency_key=f"idem-{analysis_event_id}",
        account_id=account.id,
        symbol=symbol,
        side="LONG",
        quantity=Decimal("10"),
        entry_price=entry,
        stop_loss=Decimal("90"),
        correlation_id=analysis_event_id,
        risk_approved_event_id=analysis_event_id,
        rule_id="price_movement_v1",
        status="APPROVED",
    )
    Order.objects.create(
        execution_request_id=request_pk(analysis_event_id),
        account_id=account.id,
        symbol=symbol,
        side="LONG",
        quantity=10,
        filled_quantity=10,
        entry_price=entry,
        stop_loss=Decimal("90"),
        avg_fill_price=fill,
        status="FILLED",
        correlation_id=analysis_event_id,
    )


def request_pk(analysis_event_id) -> Any:
    return (
        ExecutionRequest.objects.filter(risk_approved_event_id=analysis_event_id)
        .values_list("id", flat=True)
        .first()
    )


def _uuid() -> Any:
    import uuid as _uuid_mod

    return _uuid_mod.uuid4()


class TestComputeLiveStats:
    def test_window_stats_and_symbol_scoping(self, paper_account) -> None:
        for i in range(3):
            _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="win")
        _seed_trade(
            account=paper_account, analysis_event_id=_uuid(), net_direction="loss", symbol="INFY"
        )

        observed_all = _make_observed()
        stats = compute_live_stats(observed_all)
        assert stats.trades == 4
        assert stats.wins == 3
        assert stats.expectancy > 0
        assert stats.win_rate == Decimal("0.75")

        scoped = _make_observed(symbol="TCS")
        assert compute_live_stats(scoped).trades == 3


class TestEvaluateObservation:
    def test_sign_flip_raises_alert_and_notifies(
        self, paper_account, monkeypatch
    ) -> None:
        for _ in range(DEFAULT_MIN_TRADES):
            _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="loss")
        observed = _make_observed(baseline_expectancy=Decimal("100"))

        sent: list[str] = []
        monkeypatch.setattr(
            "apps.live_drift.infrastructure.telegram_client.TelegramNotifier.send",
            lambda self, text: sent.append(text) or True,
        )

        alert = evaluate_observation(observed)
        assert alert is not None
        assert alert.kind == DriftAlert.KIND_SIGN_FLIP
        assert alert.window_trades == DEFAULT_MIN_TRADES
        assert alert.notified is True
        assert sent and "[TradeVision drift]" in sent[0]

    def test_threshold_alert_when_live_far_below_baseline(
        self, paper_account
    ) -> None:
        from decimal import Decimal as _D

        # Live lands at a small positive expectancy (~+98/trade at these
        # prices); a 200 baseline with a 50% relative threshold trips
        # without a sign flip.
        for _ in range(6):
            _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="win")
        observed = _make_observed(baseline_expectancy=_D("200"))
        alert = evaluate_observation(observed, relative_threshold=_D("0.5"))
        assert alert is not None
        assert alert.kind == DriftAlert.KIND_THRESHOLD

    def test_insufficient_trades_is_silent(self, paper_account) -> None:
        _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="loss")
        observed = _make_observed()
        assert evaluate_observation(observed) is None
        assert DriftAlert.objects.count() == 0

    def test_healthy_no_alert(self, paper_account) -> None:
        for _ in range(DEFAULT_MIN_TRADES):
            _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="win")
        observed = _make_observed(baseline_expectancy=Decimal("-50"))
        assert evaluate_observation(observed) is None

    def test_same_day_duplicate_suppressed(self, paper_account) -> None:
        for _ in range(DEFAULT_MIN_TRADES):
            _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="loss")
        observed = _make_observed()
        first = evaluate_observation(observed)
        second = evaluate_observation(observed)
        assert first is not None
        assert second is None
        assert DriftAlert.objects.count() == 1

    def test_null_baseline_flags_negative_live_only(
        self, paper_account
    ) -> None:
        for _ in range(DEFAULT_MIN_TRADES):
            _seed_trade(account=paper_account, analysis_event_id=_uuid(), net_direction="loss")
        observed = _make_observed(baseline_expectancy=None)
        alert = evaluate_observation(observed)
        assert alert is not None
        assert alert.kind == DriftAlert.KIND_SIGN_FLIP
