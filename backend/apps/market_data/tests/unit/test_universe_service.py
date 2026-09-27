"""Tests for the NIFTY200 universe service and IndexConstituent model.

Covers the source-of-truth resolution order (IndexConstituent → env watchlist
bootstrap), upsert semantics (create/update/deactivate on re-sync), and the
rotating poll batch cursor that keeps a full NIFTY200 sweep within the Kite
historical rate limit.
"""

from __future__ import annotations

import pytest
from pytest import MonkeyPatch

from apps.market_data.application.universe_service import (
    resolve_universe,
    resolve_universe_symbols,
    upsert_constituents,
)
from apps.market_data.infrastructure.models import IndexConstituent


def _row(symbol: str, industry: str = "Financial Services", name: str = "") -> dict:
    return {
        "Company Name": name or f"{symbol} Ltd",
        "Industry": industry,
        "Symbol": symbol,
        "Series": "EQ",
        "ISIN Code": f"INF{symbol}",
    }


@pytest.mark.django_db
class TestIndexConstituentModel:
    def test_unique_together(self, db) -> None:
        IndexConstituent.objects.create(
            index_name="NIFTY200", exchange="NSE", tradingsymbol="RELIANCE"
        )
        with pytest.raises(Exception):  # IntegrityError
            IndexConstituent.objects.create(
                index_name="NIFTY200", exchange="NSE", tradingsymbol="RELIANCE"
            )

    def test_rows_are_sortable_and_scoped_by_index(self, db) -> None:
        IndexConstituent.objects.create(
            index_name="NIFTY50", exchange="NSE", tradingsymbol="RELIANCE", sort_order=0
        )
        IndexConstituent.objects.create(
            index_name="NIFTY200", exchange="NSE", tradingsymbol="HDFCBANK", sort_order=1
        )
        assert resolve_universe() == [("NSE", "HDFCBANK")]
        assert resolve_universe(index_name="NIFTY50") == [("NSE", "RELIANCE")]


@pytest.mark.django_db
class TestResolveUniverse:
    def test_env_watchlist_bootstrap_when_table_empty(self, settings) -> None:
        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE"), ("NSE", "TCS")]
        assert resolve_universe() == [("NSE", "RELIANCE"), ("NSE", "TCS")]
        assert resolve_universe_symbols() == ["RELIANCE", "TCS"]

    def test_empty_everywhere(self, settings) -> None:
        settings.MARKET_DATA_POLL_WATCHLIST = []
        assert resolve_universe() == []
        assert resolve_universe_symbols() == []

    def test_table_is_authoritative(self, settings) -> None:
        # Even with an env watchlist present, populated constituents win.
        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE")]
        upsert_constituents([_row("HDFCBANK"), _row("INFY")])
        assert resolve_universe() == [("NSE", "HDFCBANK"), ("NSE", "INFY")]

    def test_inactive_rows_excluded(self, db) -> None:
        upsert_constituents([_row("HDFCBANK"), _row("INFY")])
        IndexConstituent.objects.filter(tradingsymbol="INFY").update(is_active=False)
        assert resolve_universe_symbols() == ["HDFCBANK"]


@pytest.mark.django_db
class TestUpsertConstituents:
    def test_create_then_resync_updates_and_deactivates(self, db) -> None:
        first = upsert_constituents([_row("RELIANCE"), _row("TCS"), _row("INFY")])
        assert first == {"created": 3, "updated": 0, "deactivated": 0}

        # INFY dropped from the index, RELIANCE industry changed.
        second = upsert_constituents(
            [
                _row("RELIANCE", industry="Oil Gas & Consumable Fuels"),
                _row("TCS", industry="Information Technology"),
            ]
        )
        assert second["created"] == 0
        assert second["updated"] == 2
        assert second["deactivated"] == 1

        assert resolve_universe_symbols() == ["RELIANCE", "TCS"]
        assert (
            IndexConstituent.objects.get(tradingsymbol="RELIANCE").industry
            == "Oil Gas & Consumable Fuels"
        )
        assert (
            IndexConstituent.objects.get(tradingsymbol="INFY").is_active is False
        )

    def test_order_follows_csv(self, db) -> None:
        upsert_constituents([_row("B"), _row("A"), _row("C")])
        assert resolve_universe_symbols() == ["B", "A", "C"]

    def test_skips_blank_symbol_rows(self, db) -> None:
        result = upsert_constituents([{"Symbol": ""}, _row("RELIANCE")])
        assert result == {"created": 1, "updated": 0, "deactivated": 0}
        assert resolve_universe_symbols() == ["RELIANCE"]


class TestPollRatePacing:
    """The token-bucket pacing helper honours the configured cap."""

    def test_zero_rate_is_noop(self, monkeypatch: MonkeyPatch, settings) -> None:
        """rate <= 0 → pacing disabled (polling never stalls)."""
        from apps.market_data.infrastructure import polling_tasks

        settings.MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND = 0
        calls: list[str] = []

        def _fake_acquire() -> bool:
            calls.append("acquire")
            return True

        monkeypatch.setattr(
            polling_tasks, "_poll_rate_limiter", type("L", (), {"acquire": _fake_acquire})()
        )
        polling_tasks._pace_rate_limit()
        assert calls == []

    def test_pacing_acquires_slot(self, monkeypatch: MonkeyPatch, settings) -> None:
        from apps.market_data.infrastructure import polling_tasks

        settings.MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND = 3.0
        calls: list[str] = []

        class _Limiter:
            def acquire(self) -> bool:
                calls.append("acquire")
                return True

        monkeypatch.setattr(
            polling_tasks, "_poll_rate_limiter", _Limiter()
        )
        polling_tasks._pace_rate_limit()
        assert calls == ["acquire"]

    def test_redis_error_fails_open(self, monkeypatch: MonkeyPatch, settings) -> None:
        import redis

        from apps.market_data.infrastructure import polling_tasks

        settings.MARKET_DATA_POLL_RATE_LIMIT_PER_SECOND = 3.0

        def _boom(selfx) -> bool:
            raise redis.RedisError("redis down")

        monkeypatch.setattr(
            polling_tasks, "_poll_rate_limiter", type("L", (), {"acquire": _boom})()
        )
        # Must not raise.
        polling_tasks._pace_rate_limit()


@pytest.mark.django_db
class TestPollBatchResolution:
    def test_empty_universe_returns_empty(self, settings, monkeypatch: MonkeyPatch) -> None:
        from apps.market_data.infrastructure import polling_tasks

        settings.MARKET_DATA_POLL_WATCHLIST = []
        monkeypatch.setattr(
            polling_tasks, "_universe_cursor", lambda _c: 0
        )
        assert polling_tasks._resolve_poll_batch() == []

    def test_no_batching_when_smaller_than_universe(
        self, settings, monkeypatch: MonkeyPatch
    ) -> None:
        from apps.market_data.infrastructure import polling_tasks

        settings.MARKET_DATA_POLL_WATCHLIST = [("NSE", "RELIANCE")]
        settings.MARKET_DATA_POLL_BATCH_SIZE = 30
        monkeypatch.setattr(
            polling_tasks, "_universe_cursor", lambda _c: 0
        )
        assert polling_tasks._resolve_poll_batch() == [("NSE", "RELIANCE")]

    def test_rotating_batches_cover_full_universe(
        self, db, settings, monkeypatch: MonkeyPatch
    ) -> None:
        from apps.market_data.infrastructure import polling_tasks

        upsert_constituents([_row(f"SYM{i}") for i in range(10)])
        settings.MARKET_DATA_POLL_BATCH_SIZE = 3
        advance_calls: list[int] = []

        cursor = {"value": 0}

        def _fake_cursor(_c):
            return cursor["value"]

        def _fake_advance(_c, offset, mod):
            advance_calls.append(offset)
            cursor["value"] = offset % mod

        monkeypatch.setattr(polling_tasks, "_universe_cursor", _fake_cursor)
        monkeypatch.setattr(polling_tasks, "_advance_universe_cursor", _fake_advance)

        batches = [
            [s for (_e, s) in polling_tasks._resolve_poll_batch()]
            for _ in range(6)
        ]
        all_seen = [s for b in batches for s in b]
        assert len(batches[0]) == 3
        # Over 6 cycles every symbol appears at least once.
        assert set(all_seen) == {f"SYM{i}" for i in range(10)}
        # Cursor advanced by batch size each time (rotating).
        assert advance_calls == [3, 6, 9, 2, 5, 8]