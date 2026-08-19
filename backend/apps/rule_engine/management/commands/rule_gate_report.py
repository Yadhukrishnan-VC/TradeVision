"""
Management command: rule_gate_report

Shows, per rule, which market regimes it is GO-validated for (and therefore
allowed to fire in) under the ADR-029 §4 fail-closed gate
(``RuleEvaluationService._filter_by_gate``). A rule only fires when ALL of:

- a ``RuleConfig`` row exists (else ``no_config``),
- ``RuleConfig.enabled`` is True (else ``disabled``),
- the packet carries a regime (else ``no_regime``), and
- ``validated_regimes[<regime>].status == "GO"`` (else ``not_validated``).

Backtest-created config rows always have ``enabled=False`` (ADR-029 §3), so a
GO verdict alone never flips a rule live — an explicit human decision is
required. This command makes it visible *why* nothing is firing, not just that
nothing is firing.

Usage::

    python manage.py rule_gate_report
    python manage.py rule_gate_report --regime BULLISH
    python manage.py rule_gate_report --verbose
"""

from __future__ import annotations

from typing import Any

from django.core.management.base import BaseCommand

from apps.intelligence.domain.market_regime import MarketRegime
from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService
from apps.rule_engine.infrastructure.models import RuleConfig

_GATE_STATUS_GO = "GO"

_VERDICT_ORDER = ("GO", "NO_GO", "INSUFFICIENT_DATA")


class Command(BaseCommand):
    help = "Report per-rule regime GO validation status for the ADR-029 §4 gate."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--regime",
            dest="regime",
            default=None,
            help="Filter to a single regime (BULLISH, BEARISH, ...).",
        )
        parser.add_argument(
            "--verbose",
            dest="verbose",
            action="store_true",
            help="Include the stored verdict fields (expectancy, trade count, ...).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        regimes = self._resolve_regimes(options["regime"])
        rules = self._registered_rules()
        configs = {cfg.rule_id: cfg for cfg in RuleConfig.objects.all()}

        self.stdout.write("ADR-029 §4 fail-closed gate — per-rule regime GO status")
        self.stdout.write(
            "gate pass = RuleConfig exists + enabled + validated_regimes[regime].status == GO"
        )
        self.stdout.write("")

        header = f"{'RULE':<28} {'EVENT':<20} {'ENABLED':<8}" + "".join(
            f" {r:<13}" for r in regimes
        )
        self.stdout.write(header)
        self.stdout.write("-" * len(header))

        fireable_anywhere = 0
        for rule in rules:
            config = configs.get(rule.rule_id)
            cells: list[str] = []
            fireable_here = False
            for regime in regimes:
                verdict = self._gate_verdict(config, regime)
                if verdict == "GO":
                    fireable_here = True
                cells.append(self._style_verdict(verdict, regime))
            if fireable_here:
                fireable_anywhere += 1
            self.stdout.write(
                f"{rule.rule_id:<28} {rule.event_type.value:<20} "
                f"{'yes' if (config and config.enabled) else 'no':<8}" + "".join(cells)
            )

            if options["verbose"] and config:
                self.stdout.write(
                    f"    validated_regimes: {self._summarize(config, regimes)}"
                )

        self.stdout.write("")
        self.stdout.write(
            f"rules fireable in at least one reported regime: {fireable_anywhere}/{len(rules)}"
        )
        self.stdout.write(
            "note: backtest-created configs are always disabled (ADR-029 §3); "
            "a GO verdict alone never flips a rule live."
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _resolve_regimes(self, regime: str | None) -> list[str]:
        values = [m.value for m in MarketRegime]
        if regime:
            regime = regime.upper()
            if regime not in values:
                raise ValueError(
                    f"Unknown regime {regime!r}. Known: {', '.join(values)}."
                )
            return [regime]
        return values

    def _registered_rules(self):
        # Reuses the real registration path so the report always matches what
        # RuleEvaluationService would evaluate.
        return RuleEvaluationService()._registry.get_registered_rules()

    def _gate_verdict(self, config: RuleConfig | None, regime: str) -> str:
        """Mirror ``_filter_by_gate``: return the reason a rule would NOT fire
        (or ``GO`` if it would)."""
        if config is None:
            return "NO_CONFIG"
        if not config.enabled:
            return "DISABLED"
        status = self._status_for(config, regime)
        if status is None:
            return "NOT_VALIDATED"
        return status

    @staticmethod
    def _status_for(config: RuleConfig | None, regime: str) -> str | None:
        if config is None:
            return None
        entry = config.validated_regimes.get(regime)
        if not isinstance(entry, dict):
            return None
        status = entry.get("status")
        return status if isinstance(status, str) else None

    def _style_verdict(self, verdict: str, regime: str) -> str:
        cell = f" {verdict:<13}"
        if verdict == "GO":
            return self.style.SUCCESS(cell)
        if verdict in _VERDICT_ORDER:
            return self.style.WARNING(cell)
        return self.style.ERROR(cell)

    @staticmethod
    def _summarize(config: RuleConfig | None, regimes: list[str]) -> str:
        if config is None:
            return "(no RuleConfig row)"
        return " ".join(
            f"{regime}={config.validated_regimes.get(regime)}"
            for regime in regimes
            if isinstance(config.validated_regimes.get(regime), dict)
        )
