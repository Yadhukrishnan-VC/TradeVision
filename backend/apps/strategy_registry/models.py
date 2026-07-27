from __future__ import annotations

from django.db import models

from core.constants import AIProviderName
from core.models import BaseModel


class TradingStrategyStatus(models.TextChoices):
    ACTIVE = "ACTIVE", "Active"
    INACTIVE = "INACTIVE", "Inactive"
    RETIRED = "RETIRED", "Retired"


class TradingStrategy(BaseModel):
    name = models.CharField(max_length=128, unique=True)
    status = models.CharField(
        max_length=16,
        choices=TradingStrategyStatus.choices,
        default=TradingStrategyStatus.INACTIVE,
        db_index=True,
    )
    priority = models.IntegerField(default=0, db_index=True)
    symbol_filter = models.CharField(max_length=20, null=True, blank=True)
    sector_filter = models.CharField(max_length=64, null=True, blank=True)
    preferred_provider = models.CharField(
        max_length=32,
        null=True,
        blank=True,
        choices=[(p.value, p.name) for p in AIProviderName],
    )
    confidence_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.6000)
    risk_threshold = models.DecimalField(max_digits=5, decimal_places=4, default=0.5000)

    class Meta:
        ordering = ["priority", "created_at"]
        verbose_name = "Trading Strategy"
        verbose_name_plural = "Trading Strategies"

    def __str__(self) -> str:
        return f"TradingStrategy({self.name}, status={self.status})"
