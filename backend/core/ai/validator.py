"""
TradeVision AI — AI response validator.

Provides lightweight Pydantic v2 schemas for validating raw AI responses
before they are parsed into domain objects. This is a sanity shape check,
not a semantic validation — it ensures the response has the expected
structure without verifying business logic.
"""

from pydantic import BaseModel, Field, field_validator


class TokenUsageSchema(BaseModel):
    """Pydantic schema for token usage metadata."""

    prompt_tokens: int = Field(default=0, ge=0)
    completion_tokens: int = Field(default=0, ge=0)
    total_tokens: int = Field(default=0, ge=0)


class RawAIResponseSchema(BaseModel):
    """
    Pydantic v2 schema for validating the shape of a raw AI response.

    Ensures the response contains the minimum required fields with correct
    types before domain parsing occurs.
    """

    content: str = Field(..., min_length=1)
    model: str = Field(default="unknown")
    token_usage: TokenUsageSchema = Field(default_factory=TokenUsageSchema)
    latency_ms: float = Field(default=0.0, ge=0.0)

    @field_validator("content")
    @classmethod
    def content_not_blank(cls, v: str) -> str:
        """Reject whitespace-only content."""
        if not v.strip():
            raise ValueError("AI response content must not be blank")
        return v


class RecommendationSchema(BaseModel):
    """
    Pydantic v2 schema for validating a parsed recommendation payload.

    Maps to the expected JSON structure returned by AI providers after
    prompt rendering and response parsing.
    """

    direction: str = Field(..., pattern=r"^(BUY|SELL|WATCH|AVOID)$")
    confidence: float = Field(..., ge=0.0, le=1.0)
    reasoning: str = Field(..., min_length=1)
    risk_level: str = Field(..., pattern=r"^(LOW|MEDIUM|HIGH|VERY_HIGH)$")
    time_horizon: str = Field(default="SHORT", pattern=r"^(INTRADAY|SHORT|MEDIUM|LONG)$")
    target_price: float | None = None
    stop_loss: float | None = None
    key_factors: list[str] = Field(default_factory=list)
