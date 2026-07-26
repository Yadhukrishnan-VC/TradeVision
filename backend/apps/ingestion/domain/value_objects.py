from __future__ import annotations

from enum import Enum


class WebhookSource(str, Enum):
    """Identifies the origin of an ingested webhook payload."""

    TRADINGVIEW = "tradingview"
    CHARTINK = "chartink"

    @classmethod
    def from_string(cls, value: str) -> WebhookSource:
        """Parse a source string, raising ``ValueError`` on invalid input.

        Args:
            value: Raw source string (e.g. ``"tradingview"``, ``"chartink"``).

        Returns:
            The matching ``WebhookSource`` member.

        Raises:
            ValueError: If *value* does not match any known source.
        """
        try:
            return cls(value.lower())
        except ValueError:
            valid = ", ".join(m.value for m in cls)
            raise ValueError(f"Unknown webhook source {value!r}. Valid: {valid}")
