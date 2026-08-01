"""
TradeVision AI — Pattern Engine WebSocket consumers.

The Pattern Engine has no real-time push surface; results are consumed
through the EventBus (``pattern_engine.PatternAnalysisCompleted``) and the
REST API. This module exists so the app package mirrors sibling apps.
"""

from __future__ import annotations
