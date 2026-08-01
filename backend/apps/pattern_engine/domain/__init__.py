from __future__ import annotations

from apps.pattern_engine.domain.entities import (
    MatchedPattern,
    PatternAnalysisResult,
    SimilarSession,
)
from apps.pattern_engine.domain.exceptions import (
    InsufficientHistoryError,
    PatternEngineError,
)
from apps.pattern_engine.domain.similarity import (
    DEFAULT_WEIGHTS,
    build_feature_vector,
    compute_similarity,
)
from apps.pattern_engine.domain.value_objects import (
    EvidenceItem,
    FeatureVector,
    FeatureWeights,
    SimilarityScore,
)

__all__ = [
    "DEFAULT_WEIGHTS",
    "EvidenceItem",
    "FeatureVector",
    "FeatureWeights",
    "InsufficientHistoryError",
    "MatchedPattern",
    "PatternAnalysisError",
    "PatternAnalysisResult",
    "PatternEngineError",
    "SimilarSession",
    "SimilarityScore",
    "build_feature_vector",
    "compute_similarity",
]
