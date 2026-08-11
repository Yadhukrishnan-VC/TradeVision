from __future__ import annotations

import unicodedata


class WatchlistNote:
    """A user-supplied note on a watchlist entry.

    Normalised on construction: control characters are stripped and the
    length is capped at 280 characters (per WATCH-1).
    """

    MAX_LENGTH = 280

    def __init__(self, value: str = "") -> None:
        self._value = self._normalise(value or "")

    @classmethod
    def _normalise(cls, raw: str) -> str:
        cleaned = []
        for ch in raw:
            category = unicodedata.category(ch)
            if category.startswith("C") and not ch.isspace():
                continue
            cleaned.append(ch)
        return "".join(cleaned)[: cls.MAX_LENGTH]

    @property
    def value(self) -> str:
        return self._value

    def __str__(self) -> str:
        return self._value

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, WatchlistNote):
            return NotImplemented
        return self._value == other._value
