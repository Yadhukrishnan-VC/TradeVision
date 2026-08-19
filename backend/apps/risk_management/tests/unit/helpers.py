from __future__ import annotations

import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from apps.risk_management.application.risk_config import RiskConfig


def make_payload(
    *,
    symbol: str = "RELIANCE",
    rule_id: str = "long_momentum_v1",
    event_type: str = "BREAKOUT",
    entry_price: str | None = "103.00",
    stop_loss: str | None = "101.00",
    target_price: str | None = "110.00",
    direction: str | None = "long",
    occurred_at: datetime | None = None,
) -> dict:
    trigger_data: dict = {}
    if entry_price is not None:
        trigger_data["entry_price"] = entry_price
    if stop_loss is not None:
        trigger_data["stop_loss"] = stop_loss
    if target_price is not None:
        trigger_data["target_price"] = target_price
    if direction is not None:
        trigger_data["direction"] = direction
    return {
        "symbol": symbol,
        "rule_id": rule_id,
        "event_type": event_type,
        "trigger_data": trigger_data,
        "analysis_event_id": str(uuid.uuid4()),
        "occurred_at": (occurred_at or datetime.now(timezone.utc)).isoformat(),
    }


@dataclass
class FakeCapitalGateway:
    available_capital: Decimal | None = Decimal(1000000)
    max_position_size: int = 1_000_000

    def get_available_capital(self) -> Decimal | None:
        return self.available_capital

    def get_max_position_size(self) -> int:
        return self.max_position_size


@dataclass
class FakePortfolioGateway:
    implementation_name: str = "stub"
    current_exposure: Decimal = Decimal(0)
    daily_loss: Decimal = Decimal(0)
    instrument_max_qty: int | None = None
    tradable_symbols: frozenset[str] = frozenset()
    portfolio_positions: tuple = ()
    sector_by_symbol: dict[str, str] = None  # type: ignore[assignment]
    weekly_loss: Decimal = Decimal(0)

    def get_current_exposure(self) -> Decimal:
        return self.current_exposure

    def get_daily_loss(self) -> Decimal:
        return self.daily_loss

    def get_weekly_loss(self) -> Decimal:
        return self.weekly_loss

    def get_instrument_max_qty(self, symbol: str) -> int | None:
        return self.instrument_max_qty

    def get_tradable_symbols(self) -> frozenset[str]:
        return self.tradable_symbols

    def get_portfolio_positions(self) -> tuple:
        return self.portfolio_positions

    def get_instrument_sector(self, symbol: str) -> str | None:
        if not self.sector_by_symbol:
            return None
        return self.sector_by_symbol.get(symbol)


@dataclass
class FakeMarketGateway:
    is_open: bool = True
    freshness: bool = True

    def is_market_open(self, reference_dt: datetime) -> bool:
        return self.is_open

    def is_fresh(self, occurred_at: datetime, reference_dt: datetime) -> bool:
        return self.freshness


class FakeKillSwitchService:
    """In-memory kill-switch service for service-level tests."""

    def __init__(self, blocked: bool = False) -> None:
        self.blocked = blocked

    def is_trade_blocked(self, symbol: str) -> bool:
        return self.blocked


def build_service(
    *,
    config: RiskConfig | None = None,
    capital: FakeCapitalGateway | None = None,
    portfolio: FakePortfolioGateway | None = None,
    market: FakeMarketGateway | None = None,
    kill_switch: FakeKillSwitchService | None = None,
):
    from apps.risk_management.application.risk_evaluation_service import (
        RiskEvaluationService,
    )

    return RiskEvaluationService(
        capital_gateway=capital or FakeCapitalGateway(),
        portfolio_gateway=portfolio or FakePortfolioGateway(),
        market_gateway=market or FakeMarketGateway(),
        kill_switch_service=kill_switch,
        config=config,
    )
