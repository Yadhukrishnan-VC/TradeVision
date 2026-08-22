"""Live paper-trade vs backtest-baseline drift monitor (LIVE-PAPER-DRESS-REHEARSAL-1).

For every owner-flagged :class:`~apps.live_drift.infrastructure.models.ObservedRule`
this service recomputes, over a rolling window of *live paper* trades:

    expectancy = mean(net P&L per trade)
    win_rate   = wins / trades

and compares them with the rule's recorded backtest baseline expectancy
(copied from EDGE_VALIDATION_REPORT_V2 when the observation was flagged).
Two alert kinds exist:

``sign_flip``
    the baseline was positive and the live window expectancy is negative —
    the strongest possible drift signal.
``threshold``
    the live expectancy underperforms the baseline by at least
    ``DRIFT_ALERT_RELATIVE_THRESHOLD`` (fraction of |baseline|; default 1.0,
    i.e. live is at least 100% worse than backtest).

Net-P&L approximation: identical raw formula to
``BacktestStatsService.run_stats`` (direction × (avg_fill − entry) × qty)
minus a flat realistic cost estimate of ``qty × avg_fill ×
(commission_rate + slippage_bps/10_000)`` using the same constants as
``run_edge_validation``. Per-order NSE cost modelling (STT/GST/stamp legs) is
intentionally not re-derived here; the approximation is conservative and only
needs to be consistent window-over-window to detect drift.

Paper-only by construction: orders are attributed through the same
correlation chain as backtests, and the whole monitor is meaningless unless
the broker adapter is paper — asserted at task level.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import timedelta
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.utils import timezone

from apps.execution.infrastructure.models import Order
from apps.live_drift.infrastructure.models import DriftAlert, ObservedRule
from apps.rule_engine.infrastructure.models import RuleExecution
from core.utils import get_now

logger = logging.getLogger(__name__)

#: A live window with fewer trades than this is reported as insufficient and
#: never raises an alert — noise from 1-2 trades would drown real signal.
DEFAULT_MIN_TRADES = 5

#: Rolling window length in days for live paper trades.
DEFAULT_WINDOW_DAYS = 7


@dataclass(frozen=True)
class LiveWindowStats:
    trades: int
    wins: int
    expectancy: Decimal
    win_rate: Decimal


def compute_live_stats(
    observed: ObservedRule, window_days: int = DEFAULT_WINDOW_DAYS
) -> LiveWindowStats:
    """Rolling-window live paper stats for one observed (rule, regime[, symbol])."""
    commission_rate = Decimal(str(getattr(settings, "REALISTIC_COMMISSION_RATE", "0.0013")))
    slippage_bps = Decimal(str(getattr(settings, "REALISTIC_SLIPPAGE_BPS", "5.0")))
    window_start = get_now() - timedelta(days=window_days)

    exec_rows = list(
        RuleExecution.objects.filter(
            rule_id=observed.rule_id,
            created_at__gte=window_start - timedelta(days=1),
        ).values_list("analysis_event_id", "symbol", "trigger_data")
    )
    regime_rows = [
        (eid, sym)
        for eid, sym, trigger in exec_rows
        if (trigger or {}).get("regime") == observed.regime
    ]
    event_ids = [eid for eid, _ in regime_rows]
    if observed.symbol:
        allowed_symbols = {sym for _, sym in regime_rows if sym == observed.symbol}
        event_ids = [eid for eid, sym in regime_rows if sym in allowed_symbols]

    net_pnls: list[Decimal] = []
    if event_ids:
        orders = list(
            Order.objects.filter(
                correlation_id__in=event_ids,
                created_at__gte=window_start,
                status="FILLED",
            )
        )
        for order in orders:
            avg_fill = order.avg_fill_price
            entry = order.entry_price
            qty = order.filled_quantity or Decimal("0")
            if avg_fill is None or entry is None or qty <= 0:
                continue
            direction = Decimal("1") if str(order.side).upper() == "LONG" else Decimal("-1")
            raw_pnl = (avg_fill - entry) * qty * direction
            notional = qty * avg_fill
            costs = notional * (commission_rate + slippage_bps / Decimal("10000"))
            net_pnls.append(raw_pnl - costs)

    trades = len(net_pnls)
    if trades == 0:
        return LiveWindowStats(0, 0, Decimal("0"), Decimal("0"))
    wins = sum(1 for pnl in net_pnls if pnl > 0)
    expectancy = sum(net_pnls) / Decimal(trades)
    win_rate = Decimal(wins) / Decimal(trades)
    return LiveWindowStats(trades, wins, expectancy, win_rate)


def evaluate_observation(
    observed: ObservedRule,
    *,
    min_trades: int = DEFAULT_MIN_TRADES,
    relative_threshold: Decimal | None = None,
    window_days: int = DEFAULT_WINDOW_DAYS,
) -> DriftAlert | None:
    """Evaluate one observation; persist + notify on divergence.

    Returns the created :class:`DriftAlert` when an alert fired, ``None``
    otherwise (insufficient trades, healthy drift, or a duplicate alert for
    the same observation/kind today).
    """
    if relative_threshold is None:
        relative_threshold = Decimal(
            str(getattr(settings, "DRIFT_ALERT_RELATIVE_THRESHOLD", "1.0"))
        )

    stats = compute_live_stats(observed, window_days=window_days)
    scope = f"{observed.rule_id}/{observed.regime}" + (
        f"@{observed.symbol}" if observed.symbol else ""
    )
    if stats.trades < min_trades:
        logger.info(
            "live_drift_insufficient_trades",
            extra={
                "scope": scope,
                "trades": stats.trades,
                "min_trades": min_trades,
            },
        )
        return None

    baseline = observed.baseline_expectancy
    kind: str | None = None
    message = ""

    if baseline is not None and baseline > 0 and stats.expectancy < 0:
        kind = DriftAlert.KIND_SIGN_FLIP
        message = (
            f"{scope}: live expectancy {stats.expectancy:.4f} flipped sign vs "
            f"backtest baseline {baseline:.4f} over {stats.trades} paper trades"
        )
    elif (
        baseline is not None
        and baseline != 0
        and (baseline - stats.expectancy) / abs(baseline) >= relative_threshold
    ):
        kind = DriftAlert.KIND_THRESHOLD
        message = (
            f"{scope}: live expectancy {stats.expectancy:.4f} is >= "
            f"{relative_threshold:.0%} below baseline {baseline:.4f} "
            f"over {stats.trades} paper trades"
        )
    elif baseline is None and stats.expectancy < 0:
        kind = DriftAlert.KIND_SIGN_FLIP
        message = (
            f"{scope}: no recorded baseline but live expectancy is negative "
            f"({stats.expectancy:.4f}) over {stats.trades} paper trades"
        )

    if kind is None:
        logger.info(
            "live_drift_healthy",
            extra={
                "scope": scope,
                "trades": stats.trades,
                "expectancy": str(stats.expectancy),
                "win_rate": str(stats.win_rate),
            },
        )
        return None

    today_start = timezone.now().replace(hour=0, minute=0, second=0, microsecond=0)
    duplicate = DriftAlert.objects.filter(
        observed_rule=observed, kind=kind, created_at__gte=today_start
    ).exists()
    if duplicate:
        return None

    alert = DriftAlert.objects.create(
        observed_rule=observed,
        kind=kind,
        window_trades=stats.trades,
        live_expectancy=stats.expectancy.quantize(Decimal("0.000001")),
        live_win_rate=stats.win_rate.quantize(Decimal("0.0001")),
        baseline_expectancy=baseline,
        message=message,
    )

    # Local import avoids an app-loading cycle (notifier reads settings too).
    from apps.live_drift.infrastructure.telegram_client import notify

    notify("live drift detected", {"alert": message})
    alert.notified = True
    alert.save(update_fields=["notified", "updated_at"])
    return alert


def evaluate_all_observations(
    *, min_trades: int | None = None, window_days: int = DEFAULT_WINDOW_DAYS
) -> dict[str, Any]:
    """Evaluate every enabled observation; returns a run summary."""
    if min_trades is None:
        min_trades = int(getattr(settings, "DRIFT_MIN_TRADES", DEFAULT_MIN_TRADES))
    summary: dict[str, Any] = {"evaluated": 0, "alerts": []}
    for observed in ObservedRule.objects.filter(enabled=True).order_by("id"):
        summary["evaluated"] += 1
        alert = evaluate_observation(observed, min_trades=min_trades, window_days=window_days)
        if alert is not None:
            summary["alerts"].append(alert.message)
    return summary
