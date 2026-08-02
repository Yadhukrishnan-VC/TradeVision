from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal
from uuid import UUID

from apps.risk_management.application.kill_switch_service import KillSwitchService
from apps.risk_management.application.ports import (
    CapitalGateway,
    MarketStatusGateway,
    PortfolioStateGateway,
)
from apps.risk_management.application.risk_config import RiskConfig
from apps.risk_management.domain.entities import (
    RiskDecision,
    RiskDecisionStatus,
    RiskRejection,
)
from apps.risk_management.domain.rules import (
    DailyLossLimitCheck,
    DataFreshnessCheck,
    ExposureLimitCheck,
    InstrumentCheck,
    KillSwitchCheck,
    MarketSessionCheck,
    PositionSizingCheck,
    RiskCheck,
    RiskCheckContext,
    RiskRewardCheck,
    StopDirectionCheck,
)
from apps.risk_management.domain.value_objects import RejectionReason
from core.services import BaseService

_DEFAULT_CHECKS: tuple[RiskCheck, ...] = (
    KillSwitchCheck(),
    DataFreshnessCheck(),
    MarketSessionCheck(),
    InstrumentCheck(),
    StopDirectionCheck(),
    PositionSizingCheck(),
    ExposureLimitCheck(),
    DailyLossLimitCheck(),
    RiskRewardCheck(),
)

_LONG_RULES = {"long_momentum_v1", "volatility_breakout_v1"}
_SHORT_RULES = {"short_sell_v1"}


class RiskEvaluationService(BaseService):
    """Orchestrate the deterministic risk checks in a fixed, fail-closed order.

    Consumes a ``rule_engine.RuleFired`` payload, assembles an immutable
    :class:`RiskCheckContext` from gateway + config + trigger_data, runs the
    checks sequentially (first rejection wins), and produces a
    :class:`RiskDecision`.

    The service is intentionally I/O-free beyond the gateway reads it is
    handed; each check is a pure function of the context.
    """

    def __init__(
        self,
        *,
        capital_gateway: CapitalGateway,
        portfolio_gateway: PortfolioStateGateway,
        market_gateway: MarketStatusGateway,
        kill_switch_service: KillSwitchService | None = None,
        config: RiskConfig | None = None,
        checks: tuple[RiskCheck, ...] | None = None,
    ) -> None:
        super().__init__()
        self._capital_gateway = capital_gateway
        self._portfolio_gateway = portfolio_gateway
        self._market_gateway = market_gateway
        self._kill_switch_service = kill_switch_service
        self._config = config or RiskConfig()
        self._checks = checks or _DEFAULT_CHECKS

    def evaluate_rule_firing(self, payload: dict, reference_dt: datetime | None = None) -> RiskDecision:
        """Evaluate a RuleFired payload into a risk decision.

        Args:
            payload:      The ``rule_engine.RuleFired`` payload dict.
            reference_dt: Evaluation time (UTC). Defaults to now.

        Returns:
            A frozen :class:`RiskDecision` — APPROVED or REJECTED. On any
            unexpected error the decision is REJECTED with
            ``RejectionReason.UNKNOWN`` (fail-closed).
        """
        occurred_at = datetime.fromisoformat(payload.get("occurred_at", "")) or None
        analysis_event_id = UUID(payload["analysis_event_id"])
        rule_id = payload.get("rule_id", "")
        symbol = payload.get("symbol", "")
        event_type = payload.get("event_type", "")
        trigger_data = payload.get("trigger_data", {}) or {}
        now = reference_dt or datetime.now(timezone.utc)

        if occurred_at is not None and occurred_at.tzinfo is None:
            occurred_at = occurred_at.replace(tzinfo=timezone.utc)

        entry_price = self._to_decimal(trigger_data.get("entry_price"))
        stop_loss = self._to_decimal(trigger_data.get("stop_loss"))

        direction = self._infer_direction(rule_id, event_type, trigger_data)

        kill_switch_active = self._kill_switch_active(symbol)

        ctx = RiskCheckContext(
            symbol=symbol,
            rule_id=rule_id,
            event_type=event_type,
            analysis_event_id=analysis_event_id,
            occurred_at=occurred_at or now,
            entry_price=entry_price,
            stop_loss=stop_loss,
            direction=direction,
            target_price=self._to_decimal(trigger_data.get("target_price")),
            freshness_validated=self._market_gateway.is_fresh(occurred_at or now, now),
            is_market_open=self._market_gateway.is_market_open(now),
            kill_switch_active=kill_switch_active,
            tradable=(
                not self._config.tradable_symbols
                or symbol in self._config.tradable_symbols
            ),
            risk_pct=self._config.risk_pct,
            available_capital=self._capital_gateway.get_available_capital(),
            max_position_size=self._capital_gateway.get_max_position_size(),
            current_exposure=self._portfolio_gateway.get_current_exposure(),
            max_exposure_cap=self._config.max_exposure_cap,
            daily_loss=self._portfolio_gateway.get_daily_loss(),
            daily_loss_limit=self._config.daily_loss_limit,
            min_risk_reward=self._config.min_risk_reward,
            instrument_max_qty=self._portfolio_gateway.get_instrument_max_qty(symbol),
            portfolio_gateway_impl=self._portfolio_gateway.implementation_name,
        )

        decision = self._run_checks(ctx)
        self._logger.info(
            "risk_decision_made",
            extra={
                "symbol": symbol,
                "rule_id": rule_id,
                "status": decision.status.value,
                "rejection": decision.rejection.code.value if decision.rejection else None,
            },
        )
        return decision

    def _kill_switch_active(self, symbol: str) -> bool:
        """Fail-closed kill-switch lookup: GLOBAL → ACCOUNT → SYMBOL.

        Any lookup error (cache or db) is treated as active, blocking trades.
        """
        if self._kill_switch_service is None:
            return self._config.kill_switch_active
        return self._kill_switch_service.is_trade_blocked(symbol)

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _run_checks(self, ctx: RiskCheckContext) -> RiskDecision:
        sized_quantity: int | None = None
        for check in self._checks:
            result = check.safe_evaluate(ctx)
            if result is None:
                continue
            if result.reason is not None:
                return RiskDecision(
                    symbol=ctx.symbol,
                    rule_id=ctx.rule_id,
                    event_type=ctx.event_type,
                    analysis_event_id=ctx.analysis_event_id,
                    occurred_at=ctx.occurred_at,
                    status=RiskDecisionStatus.REJECTED,
                    entry_price=ctx.entry_price or Decimal(0),
                    stop_loss=ctx.stop_loss or Decimal(0),
                    position_size=0,
                    trigger_data=self._trigger_data_for(ctx),
                    rejection=RiskRejection(
                        code=result.reason,
                        message=result.message,
                    ),
                    reason_message=result.message,
                    portfolio_gateway_impl=ctx.portfolio_gateway_impl,
                )
            if result.position_size is not None:
                sized_quantity = result.position_size
                ctx = RiskCheckContext(**{**ctx.__dict__, "proposed_quantity": sized_quantity})

        if sized_quantity is None:
            return RiskDecision(
                symbol=ctx.symbol,
                rule_id=ctx.rule_id,
                event_type=ctx.event_type,
                analysis_event_id=ctx.analysis_event_id,
                occurred_at=ctx.occurred_at,
                status=RiskDecisionStatus.REJECTED,
                entry_price=ctx.entry_price or Decimal(0),
                stop_loss=ctx.stop_loss or Decimal(0),
                position_size=0,
                trigger_data=self._trigger_data_for(ctx),
                rejection=RiskRejection(
                    code=RejectionReason.UNKNOWN,
                    message="No sizing produced by the check chain",
                ),
                reason_message="No sizing produced by the check chain",
                portfolio_gateway_impl=ctx.portfolio_gateway_impl,
            )

        return RiskDecision(
            symbol=ctx.symbol,
            rule_id=ctx.rule_id,
            event_type=ctx.event_type,
            analysis_event_id=ctx.analysis_event_id,
            occurred_at=ctx.occurred_at,
            status=RiskDecisionStatus.APPROVED,
            entry_price=ctx.entry_price or Decimal(0),
            stop_loss=ctx.stop_loss or Decimal(0),
            position_size=sized_quantity,
            risk_amount=(ctx.available_capital or Decimal(0)) * ctx.risk_pct,
            risk_pct_of_capital=ctx.risk_pct,
            risk_reward_ratio=self._compute_rr(ctx),
            trigger_data=self._trigger_data_for(ctx),
            portfolio_gateway_impl=ctx.portfolio_gateway_impl,
        )

    @staticmethod
    def _compute_rr(ctx: RiskCheckContext) -> Decimal:
        if ctx.target_price is None:
            return Decimal(0)
        risk_per_unit = abs(ctx.entry_price - ctx.stop_loss)
        if risk_per_unit <= 0:
            return Decimal(0)
        return abs(ctx.target_price - ctx.entry_price) / risk_per_unit

    @staticmethod
    def _trigger_data_for(ctx: RiskCheckContext) -> dict:
        return {
            "entry_price": str(ctx.entry_price) if ctx.entry_price is not None else None,
            "stop_loss": str(ctx.stop_loss) if ctx.stop_loss is not None else None,
            "direction": ctx.direction,
        }

    @staticmethod
    def _infer_direction(rule_id: str, event_type: str, trigger_data: dict) -> str:
        explicit = trigger_data.get("direction")
        if explicit in {"long", "short"}:
            return explicit
        if rule_id in _LONG_RULES:
            return "long"
        if rule_id in _SHORT_RULES:
            return "short"
        if event_type in {"BREAKOUT", "long"}:
            return "long"
        if event_type in {"BREAKDOWN", "short"}:
            return "short"
        return "long"

    @staticmethod
    def _to_decimal(value: object) -> Decimal | None:
        if value is None:
            return None
        try:
            return Decimal(str(value))
        except (TypeError, ValueError, ArithmeticError):
            return None
