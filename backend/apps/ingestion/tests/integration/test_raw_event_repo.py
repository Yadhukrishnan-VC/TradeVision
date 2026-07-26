from __future__ import annotations

from datetime import datetime, timedelta, timezone

from django.test import TestCase
from django.utils import timezone as django_timezone

from apps.ingestion.infrastructure.models import RawWebhookEvent
from apps.ingestion.infrastructure.repositories import RawWebhookEventRepository


class TestRawWebhookEventRepository(TestCase):
    def setUp(self) -> None:
        self.repo = RawWebhookEventRepository()

    def test_create_event(self) -> None:
        event = self.repo.create(
            source="tradingview",
            raw_body={"ticker": "RELIANCE", "close": 2500},
            headers={"Content-Type": "application/json"},
            signature_valid=True,
        )
        self.assertIsNotNone(event.id)
        self.assertEqual(event.source, "tradingview")
        self.assertTrue(event.signature_valid)
        self.assertFalse(event.processed)

    def test_find_unprocessed_older_than(self) -> None:
        old_time = django_timezone.now() - timedelta(minutes=10)
        event = RawWebhookEvent.objects.create(
            source="tradingview",
            raw_body={"test": "data"},
            processed=False,
        )
        RawWebhookEvent.objects.filter(pk=event.pk).update(received_at=old_time)

        unprocessed = self.repo.find_unprocessed(older_than_minutes=2)
        self.assertIn(event, unprocessed)

    def test_find_unprocessed_excludes_recent(self) -> None:
        self.repo.create(
            source="tradingview",
            raw_body={"test": "data"},
            signature_valid=True,
        )

        unprocessed = self.repo.find_unprocessed(older_than_minutes=5)
        self.assertEqual(len(unprocessed), 0)

    def test_mark_processed(self) -> None:
        event = self.repo.create(
            source="chartink",
            raw_body={"scan": "test"},
            signature_valid=True,
        )
        self.assertFalse(event.processed)

        self.repo.mark_processed(event.id)
        event.refresh_from_db()
        self.assertTrue(event.processed)

    def test_count_unprocessed(self) -> None:
        self.repo.create(source="tradingview", raw_body={"a": 1})
        self.repo.create(source="chartink", raw_body={"b": 2})
        self.repo.create(source="tradingview", raw_body={"c": 3})

        count = self.repo.count_unprocessed()
        self.assertEqual(count, 3)
