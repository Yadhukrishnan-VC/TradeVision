from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class RiskConfig:
    """Tunable risk parameters read from ``settings.RISK_MANAGEMENT``.

    Every field has a safe default so the app runs out-of-the-box; values are
    sourced from the Django settings dict ``RISK_MANAGEMENT`` (see
    ``config/settings/base.py``).
    """

    risk_pct: Decimal = Decimal("0.01")
    max_position_size: int = 1_000_000
    max_exposure_cap: Decimal | None = None
    daily_loss_limit: Decimal | None = None
    min_risk_reward: Decimal | None = None
    kill_switch_active: bool = False
    tradable_symbols: frozenset[str] = frozenset()
    max_freshness_seconds: int = 600
    market_hours_only: bool = True
    available_capital: Decimal | None = None
    current_exposure: Decimal = Decimal(0)
    daily_loss: Decimal = Decimal(0)
    instrument_max_qty: int | None = None


def risk_config_from_settings() -> RiskConfig:
    """Build a :class:`RiskConfig` from the ``RISK_MANAGEMENT`` settings dict."""
    from decimal import Decimal as D

    from django.conf import settings

    raw = getattr(settings, "RISK_MANAGEMENT", {}) or {}

    def dec(key: str) -> Decimal | None:
        value = raw.get(key)
        if value is None:
            return None
        return D(str(value))

    return RiskConfig(
        risk_pct=dec("risk_pct") or D("0.01"),
        max_position_size=int(raw.get("max_position_size", 1_000_000)),
        max_exposure_cap=dec("max_exposure_cap"),
        daily_loss_limit=dec("daily_loss_limit"),
        min_risk_reward=dec("min_risk_reward"),
        kill_switch_active=bool(raw.get("kill_switch_active", False)),
        tradable_symbols=frozenset(raw.get("tradable_symbols", [])),
        max_freshness_seconds=int(raw.get("max_freshness_seconds", 600)),
        market_hours_only=bool(raw.get("market_hours_only", True)),
        available_capital=dec("available_capital"),
        current_exposure=dec("current_exposure") or D(0),
        daily_loss=dec("daily_loss") or D(0),
        instrument_max_qty=(
            int(raw["instrument_max_qty"]) if raw.get("instrument_max_qty") is not None else None
        ),
    )
