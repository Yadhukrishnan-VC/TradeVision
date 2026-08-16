from __future__ import annotations

import json
from unittest.mock import patch

import pytest
from django.test.utils import override_settings

from apps.technical_analysis.infrastructure.models import TASnapshot


@pytest.fixture(autouse=True)
def _mock_event_bus():
    with patch(
        "apps.technical_analysis.interfaces.api.views.get_event_bus"
    ) as mock:
        yield mock


@pytest.fixture(autouse=True)
def _override_test_settings():
    with override_settings(
        ROOT_URLCONF="apps.technical_analysis.tests.test_urls",
        TRADINGVIEW_TA_WEBHOOK_TOKEN="test_ta_token_456",
    ):
        yield


def _get_url(token: str = "test_ta_token_456") -> str:
    return f"/api/v1/technical-analysis/webhooks/tradingview/{token}/"


@pytest.mark.django_db
class TestTradingViewTAWebhookEndpoint:
    def test_happy_path_returns_202(self, api_client) -> None:
        payload = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "exchange": "NSE",
            "timeframe": "15min",
            "rsi": 62.5,
            "pine_id": "test_script",
            "pine_version": "5",
        }

        response = api_client.post(
            _get_url(),
            data=json.dumps(payload),
            content_type="application/json",
        )

        assert response.status_code == 202
        data = response.json()
        assert data["status"] == "accepted"
        assert "snapshot_id" in data

    def test_persists_snapshot_in_database(self, api_client) -> None:
        payload = {
            "ticker": "TCS",
            "close": 3500.00,
            "exchange": "NSE",
            "rsi": 58.0,
        }

        response = api_client.post(
            _get_url(),
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 202

        snapshot = TASnapshot.objects.first()
        assert snapshot is not None
        assert snapshot.symbol == "TCS"
        assert snapshot.exchange == "NSE"
        assert snapshot.indicators["rsi"] == 58.0

    def test_invalid_token_returns_401(self, api_client) -> None:
        payload = {"ticker": "RELIANCE", "close": 2850.50}

        response = api_client.post(
            _get_url(token="wrong_token"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 401
        assert response.json() == {"error": "Invalid token"}

    def test_token_compared_with_constant_time(self, api_client) -> None:
        payload = {"ticker": "RELIANCE", "close": 2850.50}

        with patch(
            "apps.technical_analysis.interfaces.api.views.hmac.compare_digest"
        ) as mock_cmp:
            mock_cmp.return_value = False
            response = api_client.post(
                _get_url(token="wrong_token"),
                data=json.dumps(payload),
                content_type="application/json",
            )
            assert response.status_code == 401
            mock_cmp.assert_called_once()

    def test_missing_required_fields_returns_400(
        self, api_client
    ) -> None:
        payload = {"ticker": "RELIANCE"}

        response = api_client.post(
            _get_url(),
            data=json.dumps(payload),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_invalid_json_returns_400(self, api_client) -> None:
        response = api_client.post(
            _get_url(),
            data=b"not valid json",
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_non_dict_json_returns_400(self, api_client) -> None:
        response = api_client.post(
            _get_url(),
            data=json.dumps([1, 2, 3]),
            content_type="application/json",
        )
        assert response.status_code == 400

    def test_pine_metadata_preserved(self, api_client) -> None:
        payload = {
            "ticker": "INFY",
            "close": 1700.00,
            "pine_id": "my_pine_script_v2",
            "pine_version": "5",
            "pine_timestamp": 1699000000000,
        }

        api_client.post(
            _get_url(),
            data=json.dumps(payload),
            content_type="application/json",
        )

        snapshot = TASnapshot.objects.first()
        assert snapshot.pine_id == "my_pine_script_v2"
        assert snapshot.pine_version == "5"
        assert snapshot.pine_timestamp == 1699000000000

    def test_raw_payload_preserved_verbatim(self, api_client) -> None:
        payload = {
            "ticker": "HDFC",
            "close": 1600.00,
            "custom_field": "preserved_value",
        }

        api_client.post(
            _get_url(),
            data=json.dumps(payload),
            content_type="application/json",
        )

        snapshot = TASnapshot.objects.first()
        assert snapshot.raw_payload["ticker"] == "HDFC"
        assert snapshot.raw_payload["custom_field"] == "preserved_value"

    @override_settings(TRADINGVIEW_TA_WEBHOOK_TOKEN="")
    def test_not_configured_returns_501(self, api_client) -> None:
        response = api_client.post(
            _get_url(token="some_token"),
            data=json.dumps({"ticker": "X", "close": 1.0}),
            content_type="application/json",
        )
        assert response.status_code == 501