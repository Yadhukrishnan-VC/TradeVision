from __future__ import annotations

from decimal import Decimal


class ExecutionDomainError(Exception):
    """Base error for the paper execution domain."""

    def __init__(self, message: str, *, code: str = "EXECUTION_ERROR") -> None:
        super().__init__(message)
        self.message = message
        self.code = code


class UnknownRuleError(ExecutionDomainError):
    """Raised when a rule id cannot be mapped to a direction."""

    def __init__(self, rule_id: str) -> None:
        super().__init__(
            f"Cannot derive position side for unknown rule_id={rule_id!r}",
            code="UNKNOWN_RULE",
        )
        self.rule_id = rule_id


class InvalidOrderTransition(ExecutionDomainError):
    """Raised when an order attempts an illegal state transition."""

    def __init__(self, current: str, next_status: str) -> None:
        super().__init__(
            f"Invalid order transition {current!r} -> {next_status!r}",
            code="INVALID_ORDER_TRANSITION",
        )
        self.current = current
        self.next_status = next_status


class BrokerRejection(ExecutionDomainError):
    """Raised by a broker adapter when it rejects a submitted order."""

    def __init__(self, reason_code: str, reason_message: str) -> None:
        super().__init__(
            reason_message,
            code=reason_code,
        )
        self.reason_code = reason_code
        self.reason_message = reason_message


class ExecutionRequestValidationError(ExecutionDomainError):
    """Raised when a RiskApproved payload is missing required fields."""

    def __init__(self, message: str) -> None:
        super().__init__(message, code="INVALID_EXECUTION_PAYLOAD")


class NoDefaultAccountError(ExecutionDomainError):
    """Raised when no seeded default account exists to route execution to."""

    def __init__(self) -> None:
        super().__init__(
            "No default Account (is_default=True) available for execution routing",
            code="NO_DEFAULT_ACCOUNT",
        )


class InsufficientCapitalForExecution(ExecutionDomainError):
    """Raised when available capital cannot cover the order's notional.

    Exposes the shortfall the M3/M4 capital gate rejects on so the intake can
    persist a ``REJECTED_INSUFFICIENT_CAPITAL`` ExecutionRequest.
    """

    def __init__(self, available: Decimal, required: Decimal) -> None:
        super().__init__(
            f"Available capital {available} < required notional {required}",
            code="INSUFFICIENT_CAPITAL",
        )
        self.available = available
        self.required = required
