from __future__ import annotations

import logging

from django.db import transaction

from apps.eventbus.domain.events import DomainEvent
from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
from apps.intelligence.models import PineOutput
from apps.signals_engine.application.dedup_service import DedupService
from apps.signals_engine.application.signal_normalization_service import (
    SignalNormalizationService,
)
from apps.signals_engine.domain.exceptions import InvalidSignalPayloadError
from apps.signals_engine.infrastructure.models import Signal

logger = logging.getLogger(__name__)


def handle_raw_alert_received(event: DomainEvent) -> None:
    payload = event.payload
    raw_payload = payload.get("raw_payload", {})
    source = payload.get("source", "tradingview")
    source_alert_id = str(raw_payload.get("alert_id", str(event.event_id)))

    dedup = DedupService()
    if dedup.is_duplicate(source_alert_id):
        bus = get_event_bus()
        dup_event = DomainEvent.create(
            event_type="signals.SignalDuplicateIgnored",
            payload={
                "source_alert_id": source_alert_id,
                "symbol": raw_payload.get("ticker", raw_payload.get("symbol", "")),
                "reason": "duplicate_within_window",
            },
            correlation_id=event.correlation_id,
            causation_id=event.event_id,
        )
        bus.publish(dup_event)
        return

    normalizer = SignalNormalizationService()
    try:
        signal = normalizer.normalize(
            raw_payload=raw_payload,
            source=source,
            source_alert_id=source_alert_id,
            account_id=payload.get("account_id"),
        )
    except InvalidSignalPayloadError:
        logger.exception("Invalid signal payload, skipping")
        return

    with transaction.atomic():
        signal_row = Signal.objects.create(
            id=signal.id,
            account_id=signal.account_id,
            instrument_symbol=signal.symbol,
            timeframe=signal.timeframe,
            direction=signal.direction.value,
            confidence_hint=signal.confidence_hint,
            indicator_snapshot=signal.indicator_snapshot,
            source_alert_id=signal.source_alert_id,
            created_at=signal.created_at,
        )

        PineOutput.objects.update_or_create(
            symbol=signal.symbol,
            timeframe=signal.timeframe,
            indicator_name="pine_composite",
            defaults={
                "values": signal.indicator_snapshot,
                "detected_timestamp": signal.created_at,
                "source": "tradingview",
            },
        )

    bus = get_event_bus()
    created_event = DomainEvent.create(
        event_type="signals.SignalCreated",
        payload={
            "signal_id": str(signal_row.id),
            "account_id": str(signal.account_id) if signal.account_id else None,
            "symbol": signal.symbol,
            "timeframe": signal.timeframe,
            "direction": signal.direction.value,
            "confidence_hint": signal.confidence_hint,
            "indicator_snapshot": signal.indicator_snapshot,
            "source_alert_id": signal.source_alert_id,
        },
        correlation_id=event.correlation_id,
        causation_id=event.event_id,
    )
    bus.publish(created_event)
