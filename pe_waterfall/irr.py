"""Return metrics: IRR from a multiple (TVPI) and from an arbitrary cash flow series."""

from __future__ import annotations

from decimal import Decimal

from .models import InputError


def irr_from_multiple(multiple: Decimal, years: Decimal) -> Decimal:
    """Annual return implied by a multiple over ``years`` (single outflow at t=0, single inflow at the end).

    A multiple of 0 or less is a total loss: -100 %.
    """
    if multiple <= 0:
        return Decimal(-1)
    return multiple ** (Decimal(1) / years) - 1


def irr_from_cashflows(cashflows: list[float], periods_per_year: float = 1.0) -> float:
    """IRR of equally spaced cash flows (index 0 = today), found by bisection on the NPV.

    Negative values are outflows, positive values inflows. Returns an annual rate.
    Raises ``InputError`` if there is no sign change (IRR undefined).
    """
    if len(cashflows) < 2:
        raise InputError("At least two cash flows are required.")
    if not (any(c < 0 for c in cashflows) and any(c > 0 for c in cashflows)):
        raise InputError("Cash flows need at least one outflow (negative) and one inflow (positive).")

    def npv(rate: float) -> float:
        return sum(cf / (1 + rate) ** t for t, cf in enumerate(cashflows))

    low, high = -0.9999, 1.0
    while npv(low) * npv(high) > 0 and high < 1e6:  # widen the bracket for very high returns
        high *= 2
    if npv(low) * npv(high) > 0:
        raise InputError("Could not find an IRR for these cash flows.")
    for _ in range(200):
        mid = (low + high) / 2
        if npv(low) * npv(mid) <= 0:
            high = mid
        else:
            low = mid
    period_rate = (low + high) / 2
    return (1 + period_rate) ** periods_per_year - 1
