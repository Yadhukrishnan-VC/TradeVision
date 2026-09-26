"""Per-symbol strategy ranking from completed backtests.

``SymbolRankingService.rank_symbol`` turns a symbol's COMPLETED backtest runs
(strategy-tagged) into an evidence-backed rank list stored as
``StrategySymbolAffinity`` rows. Only strategies that cleared the
ADR-029-style gate plus trade-count are ranked; everything else is simply
absent from the table, so ``StrategyMatcher`` falls back to the global
``priority`` ordering with no fabricated evidence.

Composite score (documented, deterministic):

    score = 1.0 * expectancy + 50 * (profit_factor - 1) - 0.2 * max_drawdown_pct

- ``expectancy`` is the dominant signal: how much a trade earns on average.
- ``profit_factor - 1`` is grossly scaled because a marginally-win rate flip
  (PF crossing 1.0) is swingy at small trade counts and should matter far
  less than expectancy.
- max drawdown is a penalty (fraction-form 0.20 == 20%).

A ``GO``-eligible strategy must have >= 30 trades, expectancy > 0,
profit_factor > 1.3 and max_drawdown < 20% (mirrors ADR-029 §4 defaults).
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from django.db import transaction

from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.backtesting.services import BacktestStatsService
from apps.strategy_registry.models import StrategySymbolAffinity, TradingStrategy
from core.services import BaseService

logger = logging.getLogger(__name__)

MIN_TRADE_COUNT = 30
MIN_PROFIT_FACTOR = Decimal("1.3")
MAX_DRAWDOWN_PCT = Decimal(20)

SCORE_EXPECTANCY_WEIGHT = Decimal("1")
SCORE_PF_WEIGHT = Decimal("50")
SCORE_DD_WEIGHT = Decimal("0.2")


def _to_decimal(value: Any) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except (TypeError, ValueError, ArithmeticError):
        return None


def composite_score(
    expectancy: Decimal,
    profit_factor: Decimal,
    max_drawdown_pct: Decimal,
) -> Decimal:
    """Deterministic composite used to order strategies for a symbol."""
    return (
        SCORE_EXPECTANCY_WEIGHT * expectancy
        + SCORE_PF_WEIGHT * (profit_factor - Decimal("1"))
        - SCORE_DD_WEIGHT * (max_drawdown_pct / Decimal("100"))
    )


class SymbolRankingService(BaseService):
    """Compute and persist per-symbol strategy rankings from backtest runs."""

    def __init__(self, stats_service: BacktestStatsService | None = None) -> None:
        super().__init__()
        self._stats = stats_service or BacktestStatsService()

    def rank_symbol(self, symbol: str, timeframe: str = "") -> list[dict[str, Any]]:
        """Rank strategies for one symbol from its COMPLETED strategy-tagged runs.

        Returns the ranked list (also persisted). Empty symbol → no runs.
        """
        normalized = symbol.strip().upper()
        runs = self._completed_runs(normalized, timeframe)

        best_run: dict[str, BacktestRun] = {}
        best_count: dict[str, int] = {}
        stats_by_run: dict[str, dict[str, Any]] = {}
        for run in runs:
            try:
                stats = self._stats.run_stats(run)
            except Exception:
                logger.exception(
                    "rank_stats_failed", extra={"run_id": str(run.id), "symbol": normalized}
                )
                continue
            stats_by_run[str(run.id)] = stats
            count = int(stats.get("trade_count") or 0)
            existing = best_count.get(str(run.strategy_id), -1)
            if count > existing:
                best_count[str(run.strategy_id)] = count
                best_run[str(run.strategy_id)] = run

        ranked: list[dict[str, Any]] = []
        for strategy_id_str, run in best_run.items():
            strategy = run.strategy
            stats = stats_by_run[str(run.id)]
            count = best_count[strategy_id_str]
            expectancy = _to_decimal(stats.get("expectancy"))
            pf = _to_decimal(stats.get("profit_factor"))
            dd = _to_decimal(stats.get("max_drawdown_pct"))

            if (
                count < MIN_TRADE_COUNT
                or expectancy is None
                or pf is None
                or dd is None
                or expectancy <= Decimal("0")
                or pf <= MIN_PROFIT_FACTOR
                or dd >= MAX_DRAWDOWN_PCT
            ):
                continue

            score = composite_score(expectancy, pf, dd)
            ranked.append(
                {
                    "strategy_id": str(strategy.id),
                    "strategy_name": strategy.name,
                    "symbol": normalized,
                    "rank": 0,  # assigned below
                    "score": score,
                    "expectancy": expectancy,
                    "profit_factor": pf,
                    "sharpe_ratio": _to_decimal(stats.get("sharpe_ratio")),
                    "max_drawdown_pct": dd,
                    "trade_count": count,
                    "source_run_id": str(run.id),
                    "evaluated_at": run.completed_at or datetime.now(timezone.utc),
                }
            )

        ranked.sort(key=lambda r: r["score"], reverse=True)
        for index, entry in enumerate(ranked, start=1):
            entry["rank"] = index

        self._persist(normalized, ranked)
        earned = [f"#{e['rank']} {e['strategy_name']} ({e['score']})" for e in ranked]
        logger.info("symbol_ranked", extra={"symbol": normalized, "rankings": earned})
        return ranked

    def rank_symbols(self, symbols: list[str], timeframe: str = "") -> dict[str, list[dict[str, Any]]]:
        """Rank strategies for each symbol; returns {symbol: ranked_list}."""
        result: dict[str, list[dict[str, Any]]] = {}
        for symbol in symbols:
            result[symbol] = self.rank_symbol(symbol, timeframe=timeframe)
        return result

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _completed_runs(
        self, symbol: str, timeframe: str
    ) -> list[BacktestRun]:
        qs = BacktestRun.objects.filter(
            symbol=symbol,
            status=BacktestRunStatus.COMPLETED,
        ).exclude(strategy_id__isnull=True).select_related("strategy")
        if timeframe:
            qs = qs.filter(timeframe=timeframe)
        return list(qs)

    def _persist(self, symbol: str, ranked: list[dict[str, Any]]) -> None:
        with transaction.atomic():
            StrategySymbolAffinity.objects.filter(symbol=symbol).delete()
            if not ranked:
                return
            rows = [
                StrategySymbolAffinity(
                    strategy_id=entry["strategy_id"],
                    symbol=symbol,
                    rank=entry["rank"],
                    score=entry["score"],
                    expectancy=entry["expectancy"],
                    profit_factor=entry["profit_factor"],
                    sharpe_ratio=entry["sharpe_ratio"],
                    max_drawdown_pct=entry["max_drawdown_pct"],
                    trade_count=entry["trade_count"],
                    source_run_id=entry["source_run_id"],
                    evaluated_at=entry["evaluated_at"],
                )
                for entry in ranked
            ]
            StrategySymbolAffinity.objects.bulk_create(rows)