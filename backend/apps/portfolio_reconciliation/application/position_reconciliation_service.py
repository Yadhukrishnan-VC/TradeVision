"""PORTFOLIO-RECONCILE-1 — position reconciliation service.

Compares the portfolio write model's open positions
(``apps.portfolio.Position``) against the dashboard read model's
``PositionSnapshot`` rows and classifies every ``(account_id, symbol)`` key
into exactly one :class:`DriftClassification`.

Repair writes ONLY fields the existing position projector already writes
(``side``, ``quantity``, ``entry_price``, ``opened_at``, ``is_open``),
taking source-of-truth values verbatim — no fabrication. The one
classification that NEVER triggers a write is ``ORPHANED_IN_READ_MODEL``:
"repairing" it would mean closing a position no one told the write model to
close, which is a judgment call this batch does not make.
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
    PositionSnapshotRepository,
    PositionSourceRepository,
    TransactionManager,
)
from apps.portfolio_reconciliation.domain.entities import (
    DriftRecord,
    ReconciliationResult,
    snapshot_from,
)
from apps.portfolio_reconciliation.domain.exceptions import (
    DriftPersistenceError,
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

# Fields the existing projector writes on an open position snapshot.
_POSITION_VALUE_FIELDS = ("side", "quantity", "entry_price", "opened_at")


class PositionReconciliationService:
    """Detect and (where safe) repair position snapshot drift."""

    def __init__(
        self,
        *,
        sources: PositionSourceRepository,
        snapshots: PositionSnapshotRepository,
        drift_records: DriftRecordRepository,
        event_publisher: EventPublisher,
        avg_price_tolerance: Decimal | None = None,
        transaction_manager: TransactionManager | None = None,
    ) -> None:
        self._sources = sources
        self._snapshots = snapshots
        self._drift_records = drift_records
        self._publisher = event_publisher
        self._tolerance = avg_price_tolerance or Decimal(
            str(getattr(settings, "RECONCILIATION_AVG_PRICE_TOLERANCE", "0.00000001"))
        )
        self._tx = transaction_manager or _DjangoTransactionManager()

    def reconcile(self, account_id: uuid.UUID) -> ReconciliationResult:
        """Run one position reconciliation pass for ``account_id``.

        Args:
            account_id: The account whose positions are reconciled.

        Returns:
            A :class:`ReconciliationResult` with per-classification counts
            and every ``DriftRecord`` persisted during the run.

        No exception propagates for a single row's comparison or repair
        failure — such rows are classified ``COMPARISON_ERROR`` (defensive
        boundary). The run never aborts mid-way; already-repaired rows stay
        repaired because each repair commits in its own transaction.
        """
        started = time.perf_counter()
        correlation_id = uuid.uuid4()
        detected_at = get_now()

        expected_rows = self._sources.list_open(account_id)
        actual_rows = self._snapshots.list_open(account_id)

        expected_by_symbol = {row.symbol: row for row in expected_rows}
        actual_by_symbol = {row.symbol: row for row in actual_rows}

        result = ReconciliationResult(account_id=account_id, entity_type=EntityType.POSITION.value)

        for symbol, position in expected_by_symbol.items():
            snapshot = actual_by_symbol.get(symbol)
            try:
                classification, expected_snapshot, actual_snapshot = self._classify(
                    position, snapshot
                )
            except Exception as exc:  # malformed row — defensive boundary
                logger.exception(
                    "portfolio_reconciliation_position_classify_failed",
                    extra={
                        "account_id": str(account_id),
                        "symbol": symbol,
                        "reason": str(exc),
                        "correlation_id": str(correlation_id),
                    },
                )
                self._record_comparison_error(
                    account_id=account_id,
                    entity_key=f"{account_id}:{symbol}",
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
                symbol=symbol,
                position=position,
                snapshot=snapshot,
                classification=classification,
                expected_snapshot=expected_snapshot,
                actual_snapshot=actual_snapshot,
                detected_at=detected_at,
                correlation_id=correlation_id,
                result=result,
            )

        self._find_orphans(
            account_id=account_id,
            expected_symbols=set(expected_by_symbol),
            actual_by_symbol=actual_by_symbol,
            detected_at=detected_at,
            correlation_id=correlation_id,
            result=result,
        )

        RECONCILIATION_RUN_DURATION_SECONDS.labels(entity_type=EntityType.POSITION.value).observe(
            time.perf_counter() - started
        )
        logger.info(
            "portfolio_reconciliation_position_run_complete",
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
        position: Any,
        snapshot: Any | None,
    ) -> tuple[DriftClassification, dict[str, object], dict[str, object]]:
        """Classify one ``(account, symbol)`` key against its snapshot.

        Args:
            position: The write-model ``Position`` row (source of truth).
            snapshot: The ``PositionSnapshot`` row, or ``None`` when the
                key is absent from the open read-model set.

        Returns:
            The classification plus JSON-safe expected/actual snapshots.
        """
        expected = snapshot_from(
            {
                "symbol": position.symbol,
                "side": position.side,
                "quantity": position.quantity,
                "avg_entry_price": position.avg_entry_price,
                "opened_at": position.opened_at,
            }
        )
        if snapshot is None:
            return (DriftClassification.MISSING_IN_READ_MODEL, expected, {})

        actual = snapshot_from(
            {
                "symbol": snapshot.symbol,
                "side": snapshot.side,
                "quantity": snapshot.quantity,
                "entry_price": snapshot.entry_price,
                "opened_at": snapshot.opened_at,
            }
        )
        if self._matches(position, snapshot):
            return (DriftClassification.MATCHED, expected, actual)
        return (DriftClassification.STALE_IN_READ_MODEL, expected, actual)

    def _matches(self, position: Any, snapshot: Any) -> bool:
        """Return True when the snapshot agrees with the write model.

        ``quantity`` and ``side`` compare exactly; ``avg_entry_price`` allows
        the configurable rounding tolerance
        (``RECONCILIATION_AVG_PRICE_TOLERANCE``) because the write model may
        carry more precision than the read-model field. In practice these
        match exactly — the tolerance exists purely for defensive
        correctness.
        """
        try:
            side_ok = snapshot.side == position.side
            qty_ok = Decimal(str(snapshot.quantity)) == Decimal(str(position.quantity))
            price_ok = abs(
                Decimal(str(snapshot.entry_price)) - Decimal(str(position.avg_entry_price))
            ) <= self._tolerance
            return side_ok and qty_ok and price_ok
        except (TypeError, ValueError, InvalidOperation) as exc:
            logger.warning(
                "portfolio_reconciliation_position_compare_failed",
                extra={
                    "account_id": str(position.account_id),
                    "symbol": position.symbol,
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
        symbol: str,
        position: Any,
        snapshot: Any | None,
        classification: DriftClassification,
        expected_snapshot: dict[str, object],
        actual_snapshot: dict[str, object],
        detected_at: datetime,
        correlation_id: uuid.UUID,
        result: ReconciliationResult,
    ) -> None:
        """Repair (when allowed) and persist one non-MATCHED key.

        Each repaired row commits in its own ``transaction.atomic()`` block
        (repair + ``DriftRecord`` together), so a mid-run failure leaves
        already-repaired rows repaired. A row-level failure is downgraded to
        ``COMPARISON_ERROR`` and never propagates.
        """
        repaired = False
        repaired_fields: list[str] = []
        outcome = classification

        try:
            with self._tx.atomic():
                if classification is DriftClassification.MISSING_IN_READ_MODEL:
                    self._snapshots.create_open(
                        position_id=position.id,
                        account_id=account_id,
                        symbol=symbol,
                        side=position.side,
                        quantity=position.quantity,
                        entry_price=position.avg_entry_price,
                        opened_at=position.opened_at,
                    )
                    repaired = True
                    repaired_fields = list(_POSITION_VALUE_FIELDS)

                elif classification is DriftClassification.STALE_IN_READ_MODEL:
                    self._snapshots.repair_open(
                        account_id=account_id,
                        symbol=symbol,
                        side=position.side,
                        quantity=position.quantity,
                        entry_price=position.avg_entry_price,
                        opened_at=position.opened_at,
                    )
                    repaired = True
                    repaired_fields = self._differing_fields(position, snapshot)

                self._record_and_publish(
                    account_id=account_id,
                    entity_key=f"{account_id}:{symbol}",
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
                "portfolio_reconciliation_position_row_failed",
                extra={
                    "account_id": str(account_id),
                    "symbol": symbol,
                    "classification": classification.value,
                    "reason": str(exc),
                    "correlation_id": str(correlation_id),
                },
            )
            outcome = DriftClassification.COMPARISON_ERROR
            try:
                self._record_and_publish(
                    account_id=account_id,
                    entity_key=f"{account_id}:{symbol}",
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
                    "portfolio_reconciliation_position_error_record_failed",
                    extra={
                        "account_id": str(account_id),
                        "symbol": symbol,
                        "correlation_id": str(correlation_id),
                    },
                )

        self._apply_outcome_counts(result, outcome)

    def _find_orphans(
        self,
        *,
        account_id: uuid.UUID,
        expected_symbols: set[str],
        actual_by_symbol: dict[str, Any],
        detected_at: datetime,
        correlation_id: uuid.UUID,
        result: ReconciliationResult,
    ) -> None:
        """Record open snapshots that have no matching open position.

        These are NEVER auto-repaired: closing them would fabricate a
        position close the write model never ordered. Each is surfaced as a
        ``DriftRecord`` (and ``DriftDetected`` event) for manual review.
        """
        for symbol, snapshot in actual_by_symbol.items():
            if symbol in expected_symbols:
                continue
            actual = snapshot_from(
                {
                    "symbol": snapshot.symbol,
                    "side": snapshot.side,
                    "quantity": snapshot.quantity,
                    "entry_price": snapshot.entry_price,
                    "opened_at": snapshot.opened_at,
                }
            )
            try:
                self._record_and_publish(
                    account_id=account_id,
                    entity_key=f"{account_id}:{symbol}",
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
                    "portfolio_reconciliation_position_orphan_failed",
                    extra={
                        "account_id": str(account_id),
                        "symbol": symbol,
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
        """Persist a COMPARISON_ERROR record for a row that could not be
        classified at all (best-effort; never propagates)."""
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
                "portfolio_reconciliation_position_classify_error_record_failed",
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
        """Persist a ``DriftRecord`` and publish its events.

        The record is persisted before any event is published
        (persist-before-publish); a publish failure is logged and never
        blocks detection.
        """
        repaired_at = detected_at if repaired else None
        record = DriftRecord(
            account_id=account_id,
            entity_type=EntityType.POSITION.value,
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
            entity_type=EntityType.POSITION.value,
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
            RECONCILIATION_REPAIRS_TOTAL.labels(entity_type=EntityType.POSITION.value).inc()

        RECONCILIATION_DRIFT_TOTAL.labels(
            entity_type=EntityType.POSITION.value,
            classification=classification.value,
        ).inc()

        logger.info(
            "portfolio_reconciliation_drift_detected",
            extra={
                "correlation_id": str(correlation_id),
                "entity_type": EntityType.POSITION.value,
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
            "entity_type": EntityType.POSITION.value,
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
    def _differing_fields(position: Any, snapshot: Any) -> list[str]:
        """Return the value fields that differed for a STALE row.

        Falls back to the full value-field set when a difference cannot be
        computed (the repair still overwrites everything, which is correct).
        """
        differing: list[str] = []
        try:
            if Decimal(str(snapshot.quantity)) != Decimal(str(position.quantity)):
                differing.append("quantity")
            if snapshot.side != position.side:
                differing.append("side")
            if Decimal(str(snapshot.entry_price)) != Decimal(str(position.avg_entry_price)):
                differing.append("entry_price")
        except (TypeError, ValueError, InvalidOperation):
            differing = []
        if not differing:
            differing = list(_POSITION_VALUE_FIELDS)
        return differing


class _DjangoTransactionManager:
    """Production transaction manager using Django's ``transaction.atomic()``."""

    @contextlib.contextmanager
    def atomic(self):
        from django.db import transaction

        with transaction.atomic():
            yield


def get_position_reconciliation_service() -> PositionReconciliationService:
    """Build the service with production infrastructure wiring."""
    from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
    from apps.portfolio.infrastructure.repositories import PositionRepository
    from apps.portfolio_reconciliation.infrastructure.repositories import (
        DriftRecordRepository,
        PositionSnapshotRepository,
    )

    return PositionReconciliationService(
        sources=PositionRepository(),
        snapshots=PositionSnapshotRepository(),
        drift_records=DriftRecordRepository(),
        event_publisher=get_event_bus(),
    )
