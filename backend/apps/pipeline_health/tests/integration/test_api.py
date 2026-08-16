from __future__ import annotations

import uuid
from datetime import datetime, timedelta, timezone

import pytest
from rest_framework import status
from rest_framework.test import APIClient

from apps.pipeline_health.infrastructure.models import (
    PipelineHealthSnapshot,
    StageHeartbeat,
)

pytestmark = pytest.mark.django_db

PATH = "/api/v1/pipeline-health/"

NOW = datetime(2026, 8, 11, 9, 30, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _register(register_consumers):
    register_consumers()
    yield


def _seed_heartbeat(stage: str, symbol_scope: str) -> None:
    StageHeartbeat.objects.create(
        stage=stage,
        symbol_scope=symbol_scope,
        last_event_at=NOW - timedelta(seconds=10),
        last_event_id=uuid.uuid4(),
        last_correlation_id=uuid.uuid4(),
    )


def _seed_snapshot() -> PipelineHealthSnapshot:
    return PipelineHealthSnapshot.objects.create(
        evaluated_at=NOW,
        overall_status="HEALTHY",
        stage_statuses={"MARKET_DATA": "HEALTHY"},
    )


class TestPipelineHealthAPI:
    def test_requires_authentication(self, api_client: APIClient) -> None:
        response = api_client.get(PATH)

        # With the global authenticators registered, an unauthenticated request
        # to a protected endpoint raises NotAuthenticated -> 401 (not 403).
        assert response.status_code == status.HTTP_401_UNAUTHORIZED

    def test_returns_heartbeats_when_no_snapshot_yet(
        self, api_client: APIClient, user
    ) -> None:
        api_client.force_authenticate(user=user)
        _seed_heartbeat("MARKET_DATA", "RELIANCE")

        response = api_client.get(PATH)

        assert response.status_code == status.HTTP_200_OK
        assert "snapshot" not in response.data
        assert len(response.data["heartbeats"]) == 1
        assert response.data["heartbeats"][0]["stage"] == "MARKET_DATA"
        assert response.data["heartbeats"][0]["symbol_scope"] == "RELIANCE"

    def test_returns_latest_snapshot_with_heartbeats(
        self, api_client: APIClient, user
    ) -> None:
        api_client.force_authenticate(user=user)
        _seed_heartbeat("MARKET_DATA", "RELIANCE")
        _seed_snapshot()

        response = api_client.get(PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["snapshot"]["overall_status"] == "HEALTHY"
        assert response.data["snapshot"]["evaluated_at"] is not None
        assert response.data["snapshot"]["stage_statuses"] == {"MARKET_DATA": "HEALTHY"}
        assert len(response.data["heartbeats"]) == 1

    def test_returns_latest_snapshot_not_oldest(
        self, api_client: APIClient, user
    ) -> None:
        api_client.force_authenticate(user=user)
        PipelineHealthSnapshot.objects.create(
            evaluated_at=NOW - timedelta(minutes=5),
            overall_status="HEALTHY",
            stage_statuses={},
        )
        PipelineHealthSnapshot.objects.create(
            evaluated_at=NOW,
            overall_status="STALLED",
            stage_statuses={"RULE_ENGINE": "STALLED"},
        )

        response = api_client.get(PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["snapshot"]["overall_status"] == "STALLED"

    def test_market_data_heartbeat_uses_resolved_symbol(
        self, api_client: APIClient, user, instrument
    ) -> None:
        api_client.force_authenticate(user=user)
        _seed_heartbeat("MARKET_DATA", instrument.tradingsymbol)

        response = api_client.get(PATH)

        assert response.status_code == status.HTTP_200_OK
        assert response.data["heartbeats"][0]["symbol_scope"] == "RELIANCE"
