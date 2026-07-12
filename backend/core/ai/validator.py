"""
TradeVision AI — AI response validator.

Parses and validates the raw text returned by an AI provider into a
structured schema using Pydantic v2. The validator is a pure framework
layer — it enforces shape and enum correctness only.

Business rules (confidence floor, hallucination detection, data quality
gating, budget enforcement) are applied in Phase 4 by the AI orchestration
layer, not here.
"""

import json
import logging
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator

from core.ai.base_provider import AIRawResponse
from core.ai.exceptions import AIResponseValidationError

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Pydantic v2 schema
# ---------------------------------------------------------------------------


class AIResponseSchema(BaseModel):
    """
    Pydantic v2 model that defines the expected JSON structure of an AI response.

    The LLM is expected to return a JSON object conforming to this schema.
    Field validators enforce that enum values are drawn from the correct sets.
    Extra fields from the LLM output are silently ignored.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=False,
    )

    direction: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=10)
    risk_level: str
    risk_explanation: str = Field(min_length=10)
    key_factors: list[str] = Field(default_factory=list)
    contradicting_factors: list[str] = Field(default_factory=list)
    time_horizon: str
    follow_up_triggers: list[str] = Field(default_factory=list)

    @field_validator("direction")
    @classmethod
    def validate_direction(cls, value: str) -> str:
        """Ensure direction is a valid RecommendationDirection value."""
        from core.constants import RecommendationDirection

        valid: set[str] = {d.value for d in RecommendationDirection}
        if value not in valid:
            raise ValueError(
                f"'{value}' is not a valid direction. Expected one of: {sorted(valid)}"
            )
        return value

    @field_validator("risk_level")
    @classmethod
    def validate_risk_level(cls, value: str) -> str:
        """Ensure risk_level is a valid RiskLevel value."""
        from core.constants import RiskLevel

        valid: set[str] = {r.value for r in RiskLevel}
        if value not in valid:
            raise ValueError(
                f"'{value}' is not a valid risk level. Expected one of: {sorted(valid)}"
            )
        return value

    @field_validator("time_horizon")
    @classmethod
    def validate_time_horizon(cls, value: str) -> str:
        """Ensure time_horizon is a valid RecommendationTimeHorizon value."""
        from core.constants import RecommendationTimeHorizon

        valid: set[str] = {t.value for t in RecommendationTimeHorizon}
        if value not in valid:
            raise ValueError(
                f"'{value}' is not a valid time horizon. Expected one of: {sorted(valid)}"
            )
        return value


# ---------------------------------------------------------------------------
# Validator class
# ---------------------------------------------------------------------------


class AIResponseValidator:
    """
    Validates and parses raw AI provider output into a structured schema.

    Accepts an ``AIRawResponse`` whose ``raw_text`` is expected to be a
    JSON object conforming to ``AIResponseSchema``.

    Raises ``AIResponseValidationError`` on any parse or validation failure
    so callers never need to handle raw ``json.JSONDecodeError`` or Pydantic
    ``ValidationError`` directly.
    """

    def validate(self, raw_response: AIRawResponse) -> AIResponseSchema:
        """
        Parse and validate the raw LLM text.

        Args:
            raw_response: The ``AIRawResponse`` returned by a provider.

        Returns:
            A validated ``AIResponseSchema`` instance ready for conversion
            into an ``AIRecommendation``.

        Raises:
            AIResponseValidationError: If the text is not valid JSON or does
                                       not conform to ``AIResponseSchema``.
        """
        try:
            data: Any = json.loads(raw_response.raw_text)
        except json.JSONDecodeError as exc:
            logger.error(
                "ai_response_json_parse_failed",
                extra={
                    "request_id": str(raw_response.request_id),
                    "provider": raw_response.provider,
                    "error": str(exc),
                    "raw_preview": raw_response.raw_text[:200],
                },
            )
            raise AIResponseValidationError(
                f"AI response is not valid JSON: {exc}"
            ) from exc

        if not isinstance(data, dict):
            raise AIResponseValidationError(
                f"AI response must be a JSON object, got {type(data).__name__}."
            )

        try:
            schema = AIResponseSchema.model_validate(data)
        except ValidationError as exc:
            logger.error(
                "ai_response_schema_validation_failed",
                extra={
                    "request_id": str(raw_response.request_id),
                    "provider": raw_response.provider,
                    "validation_errors": exc.errors(),
                },
            )
            raise AIResponseValidationError(
                f"AI response failed schema validation: {exc}"
            ) from exc

        logger.debug(
            "ai_response_validated",
            extra={
                "request_id": str(raw_response.request_id),
                "direction": schema.direction,
                "confidence_score": schema.confidence_score,
            },
        )
        return schema
