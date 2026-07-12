"""
TradeVision AI — Common application models.

Re-exports ``BaseModel`` and its mixins so that all apps can import from a
single, consistent path::

    from apps.common.models import BaseModel

Shared lookup models (e.g. ``Exchange``, ``Sector``) will be added to this
module as the platform grows. They do not belong in individual feature apps
because they represent stable reference data shared across domains.
"""

from core.models import (  # noqa: F401 — re-exported for convenience
    AllObjectsManager,
    AuditMixin,
    BaseModel,
    SoftDeleteManager,
    SoftDeleteMixin,
    SoftDeleteQuerySet,
    TimestampMixin,
    UUIDMixin,
)

# ---------------------------------------------------------------------------
# Shared reference models — added here in future phases
# ---------------------------------------------------------------------------
#
# class Exchange(BaseModel):
#     """Stock exchange (NSE / BSE)."""
#     code = models.CharField(max_length=10, unique=True)
#     name = models.CharField(max_length=100)
#
# class Sector(BaseModel):
#     """NSE sector classification."""
#     name = models.CharField(max_length=100, unique=True)
#     nse_code = models.CharField(max_length=50, blank=True)
