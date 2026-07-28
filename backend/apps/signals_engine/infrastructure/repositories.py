from __future__ import annotations

import logging
import uuid
from typing import Any

from apps.signals_engine.infrastructure.models import Signal

logger = logging.getLogger(__name__)


class SignalRepository:
    def get_by_id(self, signal_id: uuid.UUID) -> Signal | None:
        try:
            return Signal.objects.get(id=signal_id)
        except Signal.DoesNotExist:
            return None

    def list(
        self,
        symbol: str | None = None,
        direction: str | None = None,
        offset: int = 0,
        limit: int = 20,
    ) -> list[Signal]:
        filters: dict[str, Any] = {}
        if symbol:
            filters["instrument_symbol"] = symbol
        if direction:
            filters["direction"] = direction
        return list(
            Signal.objects.filter(**filters)
            .select_for_update()
            .order_by("-created_at")[offset : offset + limit]
        )

    def count(self, **filters: Any) -> int:
        return Signal.objects.filter(**filters).count()

    def exists(self, signal_id: uuid.UUID) -> bool:
        return Signal.objects.filter(id=signal_id).exists()
