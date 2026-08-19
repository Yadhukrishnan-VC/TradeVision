"""Risk Sophistication batch — calibration-drift detector tests.

The detector must prove a KNOWN calibration break: a rule whose live win rate
degrades sharply partway through the window must flag ``drifted=True``, while a
stable rule must not. Fixtures build the synthetic JournalEntry/RuleExecution
records (or direct outcomes) that drive the detector and the Celery task.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from apps.trader_memory.domain.calibration import (
    CalibrationOutcome,
    detect_calibration_drift,
)
from apps.trader_memory.infrastructure.models import CalibrationDriftRecord

_UTC = timezone.utc


def _outcomes(flags: list[bool]) -> list[CalibrationOutcome]:
    base = datetime(2026, 1, 1, tzinfo=_UTC)
    return [
        CalibrationOutcome(occurred_at=base + timedelta(days=i), won=flag)
        for i, flag in enumerate(flags)
    ]


class TestDetectCalibrationDrift:
    def test_stable_rule_not_drifted(self) -> None:
        flags = [i % 2 == 0 for i in range(60)]  # 30/60 = 0.5
        result = detect_calibration_drift(_outcomes(flags), 0.5)
        assert result.drifted is False
        assert result.n_live_trades == 60
        assert result.p_value is not None and result.p_value > 0.05

    def test_known_break_flags_drift(self) -> None:
        """Rule wins the first half of the window, then degrades sharply to
        all losses: live win rate 0.5 vs expected 0.7 -> z-test significant."""
        flags = [True] * 30 + [False] * 30
        result = detect_calibration_drift(_outcomes(flags), 0.7, rule_id="long_momentum_v1")
        assert result.drifted is True
        assert result.p_value is not None and result.p_value < 0.05
        assert result.live_win_rate == pytest.approx(0.5)

    def test_improvement_also_flags(self) -> None:
        """Two-sided test flags divergence in either direction (improvement
        is also a calibration break)."""
        flags = [True] * 60
        result = detect_calibration_drift(_outcomes(flags), 0.5)
        assert result.drifted is True

    def test_insufficient_sample_no_verdict(self) -> None:
        result = detect_calibration_drift(_outcomes([True] * 10), 0.7)
        assert result.drifted is None
        assert result.reason == "INSUFFICIENT_SAMPLE"

    def test_invalid_expectation_no_verdict(self) -> None:
        result = detect_calibration_drift(_outcomes([True] * 60), 1.0)
        assert result.drifted is None
        assert result.reason == "INVALID_EXPECTATION"


@pytest.mark.django_db
class TestCalibrationRepository:
    def _account(self, django_user_model):
        from apps.accounts.infrastructure.models import Account

        user = django_user_model.objects.create_user(
            username=f"cal_{uuid.uuid4().hex[:8]}", password="p"
        )
        return Account.objects.create(name="Cal", owner=user)

    def _seed_outcomes(self, rule_id: str, flags: list[bool], account) -> None:
        from apps.journal.infrastructure.models import JournalEntry
        from apps.rule_engine.infrastructure.models import RuleExecution

        base = datetime(2026, 1, 1, tzinfo=_UTC)
        for i, flag in enumerate(flags):
            correlation_id = uuid.uuid4()
            RuleExecution.objects.create(
                analysis_event_id=correlation_id,
                symbol="RELIANCE",
                rule_id=rule_id,
                severity="info",
                trigger_data={"mode": "live"},
            )
            JournalEntry.objects.create(
                correlation_id=correlation_id,
                account=account,
                outcome="won" if flag else "lost",
                realized_pnl=Decimal("500") if flag else Decimal("-500"),
                finalized=True,
                finalized_at=base + timedelta(days=i),
            )

    def test_recent_outcomes_attribute_to_rule(self, django_user_model) -> None:
        from apps.trader_memory.infrastructure.calibration_repository import (
            CalibrationOutcomeRepository,
        )

        account = self._account(django_user_model)
        self._seed_outcomes("long_momentum_v1", [True, False, True, False], account)
        repo = CalibrationOutcomeRepository()
        since = datetime(2025, 12, 1, tzinfo=_UTC)
        outcomes = repo.list_recent_outcomes("long_momentum_v1", since)
        assert len(outcomes) == 4
        assert [o.won for o in outcomes] == [True, False, True, False]
        assert repo.list_recent_outcomes("short_sell_v1", since) == []

    def test_backtest_win_rate_none_without_completed_run(self, django_user_model) -> None:
        from apps.trader_memory.infrastructure.calibration_repository import (
            CalibrationOutcomeRepository,
        )

        assert CalibrationOutcomeRepository().get_backtest_win_rate("long_momentum_v1") is None


@pytest.mark.django_db
class TestCalibrationDriftService:
    def test_service_flags_known_break_and_persists_record(self, django_user_model, settings) -> None:
        from apps.journal.infrastructure.models import JournalEntry
        from apps.rule_engine.infrastructure.models import RuleExecution
        from apps.trader_memory.application.calibration_service import (
            CalibrationDriftService,
        )
        from apps.trader_memory.infrastructure.calibration_repository import (
            CalibrationOutcomeRepository,
        )

        settings.CALIBRATION_DRIFT_WINDOW_DAYS = 365
        settings.CALIBRATION_DRIFT_MIN_TRADES = 30
        settings.CALIBRATION_DRIFT_ALPHA = 0.05

        user = django_user_model.objects.create_user(
            username=f"cal_svc_{uuid.uuid4().hex[:8]}", password="p"
        )
        from apps.accounts.infrastructure.models import Account

        account = Account.objects.create(name="Cal", owner=user)

        base = datetime(2026, 1, 1, tzinfo=_UTC)
        flags = [True] * 30 + [False] * 30
        for i, flag in enumerate(flags):
            correlation_id = uuid.uuid4()
            RuleExecution.objects.create(
                analysis_event_id=correlation_id,
                symbol="RELIANCE",
                rule_id="long_momentum_v1",
                severity="info",
                trigger_data={"mode": "live"},
            )
            JournalEntry.objects.create(
                correlation_id=correlation_id,
                account=account,
                outcome="won" if flag else "lost",
                realized_pnl=Decimal("500") if flag else Decimal("-500"),
                finalized=True,
                finalized_at=base + timedelta(days=i),
            )

        repo = CalibrationOutcomeRepository()
        # Backtest expectation is not computable without a real run; pin it.
        repo.get_backtest_win_rate = lambda rule_id: 0.7  # type: ignore[method-assign]
        result = CalibrationDriftService(repository=repo).run()

        assert result["drift_flags"] == 1
        assert result["rules_evaluated"] == 1
        assert result["by_rule"][0]["status"] == "DRIFTED"
        record = CalibrationDriftRecord.objects.filter(rule_id="long_momentum_v1").first()
        assert record is not None
        assert record.drifted is True
        assert record.n_trades == 60
        assert record.expected_win_rate == Decimal("0.7")

    def test_service_reports_no_expectation_without_backtest(self, django_user_model, settings) -> None:
        from apps.journal.infrastructure.models import JournalEntry
        from apps.rule_engine.infrastructure.models import RuleExecution
        from apps.trader_memory.application.calibration_service import (
            CalibrationDriftService,
        )

        settings.CALIBRATION_DRIFT_WINDOW_DAYS = 365
        user = django_user_model.objects.create_user(
            username=f"cal_ne_{uuid.uuid4().hex[:8]}", password="p"
        )
        from apps.accounts.infrastructure.models import Account

        account = Account.objects.create(name="Cal", owner=user)
        correlation_id = uuid.uuid4()
        RuleExecution.objects.create(
            analysis_event_id=correlation_id,
            symbol="RELIANCE",
            rule_id="long_momentum_v1",
            severity="info",
            trigger_data={"mode": "live"},
        )
        JournalEntry.objects.create(
            correlation_id=correlation_id,
            account=account,
            outcome="won",
            realized_pnl=Decimal("500"),
            finalized=True,
            finalized_at=datetime(2026, 1, 1, tzinfo=_UTC),
        )
        result = CalibrationDriftService().run()
        assert result["rules_evaluated"] == 1
        assert result["by_rule"][0]["status"] == "NO_EXPECTATION"
        assert result["drift_flags"] == 0
        assert CalibrationDriftRecord.objects.count() == 0