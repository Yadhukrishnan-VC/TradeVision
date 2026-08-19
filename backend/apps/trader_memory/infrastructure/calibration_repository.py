from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from apps.trader_memory.domain.calibration import CalibrationOutcome, RuleCalibration
from apps.trader_memory.infrastructure.models import CalibrationDriftRecord


class CalibrationOutcomeRepository:
    """Data access for the calibration-drift evaluator.

    Live outcomes come from finalized ``JournalEntry`` rows, attributed to the
    rule that produced them through ``Order.correlation_id ==
    RuleExecution.analysis_event_id`` (the same join the backtest attribution
    uses). The backtested expectation is the win rate of the most recent
    COMPLETED backtest run's per-rule bucket.
    """

    def list_rules_with_outcomes(self, since: datetime) -> list[str]:
        from apps.journal.infrastructure.models import JournalEntry
        from apps.rule_engine.infrastructure.models import RuleExecution

        correlation_ids = JournalEntry.objects.filter(
            finalized=True,
            finalized_at__gte=since,
        ).values_list("correlation_id", flat=True)
        if not correlation_ids:
            return []
        return list(
            RuleExecution.objects.filter(
                analysis_event_id__in=correlation_ids
            ).values_list("rule_id", flat=True).distinct()
        )

    def list_recent_outcomes(self, rule_id: str, since: datetime) -> list[CalibrationOutcome]:
        from apps.journal.infrastructure.models import JournalEntry
        from apps.rule_engine.infrastructure.models import RuleExecution

        event_ids = RuleExecution.objects.filter(
            rule_id=rule_id
        ).values_list("analysis_event_id", flat=True)
        if not event_ids:
            return []
        entries = JournalEntry.objects.filter(
            finalized=True,
            finalized_at__gte=since,
            correlation_id__in=event_ids,
        ).order_by("finalized_at")
        return [
            CalibrationOutcome(
                occurred_at=entry.finalized_at or entry.created_at,
                won=entry.outcome in {"won", "breakeven"},
                pnl=entry.realized_pnl or 0,
            )
            for entry in entries
        ]

    def get_backtest_win_rate(self, rule_id: str) -> float | None:
        """Expected win rate from the latest COMPLETED backtest run.

        Returns ``None`` when no completed run exists or the rule has no
        attributed trades in it (no usable expectation).
        """
        from apps.backtesting.models import BacktestRun
        from apps.backtesting.services import BacktestStatsService

        run = (
            BacktestRun.objects.filter(status="COMPLETED")
            .order_by("-created_at")
            .first()
        )
        if run is None:
            return None
        try:
            stats = BacktestStatsService().run_stats(run)
        except Exception:
            return None
        bucket = stats.get("by_rule", {}).get(rule_id)
        if bucket is None or bucket.get("trade_count", 0) == 0:
            return None
        return bucket["win_count"] / bucket["trade_count"]

    def create_drift_record(
        self,
        rule_id: str,
        window_start: datetime,
        window_end: datetime,
        calibration: RuleCalibration,
    ) -> CalibrationDriftRecord:
        record = CalibrationDriftRecord(
            rule_id=rule_id,
            window_start=window_start,
            window_end=window_end,
            n_trades=calibration.n_live_trades,
            live_win_rate=Decimal(
                str(round(calibration.live_win_rate, 6))
            ),
            expected_win_rate=Decimal(
                str(round(calibration.expected_win_rate or 0.0, 6))
            ),
            p_value=Decimal(str(round(calibration.p_value or 0.0, 8))),
            drifted=bool(calibration.drifted),
        )
        record.full_clean()
        record.save()
        return record