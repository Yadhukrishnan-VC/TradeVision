"""Management command: capital_requirement_report

Compute the real minimum trading capital per watchlist symbol from the
stop distances actually used in the completed per-symbol backtest evidence
runs, replacing the earlier ATR-based estimate.

Source of truth per ADR-028 / the position-sizing formula:

    risk_per_unit = |entry_price - stop_loss|
    min_capital   = risk_per_unit / risk_pct

so that ``risk_amount = capital x risk_pct >= risk_per_unit`` and the
``PositionSizingCheck`` raw size floors to >= 1 unit instead of silently
zero (RejectionReason.INSUFFICIENT_CAPITAL / POSITION_SIZE_ZERO).

Evidence sources, in priority order:
1. ``RiskDecisionExecution`` rows whose created_at falls inside at least
   one COMPLETED ``BacktestRun`` window for the same symbol. RDE is the
   per-evaluation audit row written by ``RiskEvaluationService`` and
   persists the real ``entry_price`` / ``stop_loss`` each firing was
   evaluated against, including REJECTED evaluations.
2. For symbols with zero RDE evidence (e.g. HDFCBANK run variants that
   wrote only execution rows), fall back to ``ExecutionRequest`` rows for
   the completed-run accounts — the actual filled orders with entry/stop.

Rows are restricted to those with both entry and stop prices present.

Usage::

    python manage.py capital_requirement_report
    python manage.py capital_requirement_report --risk-pct 0.01
"""

from __future__ import annotations

from decimal import ROUND_CEILING, ROUND_HALF_UP, Decimal

from django.core.management.base import BaseCommand

from apps.backtesting.application.capital_requirement_service import evidence_distances
from apps.backtesting.models import BacktestRun

# The watchlist symbols the ATR estimate originally covered. The user asked
# for these specifically; the command also accepts --symbols to override.
DEFAULT_SYMBOLS = [
    "RELIANCE",
    "HDFCBANK",
    "INFY",
    "TCS",
    "SBIN",
    "ICICIBANK",
    "ITC",
    "LT",
]


class Command(BaseCommand):
    help = "Compute per-symbol minimum capital from completed backtest evidence."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--risk-pct",
            type=Decimal,
            default=Decimal("0.01"),
            help="Fraction of capital risked per trade (RISK_MANAGEMENT['risk_pct']).",
        )
        parser.add_argument(
            "--symbols",
            type=str,
            default="",
            help="Comma-separated symbols; defaults to the watchlist set.",
        )

    def handle(self, *args, **options) -> None:
        risk_pct = options["risk_pct"]
        if risk_pct <= 0:
            self.stderr.write("--risk-pct must be > 0")
            return

        symbols = options["symbols"]
        requested = [s.strip().upper() for s in symbols.split(",") if s.strip()]
        symbols = requested or DEFAULT_SYMBOLS

        self.stdout.write(f"risk_pct = {risk_pct}")
        self.stdout.write(f"{'SYMBOL':<11} {'runs':>4} {'samples':>7} "
                          f"{'avg_rpu':>12} {'worst_rpu':>12} {'min_capital_avg':>16} "
                          f"{'min_capital_worst':>18}")
        self.stdout.write("-" * 92)

        for symbol in symbols:
            runs = BacktestRun.objects.filter(status="COMPLETED", symbol=symbol)
            windows = [(run.range_start, run.range_end) for run in runs]
            distances = evidence_distances(symbol)

            if not distances:
                self.stdout.write(
                    f"{symbol:<11} {len(runs):>4} {'0':>7}  "
                    f"{'no evidence':>12} {'':>12} {'':>16} {'':>18}"
                )
                continue

            avg_rpu = sum(distances, Decimal(0)) / len(distances)
            worst_rpu = max(distances)
            min_cap_avg = (avg_rpu / risk_pct).quantize(
                Decimal("0.01"), rounding=ROUND_CEILING
            )
            min_cap_worst = (worst_rpu / risk_pct).quantize(
                Decimal("0.01"), rounding=ROUND_CEILING
            )
            rpu_quant = lambda v: v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
            self.stdout.write(
                f"{symbol:<11} {len(windows):>4} {len(distances):>7} "
                f"{rpu_quant(avg_rpu):>12} {rpu_quant(worst_rpu):>12} "
                f"{min_cap_avg:>16} {min_cap_worst:>18}"
            )