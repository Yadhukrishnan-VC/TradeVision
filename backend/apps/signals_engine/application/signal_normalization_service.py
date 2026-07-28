from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal
from typing import Any

from core.services import BaseService
from apps.signals_engine.domain.entities import Signal
from apps.signals_engine.domain.exceptions import InvalidSignalPayloadError
from apps.signals_engine.domain.value_objects import SignalDirection


class SignalNormalizationService(BaseService):
    def normalize(
        self,
        raw_payload: dict[str, Any],
        source: str,
        source_alert_id: str,
        account_id: uuid.UUID | None = None,
    ) -> Signal:
        ticker = self._extract_ticker(raw_payload, source)
        direction = self._extract_direction(raw_payload, source)
        timeframe = self._extract_timeframe(raw_payload, source)
        confidence_hint = self._extract_confidence_hint(raw_payload, source)
        indicator_snapshot = self._extract_indicator_snapshot(raw_payload, source)

        return Signal(
            id=uuid.uuid4(),
            account_id=account_id,
            symbol=ticker,
            timeframe=timeframe,
            direction=direction,
            confidence_hint=confidence_hint,
            indicator_snapshot=indicator_snapshot,
            source_alert_id=source_alert_id,
            created_at=datetime.now(timezone.utc),
        )

    def _extract_ticker(self, payload: dict[str, Any], source: str) -> str:
        if source == "tradingview":
            ticker = payload.get("ticker") or payload.get("symbol")
        else:
            ticker = payload.get("symbol") or payload.get("ticker")
        if not ticker:
            raise InvalidSignalPayloadError(
                message="Missing ticker/symbol in signal payload",
                code="MISSING_TICKER",
            )
        return str(ticker).strip().upper()

    def _extract_direction(
        self, payload: dict[str, Any], source: str
    ) -> SignalDirection:
        raw = payload.get("direction") or payload.get("action") or "WAIT"
        raw_upper = str(raw).strip().upper()
        if raw_upper in ("BUY", "LONG", "BULLISH"):
            return SignalDirection.BUY
        if raw_upper in ("SELL", "SHORT", "BEARISH"):
            return SignalDirection.SELL
        return SignalDirection.WAIT

    def _extract_timeframe(self, payload: dict[str, Any], source: str) -> str:
        tf = payload.get("timeframe") or payload.get("interval") or "1h"
        return str(tf).strip()

    def _extract_confidence_hint(self, payload: dict[str, Any], source: str) -> float:
        raw = payload.get("confidence_hint") or payload.get("confidence") or 0.0
        try:
            return float(raw)
        except (TypeError, ValueError):
            return 0.0

    def _extract_indicator_snapshot(
        self, payload: dict[str, Any], source: str
    ) -> dict[str, Any]:
        snapshot = payload.get("indicator_snapshot") or payload.get("indicators") or {}
        if not isinstance(snapshot, dict):
            return {}
        return dict(snapshot)
