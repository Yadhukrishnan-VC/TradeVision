from __future__ import annotations

from uuid import UUID

from apps.dashboard.application.trading_core.dto import OrderSnapshotDTO
from apps.dashboard.infrastructure.trading_core.repositories import OrderSnapshotRepository


class OrdersService:
    def __init__(
        self,
        repository: OrderSnapshotRepository | None = None,
    ) -> None:
        self._repository = repository or OrderSnapshotRepository()

    def list(self, account_id: UUID, filters: dict | None = None) -> list[OrderSnapshotDTO]:
        if filters:
            qs = self._repository.filter_all(account_id, **filters)
        else:
            qs = self._repository.list_all(account_id)
        return [self._to_dto(order) for order in qs]

    def get(self, account_id: UUID, order_id: UUID) -> OrderSnapshotDTO:
        order = self._repository.get(account_id, order_id)
        return self._to_dto(order)

    @staticmethod
    def _to_dto(order: object) -> OrderSnapshotDTO:
        return OrderSnapshotDTO(
            order_id=order.order_id,
            account_id=order.account_id,
            symbol=order.symbol,
            side=order.side,
            order_type=order.order_type,
            status=order.status,
            quantity=order.quantity,
            filled_quantity=order.filled_quantity,
            avg_fill_price=order.avg_fill_price,
            limit_price=order.limit_price,
            placed_at=order.placed_at,
        )
