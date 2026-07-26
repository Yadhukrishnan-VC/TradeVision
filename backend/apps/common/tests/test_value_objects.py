from __future__ import annotations

from decimal import Decimal

import pytest

from apps.common.domain.value_objects import IdempotencyKey, Money, Symbol


class TestMoney:
    def test_accepts_decimal_amount(self) -> None:
        m = Money(amount=Decimal("100.50"))
        assert m.amount == Decimal("100.50")
        assert m.currency == "INR"

    def test_rejects_float_amount(self) -> None:
        with pytest.raises(TypeError, match="Money.amount must be a Decimal"):
            Money(amount=100.50)  # type: ignore[arg-type]

    def test_rejects_int_amount(self) -> None:
        with pytest.raises(TypeError, match="Money.amount must be a Decimal"):
            Money(amount=100)  # type: ignore[arg-type]

    def test_add_same_currency(self) -> None:
        a = Money(Decimal("100"), "USD")
        b = Money(Decimal("50"), "USD")
        result = a + b
        assert result.amount == Decimal("150")
        assert result.currency == "USD"

    def test_add_different_currency_raises(self) -> None:
        a = Money(Decimal("100"), "USD")
        b = Money(Decimal("50"), "INR")
        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = a + b

    def test_sub_same_currency(self) -> None:
        a = Money(Decimal("100"), "INR")
        b = Money(Decimal("30"), "INR")
        result = a - b
        assert result.amount == Decimal("70")

    def test_sub_different_currency_raises(self) -> None:
        a = Money(Decimal("100"), "USD")
        b = Money(Decimal("30"), "INR")
        with pytest.raises(ValueError, match="Currency mismatch"):
            _ = a - b

    def test_mul_by_decimal_factor(self) -> None:
        m = Money(Decimal("100"), "INR")
        result = m * Decimal("2.5")
        assert result.amount == Decimal("250")
        assert result.currency == "INR"

    def test_mul_rejects_float_factor(self) -> None:
        m = Money(Decimal("100"), "INR")
        with pytest.raises(TypeError, match="Factor must be a Decimal"):
            _ = m * 2.5  # type: ignore[operator]

    def test_is_negative_true(self) -> None:
        m = Money(Decimal("-10"))
        assert m.is_negative() is True

    def test_is_negative_false(self) -> None:
        m = Money(Decimal("10"))
        assert m.is_negative() is False

    def test_equality(self) -> None:
        a = Money(Decimal("100"), "INR")
        b = Money(Decimal("100"), "INR")
        c = Money(Decimal("100"), "USD")
        assert a == b
        assert a != c

    def test_immutability(self) -> None:
        m = Money(Decimal("100"))
        with pytest.raises(AttributeError):
            m.amount = Decimal("200")  # type: ignore[misc]

    def test_default_currency(self) -> None:
        m = Money(Decimal("50"))
        assert m.currency == "INR"


class TestSymbol:
    def test_as_broker_string(self) -> None:
        s = Symbol(exchange="NSE", tradingsymbol="RELIANCE")
        assert s.as_broker_string() == "NSE:RELIANCE"

    def test_with_optional_fields(self) -> None:
        s = Symbol(exchange="NSE", tradingsymbol="INFY", instrument_token=12345, segment="EQ")
        assert s.instrument_token == 12345
        assert s.segment == "EQ"

    def test_equality(self) -> None:
        a = Symbol(exchange="NSE", tradingsymbol="TCS")
        b = Symbol(exchange="NSE", tradingsymbol="TCS")
        c = Symbol(exchange="BSE", tradingsymbol="TCS")
        assert a == b
        assert a != c

    def test_frozen(self) -> None:
        s = Symbol(exchange="NSE", tradingsymbol="HDFC")
        with pytest.raises(AttributeError):
            s.exchange = "BSE"  # type: ignore[misc]


class TestIdempotencyKey:
    def test_generate_is_deterministic(self) -> None:
        k1 = IdempotencyKey.generate("user_1", "trade_42")
        k2 = IdempotencyKey.generate("user_1", "trade_42")
        assert k1 == k2

    def test_generate_different_inputs_differ(self) -> None:
        k1 = IdempotencyKey.generate("user_1", "trade_42")
        k2 = IdempotencyKey.generate("user_2", "trade_42")
        assert k1 != k2

    def test_value_is_sha256_hexdigest(self) -> None:
        k = IdempotencyKey.generate("a", "b")
        assert len(k.value) == 64
        assert all(c in "0123456789abcdef" for c in k.value)

    def test_single_part(self) -> None:
        k = IdempotencyKey.generate("single")
        assert len(k.value) == 64
