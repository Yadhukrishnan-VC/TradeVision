from __future__ import annotations

import uuid
from typing import Any

from django.db import IntegrityError, transaction

from apps.watchlist.domain.exceptions import (
    InstrumentNotFoundError,
    WatchlistEntryNotFoundError,
)
from apps.watchlist.domain.value_objects import WatchlistNote
from apps.watchlist.infrastructure.models import WatchlistEntry
from apps.watchlist.infrastructure.repositories import WatchlistRepository
from core.services import BaseService


class WatchlistService(BaseService):
    """Application service for per-account instrument watchlists.

    All mutations are idempotent where the batch demands it:
        - ``add`` is safe to retry — a duplicate ``(account, instrument)``
          returns the existing row instead of raising.
        - ``remove`` returns whether an entry was actually deleted.
        - ``reorder`` is atomic: an unknown token aborts the whole reorder.
    """

    def __init__(self, repository: WatchlistRepository | None = None) -> None:
        super().__init__()
        self._repository = repository or WatchlistRepository()

    def add(
        self,
        account_id: uuid.UUID,
        instrument_token: int,
        note: str = "",
    ) -> tuple[WatchlistEntry, bool]:
        """Add *instrument_token* to the account's watchlist.

        Returns a ``(entry, created)`` pair. When the instrument is already
        tracked the existing row is returned with ``created=False`` (the
        unique ``(account, instrument)`` constraint is the source of truth;
        a pre-check-then-insert is deliberately avoided so concurrent adds
        stay race-free).
        """
        if not self._repository.instrument_exists(instrument_token):
            raise InstrumentNotFoundError(
                message=f"Instrument {instrument_token} not found",
                code="INSTRUMENT_NOT_FOUND",
                details={"instrument_token": instrument_token},
            )

        note_text = WatchlistNote(note).value
        next_sort_order = self._repository.next_sort_order(account_id)
        try:
            with transaction.atomic():
                entry = self._repository.create(
                    account_id=account_id,
                    instrument_token=instrument_token,
                    note=note_text,
                    sort_order=next_sort_order,
                )
        except IntegrityError:
            existing = self._repository.get(account_id, instrument_token)
            if existing is None:
                raise
            return existing, False
        return entry, True

    def remove(self, account_id: uuid.UUID, instrument_token: int) -> bool:
        """Remove *instrument_token* from the account's watchlist.

        Returns ``True`` when an entry was deleted, ``False`` when there was
        nothing to remove (idempotent — removing twice yields ``True`` then
        ``False``).
        """
        return self._repository.delete(account_id, instrument_token)

    def list(self, account_id: uuid.UUID) -> list[WatchlistEntry]:
        """Return the account's watchlist ordered by ``sort_order`` then ``created_at``."""
        return self._repository.list_for_account(account_id)

    def reorder(self, account_id: uuid.UUID, ordered_tokens: list[int]) -> None:
        """Apply a new display order to the account's watchlist.

        Atomic: if any token is not on the account's watchlist the whole
        reorder is rolled back and :class:`WatchlistEntryNotFoundError` is
        raised. Tokens already present keep their relative order implicitly
        by position.
        """
        with transaction.atomic():
            current = {
                entry.instrument_id: entry
                for entry in self._repository.list_for_account(account_id)
            }
            if set(ordered_tokens) != set(current):
                missing = set(ordered_tokens) - set(current)
                raise WatchlistEntryNotFoundError(
                    message=(
                        "Reorder aborted: entries not on this account's "
                        f"watchlist: {sorted(missing)}"
                    ),
                    code="WATCHLIST_ENTRY_NOT_FOUND",
                    details={"missing_tokens": sorted(missing)},
                )
            for position, token in enumerate(ordered_tokens):
                self._repository.update_sort_order(account_id, token, position)
