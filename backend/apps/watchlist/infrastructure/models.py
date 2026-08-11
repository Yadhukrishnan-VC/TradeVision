from __future__ import annotations

import uuid

from django.db import models

from apps.common.infrastructure.model_mixins import TimestampedModel


class WatchlistEntry(TimestampedModel):
    """A single instrument tracked on one account's watchlist.

    Constraints:
        - ``unique_together (account, instrument)`` — the same instrument
          cannot appear twice on one account's watchlist (WATCH-1 section L).
        - Index on ``(account, sort_order)`` for ordered listing.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    account = models.ForeignKey(
        "accounts.Account",
        on_delete=models.CASCADE,
        related_name="watchlist_entries",
        help_text="The account that owns this watchlist entry.",
    )
    instrument = models.ForeignKey(
        "market_data.Instrument",
        on_delete=models.CASCADE,
        related_name="watchlist_entries",
        help_text="The instrument tracked on the watchlist.",
    )
    note = models.CharField(
        max_length=280,
        blank=True,
        default="",
        help_text="Optional user note (control characters stripped).",
    )
    sort_order = models.IntegerField(
        default=0,
        help_text="Display order within the account's watchlist.",
    )

    class Meta:
        app_label = "watchlist"
        db_table = "watchlist_watchlistentry"
        verbose_name = "Watchlist Entry"
        verbose_name_plural = "Watchlist Entries"
        unique_together = [("account", "instrument")]
        indexes = [
            models.Index(fields=["account", "sort_order"], name="idx_watchlist_account_sort"),
        ]

    def __str__(self) -> str:
        return f"Watchlist({self.account_id}, {self.instrument_id})"
