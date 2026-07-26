from __future__ import annotations

from decimal import Decimal
from uuid import UUID

from apps.dashboard.application.trading_core.dto import PositionSnapshotDTO
from apps.dashboard.infrastructure.trading_core.cache import LatestPriceCache
from apps.dashboard.infrastructure.trading_core.repositories import PositionSnapshotRepository


class LivePositionsService:
    def __init__(
        self,
        repository: PositionSnapshotRepository | None = None,
        price_cache: LatestPriceCache | None = None,
    ) -> None:
        self._repository = repository or PositionSnapshotRepository()
        self._price_cache = price_cache or LatestPriceCache()

    def list_open(
        self, account_id: UUID, filters: dict | None = None
    ) -> list[PositionSnapshotDTO]:
        if filters:
            qs = self._repository.filter_open(account_id, **filters)
        else:
            qs = self._repository.list_open(account_id)
        return [self.to_dto(pos) for pos in qs]

    def get(self, account_id: UUID, position_id: UUID) -> PositionSnapshotDTO:
        position = self._repository.get(account_id, position_id)
        return self.to_dto(position)

    def to_dto(self, position: object) -> PositionSnapshotDTO:
        current_price = self._price_cache.get_price(position.symbol)
        unrealized_pnl: Decimal | None = None
        unrealized_pnl_pct: Decimal | None = None

        if current_price:
            if position.side == "LONG":
                unrealized_pnl = (current_price - position.entry_price) * position.quantity
            else:
                unrealized_pnl = (position.entry_price - current_price) * position.quantity

            if position.entry_price > 0:
                if position.side == "LONG":
                    unrealized_pnl_pct = (
                        (current_price - position.entry_price) / position.entry_price
                    ) * Decimal("100")
                else:
                    unrealized_pnl_pct = (
                        (position.entry_price - current_price) / position.entry_price
                    ) * Decimal("100")

        return PositionSnapshotDTO(
            position_id=position.position_id,
            account_id=position.account_id,
            symbol=position.symbol,
            side=position.side,
            quantity=position.quantity,
            entry_price=position.entry_price,
            current_price=current_price,
            unrealized_pnl=unrealized_pnl,
            unrealized_pnl_pct=unrealized_pnl_pct,
            is_open=position.is_open,
            opened_at=position.opened_at,
            closed_at=position.closed_at,
        )
