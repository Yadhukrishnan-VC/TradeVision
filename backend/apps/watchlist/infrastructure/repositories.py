from __future__ import annotations

import uuid

from apps.market_data.infrastructure.models import Instrument
from apps.watchlist.infrastructure.models import WatchlistEntry


class WatchlistRepository:
    """Persistence for the per-account watchlist."""

    def create(
        self,
        *,
        account_id: uuid.UUID,
        instrument_token: int,
        note: str,
        sort_order: int,
    ) -> WatchlistEntry:
        return WatchlistEntry.objects.create(
            account_id=account_id,
            instrument_id=instrument_token,
            note=note,
            sort_order=sort_order,
        )

    def get(self, account_id: uuid.UUID, instrument_token: int) -> WatchlistEntry | None:
        return (
            WatchlistEntry.objects.filter(
                account_id=account_id,
                instrument_id=instrument_token,
            )
            .select_related("instrument")
            .first()
        )

    def delete(self, account_id: uuid.UUID, instrument_token: int) -> bool:
        deleted, _ = WatchlistEntry.objects.filter(
            account_id=account_id,
            instrument_id=instrument_token,
        ).delete()
        return deleted > 0

    def list_for_account(self, account_id: uuid.UUID) -> list[WatchlistEntry]:
        return list(
            WatchlistEntry.objects.filter(account_id=account_id)
            .select_related("instrument")
            .order_by("sort_order", "created_at")
        )

    def next_sort_order(self, account_id: uuid.UUID) -> int:
        last = (
            WatchlistEntry.objects.filter(account_id=account_id)
            .order_by("-sort_order", "-created_at")
            .first()
        )
        return (last.sort_order + 1) if last is not None else 0

    def update_sort_order(
        self, account_id: uuid.UUID, instrument_token: int, sort_order: int
    ) -> None:
        WatchlistEntry.objects.filter(
            account_id=account_id,
            instrument_id=instrument_token,
        ).update(sort_order=sort_order)

    def instrument_exists(self, instrument_token: int) -> bool:
        return Instrument.objects.filter(instrument_token=instrument_token).exists()
