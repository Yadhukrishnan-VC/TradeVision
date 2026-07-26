from __future__ import annotations

from uuid import UUID

from apps.dashboard.application.trading_core.dto import PositionSnapshotDTO, TradeRecordDTO
from apps.dashboard.application.trading_core.services.live_positions_service import (
    LivePositionsService,
)
from apps.dashboard.application.trading_core.services.trade_history_service import (
    TradeHistoryService,
)


class OpenTradesService:
    def __init__(
        self,
        live_positions_service: LivePositionsService | None = None,
    ) -> None:
        self._live_positions = live_positions_service or LivePositionsService()

    def list_open(self, account_id: UUID, filters: dict | None = None) -> list[PositionSnapshotDTO]:
        return self._live_positions.list_open(account_id, filters)


class ClosedTradesService:
    def __init__(
        self,
        trade_history_service: TradeHistoryService | None = None,
    ) -> None:
        self._trade_history = trade_history_service or TradeHistoryService()

    def list_closed(self, account_id: UUID, filters: dict | None = None) -> list[TradeRecordDTO]:
        combined_filters = dict(filters or {})
        combined_filters["closed_at__isnull"] = False
        return self._trade_history.list(account_id, combined_filters)
