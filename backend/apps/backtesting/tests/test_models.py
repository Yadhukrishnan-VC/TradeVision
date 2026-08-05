"""BacktestRun model + repository lifecycle tests."""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from apps.backtesting.models import BacktestRun, BacktestRunStatus
from apps.backtesting.repository import BacktestRunRepository

pytestmark = pytest.mark.django_db


def _make_run(account) -> BacktestRun:
    return BacktestRun(
        symbol="RELIANCE",
        timeframe="1D",
        range_start=datetime(2024, 6, 9, tzinfo=timezone.utc),
        range_end=datetime(2024, 6, 11, tzinfo=timezone.utc),
        account=account,
        status=BacktestRunStatus.PENDING,
    )


def test_default_status_is_pending(backtest_run) -> None:
    assert backtest_run.status == BacktestRunStatus.PENDING
    assert backtest_run.failure_reason == ""
    assert backtest_run.last_processed_snapshot_id is None
    assert backtest_run.started_at is None
    assert backtest_run.completed_at is None


def test_str_contains_status_and_symbol(backtest_run) -> None:
    rendered = str(backtest_run)
    assert "BacktestRun" in rendered
    assert "PENDING" in rendered
    assert "RELIANCE" in rendered


def test_run_bound_to_dedicated_account(funded_account) -> None:
    run = _make_run(funded_account)
    run.full_clean()
    run.save()
    assert run.account_id == funded_account.id
    assert funded_account.is_default is False
    assert funded_account.backtest_run.id == run.id


def test_account_can_only_host_one_run(funded_account) -> None:
    first = _make_run(funded_account)
    first.full_clean()
    first.save()
    second = _make_run(funded_account)
    with pytest.raises(Exception):
        second.full_clean()
    with pytest.raises(Exception):
        second.save()


def test_repository_crud(funded_account) -> None:
    repo = BacktestRunRepository()
    run = _make_run(funded_account)
    run.full_clean()
    run.save()

    fetched = repo.get_by_id(run.id)
    assert fetched is not None
    assert fetched.id == run.id
    assert fetched.symbol == "RELIANCE"

    assert repo.exists(run.id) is True
    assert repo.count() == 1
    assert len(repo.list(symbol="RELIANCE")) == 1
    assert len(repo.list(symbol="TATA")) == 0

    fetched.symbol = "TCS"
    fetched.full_clean()
    repo.update(fetched)
    assert repo.get_by_id(run.id).symbol == "TCS"

    repo.delete(run.id)
    assert repo.get_by_id(run.id) is None


def test_repository_get_by_id_unknown() -> None:
    import uuid

    assert BacktestRunRepository().get_by_id(uuid.uuid4()) is None


def test_repository_lifecycle_transitions(backtest_run) -> None:
    repo = BacktestRunRepository()
    now = datetime(2024, 6, 10, 7, 0, 0, tzinfo=timezone.utc)

    repo.mark_running(backtest_run.id, started_at=now)
    run = repo.get_by_id(backtest_run.id)
    assert run.status == BacktestRunStatus.RUNNING
    assert run.started_at == now

    cursor = __import__("uuid").uuid4()
    repo.update_cursor(backtest_run.id, cursor)
    assert repo.get_by_id(backtest_run.id).last_processed_snapshot_id == cursor

    repo.mark_completed(backtest_run.id, completed_at=now)
    run = repo.get_by_id(backtest_run.id)
    assert run.status == BacktestRunStatus.COMPLETED
    assert run.completed_at == now

    repo.mark_failed(backtest_run.id, "boom")
    run = repo.get_by_id(backtest_run.id)
    assert run.status == BacktestRunStatus.FAILED
    assert run.failure_reason == "boom"


def test_repository_mark_failed_truncates_reason(backtest_run) -> None:
    BacktestRunRepository().mark_failed(backtest_run.id, "x" * 9000)
    run = BacktestRunRepository().get_by_id(backtest_run.id)
    assert len(run.failure_reason) == 4000


def test_repository_delete_hard_deletes(funded_account) -> None:
    run = _make_run(funded_account)
    run.full_clean()
    run.save()
    repo = BacktestRunRepository()
    repo.delete(run.id)
    assert BacktestRun.all_objects.filter(id=run.id).exists() is False


def test_db_table_and_indexes() -> None:
    meta = BacktestRun._meta
    assert meta.db_table == "backtesting_backtestrun"
    names = {index.name for index in meta.indexes}
    assert {"idx_bt_symbol_range", "idx_bt_status"} <= names
