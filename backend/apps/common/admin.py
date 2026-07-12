"""
TradeVision AI — Common application admin configuration.

No models are registered here yet. This module re-exports ``BaseModelAdmin``
and ``SoftDeleteAdmin`` so that all other apps import from a single path::

    from apps.common.admin import BaseModelAdmin
"""

from core.admin import BaseModelAdmin, SoftDeleteAdmin  # noqa: F401 — re-exported

# Models from apps.common will be registered here as they are added.
# Example:
#   @admin.register(Sector)
#   class SectorAdmin(BaseModelAdmin):
#       list_display = ("name", "nse_code")
