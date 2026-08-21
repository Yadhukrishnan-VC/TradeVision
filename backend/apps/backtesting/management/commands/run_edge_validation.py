"""
Management command: run_edge_validation

Run the full edge validation pipeline for all symbols with historical data:
- WalkForwardService for each symbol
- EdgeValidationService.compare_costs for each symbol (zero-cost baseline vs
  realistic NSE costs: commission_rate=0.0013, slippage_bps=5)
- shuffled_baseline_significance per (rule x regime) on the pooled per-trade
  net P&L sequence across symbols
- produces per-rule, per-regime verdicts (GO/NO-GO/INSUFFICIENT-DATA) with
  real p-values.

Does NOT write RuleConfig.validated_regimes — that's a separate reviewed step.

Per-trade regimes are read from ``RuleExecution.trigger_data["regime"]``
(joined to orders via ``correlation_id == analysis_event_id``), exactly the
resolution ``BacktestStatsService._resolve_regimes`` uses, so the verdicts are
grounded in the regimes the pattern/intelligence pipeline actually labelled.

Duplicate-snapshot hygiene: the runner is constructed with
``DistinctTASnapshotRepository`` so repeated historical ingestion of the same
candle timestamp never compounds the replay length (see
``technical_analysis/infrastructure/repositories.py``).

Parallel execution: run one process per symbol (or small groups) with
``--per-symbol-json DIR``, then aggregate:

    for sym in RELIANCE TCS ...; do
        python manage.py run_edge_validation --symbols $sym \
            --per-symbol-json docs/edge_validation_json &
    done
    wait
    python manage.py run_edge_validation --aggregate-json docs/edge_validation_json

Usage::

    python manage.py run_edge_validation \\
        --symbols RELIANCE,TCS,INFY \\
        --timeframe 1D \\
        --years 3 \\
        --output docs/EDGE_VALIDATION_REPORT_V2.md
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone as dj_timezone

from apps.backtesting.application.edge_validation_service import EdgeValidationService
from apps.backtesting.application.walk_forward_service import WalkForwardService
from apps.backtesting.domain.significance import shuffled_baseline_significance, SignificanceResult
from apps.backtesting.services import BacktestRunnerService
from apps.market_data.infrastructure.models import Candle as CandleModel
from apps.technical_analysis.infrastructure.repositories import DistinctTASnapshotRepository


# Realistic Indian equity costs
# STT: 0.1% on sell side (delivery) + brokerage ~0.03% + slippage ~5bps
# Combined approximate: commission_rate=0.0013 (0.13%), slippage_bps=5
REALISTIC_COMMISSION_RATE = Decimal("0.0013")  # 0.13% combined
REALISTIC_SLIPPAGE_BPS = Decimal("5.0")  # 5 basis points


def _sig_to_dict(sig: SignificanceResult | None) -> dict[str, Any] | None:
    if sig is None:
        return None
    return {
        "verdict": sig.verdict,
        "reason": sig.reason,
        "observed_mean": sig.observed_mean,
        "baseline_mean": sig.baseline_mean,
        "baseline_std": sig.baseline_std,
        "z_score": sig.z_score,
        "p_value": sig.p_value,
        "n_trades": sig.n_trades,
        "n_shuffles": sig.n_shuffles,
        "alpha": sig.alpha,
    }


def _jsonable(value: Any) -> Any:
    """Convert Decimals / datetimes into JSON-safe scalars."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, datetime):
        return value.isoformat()
    return value


class Command(BaseCommand):
    help = "Run full edge validation pipeline for all symbols with historical data."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--symbols",
            dest="symbols",
            default="",
            help="Comma-separated symbols to analyze (default: all with candle data).",
        )
        parser.add_argument(
            "--timeframe",
            dest="timeframe",
            default="1D",
            help="Candle timeframe (default: 1D).",
        )
        parser.add_argument(
            "--years",
            dest="years",
            type=int,
            default=3,
            help="Years of history to use (default: 3).",
        )
        parser.add_argument(
            "--window-size-days",
            dest="window_size_days",
            type=int,
            default=252,  # ~1 year
            help="Walk-forward window size in days (default: 252).",
        )
        parser.add_argument(
            "--step-size-days",
            dest="step_size_days",
            type=int,
            default=63,  # ~1 quarter
            help="Walk-forward step size in days (default: 63).",
        )
        parser.add_argument(
            "--in-sample-ratio",
            dest="in_sample_ratio",
            default="0.70",
            help="In-sample ratio for walk-forward (default: 0.70).",
        )
        parser.add_argument(
            "--output",
            dest="output",
            default="docs/EDGE_VALIDATION_REPORT_V2.md",
            help="Output report path (default: docs/EDGE_VALIDATION_REPORT_V2.md).",
        )
        parser.add_argument(
            "--initial-capital",
            dest="initial_capital",
            type=int,
            default=1000000,
            help="Initial capital per backtest (default: 1000000).",
        )
        parser.add_argument(
            "--min-trades",
            dest="min_trades",
            type=int,
            default=10,
            help="Minimum trades for significance test (default: 10).",
        )
        parser.add_argument(
            "--n-shuffles",
            dest="n_shuffles",
            type=int,
            default=1000,
            help="Number of shuffles for significance test (default: 1000).",
        )
        parser.add_argument(
            "--alpha",
            dest="alpha",
            type=float,
            default=0.05,
            help="Significance threshold (default: 0.05).",
        )
        parser.add_argument(
            "--per-symbol-json",
            dest="per_symbol_json",
            default="",
            help="Directory to write per-symbol results as JSON (for parallel runs).",
        )
        parser.add_argument(
            "--aggregate-json",
            dest="aggregate_json",
            default="",
            help="Skip analysis; build the report from per-symbol JSON files in this directory.",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        # Backtest replay requires CELERY_TASK_ALWAYS_EAGER=True
        from django.conf import settings
        settings.CELERY_TASK_ALWAYS_EAGER = True

        output_path = Path(options["output"])

        if options["aggregate_json"]:
            aggregate_dir = Path(options["aggregate_json"])
            all_results, symbols = self._load_per_symbol_json(aggregate_dir)
            self._generate_report(
                all_results,
                output_path,
                symbols,
                options["timeframe"],
                options["years"],
                options["window_size_days"],
                options["step_size_days"],
                Decimal(options["in_sample_ratio"]),
                options["min_trades"],
                options["n_shuffles"],
                options["alpha"],
            )
            self.stdout.write(self.style.SUCCESS(f"\nAggregated report saved to {output_path}"))
            return

        symbols = self._resolve_symbols(options["symbols"], options["timeframe"])
        if not symbols:
            raise CommandError("No symbols with candle data found. Run import first.")

        timeframe = options["timeframe"]
        years = options["years"]
        window_size_days = options["window_size_days"]
        step_size_days = options["step_size_days"]
        in_sample_ratio = Decimal(options["in_sample_ratio"])
        initial_capital = Decimal(options["initial_capital"])
        min_trades = options["min_trades"]
        n_shuffles = options["n_shuffles"]
        alpha = options["alpha"]
        per_symbol_json = Path(options["per_symbol_json"]) if options["per_symbol_json"] else None
        if per_symbol_json:
            per_symbol_json.mkdir(parents=True, exist_ok=True)

        self.stdout.write(
            f"Running edge validation for {len(symbols)} symbols "
            f"(timeframe={timeframe}, years={years}, window={window_size_days}d, step={step_size_days}d)"
        )

        User = get_user_model()
        owner = User.objects.filter(is_superuser=True).first()
        if not owner:
            raise CommandError("No superuser found. Run createsuperuser first.")

        end_date = dj_timezone.now()
        start_date = end_date - timedelta(days=years * 365 + 30)

        self.stdout.write(f"Date range: {start_date.date()} to {end_date.date()}")

        # Dedup TA repository so replay never compounds duplicate snapshots.
        dedup_repo = DistinctTASnapshotRepository()
        runner = BacktestRunnerService(ta_repo=dedup_repo)
        walk_forward_service = WalkForwardService(runner=runner)
        edge_service = EdgeValidationService(runner=runner, walk_forward=walk_forward_service)

        all_results: dict[str, dict[str, list[dict[str, Any]]]] = {}  # rule_id -> {regime -> [entry]}

        for symbol in symbols:
            self.stdout.write(f"\nAnalyzing {symbol}...")
            try:
                symbol_results = self._analyze_symbol(
                    symbol=symbol,
                    timeframe=timeframe,
                    start_date=start_date,
                    end_date=end_date,
                    owner=owner,
                    initial_capital=initial_capital,
                    window_size_days=window_size_days,
                    step_size_days=step_size_days,
                    in_sample_ratio=in_sample_ratio,
                    edge_service=edge_service,
                    min_trades=min_trades,
                    n_shuffles=n_shuffles,
                    alpha=alpha,
                )
                for rule_id, regime_data in symbol_results.items():
                    if rule_id not in all_results:
                        all_results[rule_id] = {}
                    for regime, entries in regime_data.items():
                        all_results[rule_id].setdefault(regime, []).extend(entries)

                if per_symbol_json:
                    dump = {
                        "symbol": symbol,
                        "results": symbol_results,
                    }
                    target = per_symbol_json / f"{symbol}.json"
                    with target.open("w", encoding="utf-8") as f:
                        json.dump(dump, f, default=_jsonable, indent=1)
                    self.stdout.write(f"  wrote {target}")

            except Exception as exc:  # noqa: BLE001
                self.stderr.write(self.style.ERROR(f"  {symbol}: FAILED - {exc}"))
                if per_symbol_json:
                    target = per_symbol_json / f"{symbol}.json"
                    with target.open("w", encoding="utf-8") as f:
                        json.dump({"symbol": symbol, "error": str(exc)}, f)
                continue

        self._generate_report(
            all_results,
            output_path,
            symbols,
            timeframe,
            years,
            window_size_days,
            step_size_days,
            in_sample_ratio,
            min_trades,
            n_shuffles,
            alpha,
        )

        self.stdout.write(self.style.SUCCESS(f"\nReport saved to {output_path}"))

    # ------------------------------------------------------------------
    # Analysis
    # ------------------------------------------------------------------

    def _resolve_symbols(self, symbols_raw: str, timeframe: str) -> list[str]:
        """Resolve symbols from --symbols or auto-discover from candle data."""
        if symbols_raw:
            return [s.strip().upper() for s in symbols_raw.split(",") if s.strip()]
        qs = CandleModel.objects.filter(timeframe=timeframe).values_list(
            "instrument__tradingsymbol", flat=True
        ).distinct()
        return sorted(list(qs))

    def _analyze_symbol(
        self,
        symbol: str,
        timeframe: str,
        start_date: datetime,
        end_date: datetime,
        owner: Any,
        initial_capital: Decimal,
        window_size_days: int,
        step_size_days: int,
        in_sample_ratio: Decimal,
        edge_service: EdgeValidationService,
        min_trades: int,
        n_shuffles: int,
        alpha: float,
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        """Analyze one symbol; returns rule_id -> regime -> [entry]."""
        self.stdout.write(f"  Running edge validation for {symbol}...")

        result = edge_service.compare_costs(
            owner=owner,
            symbol=symbol,
            timeframe=timeframe,
            range_start=start_date,
            range_end=end_date,
            window_size_days=window_size_days,
            step_size_days=step_size_days,
            in_sample_ratio=in_sample_ratio,
            realistic_commission_rate=REALISTIC_COMMISSION_RATE,
            realistic_slippage_bps=REALISTIC_SLIPPAGE_BPS,
            initial_capital=initial_capital,
        )

        # --- Per-trade regime attribution from the realistic-cost single run ---
        # regime_buckets are keyed by the regime the intelligence pipeline
        # labelled the triggering packet (RuleExecution.trigger_data["regime"],
        # joined via correlation_id == analysis_event_id).
        realistic = result.get("realistic_cost") or {}
        realistic_stats = realistic.get("single_run") or {}
        by_regime = realistic_stats.get("by_regime") or {}
        by_rule = realistic_stats.get("by_rule") or {}

        regime_by_order: dict[str, str] = {}
        for regime, bucket in by_regime.items():
            for trade in bucket.get("trades", []):
                order_id = trade.get("order_id")
                if order_id and order_id not in regime_by_order:
                    regime_by_order[order_id] = regime

        # rule x regime trade sequences (net P&L, costs already applied)
        rule_regime_pnls: dict[tuple[str, str], list[float]] = {}
        for rule_id, bucket in by_rule.items():
            for trade in bucket.get("trades", []):
                order_id = trade.get("order_id")
                regime = regime_by_order.get(order_id)
                if regime is None:
                    continue
                net_pnl = trade.get("net_pnl")
                if net_pnl is None:
                    continue
                rule_regime_pnls.setdefault((rule_id, regime), []).append(
                    float(Decimal(str(net_pnl)))
                )

        walk_forward = realistic.get("walk_forward") or {}
        wf_dist = walk_forward.get("distribution") or {}

        results_by_rule_regime: dict[str, dict[str, list[dict[str, Any]]]] = {}

        for rule_id, rule_data in result.get("by_rule", {}).items():
            baseline_report = rule_data.get("baseline") or {}
            realistic_report = rule_data.get("realistic_cost") or {}

            # Collect this rule's regimes (from trades attributed above).
            rule_regimes = {
                regime
                for (rid, regime) in rule_regime_pnls
                if rid == rule_id
            }
            if not rule_regimes:
                # Rule fired but no regime was attributable — surface as UNKNOWN.
                rule_regimes = {"UNKNOWN"}

            for regime in sorted(rule_regimes):
                pnls = rule_regime_pnls.get((rule_id, regime), [])
                significance = None
                if len(pnls) >= min_trades:
                    significance = shuffled_baseline_significance(
                        pnls,
                        n_shuffles=n_shuffles,
                        alpha=alpha,
                        min_trades=min_trades,
                    )

                regime_bucket = by_regime.get(regime) or {}

                entry = {
                    "symbol": symbol,
                    "rule_id": rule_id,
                    "regime": regime,
                    "baseline_has_edge": rule_data.get("baseline_has_edge"),
                    "realistic_has_edge": rule_data.get("realistic_cost_has_edge"),
                    "flipped": rule_data.get("flipped", False),
                    "trade_count_baseline": baseline_report.get("trade_count", 0),
                    "trade_count_realistic": realistic_report.get("trade_count", 0),
                    "expectancy_baseline": baseline_report.get("expectancy"),
                    "expectancy_realistic": realistic_report.get("expectancy"),
                    "profit_factor_baseline": baseline_report.get("profit_factor"),
                    "profit_factor_realistic": realistic_report.get("profit_factor"),
                    "sharpe_baseline": baseline_report.get("sharpe_ratio"),
                    "sharpe_realistic": realistic_report.get("sharpe_ratio"),
                    "max_drawdown_baseline": baseline_report.get("max_drawdown_pct"),
                    "max_drawdown_realistic": realistic_report.get("max_drawdown_pct"),
                    "regime_trade_count": regime_bucket.get("trade_count", 0),
                    "regime_expectancy": regime_bucket.get("expectancy"),
                    "regime_win_rate": regime_bucket.get("win_rate"),
                    "walk_forward_windows": walk_forward.get("total_windows", 0),
                    "walk_forward_included": walk_forward.get("included_window_count", 0),
                    "walk_forward_oos_expectancy_mean": (wf_dist.get("out_of_sample_expectancy") or {}).get("mean"),
                    "trade_count_significance": len(pnls),
                    "trades": pnls,
                }
                results_by_rule_regime.setdefault(rule_id, {}).setdefault(regime, []).append(entry)

        return results_by_rule_regime

    # ------------------------------------------------------------------
    # Report
    # ------------------------------------------------------------------

    def _load_per_symbol_json(self, directory: Path) -> tuple[dict[str, dict[str, list[dict[str, Any]]]], list[str]]:
        all_results: dict[str, dict[str, list[dict[str, Any]]]] = {}
        symbols: list[str] = []
        for path in sorted(directory.glob("*.json")):
            with path.open(encoding="utf-8") as f:
                payload = json.load(f)
            if payload.get("error"):
                self.stderr.write(self.style.ERROR(f"{payload['symbol']}: FAILED - {payload['error']}"))
                continue
            symbol = payload["symbol"]
            symbols.append(symbol)
            for rule_id, regime_data in payload.get("results", {}).items():
                for regime, entries in regime_data.items():
                    all_results.setdefault(rule_id, {}).setdefault(regime, []).extend(entries)
        return all_results, sorted(symbols)

    def _aggregate_verdicts(
        self,
        all_results: dict[str, dict[str, list[dict[str, Any]]]],
        min_trades: int,
        n_shuffles: int,
        alpha: float,
    ) -> tuple[dict[str, dict[str, str]], dict[str, dict[str, dict[str, Any]]]]:
        """Return (verdicts, pooled summaries) per rule x regime."""
        verdicts: dict[str, dict[str, str]] = {}
        pooled: dict[str, dict[str, dict[str, Any]]] = {}

        for rule_id, regime_data in all_results.items():
            verdicts[rule_id] = {}
            pooled[rule_id] = {}
            for regime, entries in regime_data.items():
                pooled_trades: list[float] = []
                has_edge_count = 0
                no_edge_count = 0
                for entry in entries:
                    pooled_trades.extend(entry.get("trades", []))
                    edge = entry.get("realistic_has_edge")
                    if edge is True:
                        has_edge_count += 1
                    elif edge is False:
                        no_edge_count += 1

                significance = None
                if len(pooled_trades) >= min_trades:
                    significance = shuffled_baseline_significance(
                        pooled_trades,
                        n_shuffles=n_shuffles,
                        alpha=alpha,
                        min_trades=min_trades,
                    )

                if len(pooled_trades) < min_trades:
                    verdict = "INSUFFICIENT-DATA"
                elif has_edge_count > 0 and significance is not None and significance.verdict == "SIGNIFICANT":
                    verdict = "GO"
                elif no_edge_count > 0:
                    verdict = "NO-GO"
                else:
                    verdict = "INSUFFICIENT-DATA"

                verdicts[rule_id][regime] = verdict
                pooled[rule_id][regime] = {
                    "symbols": len(entries),
                    "total_trades": len(pooled_trades),
                    "has_edge_count": has_edge_count,
                    "no_edge_count": no_edge_count,
                    "pooled_expectancy": (
                        sum(pooled_trades) / len(pooled_trades) if pooled_trades else None
                    ),
                    "significance": _sig_to_dict(significance),
                }

        return verdicts, pooled

    def _generate_report(
        self,
        all_results: dict[str, dict[str, list[dict[str, Any]]]],
        output_path: Path,
        symbols: list[str],
        timeframe: str,
        years: int,
        window_size_days: int,
        step_size_days: int,
        in_sample_ratio: Decimal,
        min_trades: int,
        n_shuffles: int,
        alpha: float,
    ) -> None:
        """Generate the markdown report."""
        output_path.parent.mkdir(parents=True, exist_ok=True)

        verdicts, pooled = self._aggregate_verdicts(all_results, min_trades, n_shuffles, alpha)

        observed_regimes = sorted({
            regime
            for regime_data in all_results.values()
            for regime in regime_data
        })

        with output_path.open("w", encoding="utf-8") as f:
            f.write("# Edge Validation Report V2 — TradeVision\n\n")
            f.write(f"**Generated:** {dj_timezone.now().isoformat()}\n\n")
            f.write(f"**Symbols analyzed:** {len(symbols)} ({', '.join(symbols)})\n")
            f.write(f"**Timeframe:** {timeframe}\n")
            f.write(f"**Years of history:** {years}\n")
            f.write(f"**Walk-forward window:** {window_size_days} days\n")
            f.write(f"**Walk-forward step:** {step_size_days} days\n")
            f.write(f"**In-sample ratio:** {in_sample_ratio}\n")
            f.write(f"**Realistic commission rate:** {REALISTIC_COMMISSION_RATE} (0.13%)\n")
            f.write(f"**Realistic slippage:** {REALISTIC_SLIPPAGE_BPS} bps\n")
            f.write(f"**Significance test:** pooled shuffled baseline, n_shuffles={n_shuffles}, alpha={alpha}, min_trades={min_trades}\n\n")

            f.write("---\n\n")
            f.write("## Overall Verdicts\n\n")

            f.write("| Rule ID | Regime | Verdict | Symbols | Trades | Pooled Expectancy | p-value | Significant |\n")
            f.write("|---------|--------|---------|---------|--------|-------------------|---------|-------------|\n")

            for rule_id in sorted(verdicts.keys()):
                for regime in sorted(verdicts[rule_id].keys()):
                    info = pooled[rule_id][regime]
                    sig = info["significance"]
                    p_str = f"{sig['p_value']:.4f}" if sig and sig["p_value"] is not None else "—"
                    sig_str = "YES" if sig and sig["verdict"] == "SIGNIFICANT" else ("NO" if sig else "N/A")
                    exp = info["pooled_expectancy"]
                    exp_str = f"{exp:.4f}" if exp is not None else "—"
                    f.write(
                        f"| {rule_id} | {regime} | **{verdicts[rule_id][regime]}** | "
                        f"{info['symbols']} | {info['total_trades']} | {exp_str} | {p_str} | {sig_str} |\n"
                    )

            f.write("\n---\n\n")
            f.write("## Per-Symbol Detail\n\n")

            for rule_id in sorted(all_results.keys()):
                f.write(f"### {rule_id}\n\n")
                for regime in sorted(all_results[rule_id].keys()):
                    f.write(f"#### Regime: {regime}\n\n")
                    entries = all_results[rule_id][regime]
                    f.write(
                        "| Symbol | Baseline Edge | Realistic Edge | Flipped | Trades (Base) | "
                        "Trades (Real) | Expectancy (Base) | Expectancy (Real) | "
                        "Profit Factor (Real) | Sharpe (Real) | Max DD (Real) | "
                        "Regime Trades | WF OOS Mean |\n"
                    )
                    f.write(
                        "|--------|---------------|----------------|---------|---------------|"
                        "---------------|-------------------|-------------------|"
                        "---------------------|---------------|---------------|"
                        "--------------|--------------|\n"
                    )

                    for entry in entries:
                        def _edge_str(value: Any) -> str:
                            if value is True:
                                return "GO"
                            if value is False:
                                return "NO-GO"
                            return "INSUFF"

                        wf_mean = entry.get("walk_forward_oos_expectancy_mean")
                        wf_str = f"{wf_mean:.4f}" if isinstance(wf_mean, (int, float)) else "—"

                        f.write(
                            f"| {entry['symbol']} | "
                            f"{_edge_str(entry['baseline_has_edge'])} | "
                            f"{_edge_str(entry['realistic_has_edge'])} | "
                            f"{'YES' if entry['flipped'] else 'NO'} | "
                            f"{entry['trade_count_baseline']} | {entry['trade_count_realistic']} | "
                            f"{self._num(entry['expectancy_baseline'])} | {self._num(entry['expectancy_realistic'])} | "
                            f"{self._num(entry['profit_factor_realistic'])} | {self._num(entry['sharpe_realistic'])} | "
                            f"{self._num(entry['max_drawdown_realistic'])} | "
                            f"{entry['regime_trade_count']} | {wf_str} |\n"
                        )
                    f.write("\n")

            f.write("---\n\n")
            f.write("## Notes\n\n")
            f.write("- **GO**: Rule has positive expectancy, profit factor > 1, and statistically significant edge at realistic costs.\n")
            f.write("- **NO-GO**: Rule fails the edge criterion at realistic costs.\n")
            f.write("- **INSUFFICIENT-DATA**: Not enough trades to make a determination (less than min_trades).\n")
            f.write("- Significance test is a one-sided sign-flip permutation test on the pooled per-trade net P&L sequence, costs applied.\n")
            f.write(f"- Observed regimes from the intelligence pipeline: {', '.join(observed_regimes)}.\n")
            f.write(
                "- Regime detection currently falls back to RANGING for 1D-only replay: the "
                "replayed payloads carry ema_20/atr_14/rsi_14/bb_upper (no ema_50/ema_200/macd/"
                "bb_lower/avg_atr_20d/VIX), so the deterministic detect_regime classifier labels "
                "most bars RANGING. Full PatternEngine regime labels remain an outstanding item.\n"
            )
            f.write("- This report does NOT write to RuleConfig.validated_regimes. That step requires human review.\n")

    @staticmethod
    def _num(value: Any) -> str:
        if value is None:
            return "—"
        try:
            return f"{Decimal(str(value)):.4f}"
        except Exception:  # noqa: BLE001
            return str(value)