"""
TradeVision AI — Pattern Engine (Batch AI-5).

Deterministically identifies historical market sessions that resemble the
current trading session and publishes ``pattern_engine.PatternAnalysisCompleted``
for downstream consumption (see the existing, unmodified consumer in
``apps.intelligence.infrastructure.pattern_context_handler``).

The Pattern Engine never calls an AI provider, never computes technical
indicators already produced by Technical Analysis, and never generates
recommendations.
"""

from __future__ import annotations
