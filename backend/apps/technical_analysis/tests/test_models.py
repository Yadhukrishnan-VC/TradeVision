from __future__ import annotations

import uuid
from datetime import datetime, timezone

import pytest

from apps.technical_analysis.domain.entities import TASnapshot
from apps.technical_analysis.domain.value_objects import PineMetadata
from apps.technical_analysis.infrastructure.models import TASnapshot as TASnapshotModel
from apps.technical_analysis.infrastructure.repositories import TASnapshotRepository


class TestTASnapshotModel:
    def test_create_and_retrieve(self, db) -> None:
        snapshot = TASnapshotModel.objects.create(
            id=uuid.uuid4(),
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="15min",
            pine_id="script_v1",
            pine_version="5",
            pine_timestamp=1699000000000,
            indicators={"rsi": 62.5, "sma_20": 2830.0},
            raw_payload={"ticker": "RELIANCE", "close": 2850.50},
            snapshot_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        )

        fetched = TASnapshotModel.objects.get(pk=snapshot.id)
        assert fetched.symbol == "RELIANCE"
        assert fetched.exchange == "NSE"
        assert fetched.indicators["rsi"] == 62.5
        assert fetched.pine_id == "script_v1"

    def test_defaults(self, db) -> None:
        snapshot = TASnapshotModel.objects.create(
            id=uuid.uuid4(),
            symbol="TCS",
            snapshot_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        )

        assert snapshot.exchange == ""
        assert snapshot.timeframe == ""
        assert snapshot.indicators == {}
        assert snapshot.raw_payload == {}

    def test_str_representation(self, db) -> None:
        ts = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        snapshot = TASnapshotModel.objects.create(
            id=uuid.uuid4(),
            symbol="INFY",
            snapshot_timestamp=ts,
        )
        assert "INFY" in str(snapshot)

    def test_ordering(self, db) -> None:
        ts1 = datetime(2026, 7, 28, 9, 0, 0, tzinfo=timezone.utc)
        ts2 = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)

        s1 = TASnapshotModel.objects.create(
            id=uuid.uuid4(), symbol="TEST", snapshot_timestamp=ts1
        )
        s2 = TASnapshotModel.objects.create(
            id=uuid.uuid4(), symbol="TEST", snapshot_timestamp=ts2
        )

        qs = TASnapshotModel.objects.all()
        assert list(qs) == [s2, s1]


class TestTASnapshotRepository:
    def test_save_and_retrieve_domain_entity(self, db) -> None:
        repo = TASnapshotRepository()
        entity = TASnapshot(
            symbol="RELIANCE",
            exchange="NSE",
            timeframe="15min",
            indicators={"rsi": 62.5},
            pine_metadata=PineMetadata(
                pine_id="script_v1",
                pine_version="5",
                pine_timestamp=1699000000000,
            ),
            raw_payload={"ticker": "RELIANCE", "close": 2850.50},
            snapshot_timestamp=datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc),
        )

        persisted = repo.save(entity)

        assert persisted.id == entity.id
        assert persisted.symbol == "RELIANCE"
        assert persisted.exchange == "NSE"
        assert persisted.pine_metadata.pine_id == "script_v1"

    def _make_snapshot(
        self, symbol: str = "TEST", ts=None
    ) -> TASnapshot:
        if ts is None:
            ts = datetime(2026, 7, 28, 10, 0, 0, tzinfo=timezone.utc)
        return TASnapshot(
            symbol=symbol,
            exchange="",
            timeframe="",
            indicators={},
            pine_metadata=PineMetadata(),
            raw_payload={},
            snapshot_timestamp=ts,
        )

    def test_find_by_symbol(self, db) -> None:
        repo = TASnapshotRepository()

        repo.save(self._make_snapshot(symbol="RELIANCE"))

        results = repo.find_by_symbol("RELIANCE")
        assert len(results) == 1
        assert results[0].symbol == "RELIANCE"

    def test_find_by_symbol_case_insensitive(self, db) -> None:
        repo = TASnapshotRepository()

        repo.save(self._make_snapshot(symbol="RELIANCE"))

        results = repo.find_by_symbol("reliance")
        assert len(results) == 1

    def test_find_by_id(self, db) -> None:
        repo = TASnapshotRepository()
        entity = self._make_snapshot(symbol="TCS")
        repo.save(entity)

        found = repo.find_by_id(str(entity.id))
        assert found is not None
        assert found.symbol == "TCS"

    def test_find_by_id_not_found(self, db) -> None:
        repo = TASnapshotRepository()
        result = repo.find_by_id(str(uuid.uuid4()))
        assert result is None

    def test_count_by_symbol(self, db) -> None:
        repo = TASnapshotRepository()

        repo.save(self._make_snapshot(symbol="RELIANCE"))
        repo.save(self._make_snapshot(symbol="RELIANCE"))

        assert repo.count_by_symbol("RELIANCE") == 2
        assert repo.count_by_symbol("TCS") == 0
