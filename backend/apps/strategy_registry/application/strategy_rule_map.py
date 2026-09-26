"""Strategy → designed rules mapping.

Each default strategy is built around a specific setup ("Setup 1".."Setup 6",
per the rule-registry docstrings). A strategy-isolated backtest replays a
symbol with ONLY its designed rule(s) allowed to fire, so the run's fills and
metrics honestly represent that strategy's playbook on that stock — and
per-symbol rankings compare like-for-like.

Mapping is keyed by strategy *name* (the seeded default names). Strategies not
in this map replay with the full rule set (no isolation).
"""

from __future__ import annotations

STRATEGY_RULES: dict[str, list[str]] = {
    "Long Momentum (Setup 1)": ["long_momentum_v1"],
    "Short Sell (Setup 2)": ["short_sell_v1"],
    "Volatility Breakout (Setup 3)": ["volatility_breakout_v1"],
    "High Beta Breakout (Setup 4)": ["high_beta_breakout_v1"],
    "Short Breakdown (Setup 6)": ["short_breakdown_v1"],
    "Breakout (Default)": ["breakout_v1"],
}


def rules_for_strategy_name(name: str | None) -> list[str] | None:
    """Return the designed rule ids for a strategy, or ``None`` if unmapped."""
    if not name:
        return None
    return STRATEGY_RULES.get(name)