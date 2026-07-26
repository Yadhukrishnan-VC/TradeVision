from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from apps.dashboard.application.trading_core.dto import HoldingDTO, PortfolioCompositionDTO
from apps.dashboard.infrastructure.trading_core.cache import LatestPriceCache
from apps.dashboard.infrastructure.trading_core.repositories import HoldingRepository


class PortfolioService:
    def __init__(
        self,
        repository: HoldingRepository | None = None,
        price_cache: LatestPriceCache | None = None,
    ) -> None:
        self._repository = repository or HoldingRepository()
        self._price_cache = price_cache or LatestPriceCache()

    def get_composition(self, account_id: UUID) -> PortfolioCompositionDTO:
        holdings = self._repository.list_active(account_id)
        holding_dtos: list[HoldingDTO] = []
        total_market_value = Decimal("0")
        total_cost_basis = Decimal("0")

        for h in holdings:
            current_price = self._price_cache.get_price(h.symbol)
            market_value = (h.quantity * current_price) if current_price else None
            unrealized_pnl = (market_value - h.cost_basis) if market_value else None
            allocation_pct = Decimal("0")

            if current_price:
                total_market_value += market_value
            total_cost_basis += h.cost_basis

            holding_dtos.append(
                HoldingDTO(
                    account_id=h.account_id,
                    symbol=h.symbol,
                    quantity=h.quantity,
                    avg_cost=h.avg_cost,
                    cost_basis=h.cost_basis,
                    market_value=market_value,
                    allocation_pct=allocation_pct,
                    unrealized_pnl=unrealized_pnl,
                    opened_at=h.opened_at,
                )
            )

        if total_market_value > 0:
            for i, h_dto in enumerate(holding_dtos):
                if h_dto.market_value:
                    holding_dtos[i] = HoldingDTO(
                        account_id=h_dto.account_id,
                        symbol=h_dto.symbol,
                        quantity=h_dto.quantity,
                        avg_cost=h_dto.avg_cost,
                        cost_basis=h_dto.cost_basis,
                        market_value=h_dto.market_value,
                        allocation_pct=(h_dto.market_value / total_market_value) * Decimal("100"),
                        unrealized_pnl=h_dto.unrealized_pnl,
                        opened_at=h_dto.opened_at,
                    )

        return PortfolioCompositionDTO(
            account_id=account_id,
            holdings=holding_dtos,
            total_market_value=total_market_value,
            total_cost_basis=total_cost_basis,
            cash_balance=Decimal("0"),
        )

    def get_holding_detail(self, account_id: UUID, symbol: str) -> HoldingDTO:
        holding = self._repository.get(account_id, symbol)
        current_price = self._price_cache.get_price(holding.symbol)
        market_value = (holding.quantity * current_price) if current_price else None
        unrealized_pnl = (market_value - holding.cost_basis) if market_value else None

        return HoldingDTO(
            account_id=holding.account_id,
            symbol=holding.symbol,
            quantity=holding.quantity,
            avg_cost=holding.avg_cost,
            cost_basis=holding.cost_basis,
            market_value=market_value,
            allocation_pct=None,
            unrealized_pnl=unrealized_pnl,
            opened_at=holding.opened_at,
        )
