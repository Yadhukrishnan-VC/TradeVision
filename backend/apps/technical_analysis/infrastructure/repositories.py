from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from apps.technical_analysis.domain.entities import TASnapshot
from apps.technical_analysis.domain.value_objects import PineMetadata
from apps.technical_analysis.infrastructure.models import TASnapshot as TASnapshotModel

logger = logging.getLogger(__name__)


class TASnapshotRepository:
    """Repository for ``TASnapshot`` domain entities backed by the ORM model."""

    def save(self, snapshot: TASnapshot) -> TASnapshot:
        """Persist a new technical analysis snapshot.

        Args:
            snapshot: The domain entity to persist.

        Returns:
            The persisted domain entity.
        """
        obj = TASnapshotModel.objects.create(
            id=snapshot.id,
            symbol=snapshot.symbol,
            exchange=snapshot.exchange,
            timeframe=snapshot.timeframe,
            pine_id=snapshot.pine_metadata.pine_id,
            pine_version=snapshot.pine_metadata.pine_version,
            pine_timestamp=snapshot.pine_metadata.pine_timestamp,
            indicators=snapshot.indicators,
            raw_payload=snapshot.raw_payload,
            snapshot_timestamp=snapshot.snapshot_timestamp,
        )
        return self._to_domain(obj)

    def find_by_symbol(
        self,
        symbol: str,
        limit: int = 100,
    ) -> list[TASnapshot]:
        """Return the most recent snapshots for a given symbol."""
        qs = (
            TASnapshotModel.objects.filter(symbol=symbol.upper())
            .only(
                "id",
                "symbol",
                "exchange",
                "timeframe",
                "pine_id",
                "pine_version",
                "pine_timestamp",
                "indicators",
                "snapshot_timestamp",
                "received_at",
            )
            .order_by("-snapshot_timestamp")[:limit]
        )
        return [self._to_domain(obj) for obj in qs]

    def find_by_id(self, snapshot_id: str) -> TASnapshot | None:
        """Look up a snapshot by its UUID."""
        try:
            obj = TASnapshotModel.objects.get(pk=snapshot_id)
            return self._to_domain(obj)
        except TASnapshotModel.DoesNotExist:
            return None

    def find_in_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        timeframe: str | None = None,
    ) -> list[TASnapshot]:
        """Return historical snapshots for a symbol ordered chronologically.

        Read-only range query used by backtest replay. ``start``/``end`` are
        inclusive on ``snapshot_timestamp``; an optional ``timeframe`` narrows
        the range to the run's chart timeframe.
        """
        qs = TASnapshotModel.objects.filter(
            symbol=symbol.upper(),
            snapshot_timestamp__gte=start,
            snapshot_timestamp__lte=end,
        )
        if timeframe:
            qs = qs.filter(timeframe=timeframe)
        qs = qs.order_by("snapshot_timestamp")
        return [self._to_domain(obj) for obj in qs]

    def count_by_symbol(self, symbol: str) -> int:
        """Return the number of snapshots for a given symbol."""
        return TASnapshotModel.objects.filter(symbol=symbol.upper()).count()

    @staticmethod
    def _to_domain(obj: TASnapshotModel) -> TASnapshot:
        return TASnapshot(
            id=obj.id,
            symbol=obj.symbol,
            exchange=obj.exchange,
            timeframe=obj.timeframe,
            indicators=obj.indicators,
            pine_metadata=PineMetadata(
                pine_id=obj.pine_id,
                pine_version=obj.pine_version,
                pine_timestamp=obj.pine_timestamp,
            ),
            raw_payload=obj.raw_payload,
            snapshot_timestamp=obj.snapshot_timestamp,
            received_at=obj.received_at,
        )


class DistinctTASnapshotRepository(TASnapshotRepository):
    """``TASnapshotRepository`` whose range reads return one row per timestamp.

    ``TASnapshot`` has no DB uniqueness on ``(symbol, snapshot_timestamp)``, so
    repeated historical ingestion (e.g. the backtest runner re-ingesting the
    same payload every run) can pile up duplicate rows that ``find_in_range``
    would otherwise replay over and over, compounding runtime. This subclass
    keeps the same contract (chronological, inclusive range) but collapses
    duplicates via ``DISTINCT ON (snapshot_timestamp)`` so replays stay O(N)
    regardless of how many duplicate rows accumulate.

    Read-only override: ``save`` and everything else behave identically to the
    base repository, so this is safe to inject anywhere the base is accepted.
    """

    def find_in_range(
        self,
        symbol: str,
        start: datetime,
        end: datetime,
        *,
        timeframe: str | None = None,
    ) -> list[TASnapshot]:
        qs = TASnapshotModel.objects.filter(
            symbol=symbol.upper(),
            snapshot_timestamp__gte=start,
            snapshot_timestamp__lte=end,
        )
        if timeframe:
            qs = qs.filter(timeframe=timeframe)
        qs = (
            qs.order_by("snapshot_timestamp")
            .distinct("snapshot_timestamp")
        )
        return [self._to_domain(obj) for obj in qs]
