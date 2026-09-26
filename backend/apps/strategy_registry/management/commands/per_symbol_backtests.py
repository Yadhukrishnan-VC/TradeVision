"""Strategy-isolated backtests per (strategy × symbol) + per-symbol ranking.

Backtests every ACTIVE strategy against every target symbol through the real
replay pipeline, with the run pinned to its own strategy (only that strategy's
designed rules fire, and ``StrategyMatcher`` is forced to that strategy).
Completed runs then feed ``SymbolRankingService`` which stores a per-symbol
strategy ranking (``StrategySymbolAffinity``) that ``StrategyMatcher`` prefers
over global priority for live packets of that symbol.

Idempotent: a COMPLETED run for a (symbol, strategy) combo is skipped and its
ranking retained; a PENDING/RUNNING run for the combo is resumed from its
cursor.

Usage::

    python manage.py per_symbol_backtests
    python manage.py per_symbol_backtests --symbols RELIANCE,INFY --days 365
    python manage.py per_symbol_backtests --symbols RELIANCE --strategies "Breakout (Default)"
"""

from __future__ import annotations

import time
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from typing import Any

from django.conf import settings
from django.core.management.base import BaseCommand

_DEFAULT_DAYS = 365
_DEFAULT_TIMEFRAME = "1D"
_DEFAULT_CAPITAL = Decimal(1000000)


class Command(BaseCommand):
    help = (
        "Strategy-isolated backtests per (strategy x symbol) and per-symbol "
        "strategy ranking."
    )

    def add_arguments(self, parser: Any) -> None:
        parser.add_argument(
            "--symbols", type=str, default="", help="Comma-separated symbols (default: watchlist)."
        )
        parser.add_argument(
            "--strategies",
            type=str,
            default="",
            help="Comma-separated strategy name prefixes (default: all ACTIVE).",
        )
        parser.add_argument("--timeframe", type=str, default=_DEFAULT_TIMEFRAME)
        parser.add_argument("--days", type=int, default=_DEFAULT_DAYS)
        parser.add_argument("--end", type=str, default="", help="ISO yyyy-mm-dd (default: today).")
        parser.add_argument("--owner", type=str, default="admin", help="Username owning new accounts.")
        parser.add_argument(
            "--initial-capital", type=str, default=str(_DEFAULT_CAPITAL)
        )
        parser.add_argument("--no-rank", action="store_true", help="Skip ranking after runs.")

    def handle(self, *args: str, **options: object) -> None:
        # Replay must run in-process so simulation contextvars propagate.
        settings.CELERY_TASK_ALWAYS_EAGER = True
        # Inline drain reads StoredEvent directly; skip the Redis mirror
        # (per-event asyncio loop churn) during replay.
        settings.BACKTEST_NO_REDIS_MIRROR = True
        import logging

        logging.disable(logging.INFO)
        self.stdout.write("CELERY_TASK_ALWAYS_EAGER=True (in-process replay)")

        from apps.accounts.infrastructure.models import User
        from apps.backtesting.models import BacktestRun, BacktestRunStatus
        from apps.backtesting.services import BacktestRunnerService
        from apps.portfolio.application.capital_service import CapitalService
        from apps.strategy_registry.application.symbol_ranking_service import (
            SymbolRankingService,
        )
        from apps.strategy_registry.models import TradingStrategy, TradingStrategyStatus

        owner = User.objects.filter(username=str(options["owner"])).first()
        if owner is None:
            self.stderr.write(f"Owner user '{options['owner']}' not found.")
            return

        symbols = self._resolve_symbols(str(options["symbols"]))
        if not symbols:
            self.stderr.write("No symbols to backtest (empty watchlist / no --symbols).")
            return

        strategies = list(
            TradingStrategy.objects.filter(
                status=TradingStrategyStatus.ACTIVE, is_deleted=False
            ).order_by("priority")
        )
        filters = [
            s.strip() for s in str(options["strategies"]).split(",") if s.strip()
        ]
        if filters:
            strategies = [
                s for s in strategies if any(s.name.startswith(f) for f in filters)
            ]
        if not strategies:
            self.stderr.write("No active strategies matched.")
            return

        range_end = self._resolve_end(str(options["end"]))
        range_start = range_end - timedelta(
            days=int(options["days"])
        )
        timeframe = str(options["timeframe"])
        capital = _DEFAULT_CAPITAL

        self.stdout.write(
            f"Symbols({len(symbols)}): {', '.join(symbols)} "
            f"Strategies({len(strategies)}): {', '.join(s.name for s in strategies)} "
            f"range {range_start.date()} -> {range_end.date()} ({timeframe})"
        )

        runner = BacktestRunnerService()
        completed = 0
        created = 0
        committed = 0
        failed = 0
        started = time.monotonic()

        for symbol in symbols:
            for strategy in strategies:
                existing = (
                    BacktestRun.objects.filter(
                        symbol=symbol,
                        strategy=strategy,
                        timeframe=timeframe,
                    ).order_by("-created_at").first()
                )
                if existing is not None and existing.status == BacktestRunStatus.COMPLETED:
                    self.stdout.write(f"  {symbol} x {strategy.name}: COMPLETED (skip)")
                    completed += 1
                    continue

                from apps.accounts.infrastructure.models import Account

                if existing is None:
                    account = Account.objects.create(
                        name=f"BT {strategy.name} {symbol}",
                        owner=owner,
                        is_default=False,
                    )
                    CapitalService().deposit(account.id, capital)
                    run = BacktestRun(
                        symbol=symbol,
                        timeframe=timeframe,
                        strategy=strategy,
                        range_start=range_start,
                        range_end=range_end,
                        account=account,
                        status=BacktestRunStatus.PENDING,
                    )
                    run.save()
                    created += 1
                else:
                    run = existing

                result = runner.run(run.id)
                status_out = result.get("status")
                if status_out == BacktestRunStatus.COMPLETED:
                    committed += 1
                    bars = result.get("bars_processed")
                    self.stdout.write(
                        f"  {symbol} x {strategy.name}: COMPLETED ({bars} bars) run={run.id}"
                    )
                elif status_out == BacktestRunStatus.FAILED:
                    failed += 1
                    self.stderr.write(
                        f"  {symbol} x {strategy.name}: FAILED {result.get('reason')}"
                    )
                else:
                    self.stdout.write(f"  {symbol} x {strategy.name}: {status_out}")

        elapsed = time.monotonic() - started
        self.stdout.write(
            f"Runs: created={created} completed={committed} skipped={completed} "
            f"failed={failed} elapsed={elapsed:.0f}s"
        )

        if not options["no_rank"]:
            ranking = SymbolRankingService()
            self.stdout.write("\nPer-symbol rankings (StrategySymbolAffinity):")
            ranked = ranking.rank_symbols(symbols, timeframe=timeframe)
            for symbol, rows in ranked.items():
                if not rows:
                    self.stdout.write(f"  {symbol}: (no evidence-backed strategies)")
                    continue
                for row in rows:
                    self.stdout.write(
                        f"  {symbol}: #{row['rank']} {row['strategy_name']} "
                        f"score={row['score']} exp={row['expectancy']} "
                        f"pf={row['profit_factor']} dd={row['max_drawdown_pct']}% "
                        f"trades={row['trade_count']} run={row['source_run_id'][:8]}"
                    )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _resolve_symbols(self, csv_symbols: str) -> list[str]:
        if csv_symbols.strip():
            return [s.strip().upper() for s in csv_symbols.split(",") if s.strip()]

        from apps.watchlist.infrastructure.models import WatchlistEntry

        seen: list[str] = []
        seen_set: set[str] = set()
        for symbol in (
            WatchlistEntry.objects.filter(instrument__tradingsymbol__isnull=False)
            .values_list("instrument__tradingsymbol", flat=True)
            .distinct()
        ):
            symbol = str(symbol).upper()
            if symbol not in seen_set:
                seen_set.add(symbol)
                seen.append(symbol)
        return seen

    def _resolve_end(self, raw: str) -> datetime:
        if raw.strip():
            return datetime.fromisoformat(raw.strip())
        return datetime.now(timezone.utc)