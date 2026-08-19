"""
Management command: seed_contract_verify

Populates realistic JournalEntry, AuditLogEntry, and RuleExecution rows through
the real write paths (event-bus handlers + rule evaluation service) so the
journal/audit/rule-engine API contracts can be body-verified against populated
data rather than an empty container shape.

The command is safe to re-run: every invocation uses fresh correlation ids /
analysis event ids, so it appends new rows instead of clobbering existing ones.
It is not part of the production seed path — it exists purely to exercise the
write side for contract verification.

Usage::

    python manage.py seed_contract_verify
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand

from apps.accounts.infrastructure.models import Account
from apps.eventbus.domain.events import DomainEvent


def _make_event(event_type: str, cid: uuid.UUID, account_id: uuid.UUID, **extra) -> DomainEvent:
    payload = {"account_id": str(account_id)}
    payload.update(extra)
    return DomainEvent.create(
        event_type=event_type,
        payload=payload,
        correlation_id=cid,
    )


def _build_enriched_data(
    *,
    change_pct: str = "3.50",
    volume: int = 2_000_000,
    avg_volume_20d: int = 500_000,
    current_price: str = "2560.00",
    bb_upper: str | None = "2550.00",
    resistance_levels: list[str] | None = None,
    avg_volume_10d: int | None = None,
    avg_volume_5d: int | None = None,
    technical_extra: dict | None = None,
) -> dict:
    if resistance_levels is None:
        resistance_levels = ["2520.00"]

    price_context = {
        "current_price": current_price,
        "open_price": "2530.00",
        "high": "2570.00",
        "low": "2520.00",
        "prev_close": "2470.00",
        "change_pct": change_pct,
        "volume": volume,
        "avg_volume_20d": avg_volume_20d,
        "avg_volume_10d": avg_volume_10d,
        "avg_volume_5d": avg_volume_5d,
        "circuit_status": "NORMAL",
    }
    technical_context = {
        "rsi_14": "65.5",
        "bb_upper": bb_upper,
        "bb_lower": "2400.00",
        "resistance_levels": [Decimal(v) for v in resistance_levels],
    }
    if technical_extra:
        technical_context.update(technical_extra)

    return {
        "packet": {
            "symbol": "RELIANCE",
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "freshness_validated": True,
            "regime": "BULLISH",
            "price_context": price_context,
            "technical_context": technical_context,
            "breadth_context": {
                "sector_index_change_pct": "0.50",
                "sector_advance_decline": "0.30",
                "nifty_change_pct": "0.40",
                "sensex_change_pct": "0.30",
            },
            "news_context": {},
            "data_quality": {"quality_score": 1.0},
        },
        "portfolio_context": None,
        "risk_context": None,
    }


class Command(BaseCommand):
    help = "Seed populated journal/audit/rule-engine rows for API contract verification."

    def handle(self, *args, **options) -> None:
        # Force the in-process bus so handlers run synchronously during seeding.
        settings.EVENT_BUS_IMPLEMENTATION = "fake"

        user = self._ensure_contract_user()
        account = self._ensure_default_account(user)

        journal_count, audit_count = self._seed_journal_and_audit(account.id)
        rule_count, fired_count = self._seed_rule_executions()

        self.stdout.write(
            self.style.SUCCESS(
                "Seeded contract-verify data:\n"
                f"  journal entries  : {journal_count}\n"
                f"  audit log entries: {audit_count}\n"
                f"  rule executions  : {rule_count}\n"
                f"  rule fired events: {fired_count}\n"
                f"  account_id       : {account.id}\n"
                f"  user             : {user.username}"
            )
        )

    # ------------------------------------------------------------------
    # Base entities
    # ------------------------------------------------------------------
    def _ensure_contract_user(self) -> object:
        User = get_user_model()
        user, _ = User.objects.get_or_create(
            username="contract-verify",
            defaults={
                "role": "staff",
                "is_staff": True,
            },
        )
        user.role = "staff"
        user.is_staff = True
        user.save()
        return user

    def _ensure_default_account(self, user: object) -> Account:
        account = Account.objects.filter(owner=user).first()
        if account is None:
            account = Account.objects.create(
                name="Contract Verification",
                owner=user,
                is_default=True,
            )
        account.is_default = True
        account.save()
        return account

    # ------------------------------------------------------------------
    # Journal + Audit via the real event-bus write path
    # ------------------------------------------------------------------
    def _seed_journal_and_audit(self, account_id: uuid.UUID) -> tuple[int, int]:
        from apps.eventbus.infrastructure.event_bus_factory import reset_event_bus, get_event_bus
        from apps.journal.infrastructure.event_handlers import register_handlers as register_journal
        from apps.audit_log.infrastructure.event_handlers import register_handlers as register_audit

        reset_event_bus()
        bus = get_event_bus()
        register_journal(bus)
        register_audit(bus)

        lifecycles = [
            {
                "symbol": "RELIANCE",
                "decision": "enter_long",
                "side": "buy",
                "quantity": 100,
                "fill_price": 2500.00,
                "entry_price": 2500.00,
                "realized_pnl": 5000.00,
            },
            {
                "symbol": "HDFCBANK",
                "decision": "enter_long",
                "side": "buy",
                "quantity": 150,
                "fill_price": 1650.00,
                "entry_price": 1650.00,
                "realized_pnl": -3750.00,
            },
            {
                "symbol": "INFY",
                "decision": "enter_long",
                "side": "buy",
                "quantity": 200,
                "fill_price": 1480.00,
                "entry_price": 1480.00,
                "realized_pnl": 0.00,
            },
            {
                "symbol": "TCS",
                "decision": "enter_long",
                "side": "buy",
                "quantity": 75,
                "fill_price": 4100.00,
                "entry_price": 4100.00,
                "realized_pnl": None,
            },
        ]

        journal_count = 0
        for spec in lifecycles:
            cid = uuid.uuid4()
            position_id = uuid.uuid4()
            events = [
                _make_event(
                    "signals.SignalCreated",
                    cid,
                    account_id,
                    symbol=spec["symbol"],
                    signal_type="buy",
                    confidence=0.85,
                ),
                _make_event(
                    "decisions.TradeDecisionMade",
                    cid,
                    account_id,
                    symbol=spec["symbol"],
                    decision=spec["decision"],
                    quantity=spec["quantity"],
                ),
                _make_event(
                    "orders.OrderPlaced",
                    cid,
                    account_id,
                    order_id=str(uuid.uuid4()),
                    symbol=spec["symbol"],
                    side=spec["side"],
                    quantity=spec["quantity"],
                ),
                _make_event(
                    "orders.OrderFilled",
                    cid,
                    account_id,
                    order_id=str(uuid.uuid4()),
                    symbol=spec["symbol"],
                    side=spec["side"],
                    quantity=spec["quantity"],
                    fill_price=spec["fill_price"],
                ),
                _make_event(
                    "positions.PositionOpened",
                    cid,
                    account_id,
                    position_id=str(position_id),
                    symbol=spec["symbol"],
                    quantity=spec["quantity"],
                    entry_price=spec["entry_price"],
                ),
            ]
            if spec["realized_pnl"] is not None:
                events.append(
                    _make_event(
                        "positions.PositionClosed",
                        cid,
                        account_id,
                        position_id=str(position_id),
                        symbol=spec["symbol"],
                        realized_pnl=spec["realized_pnl"],
                    )
                )
            for event in events:
                bus.publish(event)
            journal_count += 1

        from apps.audit_log.infrastructure.models import AuditLogEntry
        return journal_count, AuditLogEntry.objects.count()

    # ------------------------------------------------------------------
    # Rule executions via the real rule-evaluation service
    # ------------------------------------------------------------------
    def _seed_rule_executions(self) -> tuple[int, int]:
        from apps.rule_engine.infrastructure.models import RuleConfig
        from apps.rule_engine.infrastructure.event_handlers import _deserialize_enriched_packet
        from apps.rule_engine.application.rule_evaluation_service import RuleEvaluationService

        rule_ids = (
            "price_movement_v1",
            "volume_spike_v1",
            "breakout_v1",
            "long_momentum_v1",
            "short_sell_v1",
            "volatility_breakout_v1",
            "high_beta_breakout_v1",
            "short_breakdown_v1",
        )
        for rule_id in rule_ids:
            RuleConfig.objects.get_or_create(
                rule_id=rule_id,
                defaults={
                    "enabled": True,
                    "validated_regimes": {"BULLISH": {"status": "GO"}},
                },
            )

        packets = [
            # Fires price_movement_v1 + volume_spike_v1 + breakout_v1.
            _build_enriched_data(),
            # LongMomentum setup.
            _build_enriched_data(
                change_pct="1.00",
                volume=3_000_000,
                avg_volume_20d=5_000_000,
                current_price="103.00",
                bb_upper=None,
                resistance_levels=None,
                avg_volume_10d=900_000,
                technical_extra={
                    "vwap": "102.00",
                    "ema_20": "101.00",
                    "opening_15m_open": "100.00",
                    "opening_15m_high": "101.00",
                    "opening_15m_low": "100.00",
                    "opening_15m_close": "101.00",
                },
            ),
            # HighBetaBreakout setup.
            _build_enriched_data(
                change_pct="1.00",
                volume=1_200_000,
                avg_volume_20d=5_000_000,
                avg_volume_5d=500_000,
                current_price="103.00",
                bb_upper="102.00",
                resistance_levels=None,
                technical_extra={"rsi_14": "70.00"},
            ),
            # ShortBreakdown setup.
            _build_enriched_data(
                change_pct="1.00",
                volume=3_000_000,
                avg_volume_20d=5_000_000,
                avg_volume_10d=900_000,
                current_price="98.00",
                bb_upper=None,
                resistance_levels=None,
                technical_extra={"vwap": "101.00", "rsi_14": "30.00"},
            ),
        ]

        service = RuleEvaluationService()
        total_executions = 0
        fired_events = 0
        for packet_data in packets:
            enriched = _deserialize_enriched_packet(packet_data)
            analysis_event_id = uuid.uuid4()
            firings = service.evaluate_enriched_packet(
                enriched,
                analysis_event_id=analysis_event_id,
            )
            total_executions += len(firings)
            for firing in firings:
                try:
                    service.publish_rule_firing(firing)
                    fired_events += 1
                except Exception:
                    self.stderr.write(f"  publish failed for rule={firing.rule_id}")

        return total_executions, fired_events
