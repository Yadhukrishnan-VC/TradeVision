"""PORTFOLIO-RECONCILE-1 — unit tests for ``PositionReconciliationService``.

Pure classification/repair-logic tests using in-memory fakes (no DB). Every
assertion is on an exact expected value.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.portfolio_reconciliation.application.position_reconciliation_service import (
    PositionReconciliationService,
)
from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
    EntityType,
)
from apps.portfolio_reconciliation.tests.conftest import (
    FakeDriftRecords,
    FakeEventPublisher,
    FakePositionSnapshots,
    FakePositionSource,
    _NoOpTransactionManager,
    make_position,
    make_snapshot,
)


def build_service(
    *,
    positions: list | None = None,
    snapshots: list | None = None,
    tolerance: str | None = None,
):
    sources = FakePositionSource(positions or [])
    snap = FakePositionSnapshots(snapshots or [])
    drift = FakeDriftRecords()
    publisher = FakeEventPublisher()
    kwargs = {}
    if tolerance is not None:
        kwargs["avg_price_tolerance"] = tolerance
    service = PositionReconciliationService(
        sources=sources,
        snapshots=snap,
        drift_records=drift,
        event_publisher=publisher,
        transaction_manager=_NoOpTransactionManager(),
        **kwargs,
    )
    return service, sources, snap, drift, publisher


class TestPositionClassification:
    def test_matched_requires_no_write_and_no_drift_record(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(account_id=account_id, symbol="RELIANCE")
        snapshot = make_snapshot(
            account_id=account_id,
            symbol="RELIANCE",
            quantity="100",
            entry_price="250.50",
        )
        service, _sources, snap, drift, publisher = build_service(
            positions=[position], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.matched == 1
        assert result.total_drift == 0
        assert result.missing_in_read_model == 0
        assert snap.created == []
        assert snap.repaired == []
        assert drift.records == []
        assert publisher.events == []

    def test_stale_quantity_is_classified_and_repaired(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(
            account_id=account_id, symbol="RELIANCE", quantity="100"
        )
        snapshot = make_snapshot(
            account_id=account_id,
            symbol="RELIANCE",
            quantity="90",
            entry_price="250.50",
        )
        service, _sources, snap, drift, publisher = build_service(
            positions=[position], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.stale_in_read_model == 1
        assert result.total_drift == 1
        assert len(snap.repaired) == 1
        assert snap.repaired[0]["quantity"] == position.quantity
        assert snap.repaired[0]["entry_price"] == position.avg_entry_price
        assert snap.repaired[0]["side"] == position.side
        assert snap.repaired[0]["symbol"] == "RELIANCE"
        assert result.drift_records[0].classification is (
            DriftClassification.STALE_IN_READ_MODEL
        )
        assert result.drift_records[0].auto_repaired is True
        assert len(drift.records) == 1
        assert drift.records[0]["auto_repaired"] is True

    def test_avg_price_tolerance_prevents_false_stale(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(
            account_id=account_id, symbol="RELIANCE", avg_entry_price="250.50000001"
        )
        snapshot = make_snapshot(
            account_id=account_id, symbol="RELIANCE", entry_price="250.50"
        )
        service, _sources, snap, drift, _publisher = build_service(
            positions=[position], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.matched == 1
        assert result.total_drift == 0
        assert snap.repaired == []

    def test_missing_snapshot_is_repaired_with_exact_fields(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(
            account_id=account_id, symbol="TCS", quantity="50", avg_entry_price="3500.00"
        )
        service, _sources, snap, drift, publisher = build_service(
            positions=[position], snapshots=[]
        )

        result = service.reconcile(account_id)

        assert result.missing_in_read_model == 1
        assert result.total_drift == 1
        assert len(snap.created) == 1
        created = snap.created[0]
        assert created["position_id"] == position.id
        assert created["account_id"] == account_id
        assert created["symbol"] == "TCS"
        assert created["side"] == "LONG"
        assert created["quantity"] == position.quantity
        assert created["entry_price"] == position.avg_entry_price
        assert created["opened_at"] == position.opened_at
        assert result.drift_records[0].auto_repaired is True

    def test_orphaned_snapshot_never_triggers_a_write(self) -> None:
        account_id = uuid.uuid4()
        snapshot = make_snapshot(
            account_id=account_id, symbol="GHOST", quantity="10", entry_price="99.00"
        )
        service, _sources, snap, drift, publisher = build_service(
            positions=[], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.orphaned_in_read_model == 1
        assert result.total_drift == 1
        assert result.drift_records[0].classification is (
            DriftClassification.ORPHANED_IN_READ_MODEL
        )
        assert result.drift_records[0].auto_repaired is False
        assert snap.created == []
        assert snap.repaired == []
        # The snapshot must remain byte-for-byte untouched.
        assert snapshot.quantity == snapshot.quantity
        assert snapshot.is_open is True

    def test_closed_snapshot_counts_as_missing_not_orphan(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(account_id=account_id, symbol="RELIANCE")
        closed_snapshot = make_snapshot(
            account_id=account_id,
            symbol="RELIANCE",
            quantity="100",
            entry_price="250.50",
            is_open=False,
        )
        service, _sources, snap, _drift, _publisher = build_service(
            positions=[position], snapshots=[closed_snapshot]
        )

        result = service.reconcile(account_id)

        assert result.missing_in_read_model == 1
        assert result.orphaned_in_read_model == 0
        assert len(snap.created) == 1

    def test_event_published_once_per_drift_record(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(account_id=account_id, symbol="RELIANCE", quantity="100")
        snapshot = make_snapshot(
            account_id=account_id, symbol="RELIANCE", quantity="42"
        )
        service, _sources, _snap, _drift, publisher = build_service(
            positions=[position], snapshots=[snapshot]
        )

        service.reconcile(account_id)

        drift_events = [
            e for e in publisher.events if e.event_type == "portfolio_reconciliation.DriftDetected"
        ]
        repair_events = [
            e for e in publisher.events if e.event_type == "portfolio_reconciliation.RepairApplied"
        ]
        assert len(drift_events) == 1
        assert len(repair_events) == 1
        assert drift_events[0].payload["entity_type"] == EntityType.POSITION.value
        assert drift_events[0].payload["classification"] == "STALE_IN_READ_MODEL"
        assert drift_events[0].payload["auto_repaired"] is True
        assert drift_events[0].version == 1
        assert repair_events[0].payload["repaired_fields"] == ["quantity"]


class TestPositionIdempotency:
    def test_rerun_with_no_drift_is_a_true_noop(self) -> None:
        account_id = uuid.uuid4()
        position = make_position(account_id=account_id, symbol="RELIANCE", quantity="100")
        service, _sources, snap, drift, publisher = build_service(positions=[position])

        first = service.reconcile(account_id)
        events_after_first = len(publisher.events)
        second = service.reconcile(account_id)

        assert first.missing_in_read_model == 1
        assert second.matched == 1
        assert second.total_drift == 0
        assert len(snap.created) == 1  # only the first run created anything
        assert len(drift.records) == 1
        # The first run published DriftDetected + RepairApplied; the second
        # run (no drift) must not publish a single additional event.
        assert events_after_first == 2
        assert len(publisher.events) == events_after_first


class TestPositionRunContinuation:
    def test_single_malformed_row_does_not_abort_the_run(self) -> None:
        account_id = uuid.uuid4()
        good = make_position(account_id=account_id, symbol="RELIANCE", quantity="100")
        snap = make_snapshot(
            account_id=account_id, symbol="RELIANCE", quantity="100", entry_price="250.50"
        )
        # Malformed row has .symbol but is missing other attributes needed by _classify
        malformed = SimpleNamespace(symbol="BROKEN")
        sources = FakePositionSource([good, malformed])
        snapshots = FakePositionSnapshots([snap])
        drift = FakeDriftRecords()
        service = PositionReconciliationService(
            sources=sources,
            snapshots=snapshots,
            drift_records=drift,
            event_publisher=FakeEventPublisher(),
            transaction_manager=_NoOpTransactionManager(),
        )

        result = service.reconcile(account_id)

        # The valid row was still matched; the malformed row was downgraded.
        assert result.matched == 1
        assert result.comparison_errors == 1
        assert result.total_drift == 1