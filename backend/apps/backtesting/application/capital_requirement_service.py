"""Capital-requirement evidence service.

Single source of truth for the "how much capital does symbol X need to clear
position sizing" question, derived from the stop distances recorded in the
completed per-symbol backtest evidence runs.

Formula (ADR-028 position sizing):

    risk_per_unit = abs(entry_price - stop_loss)
    min_capital   = risk_per_unit / risk_pct

so that ``risk_amount = capital x risk_pct >= risk_per_unit`` and
``PositionSizingCheck``'s raw size floors to >= 1 unit.

Evidence sources, in priority order:
1. ``RiskDecisionExecution`` rows whose created_at falls inside at least one
   COMPLETED ``BacktestRun`` window for the same symbol (the per-evaluation
   audit record with the real entry/stop each firing was evaluated against).
2. For symbols with zero RDE evidence, ``ExecutionRequest`` rows for the
   completed-run accounts (actual filled orders with entry/stop).
"""

from __future__ import annotations

from collections.abc import Iterable
from decimal import Decimal

from apps.backtesting.models import BacktestRun
from apps.execution.infrastructure.models import ExecutionRequest
from apps.risk_management.infrastructure.models import RiskDecisionExecution


def _rde_distances(symbol: str, windows: list[tuple]) -> list[Decimal]:
    return [
        abs(Decimal(row.entry_price) - Decimal(row.stop_loss))
        for row in RiskDecisionExecution.objects.filter(
            symbol=symbol,
            entry_price__isnull=False,
            stop_loss__isnull=False,
        )
        if any(
            row.created_at >= start and row.created_at <= end
            for start, end in windows
        )
    ]


def _execution_distances(symbol: str, accounts: list) -> list[Decimal]:
    if not accounts:
        return []
    return [
        abs(Decimal(row.entry_price) - Decimal(row.stop_loss))
        for row in ExecutionRequest.objects.filter(
            account_id__in=accounts,
            entry_price__isnull=False,
            stop_loss__isnull=False,
        )
    ]


def evidence_distances(symbol: str) -> list[Decimal]:
    """Return the risk-per-unit sample set for a symbol from the evidence runs."""
    runs = BacktestRun.objects.filter(status="COMPLETED", symbol=symbol)
    windows = [(run.range_start, run.range_end) for run in runs]
    accounts = [run.account_id for run in runs]
    distances = _rde_distances(symbol, windows)
    if not distances:
        distances = _execution_distances(symbol, accounts)
    return distances


def min_capital_requirement(
    symbol: str, risk_pct: Decimal, *, worst_case: bool = True
) -> Decimal | None:
    """Worst-case (or average) min_capital for a symbol, or None if no evidence."""
    distances = evidence_distances(symbol)
    if not distances:
        return None
    reference = max(distances) if worst_case else sum(distances, Decimal(0)) / len(distances)
    return reference / risk_pct


def requirements_for_symbols(
    symbols: Iterable[str], risk_pct: Decimal, *, worst_case: bool = True
) -> dict[str, Decimal]:
    """Map symbol -> worst-case/average min_capital (evident symbols only)."""
    result: dict[str, Decimal] = {}
    for symbol in symbols:
        req = min_capital_requirement(symbol, risk_pct, worst_case=worst_case)
        if req is not None:
            result[symbol] = req
    return result