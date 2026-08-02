from __future__ import annotations

import logging
import uuid
from decimal import Decimal
from uuid import UUID

from django.utils import timezone

from apps.dashboard.infrastructure.trading_core.models import PositionSnapshot
from apps.dashboard.projection.base import BaseProjectionService
from apps.dashboard.projection.internal_events import DashboardInternalEvent, publish_internal
from apps.eventbus.domain.events import DomainEvent


class PositionProjectionService(BaseProjectionService):
    name = "position_projector"

    def _apply(self, event: DomainEvent) -> None:
        event_type = event.event_type

        if event_type == "positions.PositionOpened":
            self._apply_opened(event)
        elif event_type == "positions.PositionQuantityChanged":
            self._apply_quantity_changed(event)
        elif event_type == "positions.PositionClosed":
            self._apply_closed(event)
        elif event_type == "marketdata.PriceTick":
            pass
        else:
            logger.warning(
                "Unhandled event type in PositionProjectionService",
                extra={"event_type": event_type, "event_id": str(event.event_id)},
            )

    def _apply_opened(self, event: DomainEvent) -> None:
        payload = event.payload
        account_id = self._get_account_id(event)

        position = PositionSnapshot(
            position_id=UUID(payload["position_id"]),
            account_id=account_id,
            symbol=payload["symbol"],
            side=payload["side"],
            quantity=Decimal(str(payload["quantity"])),
            entry_price=Decimal(str(payload["entry_price"])),
            is_open=True,
            opened_at=timezone.now(),
        )
        self._update_projection_metadata(position, event)
        position.save()

        self._fire_projected_event(position, event)

    def _apply_quantity_changed(self, event: DomainEvent) -> None:
        payload = event.payload
        position_id = UUID(payload["position_id"])
        account_id = self._get_account_id(event)

        try:
            position = PositionSnapshot.objects.get(position_id=position_id, account_id=account_id)
        except PositionSnapshot.DoesNotExist:
            return

        position.quantity = Decimal(str(payload.get("quantity", position.quantity)))

        if "entry_price" in payload:
            position.entry_price = Decimal(str(payload["entry_price"]))

        self._update_projection_metadata(position, event)
        position.save()

        self._fire_projected_event(position, event)

    def _apply_closed(self, event: DomainEvent) -> None:
        payload = event.payload
        position_id = UUID(payload["position_id"])
        account_id = self._get_account_id(event)

        try:
            position = PositionSnapshot.objects.get(position_id=position_id, account_id=account_id)
        except PositionSnapshot.DoesNotExist:
            return

        position.is_open = False
        position.closed_at = timezone.now()
        self._update_projection_metadata(position, event)
        position.save()

        self._fire_projected_event(position, event)

    def _fire_projected_event(self, position: PositionSnapshot, event: DomainEvent) -> None:
        internal_event = DashboardInternalEvent.create(
            event_type="position_snapshot_projected",
            payload={
                "account_id": str(position.account_id),
                "position_id": str(position.position_id),
                "is_open": position.is_open,
            },
            source_event_id=event.event_id,
        )
        publish_internal(internal_event)


logger = logging.getLogger(__name__)
