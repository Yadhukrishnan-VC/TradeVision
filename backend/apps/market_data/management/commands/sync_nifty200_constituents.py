"""
Management command: sync_nifty200_constituents

Populate the ``IndexConstituent`` table — the source-of-truth polling
universe — from the official NIFTY index constituents CSV.

The CSV is fetched over HTTPS from the NSE/NSE-indices publisher (configurable
via ``NIFTY200_CSV_URL``) and upserted weekly by Celery Beat
(``sync-nifty200-constituents`` entry in ``CELERY_BEAT_SCHEDULE``). Symbols
listed in the latest CSV are marked active; previously-stored members no
longer in the CSV are deactivated (the CSV is authoritative, so a delisting
must never linger in the active universe).

Usage::

    python manage.py sync_nifty200_constituents
    python manage.py sync_nifty200_constituents --source-url file:///tmp/list.csv
    python manage.py sync_nifty200_constituents --index NIFTY100 --exchange NSE
"""

from __future__ import annotations

import csv
import io
import logging
from typing import Any
from urllib.request import urlopen

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from apps.market_data.application.universe_service import upsert_constituents

logger = logging.getLogger(__name__)


class Command(BaseCommand):
    help = "Sync the IndexConstituent table from the official NIFTY index CSV."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--source-url",
            dest="source_url",
            default="",
            help="Override the NIFTY constituents CSV URL (default: settings.NIFTY200_CSV_URL).",
        )
        parser.add_argument(
            "--index",
            dest="index_name",
            default="NIFTY200",
            help="Index name to store the constituents under (default: NIFTY200).",
        )
        parser.add_argument(
            "--exchange",
            dest="exchange",
            default="NSE",
            help="Exchange for the constituents (default: NSE).",
        )

    def handle(self, *args: Any, **options: Any) -> None:
        source_url = options["source_url"] or getattr(
            settings, "NIFTY200_CSV_URL", ""
        )
        if not source_url:
            raise CommandError(
                "No source URL configured. Set NIFTY200_CSV_URL or pass --source-url."
            )

        index_name = options["index_name"]
        exchange = options["exchange"]

        self.stdout.write(f"Fetching constituents CSV: {source_url}")
        rows = self._fetch_rows(source_url)

        summary = upsert_constituents(rows, index_name=index_name, exchange=exchange)
        total = summary["created"] + summary["updated"]
        self.stdout.write(
            self.style.SUCCESS(
                f"IndexConstituent sync complete: {total} active ({summary['created']} "
                f"created, {summary['updated']} updated), {summary['deactivated']} deactivated."
            )
        )

    def _fetch_rows(self, source_url: str) -> list[dict[str, Any]]:
        try:
            with urlopen(source_url, timeout=60) as response:
                raw = response.read().decode("utf-8-sig")
        except Exception as exc:  # noqa: BLE001 — surface any fetch failure cleanly
            raise CommandError(
                f"Failed to fetch constituents CSV from {source_url}: {exc}"
            ) from exc

        reader = csv.DictReader(io.StringIO(raw))
        return list(reader)