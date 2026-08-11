from __future__ import annotations

import threading
from decimal import Decimal

import pytest

from apps.watchlist.application.services import WatchlistService
from apps.watchlist.domain.exceptions import (
    InstrumentNotFoundError,
    WatchlistEntryNotFoundError,
)
from apps.watchlist.infrastructure.models import WatchlistEntry

pytestmark = pytest.mark.django_db


class TestAdd:
    def test_add_creates_entry(self, account, instrument) -> None:
        entry, created = WatchlistService().add(
            account.id, instrument.instrument_token, note="favorite"
        )

        assert created is True
        assert entry.account_id == account.id
        assert entry.instrument_id == instrument.instrument_token
        assert entry.note == "favorite"
        assert WatchlistEntry.objects.count() == 1

    def test_add_duplicate_returns_existing_not_created(
        self, account, instrument
    ) -> None:
        service = WatchlistService()
        first, created_first = service.add(account.id, instrument.instrument_token)
        second, created_second = service.add(account.id, instrument.instrument_token)

        assert created_first is True
        assert created_second is False
        assert second.id == first.id
        assert WatchlistEntry.objects.count() == 1

    def test_add_unknown_instrument_raises(self, account) -> None:
        with pytest.raises(InstrumentNotFoundError):
            WatchlistService().add(account.id, 99999999)

    def test_add_strips_control_characters(self, account, instrument) -> None:
        note = "line1\nline2\u0007BELL\x00NUL\tTAB"
        entry, _ = WatchlistService().add(account.id, instrument.instrument_token, note=note)

        assert "\u0007" not in entry.note
        assert "\x00" not in entry.note
        assert entry.note == "line1\nline2BELLNUL\tTAB"

    def test_add_note_capped_at_280(self, account, instrument) -> None:
        long_note = "x" * 500
        entry, _ = WatchlistService().add(account.id, instrument.instrument_token, note=long_note)

        assert len(entry.note) == 280

    def test_add_empty_note_default(self, account, instrument) -> None:
        entry, _ = WatchlistService().add(account.id, instrument.instrument_token)
        assert entry.note == ""


class TestConcurrency:
    @pytest.mark.django_db(transaction=True)
    def test_two_concurrent_adds_leave_one_row(self, account, instrument) -> None:
        from django.db import connections

        service = WatchlistService()
        barrier = threading.Barrier(2)
        results: list[tuple[object, bool]] = []

        def _worker() -> None:
            connections.close_all()
            barrier.wait()
            results.append(service.add(account.id, instrument.instrument_token))

        threads = [threading.Thread(target=_worker) for _ in range(2)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        assert WatchlistEntry.objects.filter(
            account_id=account.id,
            instrument_id=instrument.instrument_token,
        ).count() == 1
        assert sorted(created for _, created in results) == [False, True]


class TestRemove:
    def test_remove_deletes_entry(self, account, instrument) -> None:
        service = WatchlistService()
        service.add(account.id, instrument.instrument_token)

        removed = service.remove(account.id, instrument.instrument_token)

        assert removed is True
        assert WatchlistEntry.objects.count() == 0

    def test_remove_twice_returns_true_then_false(self, account, instrument) -> None:
        service = WatchlistService()
        service.add(account.id, instrument.instrument_token)

        assert service.remove(account.id, instrument.instrument_token) is True
        assert service.remove(account.id, instrument.instrument_token) is False


class TestList:
    def test_list_empty_for_unknown_account(self, account) -> None:
        assert WatchlistService().list(account.id) == []

    def test_list_returns_entries_ordered_by_sort_order(
        self, account, instruments
    ) -> None:
        service = WatchlistService()
        for inst in reversed(instruments):
            service.add(account.id, inst.instrument_token)

        entries = service.list(account.id)

        assert [e.instrument_id for e in entries] == [
            inst.instrument_token for inst in reversed(instruments)
        ]

    def test_list_scoped_to_account(self, account, secondary_account, instruments) -> None:
        service = WatchlistService()
        service.add(account.id, instruments[0].instrument_token)
        service.add(secondary_account.id, instruments[1].instrument_token)

        assert len(service.list(account.id)) == 1
        assert service.list(account.id)[0].instrument_id == instruments[0].instrument_token


class TestReorder:
    def test_reorder_updates_sort_order(self, account, instruments) -> None:
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)

        tokens = [inst.instrument_token for inst in instruments]
        reversed_tokens = list(reversed(tokens))
        service.reorder(account.id, reversed_tokens)

        entries = service.list(account.id)
        assert [e.instrument_id for e in entries] == reversed_tokens
        assert [e.sort_order for e in entries] == [0, 1, 2]

    @pytest.mark.django_db(transaction=True)
    def test_reorder_rolls_back_on_unknown_token(self, account, instruments) -> None:
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)

        tokens = [inst.instrument_token for inst in instruments]
        before = [(e.instrument_id, e.sort_order) for e in service.list(account.id)]

        with pytest.raises(WatchlistEntryNotFoundError):
            service.reorder(account.id, [tokens[2], 99999999, tokens[0]])

        after = [(e.instrument_id, e.sort_order) for e in service.list(account.id)]
        assert after == before

    def test_reorder_duplicate_tokens_rejected_at_api_only(self, account, instruments) -> None:
        service = WatchlistService()
        for inst in instruments:
            service.add(account.id, inst.instrument_token)

        tokens = [inst.instrument_token for inst in instruments]
        with pytest.raises(WatchlistEntryNotFoundError):
            service.reorder(account.id, [tokens[0], tokens[0], tokens[1]])

        assert len(service.list(account.id)) == 3
