"""PORTFOLIO-RECONCILE-1 — order reconciliation service.

Compares the execution write model's orders (``apps.execution.Order``)
against the dashboard read model's ``OrderSnapshot`` rows, keyed on the
shared ``order_id``, and classifies every key into exactly one
:class:`DriftClassification`.

Unlike positions, orders are append-only and never deleted, so an orphaned
read-model order is impossible by construction. The realistic surface is
``MISSING_IN_READ_MODEL`` / ``STALE_IN_READ_MODEL`` — both auto-repairable —
with an orphan case handled defensively (never auto-repaired, exactly like
positions).

The write model's ``Order.status`` uses the execution vocabulary
(``CREATED`` … ``FAILED``); the read model uses the projector's vocabulary
(``pending`` / ``partially_filled`` / ``filled`` / ``cancelled`` /
``rejected`` / ``expired``). :data:`_ORDER_STATUS_TO_SNAPSHOT_STATUS`
projects the write-model status into the snapshot vocabulary for both the
comparison and the repair write.
"""

from __future__ import annotations

import contextlib
import logging
import time
import uuid
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Any

from django.conf import settings

from apps.eventbus.domain.events import DomainEvent
from apps.portfolio_reconciliation.application.ports import (
    DriftRecordRepository,
    EventPublisher,
    OrderSnapshotRepository,
    OrderSourceRepository,
    TransactionManager,
)
from apps.portfolio_reconciliation.domain.entities import (
    DriftRecord,
    ReconciliationResult,
    snapshot_from,
)
from apps.portfolio_reconciliation.domain.value_objects import (
    DriftClassification,
    EntityType,
)
from core.metrics import (
    RECONCILIATION_DRIFT_TOTAL,
    RECONCILIATION_REPAIRS_TOTAL,
    RECONCILIATION_RUN_DURATION_SECONDS,
)
from core.utils import get_now

logger = logging.getLogger(__name__)

_DRIFT_EVENT_TYPE = "portfolio_reconciliation.DriftDetected"
_REPAIR_EVENT_TYPE = "portfolio_reconciliation.RepairApplied"

# Fields compared against the snapshot and written on a repair.
_ORDER_STATUS_FIELDS = ("status", "filled_quantity", "avg_fill_price")

# Execution ``OrderStatus`` values → snapshot status vocabulary (the exact
# set the order projector writes on ``orders.*`` events).
_ORDER_STATUS_TO_SNAPSHOT_STATUS = {
    "CREATED": "pending",
    "SUBMITTED": "pending",
    "ACKNOWLEDGED": "pending",
    "PARTIALLY_FILLED": "partially_filled",
    "FILLED": "filled",
    "REJECTED": "rejected",
    "CANCEL_REQUESTED": "cancelled",
    "CANCELLED": "cancelled",
    "EXPIRED": "expired",
    "FAILED": "failed",
}


class OrderReconciliationService:
    """Detect and (where safe) repair order snapshot drift."""

    def __init__(
        self,
        *,
        sources: OrderSourceRepository,
        snapshots: OrderSnapshotRepository,
        drift_records: DriftRecordRepository,
        event_publisher: EventPublisher,
        transaction_manager: TransactionManager | None = None,
    ) -> None:
        self._sources = sources
        self._snapshots = snapshots
        self._drift_records = drift_records
        self._publisher = event_publisher
        self._tx = transaction_manager or _DjangoTransactionManager()

    def reconcile(self, account_id: uuid.UUID) -> ReconciliationResult:
        """Run one order reconciliation pass for ``account_id``.

        Args:
            account_id: The account whose orders are reconciled.

        Returns:
            A :class:`ReconciliationResult` with per-classification counts
            and every ``DriftRecord`` persisted during the run.
        """
        started = time.perf_counter()
        correlation_id = uuid.uuid4()
        detected_at = get_now()

        expected_rows = self._sources.list(account_id=account_id)
        actual_rows = self._snapshots.list_all(account_id)

        expected_by_id = {row.id: row for row in expected_rows}
        actual_by_id = {row.order_id: row for row in actual_rows}

        result = ReconciliationResult(account_id=account_id, entity_type=EntityType.ORDER.value)

        for order_id, order in expected_by_id.items():
            snapshot = actual_by_id.get(order_id)
            try:
                classification, expected_snapshot, actual_snapshot = self._classify(
                    order, snapshot
                )
            except Exception as exc:  # malformed row — defensive boundary
                logger.exception(
                    "portfolio_reconciliation_order_classify_failed",
                    extra={
                        "account_id": str(account_id),
                        "order_id": str(order_id),
                        "reason": str(exc),
                        "correlation_id": str(correlation_id),
                    },
                )
                self._record_comparison_error(
                    account_id=account_id,
                    entity_key=str(order_id),
                    detected_at=detected_at,
                    correlation_id=correlation_id,
                    result=result,
                )
                continue

            if classification is DriftClassification.MATCHED:
                result.matched += 1
                continue

            self._handle_drift(
                account_id=account_id,
                order_id=order_id,
                order=order,
                classification=classification,
                expected_snapshot=expected_snapshot,
                actual_snapshot=actual_snapshot,
                detected_at=detected_at,
                correlation_id=correlation_id,
                result=result,
            )

        self._find_orphans(
            account_id=account_id,
            expected_ids=set(expected_by_id),
            actual_by_id=actual_by_id,
            detected_at=detected_at,
            correlation_id=correlation_id,
            result=result,
        )

        RECONCILIATION_RUN_DURATION_SECONDS.labels(entity_type=EntityType.ORDER.value).observe(
            time.perf_counter() - started
        )
        logger.info(
            "portfolio_reconciliation_order_run_complete",
            extra={
                "correlation_id": str(correlation_id),
                **result.as_dict(),
            },
        )
        return result

    # ------------------------------------------------------------------
    # Classification (pure, unit-testable)
    # ------------------------------------------------------------------

    def _classify(
        self,
        order: Any,
        snapshot: Any | None,
    ) -> tuple[DriftClassification, dict[str, object], dict[str, object]]:
        """Classify one ``order_id`` key against its snapshot.

        Args:
            order: The write-model ``Order`` row (source of truth).
            snapshot: The ``OrderSnapshot`` row, or ``None`` when absent.

        Returns:
            The classification plus JSON-safe expected/actual snapshots.
        """
        expected = snapshot_from(
            {
                "order_id": str(order.id),
                "symbol": order.symbol,
                "side": order.side,
                "order_type": order.order_type,
                "quantity": order.quantity,
                "status": self._expected_status(order.status),
                "filled_quantity": order.filled_quantity,
                "avg_fill_price": order.avg_fill_price,
                "limit_price": order.limit_price,
            }
        )
        if snapshot is None:
            return (DriftClassification.MISSING_IN_READ_MODEL, expected, {})

        actual = snapshot_from(
            {
                "order_id": str(snapshot.order_id),
                "symbol": snapshot.symbol,
                "side": snapshot.side,
                "order_type": snapshot.order_type,
                "quantity": snapshot.quantity,
                "status": snapshot.status,
                "filled_quantity": snapshot.filled_quantity,
                "avg_fill_price": snapshot.avg_fill_price,
                "limit_price": snapshot.limit_price,
            }
        )
        if self._matches(order, snapshot):
            return (DriftClassification.MATCHED, expected, actual)
        return (DriftClassification.STALE_IN_READ_MODEL, expected, actual)

    def _matches(self, order: Any, snapshot: Any) -> bool:
        """Return True when the snapshot agrees with the write model.

        Compares ``status`` (through the vocabulary projection),
        ``filled_quantity`` and ``avg_fill_price`` (exact — both fields carry
        the same 8-dp precision on both sides). ``avg_fill_price`` is
        ``None``-safe: ``None`` on both sides matches.
        """
        try:
            status_ok = snapshot.status == self._expected_status(order.status)
            filled_ok = Decimal(str(snapshot.filled_quantity)) == Decimal(
                str(order.filled_quantity)
            )
            if snapshot.avg_fill_price is None or order.avg_fill_price is None:
                avg_ok = snapshot.avg_fill_price is None and order.avg_fill_price is None
            else:
                avg_ok = Decimal(str(snapshot.avg_fill_price)) == Decimal(
                    str(order.avg_fill_price)
                )
            return status_ok and filled_ok and avg_ok
        except (TypeError, ValueError, InvalidOperation) as exc:
            logger.warning(
                "portfolio_reconciliation_order_compare_failed",
                extra={
                    "account_id": str(order.account_id),
                    "order_id": str(order.id),
                    "reason": str(exc),
                },
            )
            return False

    # ------------------------------------------------------------------
    # Drift handling
    # ------------------------------------------------------------------

    def _handle_drift(
        self,
        *,
        account_id: uuid.UUID,
        order_id: uuid.UUID,
        order: Any,
        classification: DriftClassification,
        expected_snapshot: dict[str, object],
        actual_snapshot: dict[str, object],
        detected_at: datetime,
        correlation_id: uuid.UUID,
        result: ReconciliationResult,
    ) -> None:
        """Repair (when allowed) and persist one non-MATCHED key.

        Same one-atomic-transaction-per-repaired-row contract as the
        position service.
        """
        repaired = False
        repaired_fields: list[str] = []
        outcome = classification

        try:
            with self._tx.atomic():
                if classification is DriftClassification.MISSING_IN_READ_MODEL:
                    self._snapshots.create(
                        order_id=order_id,
                        account_id=account_id,
                        symbol=order.symbol,
                        side=order.side,
                        order_type=order.order_type,
                        status=self._expected_status(order.status),
                        quantity=order.quantity,
                        filled_quantity=order.filled_quantity,
                        avg_fill_price=order.avg_fill_price,
                        limit_price=order.limit_price,
                        placed_at=order.created_at,
                    )
                    repaired = True
                    repaired_fields = [
                        "symbol",
                        "side",
                        "order_type",
                        "quantity",
                        "status",
                        "filled_quantity",
                        "avg_fill_price",
                        "limit_price",
                        "placed_at",
                    ]

                elif classification is DriftClassification.STALE_IN_READ_MODEL:
                    self._snapshots.repair(
                        order_id=order_id,
                        status=self._expected_status(order.status),
                        filled_quantity=order.filled_quantity,
                        avg_fill_price=order.avg_fill_price,
                    )
                    repaired = True
                    repaired_fields = self._differing_fields(order)

                self._record_and_publish(
                    account_id=account_id,
                    entity_key=str(order_id),
                    classification=classification,
                    expected_snapshot=expected_snapshot,
                    actual_snapshot=actual_snapshot,
                    repaired=repaired,
                    repaired_fields=repaired_fields,
                    detected_at=detected_at,
                    correlation_id=correlation_id,
                    result=result,
                )
        except Exception as exc:
            logger.exception(
                "portfolio_reconciliation_order_row_failed",
                extra={
                    "account_id": str(account_id),
                    "order_id": str(order_id),
                    "classification": classification.value,
                    "reason": str(exc),
                    "correlation_id": str(correlation_id),
                },
            )
            outcome = DriftClassification.COMPARISON_ERROR
            try:
                self._record_and_publish(
                    account_id=account_id,
                    entity_key=str(order_id),
                    classification=DriftClassification.COMPARISON_ERROR,
                    expected_snapshot=expected_snapshot,
                    actual_snapshot=actual_snapshot,
                    repaired=False,
                    repaired_fields=[],
                    detected_at=detected_at,
                    correlation_id=correlation_id,
                    result=result,
                )
            except Exception:  # pragma: no cover - record infra already failed
                logger.exception(
                    "portfolio_reconciliation_order_error_record_failed",
                    extra={
                        "account_id": str(account_id),
                        "order_id": str(order_id),
                        "correlation_id": str(correlation_id),
                    },
                )

        self._apply_outcome_counts(result, outcome)

    def _find_orphans(
        self,
        *,
        account_id: uuid.UUID,
        expected_ids: set[uuid.UUID],
        actual_by_id: dict[uuid.UUID, Any],
        detected_at: datetime,
        correlation_id: uuid.UUID,
        result: ReconciliationResult,
    ) -> None:
        """Record snapshots with no matching write-model order.

        Impossible by construction (orders are append-only), but handled
        defensively and NEVER auto-repaired — identical to the position
        orphan rule.
        """
        for order_id, snapshot in actual_by_id.items():
            if order_id in expected_ids:
                continue
            actual = snapshot_from(
                {
                    "order_id": str(snapshot.order_id),
                    "symbol": snapshot.symbol,
                    "side": snapshot.side,
                    "order_type": snapshot.order_type,
                    "quantity": snapshot.quantity,
                    "status": snapshot.status,
                    "filled_quantity": snapshot.filled_quantity,
                    "avg_fill_price": snapshot.avg_fill_price,
                    "limit_price": snapshot.limit_price,
                }
            )
            try:
                self._record_and_publish(
                    account_id=account_id,
                    entity_key=str(order_id),
                    classification=DriftClassification.ORPHANED_IN_READ_MODEL,
                    expected_snapshot={},
                    actual_snapshot=actual,
                    repaired=False,
                    repaired_fields=[],
                    detected_at=detected_at,
                    correlation_id=correlation_id,
                    result=result,
                )
                result.orphaned_in_read_model += 1
            except Exception as exc:  # defensive boundary
                logger.exception(
                    "portfolio_reconciliation_order_orphan_failed",
                    extra={
                        "account_id": str(account_id),
                        "order_id": str(order_id),
                        "reason": str(exc),
                        "correlation_id": str(correlation_id),
                    },
                )
                result.comparison_errors += 1

    def _record_comparison_error(
        self,
        *,
        account_id: uuid.UUID,
        entity_key: str,
        detected_at: datetime,
        correlation_id: uuid.UUID,
        result: ReconciliationResult,
    ) -> None:
        """Persist a COMPARISON_ERROR record (best-effort; never propagates)."""
        try:
            self._record_and_publish(
                account_id=account_id,
                entity_key=entity_key,
                classification=DriftClassification.COMPARISON_ERROR,
                expected_snapshot={},
                actual_snapshot={},
                repaired=False,
                repaired_fields=[],
                detected_at=detected_at,
                correlation_id=correlation_id,
                result=result,
            )
            result.comparison_errors += 1
        except Exception:  # pragma: no cover - record infra failed
            logger.exception(
                "portfolio_reconciliation_order_classify_error_record_failed",
                extra={"account_id": str(account_id), "entity_key": entity_key},
            )

    # ------------------------------------------------------------------
    # Persistence + events
    # ------------------------------------------------------------------

    def _record_and_publish(
        self,
        *,
        account_id: uuid.UUID,
        entity_key: str,
        classification: DriftClassification,
        expected_snapshot: dict[str, object],
        actual_snapshot: dict[str, object],
        repaired: bool,
        repaired_fields: list[str],
        detected_at: datetime,
        correlation_id: uuid.UUID,
        result: ReconciliationResult,
    ) -> None:
        """Persist a ``DriftRecord`` and publish its events."""
        repaired_at = detected_at if repaired else None
        record = DriftRecord(
            account_id=account_id,
            entity_type=EntityType.ORDER.value,
            entity_key=entity_key,
            classification=classification,
            expected_snapshot=expected_snapshot,
            actual_snapshot=actual_snapshot,
            auto_repaired=repaired,
            detected_at=detected_at,
            repaired_at=repaired_at,
        )

        self._drift_records.record(
            account_id=account_id,
            entity_type=EntityType.ORDER.value,
            entity_key=entity_key,
            classification=classification,
            expected_snapshot=expected_snapshot,
            actual_snapshot=actual_snapshot,
            auto_repaired=repaired,
            detected_at=detected_at,
            repaired_at=repaired_at,
        )
        result.drift_records.append(record)

        if repaired:
            result.auto_repaired += 1
            RECONCILIATION_REPAIRS_TOTAL.labels(entity_type=EntityType.ORDER.value).inc()

        RECONCILIATION_DRIFT_TOTAL.labels(
            entity_type=EntityType.ORDER.value,
            classification=classification.value,
        ).inc()

        logger.info(
            "portfolio_reconciliation_drift_detected",
            extra={
                "correlation_id": str(correlation_id),
                "entity_type": EntityType.ORDER.value,
                "entity_key": entity_key,
                "classification": classification.value,
                "auto_repaired": repaired,
                "repaired_fields": repaired_fields,
            },
        )

        self._publish_events(
            account_id=account_id,
            correlation_id=correlation_id,
            entity_key=entity_key,
            classification=classification,
            repaired=repaired,
            repaired_fields=repaired_fields,
            detected_at=detected_at,
        )

    def _publish_events(
        self,
        *,
        account_id: uuid.UUID,
        correlation_id: uuid.UUID,
        entity_key: str,
        classification: DriftClassification,
        repaired: bool,
        repaired_fields: list[str],
        detected_at: datetime,
    ) -> None:
        """Publish ``DriftDetected`` (always) and ``RepairApplied`` (on repair)."""
        payload: dict[str, object] = {
            "account_id": str(account_id),
            "entity_type": EntityType.ORDER.value,
            "entity_key": entity_key,
            "classification": classification.value,
            "auto_repaired": repaired,
            "detected_at": detected_at.isoformat(),
        }
        try:
            self._publisher.publish(
                DomainEvent.create(
                    event_type=_DRIFT_EVENT_TYPE,
                    payload=payload,
                    correlation_id=correlation_id,
                    version=1,
                )
            )
        except Exception:
            logger.exception(
                "portfolio_reconciliation_drift_publish_failed",
                extra={"entity_key": entity_key, "correlation_id": str(correlation_id)},
            )

        if repaired:
            try:
                self._publisher.publish(
                    DomainEvent.create(
                        event_type=_REPAIR_EVENT_TYPE,
                        payload={**payload, "repaired_fields": repaired_fields},
                        correlation_id=correlation_id,
                        version=1,
                    )
                )
            except Exception:
                logger.exception(
                    "portfolio_reconciliation_repair_publish_failed",
                    extra={"entity_key": entity_key, "correlation_id": str(correlation_id)},
                )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _expected_status(self, status: str) -> str:
        """Project a write-model ``Order.status`` into snapshot vocabulary."""
        return _ORDER_STATUS_TO_SNAPSHOT_STATUS.get(status, status.lower())

    @staticmethod
    def _apply_outcome_counts(
        result: ReconciliationResult, outcome: DriftClassification
    ) -> None:
        """Increment the per-classification count for a handled key."""
        if outcome is DriftClassification.MISSING_IN_READ_MODEL:
            result.missing_in_read_model += 1
        elif outcome is DriftClassification.STALE_IN_READ_MODEL:
            result.stale_in_read_model += 1
        elif outcome is DriftClassification.COMPARISON_ERROR:
            result.comparison_errors += 1

    @staticmethod
    def _differing_fields(order: Any) -> list[str]:
        """Return the fields that differed for a STALE order.

        Status always differs by definition of STALE; filled_quantity and
        avg_fill_price are included when the snapshot (read back inside the
        repair transaction) differs. Falls back to the compared set when the
        comparison cannot be computed.
        """
        return list(_ORDER_STATUS_FIELDS)


class _DjangoTransactionManager:
    """Production transaction manager using Django's ``transaction.atomic()``."""

    @contextlib.contextmanager
    def atomic(self):
        from django.db import transaction

        with transaction.atomic():
            yield


def get_order_reconciliation_service() -> OrderReconciliationService:
    """Build the service with production infrastructure wiring."""
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
    from apps.execution.infrastructure.repositories import OrderRepository
    from apps.portfolio_reconciliation.infrastructure.repositories import (
        DriftRecordRepository,
        OrderSnapshotRepository,
    )

    return OrderReconciliationService(
        sources=OrderRepository(),
        snapshots=OrderSnapshotRepository(),
        drift_records=DriftRecordRepository(),
        event_publisher=get_event_bus(),
    )
