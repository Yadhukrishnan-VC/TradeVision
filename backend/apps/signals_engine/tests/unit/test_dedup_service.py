from __future__ import annotations

from typing import Any

import pytest

from apps.signals_engine.application.dedup_service import DedupService
from apps.signals_engine.infrastructure.models import Signal


class TestDedupService:
    @pytest.fixture
    def service(self) -> DedupService:
        return DedupService()

    def test_not_duplicate_for_new_alert(self, service: DedupService, db: Any) -> None:
        assert service.is_duplicate("new_alert_id") is False

    def test_duplicate_detected_for_existing_alert(self, service: DedupService, db: Any) -> None:
        Signal.objects.create(
            instrument_symbol="RELIANCE",
            timeframe="1h",
            direction="BUY",
            confidence_hint=0.75,
            source_alert_id="dup_alert",
            indicator_snapshot={},
        )
        assert service.is_duplicate("dup_alert") is True

    def test_different_alert_ids_not_duplicates(self, service: DedupService, db: Any) -> None:
        Signal.objects.create(
            instrument_symbol="RELIANCE",
            timeframe="1h",
            direction="BUY",
            confidence_hint=0.75,
            source_alert_id="alert_a",
            indicator_snapshot={},
        )
        assert service.is_duplicate("alert_b") is False
