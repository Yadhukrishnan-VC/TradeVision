from __future__ import annotations

import logging

from apps.execution.application.ports import BrokerAdapter
from apps.execution.domain.exceptions import ExecutionDomainError
from apps.execution.domain.value_objects import FillMode
from apps.execution.infrastructure.brokers.paper_broker import PaperBroker

logger = logging.getLogger(__name__)


def get_broker_adapter(
    adapter_name: str | None = None,
    environment: str | None = None,
) -> BrokerAdapter:
    """Return the active broker adapter behind the settings-driven factory.

    Selection is driven by ``TradeVisionConfig.broker_adapter``
    (``BROKER_ADAPTER`` env): ``paper`` (default) or ``zerodha``. Switching
    adapters is a config change, never a code change — the execution engine
    already accepts any ``BrokerAdapter`` implementation.

    Usage::

        from apps.execution.infrastructure.brokers import get_broker_adapter

        engine = ExecutionEngine(broker=get_broker_adapter())
    """
    from core.config import config
    from apps.execution.infrastructure.brokers.zerodha_broker import ZerodhaBroker

    name = (adapter_name or config.broker_adapter).lower()
    env = (environment or config.broker_environment).lower()

    if name == "paper":
        return PaperBroker(mode=FillMode.FULL_FILL)
    if name == "zerodha":
        return ZerodhaBroker(environment=env)

    raise ExecutionDomainError(
        f"Unknown broker adapter: '{name}'. Supported adapters: paper, "
        "zerodha. Set BROKER_ADAPTER to a supported value.",
        code="UNKNOWN_BROKER_ADAPTER",
    )
