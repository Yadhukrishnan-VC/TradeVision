from __future__ import annotations

import hashlib
import hmac

import pytest

from apps.ingestion.application.services import WebhookSignatureVerifier
from apps.ingestion.domain.exceptions import InvalidSignatureError


class TestWebhookSignatureVerifier:
    def test_verify_url_token_valid(self) -> None:
        verifier = WebhookSignatureVerifier()
        verifier.verify_url_token("abc123", "abc123")

    def test_verify_url_token_invalid(self) -> None:
        verifier = WebhookSignatureVerifier()
        with pytest.raises(InvalidSignatureError):
            verifier.verify_url_token("abc123", "wrong_token")

    def test_verify_url_token_empty(self) -> None:
        verifier = WebhookSignatureVerifier()
        with pytest.raises(InvalidSignatureError):
            verifier.verify_url_token("", "secret")

    def test_verify_header_signature_valid(self) -> None:
        secret = "my_shared_secret"
        body = b'{"ticker": "RELIANCE", "close": 2500}'
        expected_sig = hmac.new(
            secret.encode("utf-8"),
            body,
            hashlib.sha256,
        ).hexdigest()

        verifier = WebhookSignatureVerifier(shared_secret=secret)
        verifier.verify_header_signature(body, expected_sig)

    def test_verify_header_signature_missing(self) -> None:
        verifier = WebhookSignatureVerifier(shared_secret="secret")
        with pytest.raises(InvalidSignatureError, match="Missing X-Signature"):
            verifier.verify_header_signature(b"{}", None)

    def test_verify_header_signature_invalid(self) -> None:
        verifier = WebhookSignatureVerifier(shared_secret="secret")
        with pytest.raises(InvalidSignatureError, match="Invalid webhook signature"):
            verifier.verify_header_signature(b'{"key": "value"}', "invalid_sig")

    def test_verify_ip_allowed(self) -> None:
        verifier = WebhookSignatureVerifier(allowed_ips=["192.168.1.0/24"])
        verifier.verify_ip("192.168.1.100")

    def test_verify_ip_blocked(self) -> None:
        verifier = WebhookSignatureVerifier(allowed_ips=["192.168.1.0/24"])
        with pytest.raises(InvalidSignatureError, match="not in the allowlist"):
            verifier.verify_ip("10.0.0.1")

    def test_verify_ip_invalid_address(self) -> None:
        verifier = WebhookSignatureVerifier(allowed_ips=["192.168.1.0/24"])
        with pytest.raises(InvalidSignatureError, match="Invalid remote address"):
            verifier.verify_ip("not_an_ip")

    def test_verify_no_allowlist_skips_check(self) -> None:
        verifier = WebhookSignatureVerifier()
        verifier.verify_ip("10.0.0.1")

    def test_verify_no_shared_secret_skips_check(self) -> None:
        verifier = WebhookSignatureVerifier()
        verifier.verify_header_signature(b"test", "some_signature")

    def test_replay_detection_same_body_different_signature(self) -> None:
        secret = "secret1"
        body = b'{"ticker": "RELIANCE"}'
        valid_sig = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()

        verifier_valid = WebhookSignatureVerifier(shared_secret=secret)
        verifier_valid.verify_header_signature(body, valid_sig)

        verifier_wrong = WebhookSignatureVerifier(shared_secret="different_secret")
        with pytest.raises(InvalidSignatureError):
            verifier_wrong.verify_header_signature(body, valid_sig)
