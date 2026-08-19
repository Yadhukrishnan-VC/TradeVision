"""Shuffled-baseline statistical significance for rule trade sequences.

Pure module (no Django, no DB) implementing the randomized-entry baseline
comparison required by the Edge Validation batch. Given a rule's realized
per-trade net P&L sequence, it answers: *is the observed mean trade outcome
distinguishable from a null hypothesis where the strategy's entry selection
carries no information?*

Method — sign-flip permutation test at matching trade frequency:

- The trade count (frequency) is fixed; only the *sign* of each realized
  outcome magnitude is randomized, i.e. each realized trade could equally have
  been entered in the opposite direction. This preserves the realized outcome
  distribution and trade count while destroying any signal-consistent entry
  timing, which is exactly the "randomized/shuffled entries at matching
  frequency" baseline.
- The test statistic is the mean per-trade net P&L (sign-flipping preserves the
  magnitude multiset, so Sharpe ranks identically to the mean).
- The null distribution is the mean over ``n_shuffles`` sign-flipped
  permutations; the one-sided p-value (alternative: true edge > noise) is
  ``(1 + count(null_mean >= observed_mean)) / (1 + n_shuffles)``.
- ``verdict`` is ``SIGNIFICANT`` iff ``p_value <= alpha``, else
  ``NOT_SIGNIFICANT``. Below ``min_trades`` trades the test is not attempted
  and ``verdict`` is ``None`` with ``reason="INSUFFICIENT_TRADES"`` — no edge
  evidence is neither evidence of no edge nor of edge.

Deterministic: pass ``seed`` for reproducible results.
"""

from __future__ import annotations

import random
import statistics
from collections.abc import Sequence
from dataclasses import dataclass
from decimal import Decimal

#: Minimum number of trades before the permutation test is attempted. Below
#: this the tool reports ``verdict=None`` (insufficient data) rather than a
#: verdict the sample cannot support.
MIN_TRADES_FOR_TEST = 10


@dataclass(frozen=True)
class SignificanceResult:
    """Outcome of one shuffled-baseline significance comparison."""

    verdict: str | None
    reason: str
    observed_mean: float
    baseline_mean: float
    baseline_std: float
    z_score: float | None
    p_value: float | None
    n_trades: int
    n_shuffles: int
    alpha: float

    @property
    def significant(self) -> bool | None:
        """True iff SIGNIFICANT; None when the test was not attempted."""
        if self.verdict is None:
            return None
        return self.verdict == "SIGNIFICANT"


def shuffled_baseline_significance(
    trade_pnls: Sequence[float | Decimal],
    *,
    n_shuffles: int = 1000,
    alpha: float = 0.05,
    seed: int | None = None,
    min_trades: int = MIN_TRADES_FOR_TEST,
) -> SignificanceResult:
    """Compare observed mean trade P&L against the sign-flip null baseline.

    Args:
        trade_pnls: realized per-trade net P&L (costs already applied), in
            consistent units (currency or R multiples).
        n_shuffles: number of randomized sign-flip baselines (default 1000).
        alpha: significance threshold for ``SIGNIFICANT``.
        seed: optional RNG seed for reproducible output.
        min_trades: minimum sample size to attempt the test.

    Returns:
        A :class:`SignificanceResult`; ``verdict`` is ``None`` when the sample
        is below ``min_trades``.
    """
    if n_shuffles < 1:
        raise ValueError(f"n_shuffles must be >= 1, got {n_shuffles}")
    if not 0 < alpha < 1:
        raise ValueError(f"alpha must be in (0, 1), got {alpha}")

    values = [float(v) for v in trade_pnls]
    n_trades = len(values)
    if n_trades == 0:
        return SignificanceResult(
            verdict=None,
            reason="INSUFFICIENT_TRADES",
            observed_mean=0.0,
            baseline_mean=0.0,
            baseline_std=0.0,
            z_score=None,
            p_value=None,
            n_trades=0,
            n_shuffles=n_shuffles,
            alpha=alpha,
        )
    if n_trades < min_trades:
        observed = sum(values) / n_trades
        return SignificanceResult(
            verdict=None,
            reason="INSUFFICIENT_TRADES",
            observed_mean=observed,
            baseline_mean=0.0,
            baseline_std=0.0,
            z_score=None,
            p_value=None,
            n_trades=n_trades,
            n_shuffles=n_shuffles,
            alpha=alpha,
        )

    magnitudes = [abs(v) for v in values]
    observed_mean = sum(values) / n_trades
    rng = random.Random(seed)

    baseline_means: list[float] = []
    for _ in range(n_shuffles):
        flipped = [
            magnitude if rng.random() < 0.5 else -magnitude for magnitude in magnitudes
        ]
        baseline_means.append(sum(flipped) / n_trades)

    baseline_mean = statistics.fmean(baseline_means)
    baseline_std = statistics.pstdev(baseline_means)
    p_value = (1 + sum(1 for value in baseline_means if value >= observed_mean)) / (
        n_shuffles + 1
    )
    z_score = (
        (observed_mean - baseline_mean) / baseline_std if baseline_std > 0 else None
    )
    verdict = "SIGNIFICANT" if p_value <= alpha else "NOT_SIGNIFICANT"
    reason = (
        f"one-sided sign-flip permutation test, {n_shuffles} shuffles, alpha={alpha}"
    )

    return SignificanceResult(
        verdict=verdict,
        reason=reason,
        observed_mean=observed_mean,
        baseline_mean=baseline_mean,
        baseline_std=baseline_std,
        z_score=z_score,
        p_value=p_value,
        n_trades=n_trades,
        n_shuffles=n_shuffles,
        alpha=alpha,
    )
