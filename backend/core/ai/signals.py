"""
TradeVision AI — Intelligence Domain Signal Types.

These are the five possible outputs of the AI Brain. They are distinct from
Trading Core's ``RecommendationDirection`` enum and are translated to it
via ``map_signal_to_recommendation()`` — the only bridge between the
Intelligence domain and Trading Core.

Design rules:
    - Never import from ``core.constants`` here.
    - ``map_signal_to_recommendation()`` is the single translation point.
    - No other code in the Intelligence domain should reference
      ``RecommendationDirection`` directly.
"""

from __future__ import annotations

from enum import Enum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from core.constants import RecommendationDirection


class IntelligenceSignal(str, Enum):
    """AI reasoning outputs — the five possible conclusions from the AI Brain."""

    BUY = "BUY"
    """Strong conviction, favourable entry point identified."""

    SELL = "SELL"
    """Bearish conviction, exit existing long or consider short."""

    WAIT = "WAIT"
    """Signal is ambiguous — hold existing position, do not enter new."""

    EXIT = "EXIT"
    """Active position should be closed immediately (urgency signal)."""

    REDUCE = "REDUCE"
    """Reduce position size by half — risk management action."""


class SignalConfidence(str, Enum):
    """Confidence tier after deterministic modifiers are applied."""

    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


def map_signal_to_recommendation(signal: IntelligenceSignal) -> str:
    """Translate an IntelligenceSignal to Trading Core's RecommendationDirection value.

    This is the single bridge between the Intelligence domain and Trading Core.
    All cross-domain translation flows through this function.

    Args:
        signal: The AI's output signal.

    Returns:
        The equivalent RecommendationDirection value string.
    """
    from core.constants import RecommendationDirection

    _mapping: dict[IntelligenceSignal, RecommendationDirection] = {
        IntelligenceSignal.BUY: RecommendationDirection.BUY,
        IntelligenceSignal.SELL: RecommendationDirection.SELL,
        IntelligenceSignal.WAIT: RecommendationDirection.WATCH,
        IntelligenceSignal.EXIT: RecommendationDirection.SELL,
        IntelligenceSignal.REDUCE: RecommendationDirection.SELL,
    }
    return _mapping[signal].value
