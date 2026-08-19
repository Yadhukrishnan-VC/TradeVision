"""NEWS-FEED-1 — news provider taxonomy.

``NewsProvider`` names the concrete provider implementations selectable via
``NEWS_PROVIDER``. ``SUPPORTED_PROVIDERS`` is the vetted set; adding a new
provider requires an explicit batch scope change (mirrors the macro-context
series taxonomy convention).
"""

from __future__ import annotations

from enum import Enum


class NewsProvider(str, Enum):
    """The supported news providers."""

    MARKETAUX = "marketaux"
    FAKE = "fake"

    @classmethod
    def choices(cls) -> list[tuple[str, str]]:
        return [(member.value, member.value) for member in cls]


SUPPORTED_PROVIDERS: tuple[str, ...] = tuple(member.value for member in NewsProvider)
