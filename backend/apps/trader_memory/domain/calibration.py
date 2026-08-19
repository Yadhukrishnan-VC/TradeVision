"""Calibration-drift detection for rule-level live paper outcomes.

Pure module (no Django, no DB). Compares a rule's live paper-trading win rate
over a rolling window against the backtested expected win rate and answers:
*has the rule's live behaviour drifted away from its backtested calibration?*

Method — two-sided normal-approximation z-test on the win rate:

- Null hypothesis: live win rate == backtested expected win rate.
- Test statistic ``z = (observed - expected) / se`` where
  ``se = sqrt(expected * (1 - expected) / n)``.
- Two-sided p-value ``2 * (1 - Phi(|z|))`` flags divergence in *either*
  direction (improvement or degradation), not just degradation.
- ``drifted`` is ``True`` iff ``p_value < alpha``.
- Below ``min_trades`` the test is not attempted and ``drifted`` is ``None``
  (insufficient sample — no calibration claim is made either way).
- An expected win rate outside ``(0, 1)`` is unusable for the z-test variance;
  ``drifted`` is ``None`` with ``reason="INVALID_EXPECTATION"``.

Uses only the stdlib (``math.erf`` for the normal CDF) so it stays
dependency-free and deterministic.
"""

from __future__ import annotations

import math
from collections.abc import Sequence
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal

#: Minimum number of live outcomes in the window before a drift verdict is
#: attempted. Below this no calibration claim is made.
MIN_TRADES_FOR_DRIFT = 30


@dataclass(frozen=True)
class CalibrationOutcome:
    """One realized live paper-trading outcome for a rule."""

    occurred_at: datetime
    won: bool
    pnl: Decimal = Decimal(0)


@dataclass(frozen=True)
class RuleCalibration:
    """Result of comparing a rule's live win rate against expectation."""

    rule_id: str
    n_live_trades: int
    live_win_rate: float
    expected_win_rate: float | None
    z_score: float | None
    p_value: float | None
    drifted: bool | None
    reason: str


def _normal_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def detect_calibration_drift(
    outcomes: Sequence[CalibrationOutcome],
    expected_win_rate: float,
    *,
    rule_id: str = "",
    min_trades: int = MIN_TRADES_FOR_DRIFT,
    alpha: float = 0.05,
) -> RuleCalibration:
    """Compare a rule's live win rate against its backtested expectation.

    Args:
        outcomes: live paper-trading outcomes over the rolling window.
        expected_win_rate: backtested expected win rate in ``(0, 1)``.
        rule_id: rule identifier echoed back for the caller's convenience.
        min_trades: minimum sample size to attempt the test.
        alpha: two-sided significance threshold for ``drifted=True``.

    Returns:
        A :class:`RuleCalibration`; ``drifted`` is ``None`` when the sample is
        too small or the expectation is unusable.
    """
    n = len(outcomes)
    live_win_rate = (
        sum(1 for o in outcomes if o.won) / n if n else 0.0
    )

    if n < min_trades:
        return RuleCalibration(
            rule_id=rule_id,
            n_live_trades=n,
            live_win_rate=live_win_rate,
            expected_win_rate=expected_win_rate,
            z_score=None,
            p_value=None,
            drifted=None,
            reason="INSUFFICIENT_SAMPLE",
        )

    if not 0.0 < expected_win_rate < 1.0:
        return RuleCalibration(
            rule_id=rule_id,
            n_live_trades=n,
            live_win_rate=live_win_rate,
            expected_win_rate=expected_win_rate,
            z_score=None,
            p_value=None,
            drifted=None,
            reason="INVALID_EXPECTATION",
        )

    se = math.sqrt(expected_win_rate * (1.0 - expected_win_rate) / n)
    z = (live_win_rate - expected_win_rate) / se
    p_two = 2.0 * (1.0 - _normal_cdf(abs(z)))
    drifted = p_two < alpha
    return RuleCalibration(
        rule_id=rule_id,
        n_live_trades=n,
        live_win_rate=live_win_rate,
        expected_win_rate=expected_win_rate,
        z_score=z,
        p_value=p_two,
        drifted=drifted,
        reason=f"two-sided win-rate z-test, n={n}, alpha={alpha}",
    )