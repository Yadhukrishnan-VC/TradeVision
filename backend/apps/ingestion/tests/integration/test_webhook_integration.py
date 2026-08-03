from __future__ import annotations

import hashlib
import hmac
import json

from django.test import TestCase, override_settings

from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus
from apps.ingestion.infrastructure.models import RawWebhookEvent


def _chartink_signature(body: bytes, shared_secret: str) -> str:
    return hmac.new(
        shared_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


@override_settings(
    TRADINGVIEW_WEBHOOK_TOKEN="test_token_123",
    TRADINGVIEW_ALLOWED_IPS=None,
    EVENT_BUS_IMPLEMENTATION="fake",
)
class TestTradingViewWebhookIntegration(TestCase):
    def setUp(self) -> None:
        reset_event_bus()

    def test_webhook_accepted_and_persisted(self) -> None:
        from apps.eventbus.infrastructure.event_bus_factory import get_event_bus
        from apps.eventbus.infrastructure.fake_event_bus import FakeEventBus

        bus = get_event_bus()
        self.assertIsInstance(bus, FakeEventBus)

        body = {
            "ticker": "RELIANCE",
            "close": 2500.50,
            "time": "2025-03-10T10:00:00Z",
            "volume": 100000,
        }

        request = self.client.post(
            "/api/v1/ingestion/webhooks/tradingview/test_token_123/",
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(request.status_code, 202)
        data = request.json()
        self.assertEqual(data["status"], "accepted")
        self.assertIn("event_id", data)

        raw_events = RawWebhookEvent.objects.all()
        self.assertEqual(raw_events.count(), 1)
        self.assertEqual(raw_events[0].source, "tradingview")
        self.assertTrue(raw_events[0].signature_valid)
        self.assertTrue(raw_events[0].processed)

    def test_webhook_invalid_token_rejected(self) -> None:
        body = {"ticker": "RELIANCE", "close": 2500, "time": "2025-03-10T10:00:00Z"}
        request = self.client.post(
            "/api/v1/ingestion/webhooks/tradingview/wrong_token/",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(request.status_code, 401)

    def test_webhook_missing_fields_rejected(self) -> None:
        body = {"ticker": "RELIANCE"}
        request = self.client.post(
            "/api/v1/ingestion/webhooks/tradingview/test_token_123/",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(request.status_code, 400)


@override_settings(
    CHARTINK_WEBHOOK_TOKEN="chartink_token_456",
    CHARTINK_SHARED_SECRET="shared_secret",
    CHARTINK_ALLOWED_IPS=None,
    EVENT_BUS_IMPLEMENTATION="fake",
)
class TestChartinkWebhookIntegration(TestCase):
    def setUp(self) -> None:
        reset_event_bus()

    def test_webhook_accepted_and_persisted(self) -> None:
        body = {
            "scan_name": "my_scan",
            "symbols": ["RELIANCE", "TCS", "INFY"],
        }
        signature = _chartink_signature(
            json.dumps(body).encode("utf-8"),
            "shared_secret",
        )

        request = self.client.post(
            "/api/v1/ingestion/webhooks/chartink/chartink_token_456/",
            data=json.dumps(body),
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

        self.assertEqual(request.status_code, 202)
        data = request.json()
        self.assertEqual(data["status"], "accepted")

        raw_events = RawWebhookEvent.objects.all()
        self.assertEqual(raw_events.count(), 1)
        self.assertEqual(raw_events[0].source, "chartink")

    def test_webhook_invalid_token_rejected(self) -> None:
        body = {"symbols": ["RELIANCE"]}
        request = self.client.post(
            "/api/v1/ingestion/webhooks/chartink/wrong_token/",
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(request.status_code, 401)
