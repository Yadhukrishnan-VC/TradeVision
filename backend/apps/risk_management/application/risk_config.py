from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal

from apps.risk_management.domain.value_objects import PortfolioPosition


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
    max_sector_exposure_pct: Decimal | None = None
    correlated_trigger_max_multiple: Decimal | None = None
    sector_by_symbol: dict[str, str] = field(default_factory=dict)
    portfolio_positions: tuple[PortfolioPosition, ...] = ()
    max_daily_loss_pct: Decimal | None = None
    max_weekly_loss_pct: Decimal | None = None
    weekly_loss: Decimal = Decimal(0)


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
        max_sector_exposure_pct=dec("max_sector_exposure_pct"),
        correlated_trigger_max_multiple=dec("correlated_trigger_max_multiple"),
        sector_by_symbol=dict(raw.get("sector_by_symbol", {}) or {}),
        portfolio_positions=tuple(
            PortfolioPosition(
                symbol=str(item["symbol"]),
                sector=item.get("sector"),
                notional=D(str(item.get("notional", "0"))),
                trigger_rule=item.get("trigger_rule"),
            )
            for item in (raw.get("portfolio_positions", []) or [])
        ),
        max_daily_loss_pct=dec("max_daily_loss_pct"),
        max_weekly_loss_pct=dec("max_weekly_loss_pct"),
        weekly_loss=dec("weekly_loss") or D(0),
    )
