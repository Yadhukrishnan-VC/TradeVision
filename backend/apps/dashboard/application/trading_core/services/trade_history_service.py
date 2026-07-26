from __future__ import annotations

from uuid import UUID

from apps.dashboard.application.trading_core.dto import TradeRecordDTO
from apps.dashboard.infrastructure.trading_core.repositories import TradeRecordRepository


class TradeHistoryService:
    def __init__(
        self,
        repository: TradeRecordRepository | None = None,
    ) -> None:
        self._repository = repository or TradeRecordRepository()

    def list(self, account_id: UUID, filters: dict | None = None) -> list[TradeRecordDTO]:
        if filters:
            qs = self._repository.filter_all(account_id, **filters)
        else:
            qs = self._repository.list_all(account_id)
        return [self._to_dto(trade) for trade in qs]

    @staticmethod
    def _to_dto(trade: object) -> TradeRecordDTO:
        return TradeRecordDTO(
            trade_id=trade.trade_id,
            account_id=trade.account_id,
            symbol=trade.symbol,
            side=trade.side,
            entry_price=trade.entry_price,
            exit_price=trade.exit_price,
            quantity=trade.quantity,
            realized_pnl=trade.realized_pnl,
            realized_pnl_pct=trade.realized_pnl_pct,
            opened_at=trade.opened_at,
            closed_at=trade.closed_at,
            holding_period_seconds=trade.holding_period_seconds,
        )
