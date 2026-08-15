"""MACRO-CONTEXT-1 — FRED provider parsing tests.

The FRED ``series/observations`` contract is fixed by the St. Louis Fed API:
``{realtime_start, realtime_end, date, value}`` rows where ``value`` is a
*string* and ``"."`` means known-missing. These tests pin the mapping to
our provenance model.
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal
from unittest import mock

import pytest
import requests

from apps.macro_context.domain.exceptions import MacroProviderError
from apps.macro_context.infrastructure.providers.fred_provider import (
    FredMacroProvider,
)


def _response(observations: list[dict]) -> dict:
    return {
        "realtime_start": "1990-01-01",
        "realtime_end": "9999-12-31",
        "count": len(observations),
        "offset": 0,
        "limit": 100000,
        "observations": observations,
    }


def _row(
    date_: str,
    value: str,
    realtime_start: str,
    realtime_end: str = "9999-12-31",
) -> dict:
    return {
        "realtime_start": realtime_start,
        "realtime_end": realtime_end,
        "date": date_,
        "value": value,
    }


@pytest.fixture(autouse=True)
def _fred_key(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("django.conf.settings.FRED_API_KEY", "test-api-key")


def _fetch(rows: list[dict]):
    provider = FredMacroProvider()
    with mock.patch("apps.macro_context.infrastructure.providers.fred_provider.requests") as fake_requests:
        response = mock.Mock()
        response.json.return_value = _response(rows)
        response.raise_for_status.return_value = None
        fake_requests.get.return_value = response
        return provider.fetch_observations(
            "DGS10",
            realtime_start=date(1990, 1, 1),
            realtime_end=date(9999, 12, 31),
        ), fake_requests


class TestParsing:
    def test_maps_row_to_provenance(self) -> None:
        rows, _ = _fetch(
            [
                _row("2026-05-01", "4.20", "2026-05-02"),
                _row("2026-05-01", "4.15", "2026-05-06"),  # revision
            ]
        )
        assert len(rows) == 2
        first, revision = rows
        assert first.series_id == "DGS10"
        assert first.provider == "fred"
        assert first.observed_at == date(2026, 5, 1)
        assert first.published_at == datetime(2026, 5, 2, tzinfo=timezone.utc)
        assert first.value == Decimal("4.20")
        assert revision.published_at == datetime(2026, 5, 6, tzinfo=timezone.utc)
        assert revision.value == Decimal("4.15")

    def test_missing_sentinel_maps_to_none(self) -> None:
        rows, _ = _fetch([_row("2026-06-01", ".", "2026-06-03")])
        assert rows[0].value is None
        assert rows[0].value != Decimal(0)

    def test_decimal_uses_full_precision(self) -> None:
        rows, _ = _fetch([_row("2026-04-01", "315.123456", "2026-05-12")])
        assert rows[0].value == Decimal("315.123456")

    def test_passes_realtime_window_to_fred(self) -> None:
        _, fake_requests = _fetch([_row("2026-05-01", "4.20", "2026-05-02")])
        _, kwargs = fake_requests.get.call_args
        params = kwargs["params"]
        assert params["realtime_start"] == "1990-01-01"
        assert params["realtime_end"] == "9999-12-31"
        assert params["file_type"] == "json"
        assert params["api_key"] == "test-api-key"


class TestErrors:
    def test_raises_when_no_api_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("django.conf.settings.FRED_API_KEY", "")
        with pytest.raises(MacroProviderError):
            FredMacroProvider().fetch_observations(
                "DGS10",
                realtime_start=date(1990, 1, 1),
                realtime_end=date(9999, 12, 31),
            )

    def test_raises_on_http_error(self) -> None:
        with mock.patch(
            "apps.macro_context.infrastructure.providers.fred_provider.requests.get"
        ) as fake_get:
            fake_get.side_effect = requests.exceptions.HTTPError("HTTP 429")
            with pytest.raises(MacroProviderError):
                FredMacroProvider().fetch_observations(
                    "DGS10",
                    realtime_start=date(1990, 1, 1),
                    realtime_end=date(9999, 12, 31),
                )

    def test_raises_on_non_json_body(self) -> None:
        with mock.patch(
            "apps.macro_context.infrastructure.providers.fred_provider.requests.get"
        ) as fake_get:
            response = mock.Mock()
            response.raise_for_status.return_value = None
            response.json.side_effect = ValueError("not json")
            fake_get.return_value = response
            with pytest.raises(MacroProviderError):
                FredMacroProvider().fetch_observations(
                    "DGS10",
                    realtime_start=date(1990, 1, 1),
                    realtime_end=date(9999, 12, 31),
                )

    def test_raises_on_malformed_row(self) -> None:
        with pytest.raises(MacroProviderError):
            _fetch([_row("not-a-date", "4.20", "2026-05-02")])


class TestHealthCheck:
    def test_degraded_without_key(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setattr("django.conf.settings.FRED_API_KEY", "")
        report = FredMacroProvider().health_check()
        assert report["status"] == "degraded"

    def test_healthy_with_key(self) -> None:
        report = FredMacroProvider().health_check()
        assert report["status"] == "healthy"
