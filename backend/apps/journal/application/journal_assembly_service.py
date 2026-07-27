from __future__ import annotations

import logging
from decimal import Decimal
from uuid import UUID

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.journal.domain.exceptions import JournalEntryNotFound
from apps.journal.infrastructure.models import JournalEntry, JournalEventLog

logger = logging.getLogger(__name__)

CONSUMER_GROUP = "journal"

OUTCOME_WON = "won"
OUTCOME_LOST = "lost"
OUTCOME_BREAKEVEN = "breakeven"
OUTCOME_NO_TRADE = "no_trade"


class JournalAssemblyService:
    def handle(self, event: DomainEvent) -> None:
        if JournalEventLog.objects.has_been_applied(event.event_id, CONSUMER_GROUP):
            return

        event_type = event.event_type
        if event_type.startswith("signals."):
            self._handle_signal_created(event)
        elif event_type.startswith("decisions."):
            self._handle_decision_made(event)
        elif event_type.startswith("orders."):
            self._handle_order_event(event)
        elif event_type.startswith("positions."):
            self._handle_position_event(event)
        elif event_type.startswith("risk."):
            self._handle_risk_event(event)
        else:
            return

        JournalEventLog.objects.mark_applied(event.event_id, CONSUMER_GROUP)

    def _handle_signal_created(self, event: DomainEvent) -> None:
        correlation_id = event.correlation_id
        account_id = UUID(event.payload["account_id"])
        JournalEntry.objects.update_or_create(
            correlation_id=correlation_id,
            defaults={
                "account_id": account_id,
                "signal_snapshot": event.payload,
            },
        )

    def _handle_decision_made(self, event: DomainEvent) -> None:
        correlation_id = event.correlation_id
        account_id = UUID(event.payload["account_id"])
        JournalEntry.objects.update_or_create(
            correlation_id=correlation_id,
            defaults={
                "account_id": account_id,
                "decision_snapshot": event.payload,
            },
        )

    def _handle_order_event(self, event: DomainEvent) -> None:
        correlation_id = event.correlation_id
        entry, _ = JournalEntry.objects.get_or_create(
            correlation_id=correlation_id,
            defaults={"account_id": UUID(event.payload["account_id"])},
        )
        order_event = {
            "event_type": event.event_type,
            "event_id": str(event.event_id),
            "occurred_at": event.occurred_at.isoformat(),
            "payload": event.payload,
        }
        updated_events = list(entry.order_events) + [order_event]
        JournalEntry.objects.filter(pk=entry.pk).update(order_events=updated_events)

    def _handle_position_event(self, event: DomainEvent) -> None:
        correlation_id = event.correlation_id
        event_type = event.event_type

        if event_type == "positions.PositionOpened":
            entry, _ = JournalEntry.objects.get_or_create(
                correlation_id=correlation_id,
                defaults={"account_id": UUID(event.payload["account_id"])},
            )
            JournalEntry.objects.filter(pk=entry.pk).update(
                position_id=UUID(event.payload["position_id"]),
            )
        elif event_type == "positions.PositionClosed":
            try:
                entry = JournalEntry.objects.get(correlation_id=correlation_id)
            except JournalEntry.DoesNotExist:
                logger.warning(
                    "PositionClosed event received but no journal entry found",
                    extra={"correlation_id": str(correlation_id)},
                )
                return

            realized_pnl = Decimal(str(event.payload.get("realized_pnl", 0)))
            outcome = self._determine_outcome(realized_pnl)

            JournalEntry.objects.filter(pk=entry.pk).update(
                outcome=outcome,
                realized_pnl=realized_pnl,
                finalized=True,
                finalized_at=event.occurred_at,
            )

            self._publish_entry_finalized(entry.correlation_id, entry.account_id, outcome, realized_pnl, event.occurred_at, event.event_id)

    def _handle_risk_event(self, event: DomainEvent) -> None:
        pass

    def _determine_outcome(self, realized_pnl: Decimal) -> str:
        if realized_pnl > 0:
            return OUTCOME_WON
        elif realized_pnl < 0:
            return OUTCOME_LOST
        return OUTCOME_BREAKEVEN

    def _publish_entry_finalized(
        self,
        correlation_id: UUID,
        account_id: UUID,
        outcome: str,
        realized_pnl: Decimal,
        finalized_at: object,
        causation_id: UUID,
    ) -> None:
        event = DomainEvent.create(
            event_type="journal.EntryFinalized",
            payload={
                "correlation_id": str(correlation_id),
                "account_id": str(account_id),
                "outcome": outcome,
                "realized_pnl": str(realized_pnl),
                "finalized_at": finalized_at.isoformat() if hasattr(finalized_at, "isoformat") else str(finalized_at),
            },
            correlation_id=correlation_id,
            causation_id=causation_id,
        )
        try:
            bus = get_event_bus()
            bus.publish(event)
        except Exception:
            logger.exception(
                "Failed to publish EntryFinalized event",
                extra={"correlation_id": str(correlation_id)},
            )
