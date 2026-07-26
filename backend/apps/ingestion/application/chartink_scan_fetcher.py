from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import Any

import requests

from apps.ingestion.domain.value_objects import WebhookSource
from core.exceptions import DataIngestionError
from core.redis_client import get_redis_client
from core.resilience.circuit_breaker import CircuitBreaker, CircuitBreakerOpenError

logger = logging.getLogger(__name__)

_CHARTINK_BASE_URL = "https://chartink.com"
_CHARTINK_SCAN_ENDPOINT = "/screener/process"


class ChartinkScanFetcher:
    """Polls Chartink for scan results and returns normalised symbol lists.

    Chartink does not offer a public webhook API, so we poll their
    screener endpoint on a schedule. Results are wrapped in a circuit
    breaker for resilience.

    Args:
        scan_name:       The Chartink scan identifier.
        scan_id:         The numeric ID of the scan to run.
        shared_secret:   Optional shared secret for ``X-Signature`` header.
        breaker_name:    Name for the circuit breaker (default:
                         ``"chartink-scan"``).
    """

    def __init__(
        self,
        scan_name: str,
        scan_id: int,
        shared_secret: str | None = None,
        breaker_name: str = "chartink-scan",
    ) -> None:
        self._scan_name = scan_name
        self._scan_id = scan_id
        self._shared_secret = shared_secret
        self._redis = get_redis_client()
        self._breaker = CircuitBreaker(
            name=breaker_name,
            redis_client=self._redis,
        )

    def fetch(self) -> dict[str, Any]:
        """Execute the scan and return results.

        Returns:
            A dict with keys:
                - ``scan_name``: The configured scan name.
                - ``symbols``: List of matching trading symbols.
                - ``received_at``: ISO 8601 timestamp of the fetch.

        Raises:
            DataIngestionError: On circuit open, network error, or
                unexpected response.
        """
        try:
            result = self._breaker.call(self._execute_scan)
        except CircuitBreakerOpenError as exc:
            raise DataIngestionError(
                f"Chartink scan '{self._scan_name}' circuit breaker open: {exc}"
            ) from exc

        logger.info(
            "chartink_scan_fetched",
            extra={
                "scan_name": self._scan_name,
                "symbol_count": len(result.get("symbols", [])),
            },
        )
        return result

    def _execute_scan(self) -> dict[str, Any]:
        """Perform the HTTP request to the Chartink screener API.

        Returns:
            Dict with ``scan_name``, ``symbols``, and ``received_at``.
        """
        try:
            response = requests.post(
                f"{_CHARTINK_BASE_URL}{_CHARTINK_SCAN_ENDPOINT}",
                json={"scan_id": self._scan_id},
                headers=self._build_headers(),
                timeout=30,
            )
            response.raise_for_status()
            data = response.json()
        except requests.RequestException as exc:
            logger.error(
                "chartink_scan_http_error",
                extra={
                    "scan_name": self._scan_name,
                    "error": str(exc),
                },
            )
            raise DataIngestionError(
                f"Chartink scan HTTP error for '{self._scan_name}': {exc}"
            ) from exc
        except json.JSONDecodeError as exc:
            raise DataIngestionError(
                f"Chartink scan invalid JSON for '{self._scan_name}': {exc}"
            ) from exc

        symbols = self._extract_symbols(data)
        return {
            "scan_name": self._scan_name,
            "symbols": symbols,
            "source": WebhookSource.CHARTINK.value,
            "received_at": datetime.now(timezone.utc).isoformat(),
        }

    def _extract_symbols(self, data: Any) -> list[str]:
        """Extract trading symbols from the Chartink response.

        Chartink returns results in a ``"data"`` array where each element
        has a ``"nsecode"`` or ``"symbol"`` field.

        Args:
            data: The parsed JSON response from Chartink.

        Returns:
            A list of trading symbol strings.
        """
        symbols: list[str] = []

        if isinstance(data, dict):
            records = data.get("data", data.get("stocks", data.get("result", [])))
        elif isinstance(data, list):
            records = data
        else:
            records = []

        for record in records:
            if not isinstance(record, dict):
                continue
            symbol = (
                record.get("nsecode")
                or record.get("symbol")
                or record.get("tradingsymbol")
                or record.get("ticker")
            )
            if symbol:
                symbols.append(str(symbol).strip().upper())

        return list(dict.fromkeys(symbols))  # Preserve order, remove duplicates

    def _build_headers(self) -> dict[str, str]:
        """Build HTTP headers for the Chartink request."""
        headers: dict[str, str] = {
            "Content-Type": "application/json",
            "Accept": "application/json",
        }
        if self._shared_secret:
            headers["X-Signature"] = self._shared_secret
        return headers
