from __future__ import annotations

import hashlib
import hmac
import json

from django.test import TestCase, override_settings
from django.urls import reverse

from apps.eventbus.infrastructure.event_bus_factory import (
    get_event_bus,
    reset_event_bus,
)
from apps.ingestion.infrastructure.models import RawWebhookEvent
from apps.signals_engine.infrastructure.event_handlers import register_handlers
from apps.signals_engine.infrastructure.models import Signal


def _chartink_signature(body: bytes, shared_secret: str) -> str:
    return hmac.new(
        shared_secret.encode("utf-8"),
        body,
        hashlib.sha256,
    ).hexdigest()


@override_settings(
    TRADINGVIEW_WEBHOOK_TOKEN="tv_url_token_123",
    TRADINGVIEW_ALLOWED_IPS=None,
    EVENT_BUS_IMPLEMENTATION="fake",
)
class TestTradingViewWebhookUrlWiring(TestCase):
    """Prove the TradingView webhook is reachable through Django's URL routing.

    These tests exercise the real application boundary: HTTP request ->
    Django URL resolver -> ingestion view -> persistence -> EventBus.
    """

    def setUp(self) -> None:
        reset_event_bus()

    def test_webhook_url_reverses_to_mounted_path(self) -> None:
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "tv_url_token_123"})
        self.assertEqual(url, "/api/v1/ingestion/webhooks/tradingview/tv_url_token_123/")

    def test_valid_alert_returns_202_and_persists_raw_event(self) -> None:
        body = {
            "ticker": "RELIANCE",
            "close": 2500.50,
            "time": "2025-03-10T10:00:00Z",
            "volume": 100000,
            "direction": "BUY",
            "timeframe": "1h",
            "alert_id": "tv_url_alert_001",
        }
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "tv_url_token_123"})
        response = self.client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "accepted")

        raw_events = RawWebhookEvent.objects.all()
        self.assertEqual(raw_events.count(), 1)
        raw = raw_events[0]
        self.assertEqual(raw.source, "tradingview")
        self.assertTrue(raw.signature_valid)
        self.assertTrue(raw.processed)
        self.assertEqual(raw.raw_body["ticker"], "RELIANCE")

    def test_invalid_token_returns_401(self) -> None:
        body = {"ticker": "RELIANCE", "close": 2500, "time": "2025-03-10T10:00:00Z"}
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "wrong_token"})
        response = self.client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(RawWebhookEvent.objects.count(), 0)

    def test_malformed_json_returns_400(self) -> None:
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "tv_url_token_123"})
        response = self.client.post(
            url,
            data=b"{not valid json",
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(RawWebhookEvent.objects.count(), 0)

    def test_valid_alert_publishes_raw_alert_received(self) -> None:
        body = {
            "ticker": "TCS",
            "close": 4200,
            "time": "2025-03-10T10:00:00Z",
            "alert_id": "tv_url_alert_002",
        }
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "tv_url_token_123"})
        response = self.client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)

        bus = get_event_bus()
        raw_alert_events = [
            e
            for e in bus.published_events
            if e.event_type == "ingestion.RawAlertReceived"
        ]
        self.assertEqual(len(raw_alert_events), 1)
        self.assertEqual(raw_alert_events[0].payload["source"], "tradingview")
        self.assertTrue(raw_alert_events[0].payload["signature_valid"])
        self.assertEqual(raw_alert_events[0].payload["raw_payload"]["ticker"], "TCS")


@override_settings(
    CHARTINK_WEBHOOK_TOKEN="chartink_url_token_456",
    CHARTINK_SHARED_SECRET="chartink_url_secret",
    CHARTINK_ALLOWED_IPS=None,
    EVENT_BUS_IMPLEMENTATION="fake",
)
class TestChartinkWebhookUrlWiring(TestCase):
    """Prove the Chartink webhook is reachable through Django's URL routing."""

    def setUp(self) -> None:
        reset_event_bus()

    def test_webhook_url_reverses_to_mounted_path(self) -> None:
        url = reverse("ingestion:chartink-webhook", kwargs={"token": "chartink_url_token_456"})
        self.assertEqual(url, "/api/v1/ingestion/webhooks/chartink/chartink_url_token_456/")

    def test_valid_scan_returns_202(self) -> None:
        body = {"scan_name": "momentum", "symbols": ["RELIANCE", "TCS", "INFY"]}
        raw_body = json.dumps(body).encode("utf-8")
        signature = _chartink_signature(raw_body, "chartink_url_secret")

        url = reverse("ingestion:chartink-webhook", kwargs={"token": "chartink_url_token_456"})
        response = self.client.post(
            url,
            data=raw_body,
            content_type="application/json",
            HTTP_X_SIGNATURE=signature,
        )

        self.assertEqual(response.status_code, 202)
        data = response.json()
        self.assertEqual(data["status"], "accepted")

        raw_events = RawWebhookEvent.objects.all()
        self.assertEqual(raw_events.count(), 1)
        self.assertEqual(raw_events[0].source, "chartink")
        self.assertTrue(raw_events[0].signature_valid)
        self.assertTrue(raw_events[0].processed)

    def test_invalid_token_returns_401(self) -> None:
        body = {"scan_name": "momentum", "symbols": ["RELIANCE"]}
        url = reverse("ingestion:chartink-webhook", kwargs={"token": "wrong_token"})
        response = self.client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(RawWebhookEvent.objects.count(), 0)

    def test_invalid_signature_returns_401(self) -> None:
        body = {"scan_name": "momentum", "symbols": ["RELIANCE"]}
        url = reverse("ingestion:chartink-webhook", kwargs={"token": "chartink_url_token_456"})
        response = self.client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
            HTTP_X_SIGNATURE="not-the-correct-signature",
        )
        self.assertEqual(response.status_code, 401)
        self.assertEqual(RawWebhookEvent.objects.count(), 0)


@override_settings(
    TRADINGVIEW_WEBHOOK_TOKEN="tv_e2e_token",
    TRADINGVIEW_ALLOWED_IPS=None,
    EVENT_BUS_IMPLEMENTATION="fake",
)
class TestWebhookToSignalsEnginePipeline(TestCase):
    """End-to-end proof across the real application boundary:

    HTTP TradingView webhook
        -> apps.ingestion view
        -> RawWebhookEvent (persistence)
        -> ingestion.RawAlertReceived (EventBus publish)
        -> signals_engine handler (subscription)
        -> Signal + PineOutput (normalization/dedup persistence)
    """

    def setUp(self) -> None:
        reset_event_bus()
        register_handlers(get_event_bus())

    def test_webhook_flows_through_to_signal_creation(self) -> None:
        from apps.intelligence.models import PineOutput

        body = {
            "ticker": "RELIANCE",
            "close": 2850.50,
            "time": "2026-07-28T10:00:00Z",
            "volume": 5000000,
            "direction": "BUY",
            "timeframe": "1h",
            "confidence_hint": 0.75,
            "indicator_snapshot": {
                "rsi_14": 62.5,
                "macd": 12.30,
                "ema_20": 2830.00,
            },
            "alert_id": "tv_e2e_alert_001",
        }
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "tv_e2e_token"})
        response = self.client.post(
            url,
            data=json.dumps(body),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 202)

        self.assertEqual(RawWebhookEvent.objects.count(), 1)
        self.assertTrue(RawWebhookEvent.objects.first().processed)

        signal = Signal.objects.get(source_alert_id="tv_e2e_alert_001")
        self.assertEqual(signal.instrument_symbol, "RELIANCE")
        self.assertEqual(signal.direction, "BUY")
        self.assertEqual(signal.timeframe, "1h")

        pine = PineOutput.objects.get(
            symbol="RELIANCE",
            timeframe="1h",
            indicator_name="pine_composite",
        )
        self.assertEqual(pine.values.get("rsi_14"), 62.5)

        bus = get_event_bus()
        event_types = [e.event_type for e in bus.published_events]
        self.assertIn("ingestion.RawAlertReceived", event_types)
        self.assertIn("signals.SignalCreated", event_types)

    def test_replayed_webhook_is_deduplicated_by_signals_engine(self) -> None:
        body = {
            "ticker": "INFY",
            "close": 1850,
            "time": "2026-07-28T10:00:00Z",
            "direction": "SELL",
            "timeframe": "1h",
            "alert_id": "tv_e2e_alert_dedup",
        }
        url = reverse("ingestion:tradingview-webhook", kwargs={"token": "tv_e2e_token"})
        for _ in range(2):
            response = self.client.post(
                url,
                data=json.dumps(body),
                content_type="application/json",
            )
            self.assertEqual(response.status_code, 202)

        signals = Signal.objects.filter(source_alert_id="tv_e2e_alert_dedup")
        self.assertEqual(signals.count(), 1)

        bus = get_event_bus()
        duplicate_events = [
            e
            for e in bus.published_events
            if e.event_type == "signals.SignalDuplicateIgnored"
        ]
        self.assertEqual(len(duplicate_events), 1)
