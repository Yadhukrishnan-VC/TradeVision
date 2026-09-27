"""Universe resolution service (NIFTY200 screening).

The canonical definition of "what to poll" is the ``IndexConstituent``
table, populated weekly from the official NIFTY index CSV. Every consumer
that previously read the process-env watchlist lists
(``MARKET_DATA_POLL_WATCHLIST``, ``NEWS_POLL_SYMBOLS``,
``DEFAULT_LIVE_SYMBOLS``) should resolve their universe through
:func:`resolve_universe` instead — the env lists remain only as a bootstrap
fallback until the table is first populated, so the feature stays additive
for deployments that have not run a sync yet.

Strategy:
    * Active ``IndexConstituent`` rows (index-primary, ordered as the CSV
      publishes them) are the source of truth.
    * When the table is empty — fresh DB, or tests that never ran the sync —
      fall back to ``settings.MARKET_DATA_POLL_WATCHLIST`` so existing
      behaviour and the legacy config are preserved unchanged.
"""

from __future__ import annotations

import logging
from typing import Any

from django.conf import settings

logger = logging.getLogger(__name__)

_DEFAULT_INDEX = "NIFTY200"
_DEFAULT_EXCHANGE = "NSE"


def resolve_universe(
    index_name: str = _DEFAULT_INDEX,
    *,
    exchange: str = _DEFAULT_EXCHANGE,
) -> list[tuple[str, str]]:
    """Resolve the active polling universe as ``(exchange, tradingsymbol)`` pairs.

    ``IndexConstituent`` is primary; the env ``MARKET_DATA_POLL_WATCHLIST``
    is the bootstrap fallback used only while the table is empty.

    Args:
        index_name: The index whose members define the universe.
        exchange:   Exchange to restrict the universe to.

    Returns:
        Ordered list of ``(exchange, tradingsymbol)`` pairs, or ``[]`` when
        neither the table nor the environment defines a universe.
    """
    from django.db import OperationalError, ProgrammingError

    from apps.market_data.infrastructure.models import IndexConstituent

    try:
        rows = list(
            IndexConstituent.objects.filter(
                index_name=index_name, exchange=exchange, is_active=True
            ).order_by("sort_order", "tradingsymbol")
        )
    except (OperationalError, ProgrammingError):
        # Table not migrated yet (startup system checks run before
        # `migrate`); fall through to the env watchlist bootstrap.
        rows = []
    if rows:
        return [(row.exchange, row.tradingsymbol) for row in rows]

    fallback = list(getattr(settings, "MARKET_DATA_POLL_WATCHLIST", []) or [])
    if fallback:
        logger.info(
            "market_data_universe_bootstrap_fallback",
            extra={"index_name": index_name, "watchlist_size": len(fallback)},
        )
    return fallback


def resolve_universe_symbols(
    index_name: str = _DEFAULT_INDEX,
    *,
    exchange: str = _DEFAULT_EXCHANGE,
) -> list[str]:
    """Resolve the active polling universe as a flat list of trading symbols.

    Convenience wrapper for consumers (backtests, checks) that only care
    about the symbol, not the exchange pairing.
    """
    return [symbol for (_exchange, symbol) in resolve_universe(index_name, exchange=exchange)]


def upsert_constituents(
    rows: list[dict[str, Any]],
    *,
    index_name: str = _DEFAULT_INDEX,
    exchange: str = _DEFAULT_EXCHANGE,
) -> dict[str, int]:
    """Upsert a parsed index CSV into ``IndexConstituent``.

    ``rows`` must be ``dict``-like objects with ``Symbol`` (required) and
    optional ``Company Name`` / ``Industry`` / ``Series`` / ``ISIN Code``
    keys, matching the official NIFTY index CSV header. Symbols absent from
    the latest CSV are deactivated (the CSV is the source of truth), so
    delistings never linger in the active universe.

    Returns:
        Summary dict with ``created``, ``updated``, ``deactivated`` counts.
    """
    from apps.market_data.infrastructure.models import IndexConstituent

    seen_symbols: set[str] = set()
    created = 0
    updated = 0

    for sort_order, raw_row in enumerate(rows):
        symbol = str(raw_row.get("Symbol", "")).strip().upper()
        if not symbol:
            continue
        seen_symbols.add(symbol)
        defaults = {
            "sort_order": sort_order,
            "company_name": str(raw_row.get("Company Name", "") or "").strip(),
            "industry": str(raw_row.get("Industry", "") or "").strip(),
            "series": str(raw_row.get("Series", "EQ") or "EQ").strip() or "EQ",
            "isin_code": str(raw_row.get("ISIN Code", "") or "").strip(),
            "is_active": True,
        }
        _obj, was_created = IndexConstituent.objects.update_or_create(
            index_name=index_name,
            exchange=exchange,
            tradingsymbol=symbol,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    deactivated = IndexConstituent.objects.filter(
        index_name=index_name, exchange=exchange
    ).exclude(tradingsymbol__in=seen_symbols or [""]).update(is_active=False)

    return {"created": created, "updated": updated, "deactivated": deactivated}