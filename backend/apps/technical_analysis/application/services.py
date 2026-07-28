from __future__ import annotations

import logging
import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from apps.common.domain.value_objects import IdempotencyKey
from apps.eventbus.domain.events import DomainEvent
from apps.technical_analysis.domain.entities import TASnapshot
from apps.technical_analysis.domain.exceptions import (
    InvalidFieldValueError,
    InvalidTechnicalAnalysisPayloadError,
    MissingRequiredFieldError,
    SnapshotPersistenceError,
)
from apps.technical_analysis.domain.value_objects import PineMetadata

logger = logging.getLogger(__name__)

CANONICAL_FIELD_MAP: dict[str, str] = {
    "ticker": "ticker",
    "symbol": "ticker",
    "exchange": "exchange",
    "timeframe": "timeframe",
    "interval": "timeframe",
    "close": "close",
    "price": "close",
    "high": "high",
    "low": "low",
    "open": "open",
    "volume": "volume",
    "time": "time",
    "timestamp": "time",
    "date": "time",
    "strategy": "strategy",
    "order": "order",
    "action": "action",
    "position_size": "position_size",
    "pine_id": "pine_id",
    "pine_version": "pine_version",
    "pine_timestamp": "pine_timestamp",
}

REQUIRED_FIELDS: set[str] = {"ticker", "close"}


class TechnicalAnalysisIngestionService:
    """Ingests TradingView technical analysis webhook payloads.

    Responsibilities:
        1. Validate payload structure and required fields.
        2. Normalise field names to a canonical schema.
        3. Extract Pine Script metadata.
        4. Separate indicator values from known metadata fields.
        5. Persist a ``TASnapshot`` via the repository.
        6. Publish a ``technical_analysis.TechnicalAnalysisCompleted``
           domain event.
    """

    def __init__(
        self,
        repository: Any,
        event_bus: Any,
    ) -> None:
        self._repository = repository
        self._event_bus = event_bus

    def ingest(
        self,
        raw_payload: dict[str, Any],
        correlation_id: uuid.UUID | None = None,
    ) -> TASnapshot:
        """Validate, normalise, persist, and publish a TA snapshot.

        Args:
            raw_payload:   The raw webhook payload as a dict.
            correlation_id: Correlation UUID for event tracing.

        Returns:
            The persisted ``TASnapshot`` domain entity.

        Raises:
            MissingRequiredFieldError:   If a required field is missing.
            InvalidFieldValueError:      If a field has an invalid value.
            SnapshotPersistenceError:    If database persistence fails.
        """
        validated = self.validate(raw_payload)
        normalised = self.normalise(validated)
        snapshot = self._build_snapshot(normalised, raw_payload)

        try:
            persisted = self._repository.save(snapshot)
        except Exception as exc:
            logger.error(
                "ta_snapshot_persist_failed",
                extra={"error": str(exc), "symbol": snapshot.symbol},
            )
            raise SnapshotPersistenceError(
                message=f"Failed to persist TA snapshot: {exc}",
                code="SNAPSHOT_PERSIST_FAILED",
                details={"original_error": str(exc)},
            ) from exc

        self._publish_completed(persisted, correlation_id)

        logger.info(
            "ta_snapshot_ingested",
            extra={
                "snapshot_id": str(persisted.id),
                "symbol": persisted.symbol,
                "exchange": persisted.exchange,
                "timeframe": persisted.timeframe,
                "indicator_count": len(persisted.indicators),
            },
        )

        return persisted

    def validate(self, raw_payload: dict[str, Any]) -> dict[str, Any]:
        """Validate the raw payload and return a cleaned copy.

        Args:
            raw_payload: The raw webhook payload.

        Returns:
            A validated payload dict (values may be coerced).

        Raises:
            MissingRequiredFieldError: If required fields are absent.
            InvalidFieldValueError:    If field values are semantically
                invalid.
        """
        if not isinstance(raw_payload, dict):
            raise InvalidTechnicalAnalysisPayloadError(
                message="Payload must be a JSON object",
                code="INVALID_PAYLOAD_TYPE",
            )

        payload = {k.lower().strip(): v for k, v in raw_payload.items()}

        normalised_keys = set()
        for raw_key in payload:
            canonical = CANONICAL_FIELD_MAP.get(raw_key, raw_key)
            normalised_keys.add(canonical)

        missing = REQUIRED_FIELDS - normalised_keys
        if missing:
            raise MissingRequiredFieldError(
                message=f"Missing required fields: {', '.join(sorted(missing))}",
                code="MISSING_REQUIRED_FIELDS",
                details={"missing_fields": list(missing)},
            )

        canonical_payload: dict[str, Any] = {}
        for raw_key, value in payload.items():
            canonical = CANONICAL_FIELD_MAP.get(raw_key, raw_key)
            canonical_payload[canonical] = value

        ticker = str(canonical_payload.get("ticker", "")).strip()
        if not ticker:
            raise MissingRequiredFieldError(
                message="ticker/symbol cannot be empty",
                code="EMPTY_TICKER",
            )

        close = canonical_payload.get("close")
        if close is None:
            raise MissingRequiredFieldError(
                message="close/price is required",
                code="MISSING_CLOSE",
            )

        return canonical_payload

    def normalise(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalise field names to canonical keys.

        Known field names are mapped to the canonical form.
        Unknown fields are assumed to be indicator values and
        are preserved under their original key.

        Args:
            payload: A validated payload dict with lowercased keys.

        Returns:
            A normalised dict with canonical field names.
        """
        normalised: dict[str, Any] = {}
        for raw_key, value in payload.items():
            canonical = CANONICAL_FIELD_MAP.get(raw_key, raw_key)
            if canonical == "time" and isinstance(value, (int, float)):
                normalised["snapshot_timestamp"] = datetime.fromtimestamp(
                    value / 1000, tz=timezone.utc
                )
            if canonical in CANONICAL_FIELD_MAP.values():
                normalised[canonical] = value
            else:
                normalised.setdefault("indicators", {})[canonical] = value
        return normalised

    def _build_snapshot(
        self,
        normalised: dict[str, Any],
        raw_payload: dict[str, Any],
    ) -> TASnapshot:
        """Build a ``TASnapshot`` domain entity from a normalised payload."""
        ticker = str(normalised.get("ticker", ""))
        exchange = str(normalised.get("exchange", ""))
        timeframe = str(normalised.get("timeframe", ""))

        snapshot_timestamp = normalised.get("snapshot_timestamp")
        if snapshot_timestamp is None:
            raw_time = normalised.get("time")
            if isinstance(raw_time, (int, float)):
                snapshot_timestamp = datetime.fromtimestamp(
                    raw_time / 1000, tz=timezone.utc
                )
            else:
                snapshot_timestamp = datetime.now(timezone.utc)

        pine_metadata = PineMetadata(
            pine_id=str(normalised.get("pine_id", "")),
            pine_version=str(normalised.get("pine_version", "")),
            pine_timestamp=normalised.get("pine_timestamp"),
        )

        indicators = dict(normalised.get("indicators", {}))

        return TASnapshot(
            symbol=ticker.upper(),
            exchange=exchange.upper() if exchange else exchange,
            timeframe=timeframe,
            indicators=indicators,
            pine_metadata=pine_metadata,
            raw_payload=raw_payload,
            snapshot_timestamp=snapshot_timestamp,
        )

    def _publish_completed(
        self,
        snapshot: TASnapshot,
        correlation_id: uuid.UUID | None,
    ) -> None:
        """Publish a ``technical_analysis.TechnicalAnalysisCompleted`` event."""
        if correlation_id is None:
            correlation_source = f"technical_analysis:{snapshot.symbol}:{snapshot.snapshot_timestamp.isoformat()}"
            correlation_id = uuid.UUID(
                hex=IdempotencyKey.generate(correlation_source).value[:32],
            )

        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload={
                "snapshot_id": str(snapshot.id),
                "symbol": snapshot.symbol,
                "exchange": snapshot.exchange,
                "timeframe": snapshot.timeframe,
                "snapshot_timestamp": snapshot.snapshot_timestamp.isoformat(),
                "indicator_keys": list(snapshot.indicators.keys()),
                "pine_id": snapshot.pine_metadata.pine_id,
                "pine_version": snapshot.pine_metadata.pine_version,
            },
            correlation_id=correlation_id,
            version=1,
        )
        self._event_bus.publish(event)
