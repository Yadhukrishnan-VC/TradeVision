"""MACRO-CONTEXT-WIRING-1 — integration tests for the macro-context call sites.

Proves the two intelligence assembly sites (``ta_completed_handler`` and
``trading_signal_bridge``) populate ``IntelligencePacket.macro_context`` from
the provenance store as of the *active clock* (``core.clock.get_clock()``).

The non-negotiable case (Test 2) seeds a macro observation published *after*
the simulated replay timestamp and asserts it never leaks into the packet —
the guard that prevents re-introducing look-ahead bias via wall-clock time.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime, timezone
from decimal import Decimal
from unittest.mock import MagicMock, patch

import pytest

from apps.eventbus.domain.events import DomainEvent
from apps.intelligence.infrastructure.ta_completed_handler import (
    _build_packet,
    handle_ta_completed,
)
from apps.macro_context.domain.entities import MacroContext
from apps.macro_context.infrastructure.models import MacroObservation
from core.clock import bind_simulated_time


def _ta_payload(**overrides: object) -> dict:
    payload = {
        "symbol": "RELIANCE",
        "snapshot_id": "snap-123",
        "exchange": "NSE",
        "timeframe": "1D",
        "snapshot_timestamp": "2026-08-15T10:00:00+00:00",
        "indicators": {
            "rsi_14": "62.5",
            "macd": "1.23",
            "ema_50": "2550.00",
            "ema_200": "2500.00",
        },
        "price": {"close": "2600.00", "volume": "1000", "avg_volume_20d": "500"},
        "pine_id": "test_script",
        "pine_version": "5",
    }
    payload.update(overrides)
    return payload


@pytest.fixture
def seed_macro_observation(db):
    def _seed(series_id: str, observed_at: date, published_at: datetime, value: Decimal | None) -> MacroObservation:
        return MacroObservation.objects.create(
            provider="fred",
            series_id=series_id,
            observed_at=observed_at,
            published_at=published_at,
            value=value,
        )

    return _seed


class TestTaCompletedMacroWiring:
    @pytest.mark.django_db
    def test_live_path_populates_macro_context(self, seed_macro_observation) -> None:
        """Live (no simulated clock): macro context reflects real 'now'."""
        seed_macro_observation(
            "DGS10",
            date(2019, 12, 31),
            datetime(2020, 1, 1, 12, tzinfo=timezone.utc),
            Decimal("4.15"),
        )
        occurred_at = datetime(2026, 8, 15, 10, tzinfo=timezone.utc)

        packet = _build_packet(_ta_payload(), occurred_at=occurred_at)

        assert isinstance(packet.macro_context, MacroContext)
        assert packet.macro_context.dgs10 == Decimal("4.15")
        assert packet.macro_context.series_count >= 1

    @pytest.mark.django_db
    def test_backtest_safety_excludes_not_yet_published_vintage(
        self, seed_macro_observation
    ) -> None:
        """CRITICAL: a vintage published after the simulated replay time must
        never appear. Also asserts the positive control (after publish it does
        appear), proving it is the clock filter at work — not a broken builder.
        """
        seed_macro_observation(
            "DGS10",
            date(2026, 8, 5),
            datetime(2026, 8, 10, 12, tzinfo=timezone.utc),
            Decimal("4.20"),
        )
        occurred_at = datetime(2026, 8, 1, 10, tzinfo=timezone.utc)

        # Replay date 2026-08-01: the 2026-08-10 vintage is NOT yet public.
        with bind_simulated_time(occurred_at):
            before_publish = _build_packet(_ta_payload(), occurred_at=occurred_at)

        assert before_publish.macro_context is not None
        assert before_publish.macro_context.dgs10 is None
        assert before_publish.macro_context.series_count == 0

        # Replay date 2026-08-12 (after the 2026-08-10 vintage release): present.
        with bind_simulated_time(datetime(2026, 8, 12, 12, tzinfo=timezone.utc)):
            after_publish = _build_packet(_ta_payload(), occurred_at=occurred_at)

        assert after_publish.macro_context.dgs10 == Decimal("4.20")
        assert after_publish.macro_context.series_count == 1

    @pytest.mark.django_db
    def test_empty_macro_data_is_additive_only(self) -> None:
        """No macro data: empty MacroContext (not an exception), and the other
        context blocks are unchanged in shape — proving this is additive-only.
        """
        occurred_at = datetime(2026, 8, 15, 10, tzinfo=timezone.utc)

        packet = _build_packet(_ta_payload(), occurred_at=occurred_at)

        assert isinstance(packet.macro_context, MacroContext)
        assert packet.macro_context.series_count == 0
        assert packet.macro_context.dgs10 is None
        assert packet.macro_context.fedfunds is None
        assert packet.macro_context.cpiaucsl is None
        assert packet.macro_context.t10y2y is None

        assert packet.technical_context.rsi_14 == Decimal("62.5")
        assert packet.technical_context.ema_50 == Decimal("2550.00")
        assert packet.price_context.current_price == Decimal("2600.00")
        assert packet.breadth_context is not None

    @pytest.mark.django_db
    def test_handle_ta_completed_publishes_macro_context_in_packet_data(
        self, seed_macro_observation
    ) -> None:
        """End-to-end handler path: the macro context survives serialisation
        into the published ``PacketBuilt`` payload.
        """
        seed_macro_observation(
            "DGS10",
            date(2019, 12, 31),
            datetime(2020, 1, 1, 12, tzinfo=timezone.utc),
            Decimal("4.15"),
        )
        event = DomainEvent.create(
            event_type="technical_analysis.TechnicalAnalysisCompleted",
            payload=_ta_payload(),
            correlation_id=uuid.uuid4(),
        )

        with patch(
            "apps.intelligence.infrastructure.ta_completed_handler.get_event_bus"
        ) as mock_get_bus:
            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus
            handle_ta_completed(event)

        assert mock_bus.publish.called
        published = mock_bus.publish.call_args[0][0]
        macro = published.payload["packet_data"]["macro_context"]
        assert isinstance(macro, dict)
        assert Decimal(macro["dgs10"]) == Decimal("4.15")
        assert macro["series_count"] == 1


class TestSignalBridgeMacroWiring:
    @pytest.mark.django_db
    def test_signal_bridge_uses_clock_as_of_for_macro_context(self) -> None:
        """The signal bridge must derive the macro ``as_of`` from the active
        clock (simulated time here), never from wall-clock time.
        """
        simulated_at = datetime(2026, 7, 15, 9, 30, tzinfo=timezone.utc)
        sentinel = MacroContext(as_of=simulated_at, dgs10=Decimal("4.00"), series_count=1)
        as_of_calls: list[datetime] = []

        def _fake_build(as_of: datetime) -> MacroContext:
            as_of_calls.append(as_of)
            return sentinel

        event = DomainEvent.create(
            event_type="signals.SignalCreated",
            payload={
                "symbol": "RELIANCE",
                "signal_id": str(uuid.uuid4()),
                "direction": "BUY",
                "confidence_hint": 0.85,
            },
            correlation_id=uuid.uuid4(),
        )

        with (
            patch(
                "apps.intelligence.infrastructure.trading_signal_bridge.TASnapshotRepository"
            ) as mock_repo_cls,
            patch(
                "apps.intelligence.infrastructure.trading_signal_bridge.PineOutput.objects.filter"
            ) as mock_pine_filter,
            patch(
                "apps.intelligence.infrastructure.trading_signal_bridge.get_event_bus"
            ) as mock_get_bus,
            patch(
                "apps.intelligence.infrastructure.trading_signal_bridge.MarketContextCache"
            ) as mock_cache_cls,
            patch(
                "apps.intelligence.infrastructure.trading_signal_bridge.get_context_builder"
            ) as mock_builder_factory,
            bind_simulated_time(simulated_at),
        ):
            mock_repo = MagicMock()
            mock_snapshot = MagicMock()
            mock_snapshot.raw_payload = {
                "close": "2500.00",
                "open": "2480.00",
                "high": "2520.00",
                "low": "2470.00",
                "volume": "2000000",
                "prev_close": "2480.00",
                "change_pct": "0.81",
            }
            mock_repo.find_by_symbol.return_value = [mock_snapshot]
            mock_repo_cls.return_value = mock_repo

            mock_pine_qs = MagicMock()
            mock_pine_qs.order_by.return_value.first.return_value = None
            mock_pine_filter.return_value = mock_pine_qs

            mock_bus = MagicMock()
            mock_get_bus.return_value = mock_bus

            mock_cache = MagicMock()
            mock_cache_cls.return_value = mock_cache

            mock_builder_factory.return_value.build.side_effect = _fake_build

            from apps.intelligence.infrastructure.trading_signal_bridge import (
                handle_signal_created,
            )

            result = handle_signal_created(event)

        assert result is not None
        assert result.symbol == "RELIANCE"
        assert as_of_calls == [simulated_at]
