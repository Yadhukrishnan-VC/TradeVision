"""Seed default trading strategies and rule configurations.

Idempotent — safe to run repeatedly. It:

- Creates ``RuleConfig`` rows for every built-in rule with ``enabled=True``.
- Adds an ADR-029 ``GO`` gate verdict for each rule's designed regimes when no
  verdict exists yet. Provenance is ``owner_default_seed`` (NOT a backtest):
  this is the owner's explicit "set all by default" choice, and it stays
  transparent in ``validated_regimes[*].backtest_run_id`` so a real backtest
  verdict can later replace it. Existing verdicts are never overwritten.
- Creates the default ACTIVE strategies in the strategy registry when absent.

Usage::

    python manage.py seed_trading_defaults
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from django.core.management.base import BaseCommand

from apps.rule_engine.infrastructure.models import RuleConfig
from apps.strategy_registry.models import TradingStrategy, TradingStrategyStatus

# rule_id -> regimes the rule is designed around (verified from each rule file).
RULE_REGIMES: dict[str, list[str]] = {
    "price_movement_v1": ["RANGING", "VOLATILE"],
    "volume_spike_v1": ["RANGING", "VOLATILE"],
    "breakout_v1": ["BREAKOUT", "RANGING"],
    "long_momentum_v1": ["BULLISH"],
    "short_sell_v1": ["BEARISH"],
    "volatility_breakout_v1": ["VOLATILE"],
    "high_beta_breakout_v1": ["BULLISH", "RANGING"],
    "short_breakdown_v1": ["BEARISH"],
}

DEFAULT_STRATEGIES: list[dict[str, object]] = [
    {
        "name": "Long Momentum (Setup 1)",
        "priority": 1,
        "status": TradingStrategyStatus.ACTIVE.value,
    },
    {
        "name": "Short Sell (Setup 2)",
        "priority": 2,
        "status": TradingStrategyStatus.ACTIVE.value,
    },
    {
        "name": "Volatility Breakout (Setup 3)",
        "priority": 3,
        "status": TradingStrategyStatus.ACTIVE.value,
    },
    {
        "name": "High Beta Breakout (Setup 4)",
        "priority": 4,
        "status": TradingStrategyStatus.ACTIVE.value,
    },
    {
        "name": "Short Breakdown (Setup 6)",
        "priority": 5,
        "status": TradingStrategyStatus.ACTIVE.value,
    },
    {
        "name": "Breakout (Default)",
        "priority": 6,
        "status": TradingStrategyStatus.ACTIVE.value,
    },
]


class Command(BaseCommand):
    help = "Seed default strategies and rule configs (idempotent)."

    def handle(self, *args: str, **options: object) -> None:
        seed_defaults = seed_trading_defaults()
        for line in seed_defaults:
            self.stdout.write(line)
        self.stdout.write(self.style.SUCCESS("Seed complete."))


def _as_dict(value: object) -> dict:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            return dict(json.loads(value))
        except (json.JSONDecodeError, KeyError, TypeError):
            return {}
    return {}


def seed_trading_defaults() -> list[str]:
    lines: list[str] = []
    evaluated_at = datetime.now(timezone.utc).isoformat()

    configs = {c.rule_id: c for c in RuleConfig.objects.all()}
    for rule_id, regimes in RULE_REGIMES.items():
        config = configs.get(rule_id)
        created = config is None
        if config is None:
            config = RuleConfig(rule_id=rule_id, enabled=True)
            config.save()
        if not created and not config.enabled:
            config.enabled = True
            config.save(update_fields=["enabled", "updated_at"])

        current = _as_dict(config.validated_regimes)
        added: list[str] = []
        untouched: list[str] = []
        for regime in regimes:
            if regime in current:
                untouched.append(regime)
                continue
            current[regime] = {
                "status": "GO",
                "expectancy": "0.00000000",
                "profit_factor": "1.30",
                "sharpe_ratio": None,
                "max_drawdown_pct": "0.0000",
                "trade_count": 0,
                "backtest_run_id": "owner_default_seed",
                "evaluated_at": evaluated_at,
            }
            added.append(regime)
        if added:
            config.validated_regimes = current
            config.save(update_fields=["validated_regimes", "updated_at"])

        desc = ", ".join(f"{r}=GO" for r in added)
        if untouched:
            desc = (desc + ", " if desc else "") + ", ".join(untouched) + "=preserved"
        lines.append(
            f"rule_config {rule_id}: enabled=True " + (desc or "no regimes")
        )

    existing_names = set(
        TradingStrategy.objects.filter(is_deleted=False).values_list("name", flat=True)
    )
    for strat in DEFAULT_STRATEGIES:
        if strat["name"] in existing_names:
            continue
        TradingStrategy.objects.create(
            name=str(strat["name"]),
            status=str(strat["status"]),
            priority=int(strat["priority"]),
            confidence_threshold="0.6000",
            risk_threshold="0.5000",
        )
        lines.append(f"strategy {strat['name']}: created ACTIVE")
    return lines