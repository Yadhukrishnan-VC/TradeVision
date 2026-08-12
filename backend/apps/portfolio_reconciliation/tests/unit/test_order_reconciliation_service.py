"""PORTFOLIO-RECONCILE-1 — unit tests for ``OrderReconciliationService``.

Pure classification/repair-logic tests using in-memory fakes (no DB). Every
assertion is on an exact expected value.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace

import pytest

from apps.portfolio_reconciliation.application.order_reconciliation_service import (
    OrderReconciliationService,
)
from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
    EntityType,
)
from apps.portfolio_reconciliation.tests.conftest import (
    FakeDriftRecords,
    FakeEventPublisher,
    FakeOrderSnapshots,
    FakeOrderSource,
    _NoOpTransactionManager,
    make_order,
    make_order_snapshot,
)


def build_service(
    *,
    orders: list | None = None,
    snapshots: list | None = None,
):
    sources = FakeOrderSource(orders or [])
    snap = FakeOrderSnapshots(snapshots or [])
    drift = FakeDriftRecords()
    publisher = FakeEventPublisher()
    service = OrderReconciliationService(
        sources=sources,
        snapshots=snap,
        drift_records=drift,
        event_publisher=publisher,
        transaction_manager=_NoOpTransactionManager(),
    )
    return service, sources, snap, drift, publisher


class TestOrderClassification:
    def test_matched_requires_no_write_and_no_drift_record(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(account_id=account_id, status="FILLED", filled_quantity="100")
        snapshot = make_order_snapshot(
            account_id=account_id, order_id=order.id, status="filled", filled_quantity="100"
        )
        service, _sources, snap, drift, publisher = build_service(
            orders=[order], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.matched == 1
        assert result.total_drift == 0
        assert snap.created == []
        assert snap.repaired == []
        assert drift.records == []
        assert publisher.events == []

    def test_stale_filled_quantity_is_classified_and_repaired(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(
            account_id=account_id, status="FILLED", filled_quantity="100", avg_fill_price="250.50"
        )
        snapshot = make_order_snapshot(
            account_id=account_id, order_id=order.id, status="filled", filled_quantity="50"
        )
        service, _sources, snap, drift, publisher = build_service(
            orders=[order], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.stale_in_read_model == 1
        assert result.total_drift == 1
        assert len(snap.repaired) == 1
        assert snap.repaired[0]["status"] == "filled"
        assert snap.repaired[0]["filled_quantity"] == order.filled_quantity
        assert snap.repaired[0]["avg_fill_price"] == order.avg_fill_price
        assert result.drift_records[0].classification is (
            DriftClassification.STALE_IN_READ_MODEL
        )
        assert result.drift_records[0].auto_repaired is True
        assert len(drift.records) == 1

    def test_missing_snapshot_is_created_with_exact_fields(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(
            account_id=account_id, symbol="TCS", status="FILLED",
            filled_quantity="50", avg_fill_price="3500.00",
        )
        service, _sources, snap, drift, _publisher = build_service(
            orders=[order], snapshots=[]
        )

        result = service.reconcile(account_id)

        assert result.missing_in_read_model == 1
        assert result.total_drift == 1
        assert len(snap.created) == 1
        created = snap.created[0]
        assert created["order_id"] == order.id
        assert created["account_id"] == account_id
        assert created["symbol"] == "TCS"
        assert created["side"] == "LONG"
        assert created["status"] == "filled"
        assert created["quantity"] == order.quantity
        assert created["filled_quantity"] == order.filled_quantity
        assert created["avg_fill_price"] == order.avg_fill_price
        assert created["placed_at"] == order.created_at
        assert result.drift_records[0].auto_repaired is True

    def test_orphaned_snapshot_never_triggers_a_write(self) -> None:
        account_id = uuid.uuid4()
        snapshot = make_order_snapshot(
            account_id=account_id, order_id=uuid.uuid4(), status="filled", filled_quantity="10"
        )
        service, _sources, snap, drift, publisher = build_service(
            orders=[], snapshots=[snapshot]
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

    def test_status_vocabulary_projection_matches(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(
            account_id=account_id, status="PARTIALLY_FILLED", filled_quantity="75"
        )
        snapshot = make_order_snapshot(
            account_id=account_id, order_id=order.id, status="partially_filled",
            filled_quantity="75",
        )
        service, _sources, snap, _drift, _publisher = build_service(
            orders=[order], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.matched == 1
        assert snap.repaired == []

    def test_avg_fill_price_none_matches_none(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(
            account_id=account_id, status="CREATED", filled_quantity="0",
            avg_fill_price=None,
        )
        snapshot = make_order_snapshot(
            account_id=account_id, order_id=order.id, status="pending",
            filled_quantity="0", avg_fill_price=None,
        )
        service, _sources, snap, _drift, _publisher = build_service(
            orders=[order], snapshots=[snapshot]
        )

        result = service.reconcile(account_id)

        assert result.matched == 1
        assert snap.repaired == []

    def test_event_published_once_per_drift_record(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(account_id=account_id, status="FILLED", filled_quantity="100")
        snapshot = make_order_snapshot(
            account_id=account_id, order_id=order.id, status="filled", filled_quantity="42"
        )
        service, _sources, _snap, _drift, publisher = build_service(
            orders=[order], snapshots=[snapshot]
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
        assert drift_events[0].payload["entity_type"] == EntityType.ORDER.value
        assert drift_events[0].payload["classification"] == "STALE_IN_READ_MODEL"
        assert drift_events[0].payload["auto_repaired"] is True
        assert drift_events[0].version == 1
        assert repair_events[0].payload["repaired_fields"] == [
            "status",
            "filled_quantity",
            "avg_fill_price",
        ]


class TestOrderIdempotency:
    def test_rerun_with_no_drift_is_a_true_noop(self) -> None:
        account_id = uuid.uuid4()
        order = make_order(account_id=account_id, status="FILLED", filled_quantity="100")
        service, _sources, snap, drift, publisher = build_service(orders=[order])

        first = service.reconcile(account_id)
        events_after_first = len(publisher.events)
        second = service.reconcile(account_id)

        assert first.missing_in_read_model == 1
        assert second.matched == 1
        assert second.total_drift == 0
        assert len(snap.created) == 1  # only the first run created anything
        assert len(drift.records) == 1
        assert events_after_first == 2
        assert len(publisher.events) == events_after_first


class TestOrderRunContinuation:
    def test_single_malformed_row_does_not_abort_the_run(self) -> None:
        account_id = uuid.uuid4()
        good = make_order(account_id=account_id, status="FILLED", filled_quantity="100")
        snap = make_order_snapshot(
            account_id=account_id, order_id=good.id, status="filled", filled_quantity="100"
        )
        # Malformed row has .id but is missing the attributes _classify needs.
        malformed = SimpleNamespace(id=uuid.uuid4())
        sources = FakeOrderSource([good, malformed])
        snapshots = FakeOrderSnapshots([snap])
        drift = FakeDriftRecords()
        service = OrderReconciliationService(
            sources=sources,
            snapshots=snapshots,
            drift_records=drift,
            event_publisher=FakeEventPublisher(),
            transaction_manager=_NoOpTransactionManager(),
        )

        result = service.reconcile(account_id)

        assert result.matched == 1
        assert result.comparison_errors == 1
        assert result.total_drift == 1
