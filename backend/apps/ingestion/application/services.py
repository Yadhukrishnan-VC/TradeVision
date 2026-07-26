from __future__ import annotations

import hashlib
import hmac
import ipaddress
import json
import logging
from typing import Any

from django.conf import settings

from apps.ingestion.domain.exceptions import InvalidSignatureError, MalformedPayloadError

logger = logging.getLogger(__name__)


class WebhookSignatureVerifier:
    """Verifies HMAC-SHA256 signatures for incoming webhooks.

    Supports two verification modes:
        1. **URL-token mode**: The token is embedded in the webhook URL path.
           No header signature is required (suitable for TradingView).
        2. **Shared-secret mode**: The request includes an ``X-Signature``
           header containing the HMAC-SHA256 digest of the request body,
           computed with a shared secret (suitable for Chartink).

    Additionally, an optional IP allowlist can be enforced when configured
    in Django settings.
    """

    def __init__(
        self,
        *,
        shared_secret: str | None = None,
        allowed_ips: list[str] | None = None,
    ) -> None:
        self._shared_secret = shared_secret
        self._allowed_networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
        if allowed_ips:
            self._allowed_networks = [
                ipaddress.ip_network(ip) for ip in allowed_ips
            ]

    def verify_url_token(self, url_token: str, expected_token: str) -> None:
        """Verify that the URL token matches the expected value.

        Args:
            url_token:     The token extracted from the request URL path.
            expected_token: The expected token from settings.

        Raises:
            InvalidSignatureError: If the tokens do not match.
        """
        if not hmac.compare_digest(url_token, expected_token):
            raise InvalidSignatureError(
                message="Invalid webhook URL token",
                code="INVALID_URL_TOKEN",
            )

    def verify_header_signature(
        self,
        body: bytes,
        signature_header: str | None,
    ) -> None:
        """Verify the HMAC-SHA256 signature in the request header.

        Args:
            body:             Raw request body bytes.
            signature_header: The value of the ``X-Signature`` header.

        Raises:
            InvalidSignatureError: If the signature is missing or invalid.
        """
        if not signature_header:
            raise InvalidSignatureError(
                message="Missing X-Signature header",
                code="MISSING_SIGNATURE",
            )

        if self._shared_secret is None:
            logger.warning("shared_secret_not_configured_skipping_signature_check")
            return

        expected = hmac.new(
            self._shared_secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature_header, expected):
            raise InvalidSignatureError(
                message="Invalid webhook signature",
                code="INVALID_SIGNATURE",
            )

    def verify_ip(self, remote_addr: str) -> None:
        """Verify that the request comes from an allowed IP address.

        Args:
            remote_addr: The remote IP address string.

        Raises:
            InvalidSignatureError: If the IP is not allowed.
        """
        if not self._allowed_networks:
            return

        try:
            addr = ipaddress.ip_address(remote_addr)
        except ValueError:
            raise InvalidSignatureError(
                message=f"Invalid remote address: {remote_addr}",
                code="INVALID_REMOTE_ADDR",
            )

        if not any(addr in network for network in self._allowed_networks):
            raise InvalidSignatureError(
                message=f"IP {remote_addr} is not in the allowlist",
                code="IP_NOT_ALLOWED",
            )


class TradingViewPayloadParser:
    """Parses and validates TradingView Pine Script alert payloads.

    TradingView sends alert webhooks as JSON bodies with a schema
    defined by the alert message in the Pine Script ``alert()`` call.
    This parser normalises the wide variety of formats into a standard
    ``dict``.
    """

    REQUIRED_FIELDS: set[str] = {"ticker", "close", "time"}

    def parse(self, raw_body: bytes) -> dict[str, Any]:
        """Parse and validate a TradingView alert payload.

        Args:
            raw_body: The raw HTTP request body as bytes.

        Returns:
            A normalised dictionary with at minimum the keys from
            ``REQUIRED_FIELDS``.

        Raises:
            MalformedPayloadError: If the payload cannot be parsed or
                is missing required fields.
        """
        try:
            body_str = raw_body.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise MalformedPayloadError(
                message="Webhook body is not valid UTF-8",
                code="INVALID_ENCODING",
                details={"error": str(exc)},
            )

        # Try to parse as JSON
        try:
            payload = json.loads(body_str)
        except json.JSONDecodeError:
            # Try form-encoded or query-string format
            payload = self._parse_form_encoded(body_str)

        if not isinstance(payload, dict):
            raise MalformedPayloadError(
                message="Webhook payload must be a JSON object",
                code="INVALID_PAYLOAD_TYPE",
            )

        payload = self._normalise_payload(payload)

        missing = self.REQUIRED_FIELDS - set(payload.keys())
        if missing:
            raise MalformedPayloadError(
                message=f"Missing required fields: {', '.join(sorted(missing))}",
                code="MISSING_FIELDS",
                details={"missing_fields": list(missing)},
            )

        return payload

    def _parse_form_encoded(self, body_str: str) -> dict[str, Any]:
        """Parse a form-encoded or query-string style payload.

        TradingView can send alert data as ``key=value&key2=value2``
        when the alert message is configured as a simple string.
        """
        result: dict[str, Any] = {}
        for part in body_str.split("&"):
            if "=" not in part:
                continue
            key, _, value = part.partition("=")
            key = key.strip()
            value = value.strip()

            # Try numeric conversion
            try:
                result[key] = json.loads(value)
            except (json.JSONDecodeError, ValueError):
                result[key] = value

        return result

    def _normalise_payload(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Normalise known TradingView field variations to canonical keys."""
        mapping: dict[str, str] = {
            "ticker": "ticker",
            "symbol": "ticker",
            "close": "close",
            "price": "close",
            "high": "high",
            "low": "low",
            "open": "open",
            "volume": "volume",
            "time": "time",
            "timestamp": "time",
            "strategy": "strategy",
            "order": "order",
            "action": "action",
            "position_size": "position_size",
        }

        normalised: dict[str, Any] = {}
        for raw_key, value in payload.items():
            key = raw_key.lower().strip()
            canonical = mapping.get(key, key)
            normalised[canonical] = value

        return normalised
