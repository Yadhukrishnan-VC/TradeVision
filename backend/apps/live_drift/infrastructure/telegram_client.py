from __future__ import annotations

import logging
import urllib.parse
import urllib.request
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)


class TelegramNotifier:
    """Minimal Telegram Bot API notifier (free-integrations placeholder).

    The free-integrations batch does not exist yet, so this is the smallest
    useful thing: a plain ``sendMessage`` call, hard-disabled unless both
    ``TELEGRAM_BOT_TOKEN`` and ``TELEGRAM_CHAT_ID`` are configured. All
    failures degrade to logs — alerting must never break monitoring.
    """

    def __init__(self) -> None:
        self._token: str = getattr(settings, "TELEGRAM_BOT_TOKEN", "") or ""
        self._chat_id: str = getattr(settings, "TELEGRAM_CHAT_ID", "") or ""

    @property
    def enabled(self) -> bool:
        return bool(self._token and self._chat_id)

    def send(self, text: str) -> bool:
        if not self.enabled:
            logger.info(
                "telegram_disabled_alert_logged_only", extra={"alert": text[:200]}
            )
            return False
        try:
            url = f"https://api.telegram.org/bot{self._token}/sendMessage"
            data = urllib.parse.urlencode(
                {"chat_id": self._chat_id, "text": text[:4000]}
            ).encode()
            req = urllib.request.Request(url, data=data)  # noqa: S310
            with urllib.request.urlopen(req, timeout=10) as resp:  # noqa: S310
                ok = 200 <= resp.status < 300
            if not ok:
                logger.warning("telegram_send_failed", extra={"status": resp.status})
            return ok
        except Exception as exc:  # noqa: BLE001 - notifications never raise
            logger.warning("telegram_send_error", extra={"error": str(exc)})
            return False


def notify(title: str, detail: dict[str, Any]) -> None:
    """Log the alert always; forward to Telegram when configured."""
    line = " | ".join(f"{k}={v}" for k, v in detail.items())
    logger.error("live_drift_alert %s | %s", title, line)
    TelegramNotifier().send(f"[TradeVision drift] {title}\n{line}")
