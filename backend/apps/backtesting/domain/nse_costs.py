"""Realistic NSE equity execution cost model (Risk Sophistication batch).

The historical flat model charges ``commission_rate`` and a flat
``slippage_bps`` per fill. Real Indian-equity costs are a bundle of statutory
charges plus market impact that scales with order size relative to typical
volume:

- **STT** (Securities Transaction Tax) — charged on the *sell* side only
  (delivery 0.10%, intraday 0.025%).
- **Brokerage** — broker-specific; modelled here as a flat per-order fee (or
  optionally a percentage of notional).
- **Exchange transaction charges** — NSE cash segment 0.00297% of turnover
  (buy + sell).
- **SEBI turnover fee** — 0.0001% (₹10/crore) of turnover.
- **GST** — 18% levied on (brokerage + exchange charges + SEBI fee).
- **Stamp duty** — charged on the *buy* side (delivery 0.015%, intraday
  0.003%).
- **Impact cost** — size-dependent, NOT a flat basis-point slip: the base
  impact scales with the order's notional relative to a reference
  typical-volume figure, capped at a configurable multiple.

The model is pure and Decimal-only (mirrors the repo's no-float money rule);
``compute_trade_cost`` is a deterministic function of ``(quantity, price,
side, model)`` so every number is unit-testable against hand-computed values.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from apps.portfolio.domain.value_objects import Side

# NSE cash-segment statutory rates (2025). Rates are expressed as fractions of
# turnover so the model never mixes units.
STT_DELIVERY_SELL_RATE = Decimal("0.001")  # 0.10% sell side
STT_INTRADAY_SELL_RATE = Decimal("0.00025")  # 0.025% sell side
EXCHANGE_TRANSACTION_CHARGE_RATE = Decimal("0.0000297")  # 0.00297% of turnover
SEBI_TURNOVER_FEE_RATE = Decimal("0.000001")  # ₹10/crore = 0.0001%
GST_RATE = Decimal("0.18")  # 18% on brokerage + exchange + SEBI
STAMP_DUTY_DELIVERY_BUY_RATE = Decimal("0.00015")  # 0.015% buy side
STAMP_DUTY_INTRADAY_BUY_RATE = Decimal("0.00003")  # 0.003% buy side


def _product_rates(product: str) -> tuple[Decimal, Decimal]:
    if product == "intraday":
        return STT_INTRADAY_SELL_RATE, STAMP_DUTY_INTRADAY_BUY_RATE
    return STT_DELIVERY_SELL_RATE, STAMP_DUTY_DELIVERY_BUY_RATE


@dataclass(frozen=True)
class NseCostModel:
    """Configuration for the NSE cost function.

    ``product`` is ``"delivery"`` (default) or ``"intraday"`` and selects the
    STT / stamp-duty legs. ``brokerage_per_order`` (flat ₹) is the default;
    set ``brokerage_pct`` to charge a percentage of notional instead. The
    impact-cost leg scales ``impact_base_bps`` by the order's notional
    relative to ``impact_reference_adv``, capped at ``impact_max_multiple`` x
    the base — this is the "size-dependent, not flat slippage" requirement.
    """

    product: str = "delivery"
    stt_sell_rate: Decimal | None = None
    brokerage_per_order: Decimal = Decimal("20")
    brokerage_pct: Decimal | None = None
    transaction_charge_rate: Decimal = EXCHANGE_TRANSACTION_CHARGE_RATE
    sebi_fee_rate: Decimal = SEBI_TURNOVER_FEE_RATE
    stamp_duty_buy_rate: Decimal | None = None
    gst_rate: Decimal = GST_RATE
    impact_base_bps: Decimal = Decimal("5")
    impact_reference_adv: Decimal = Decimal("1000000")
    impact_max_multiple: Decimal = Decimal("5")

    def __post_init__(self) -> None:
        stt, stamp = _product_rates(self.product)
        if self.stt_sell_rate is None:
            object.__setattr__(self, "stt_sell_rate", stt)
        if self.stamp_duty_buy_rate is None:
            object.__setattr__(self, "stamp_duty_buy_rate", stamp)


def _side_is_sell(side: Side | str) -> bool:
    raw = side.value if isinstance(side, Side) else str(side).upper()
    return raw in {"SELL", "SHORT"}


def impact_bps_for(
    model: NseCostModel,
    notional: Decimal,
) -> Decimal:
    """Size-dependent impact in basis points.

    ``base`` at or below the reference ADV figure, scaling linearly (capped at
    ``impact_max_multiple`` x base) as the order's notional grows relative to
    it. Floor of 1x keeps small orders on the base cost.
    """
    if model.impact_reference_adv <= 0 or notional <= 0:
        return model.impact_base_bps
    ratio = notional / model.impact_reference_adv
    scale = max(Decimal("1"), ratio)
    scale = min(scale, model.impact_max_multiple)
    return model.impact_base_bps * scale


def compute_trade_cost(
    *,
    quantity: Decimal,
    price: Decimal,
    side: Side | str,
    model: NseCostModel,
) -> dict[str, Decimal]:
    """Compute the full NSE cost breakdown for one fill leg.

    Returns a dict with ``stt``, ``brokerage``, ``exchange_charges``,
    ``sebi_fee``, ``stamp_duty``, ``gst``, ``impact_cost`` and ``total`` — all
    ``Decimal``, all in the same currency unit as the notional.
    """
    notional = quantity * price
    is_sell = _side_is_sell(side)

    stt = notional * model.stt_sell_rate if is_sell else Decimal("0")

    if model.brokerage_pct is not None:
        brokerage = notional * model.brokerage_pct
    else:
        brokerage = model.brokerage_per_order

    exchange_charges = notional * model.transaction_charge_rate
    sebi_fee = notional * model.sebi_fee_rate
    stamp_duty = notional * model.stamp_duty_buy_rate if not is_sell else Decimal("0")
    gst_base = brokerage + exchange_charges + sebi_fee
    gst = gst_base * model.gst_rate
    impact_cost = notional * impact_bps_for(model, notional) / Decimal("10000")

    total = stt + brokerage + exchange_charges + sebi_fee + stamp_duty + gst + impact_cost
    return {
        "stt": stt,
        "brokerage": brokerage,
        "exchange_charges": exchange_charges,
        "sebi_fee": sebi_fee,
        "stamp_duty": stamp_duty,
        "gst": gst,
        "impact_cost": impact_cost,
        "total": total,
    }


def nse_cost_model_from_settings() -> NseCostModel:
    """Build a :class:`NseCostModel` from ``settings.BACKTEST_NSE_COST_MODEL``.

    Absent/missing keys fall back to the realistic defaults above so the model
    is usable out-of-the-box.
    """
    from django.conf import settings

    raw = getattr(settings, "BACKTEST_NSE_COST_MODEL", {}) or {}

    def dec(key: str) -> Decimal | None:
        value = raw.get(key)
        if value is None:
            return None
        return Decimal(str(value))

    def dec_or(key: str, default: Decimal) -> Decimal:
        value = dec(key)
        return default if value is None else value

    return NseCostModel(
        product=str(raw.get("product", "delivery")),
        stt_sell_rate=dec("stt_sell_rate"),
        brokerage_per_order=dec_or("brokerage_per_order", Decimal("20")),
        brokerage_pct=dec("brokerage_pct"),
        transaction_charge_rate=dec_or(
            "transaction_charge_rate", EXCHANGE_TRANSACTION_CHARGE_RATE
        ),
        sebi_fee_rate=dec_or("sebi_fee_rate", SEBI_TURNOVER_FEE_RATE),
        stamp_duty_buy_rate=dec("stamp_duty_buy_rate"),
        gst_rate=dec_or("gst_rate", GST_RATE),
        impact_base_bps=dec_or("impact_base_bps", Decimal("5")),
        impact_reference_adv=dec_or("impact_reference_adv", Decimal("1000000")),
        impact_max_multiple=dec_or("impact_max_multiple", Decimal("5")),
    )


def default_nse_cost_model() -> NseCostModel:
    """Realistic delivery defaults (no settings dependency) for unit tests."""
    return NseCostModel(product="delivery")