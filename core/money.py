"""Exact money comparison for policy caps.

Amounts travel as floats on the wire and in signed payloads (changing that
would change every digest), but cap arithmetic must not inherit binary
rounding: 0.1 + 0.2 > 0.3 is True in floats. Values are converted through
their shortest repr (what the caller actually typed) into Decimal, and every
comparison fails closed on values that are not real, non-negative amounts.
"""
from __future__ import annotations

import math
from decimal import Decimal


def is_valid_amount(value: object) -> bool:
    """True only for finite, non-negative numbers (bool is not an amount)."""
    if isinstance(value, bool) or not isinstance(value, (int, float, Decimal)):
        return False
    if isinstance(value, float) and not math.isfinite(value):
        return False
    if isinstance(value, Decimal) and not value.is_finite():
        return False
    return value >= 0


def to_decimal(value: int | float | Decimal) -> Decimal:
    if isinstance(value, Decimal):
        return value
    if isinstance(value, float):
        return Decimal(repr(value))
    return Decimal(value)


def exceeds(amount: object, cap: int | float | Decimal) -> bool:
    """amount > cap, exactly. An invalid amount always 'exceeds' (fail closed)."""
    if not is_valid_amount(amount):
        return True
    return to_decimal(amount) > to_decimal(cap)  # type: ignore[arg-type]


def total(*values: int | float | Decimal) -> Decimal:
    return sum((to_decimal(v) for v in values), Decimal(0))
