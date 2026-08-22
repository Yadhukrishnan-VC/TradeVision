"""Owner commands for the live drift monitor's opt-in observation list.

This is NOT validated_regimes: flagging a rule here only permits it to fire
on the PAPER broker against live data so the drift monitor can compare its
live paper statistics against the backtest baseline. Nothing here unlocks
real capital, and BROKER_ENVIRONMENT=live hard-refuses the bypass.

Usage::

    # flag with baseline auto-copied from docs/edge_validation_json/<SYMBOL>.json
    python manage.py flag_observed_rule add --rule breakout_v1 --regime RANGING \\
        --symbol COALINDIA

    python manage.py flag_observed_rule list
    python manage.py flag_observed_rule remove --rule breakout_v1 --regime RANGING \\
        [--symbol COALINDIA]
"""

from __future__ import annotations

import json
from decimal import Decimal, InvalidOperation
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.live_drift.infrastructure.models import ObservedRule


class Command(BaseCommand):
    help = (
        "Manage the explicit owner opt-in list of (rule, regime[, symbol]) "
        "combos under live paper observation for drift monitoring."
    )

    def add_arguments(self, parser) -> None:
        sub = parser.add_subparsers(dest="action", required=True)

        add = sub.add_parser(
            "add",
            help="Flag a rule/regime for observation. NOTE: the rule's "
            "RuleConfig must also exist and be enabled (ADR-029 §3 explicit "
            "decision); observation only waives the validation verdict on paper.",
        )
        add.add_argument("--rule", required=True)
        add.add_argument("--regime", required=True)
        add.add_argument("--symbol", default="", help="Empty = all symbols.")
        add.add_argument(
            "--baseline",
            default="",
            help="Baseline expectancy override; auto-looked up from edge-validation JSONs when omitted.",
        )
        add.add_argument("--note", default="")

        sub.add_parser("list", help="List current observations.")

        rm = sub.add_parser("remove", help="Remove an observation (hard delete).")
        rm.add_argument("--rule", required=True)
        rm.add_argument("--regime", required=True)
        rm.add_argument("--symbol", default="")

    # ------------------------------------------------------------------
    def handle(self, *args, **options) -> None:
        action = options["action"]
        if action == "add":
            self._add(options)
        elif action == "list":
            self._list()
        else:
            self._remove(options)

    def _add(self, options: dict) -> None:
        rule = options["rule"].strip()
        regime = options["regime"].strip()
        symbol = options["symbol"].strip().upper()
        if str(getattr(settings, "BROKER_ENVIRONMENT", "sandbox")) == "live":
            raise CommandError(
                "Refusing to flag observation while BROKER_ENVIRONMENT=live — "
                "observation firing is paper-only by design."
            )

        baseline_raw = options["baseline"]
        if baseline_raw:
            try:
                baseline = Decimal(baseline_raw)
            except InvalidOperation as exc:
                raise CommandError(f"Invalid --baseline: {baseline_raw!r}") from exc
        else:
            baseline = self._lookup_baseline(rule, regime, symbol)
            if baseline is None:
                self.stdout.write(self.style.WARNING(
                    "No baseline found in edge-validation JSONs; storing NULL "
                    "(monitor will only alert on negative live expectancy)."
                ))

        row, created = ObservedRule.objects.update_or_create(
            rule_id=rule,
            regime=regime,
            symbol=symbol,
            defaults={
                "baseline_expectancy": baseline,
                "enabled": True,
                "note": options["note"],
            },
        )
        verb = "created" if created else "updated"
        self.stdout.write(self.style.SUCCESS(f"{verb}: {row}"))

    def _lookup_baseline(self, rule: str, regime: str, symbol: str) -> Decimal | None:
        """Best-effort expectancy_realistic from the committed per-symbol JSONs.

        With a symbol: read that symbol's file directly. Without: average the
        rule/regime expectancy across every symbol JSON that carries it.
        """
        json_dir = Path(settings.BASE_DIR) / "docs" / "edge_validation_json"
        if not json_dir.is_dir():
            return None

        def _extract(path: Path) -> Decimal | None:
            try:
                payload = json.loads(path.read_text(encoding="utf-8"))
                entry = payload["results"][rule][regime][0]
                raw = entry.get("expectancy_realistic")
                return Decimal(str(raw)) if raw is not None else None
            except (KeyError, IndexError, OSError, ValueError, InvalidOperation):
                return None

        if symbol:
            value = _extract(json_dir / f"{symbol}.json")
            return value
        values = [v for p in sorted(json_dir.glob("*.json")) if (v := _extract(p)) is not None]
        if not values:
            return None
        return sum(values, Decimal(0)) / Decimal(len(values))

    def _list(self) -> None:
        rows = ObservedRule.objects.all().order_by("rule_id", "regime", "symbol")
        if not rows:
            self.stdout.write("(no observations flagged)")
            return
        for row in rows:
            baseline = (
                f"{row.baseline_expectancy:.4f}"
                if row.baseline_expectancy is not None
                else "—"
            )
            self.stdout.write(
                f"{row.rule_id} / {row.regime} / {row.symbol or '*'} "
                f"enabled={row.enabled} baseline={baseline} note={row.note!r}"
            )

    def _remove(self, options: dict) -> None:
        deleted, _ = ObservedRule.objects.filter(
            rule_id=options["rule"].strip(),
            regime=options["regime"].strip(),
            symbol=options["symbol"].strip().upper(),
        ).delete()
        if not deleted:
            raise CommandError("No matching observation found.")
        self.stdout.write(self.style.SUCCESS("removed"))
