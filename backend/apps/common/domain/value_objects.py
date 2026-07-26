from __future__ import annotations

import hashlib
from dataclasses import dataclass, fields
from decimal import Decimal
from typing import Any


class ValueObject:
    """Abstract base class for immutable value objects.

    Implements equality and hashing based on all dataclass fields.
    All concrete value objects should be frozen dataclasses.
    """

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, self.__class__):
            return NotImplemented
        return all(
            getattr(self, f.name) == getattr(other, f.name)
            for f in fields(self)
        )

    def __hash__(self) -> int:
        return hash(tuple(getattr(self, f.name) for f in fields(self)))

    def __repr__(self) -> str:
        cls = self.__class__.__name__
        vals = ", ".join(
            f"{f.name}={getattr(self, f.name)!r}" for f in fields(self)
        )
        return f"{cls}({vals})"


@dataclass(frozen=True)
class Money(ValueObject):
    """Represents a monetary amount in a specific currency."""

    amount: Decimal
    currency: str = "INR"

    def __post_init__(self) -> None:
        if not isinstance(self.amount, Decimal):
            raise TypeError(
                f"Money.amount must be a Decimal, got {type(self.amount).__name__}"
            )

    def _check_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"Currency mismatch: {self.currency} != {other.currency}"
            )

    def __add__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def __sub__(self, other: Money) -> Money:
        self._check_currency(other)
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def __mul__(self, factor: Decimal) -> Money:
        if not isinstance(factor, Decimal):
            raise TypeError(
                f"Factor must be a Decimal, got {type(factor).__name__}"
            )
        return Money(amount=self.amount * factor, currency=self.currency)

    def is_negative(self) -> bool:
        return self.amount < 0


@dataclass(frozen=True)
class Symbol(ValueObject):
    """Represents a financial instrument identifier."""

    exchange: str
    tradingsymbol: str
    instrument_token: int | None = None
    segment: str | None = None

    def as_broker_string(self) -> str:
        """Return the broker-standard string representation."""
        return f"{self.exchange}:{self.tradingsymbol}"


@dataclass(frozen=True)
class IdempotencyKey(ValueObject):
    """Deterministic idempotency key for exactly-once operation semantics."""

    value: str

    @classmethod
    def generate(cls, *parts: str) -> IdempotencyKey:
        """Generate a deterministic idempotency key from the given parts.

        Args:
            *parts: String parts that uniquely identify the operation.

        Returns:
            An IdempotencyKey whose value is the SHA-256 hash of the
            joined parts.
        """
        raw = ":".join(parts)
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return cls(value=digest)
