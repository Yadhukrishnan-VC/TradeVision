from __future__ import annotations

import logging
from datetime import timedelta

from django.conf import settings
from django.utils import timezone

from apps.trader_memory.domain.calibration import detect_calibration_drift
from apps.trader_memory.infrastructure.calibration_repository import (
    CalibrationOutcomeRepository,
)
from core.services import BaseService

logger = logging.getLogger(__name__)


class CalibrationDriftService(BaseService):
    """Orchestrate the per-rule calibration-drift evaluation pass.

    For every rule with finalized live paper-trading outcomes in the rolling
    window: load the outcomes, resolve the backtested expected win rate from
    the latest COMPLETED backtest, run the two-sided win-rate z-test and —
    only when the divergence is significant — persist a
    ``CalibrationDriftRecord`` flag. Rules without a usable backtest
    expectation are reported as ``NO_EXPECTATION`` (never flagged), and rules
    below the minimum sample size as ``INSUFFICIENT_SAMPLE`` (never flagged).
    """

    def __init__(
        self,
        repository: CalibrationOutcomeRepository | None = None,
    ) -> None:
        super().__init__()
        self._repo = repository or CalibrationOutcomeRepository()

    def run(self) -> dict:
        window_days = int(getattr(settings, "CALIBRATION_DRIFT_WINDOW_DAYS", 30))
        min_trades = int(getattr(settings, "CALIBRATION_DRIFT_MIN_TRADES", 30))
        alpha = float(getattr(settings, "CALIBRATION_DRIFT_ALPHA", 0.05))

        now = timezone.now()
        since = now - timedelta(days=window_days)
        rules = self._repo.list_rules_with_outcomes(since)

        by_rule: list[dict] = []
        flags = 0
        for rule_id in rules:
            outcomes = self._repo.list_recent_outcomes(rule_id, since)
            expected = self._repo.get_backtest_win_rate(rule_id)
            if expected is None:
                by_rule.append(
                    {
                        "rule_id": rule_id,
                        "status": "NO_EXPECTATION",
                        "n_trades": len(outcomes),
                    }
                )
                continue

            calibration = detect_calibration_drift(
                outcomes,
                expected,
                rule_id=rule_id,
                min_trades=min_trades,
                alpha=alpha,
            )

            if calibration.drifted:
                self._repo.create_drift_record(
                    rule_id=rule_id,
                    window_start=since,
                    window_end=now,
                    calibration=calibration,
                )
                flags += 1
                logger.warning(
                    "calibration_drift_detected",
                    extra={
                        "rule_id": rule_id,
                        "n_trades": calibration.n_live_trades,
                        "live_win_rate": calibration.live_win_rate,
                        "expected_win_rate": calibration.expected_win_rate,
                        "p_value": calibration.p_value,
                    },
                )

            status = (
                "DRIFTED"
                if calibration.drifted
                else (
                    "INSUFFICIENT_SAMPLE"
                    if calibration.drifted is None
                    else "OK"
                )
            )
            by_rule.append(
                {
                    "rule_id": rule_id,
                    "status": status,
                    "n_trades": calibration.n_live_trades,
                    "live_win_rate": calibration.live_win_rate,
                    "expected_win_rate": calibration.expected_win_rate,
                    "p_value": calibration.p_value,
                }
            )

        return {
            "window_days": window_days,
            "window_start": since.isoformat(),
            "window_end": now.isoformat(),
            "rules_evaluated": len(rules),
            "drift_flags": flags,
            "by_rule": by_rule,
        }