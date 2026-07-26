"""
TradeVision AI — Intelligence Domain Response Schema.

Pydantic v2 model for validating AI JSON output in the Intelligence domain.
This is separate from ``core/ai/validator.py`` which validates against the
older RecommendationDirection enum. The Intelligence domain uses
IntelligenceSignal (BUY, SELL, WAIT, EXIT, REDUCE).
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator


class IntelligenceResponseSchema(BaseModel):
    """Pydantic v2 model defining the expected JSON structure of an AI response.

    The LLM is instructed to return JSON conforming to this schema. Field
    validators enforce enum correctness. Extra fields are silently ignored.
    """

    model_config = ConfigDict(
        extra="ignore",
        str_strip_whitespace=True,
        validate_assignment=False,
    )

    signal: str
    confidence_score: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(min_length=20)
    trade_explanation: str = Field(min_length=10)
    risk_level: str
    risk_explanation: str = Field(min_length=10)
    key_factors: list[str] = Field(default_factory=list)
    contradicting_factors: list[str] = Field(default_factory=list)
    time_horizon: str
    follow_up_triggers: list[str] = Field(default_factory=list)
    market_regime_assessment: str
    multi_timeframe_alignment: str
    data_quality_note: str = ""

    @field_validator("signal")
    @classmethod
    def validate_signal(cls, value: str) -> str:
        """Ensure signal is a valid IntelligenceSignal value."""
        from core.ai.signals import IntelligenceSignal

        valid: set[str] = {s.value for s in IntelligenceSignal}
        if value not in valid:
            raise ValueError(
                f"'{value}' is not a valid signal. "
                f"Expected one of: {sorted(valid)}"
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
                f"'{value}' is not a valid risk level. "
                f"Expected one of: {sorted(valid)}"
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
                f"'{value}' is not a valid time horizon. "
                f"Expected one of: {sorted(valid)}"
            )
        return value

    @field_validator("market_regime_assessment")
    @classmethod
    def validate_regime_assessment(cls, value: str) -> str:
        """Ensure market_regime_assessment is a valid regime string."""
        valid: set[str] = {
            "BULLISH_TREND", "BEARISH_TREND", "RANGING",
            "VOLATILE", "BREAKOUT", "BREAKDOWN",
        }
        if value not in valid:
            raise ValueError(
                f"'{value}' is not a valid market regime assessment. "
                f"Expected one of: {sorted(valid)}"
            )
        return value

    @field_validator("multi_timeframe_alignment")
    @classmethod
    def validate_mtf_alignment(cls, value: str) -> str:
        """Ensure multi_timeframe_alignment is valid."""
        valid: set[str] = {"ALIGNED", "CONFLICTING", "NEUTRAL"}
        if value not in valid:
            raise ValueError(
                f"'{value}' is not a valid multi-timeframe alignment. "
                f"Expected one of: {sorted(valid)}"
            )
        return value
