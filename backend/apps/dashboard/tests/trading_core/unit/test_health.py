from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from django.utils import timezone as tz

from apps.dashboard.health import check_trading_core_health
from apps.dashboard.infrastructure.common.event_log import EventLog

pytestmark = pytest.mark.django_db


class TestHealth:
    def test_health_returns_degraded_when_no_events(self) -> None:
        result = check_trading_core_health()
        assert result["status"] == "degraded"

    def test_health_returns_healthy_when_recent_events(self) -> None:
        EventLog.objects.create(
            event_id=uuid.uuid4(),
            projector="position_projector",
            applied_at=tz.now(),
        )
        EventLog.objects.create(
            event_id=uuid.uuid4(),
            projector="order_projector",
            applied_at=tz.now(),
        )
        EventLog.objects.create(
            event_id=uuid.uuid4(),
            projector="trade_projector",
            applied_at=tz.now(),
        )
        EventLog.objects.create(
            event_id=uuid.uuid4(),
            projector="portfolio_summary_projector",
            applied_at=tz.now(),
        )

        result = check_trading_core_health()
        assert result["status"] == "healthy"

    def test_health_returns_degraded_when_stale(self) -> None:
        EventLog.objects.create(
            event_id=uuid.uuid4(),
            projector="position_projector",
            applied_at=tz.now() - timedelta(seconds=120),
        )

        result = check_trading_core_health()
        assert result["status"] == "degraded"

    def test_health_detail_contains_projectors(self) -> None:
        result = check_trading_core_health()
        assert "position_projector" in result["detail"]
        assert "order_projector" in result["detail"]
        assert "trade_projector" in result["detail"]
        assert "portfolio_summary_projector" in result["detail"]
