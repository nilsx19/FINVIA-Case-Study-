"""Share class comparison and break-even analysis (bonus part of the case study).

Cost of a class for the investor = total management fees + carried interest.
The cost is a continuous, piecewise-linear function of the proceeds, so crossings of the
two cost curves can be located by scanning a TVPI grid and refining with bisection.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .analysis import Analysis, analyze
from .fees import fee_schedule
from .models import ClassTerms, FundParams, InputError, Proceeds
from .waterfall import compute_waterfall


@dataclass(frozen=True)
class Comparison:
    a: Analysis
    b: Analysis

    @property
    def cheaper(self) -> str | None:
        """Name of the class with the lower total cost, or None on a tie."""
        if self.a.total_cost == self.b.total_cost:
            return None
        return self.a.terms.name if self.a.total_cost < self.b.total_cost else self.b.terms.name

    @property
    def saving(self) -> Decimal:
        """Absolute cost advantage of the cheaper class."""
        return abs(self.a.total_cost - self.b.total_cost)


def compare(fund: FundParams, a: ClassTerms, b: ClassTerms, proceeds: Proceeds) -> Comparison:
    return Comparison(analyze(fund, a, proceeds), analyze(fund, b, proceeds))


@dataclass(frozen=True)
class SweepPoint:
    gross_tvpi: Decimal
    cost_a: Decimal
    cost_b: Decimal
    net_tvpi_a: Decimal
    net_tvpi_b: Decimal

    @property
    def cheaper_is_a(self) -> bool | None:
        if self.cost_a == self.cost_b:
            return None
        return self.cost_a < self.cost_b


def _total_cost(fund: FundParams, terms: ClassTerms, fees_total: Decimal, tvpi: Decimal) -> Decimal:
    carry = compute_waterfall(fund, terms.carry_rate, tvpi * fund.committed_capital).gp_carry_total
    return fees_total + carry


def sweep(fund: FundParams, a: ClassTerms, b: ClassTerms, tvpi_values: list[Decimal]) -> list[SweepPoint]:
    """Cost and net TVPI of both classes for each gross TVPI in ``tvpi_values``."""
    fees_a = fee_schedule(fund, a)[-1].cumulative
    fees_b = fee_schedule(fund, b)[-1].cumulative
    points = []
    for tvpi in tvpi_values:
        wa = compute_waterfall(fund, a.carry_rate, tvpi * fund.committed_capital)
        wb = compute_waterfall(fund, b.carry_rate, tvpi * fund.committed_capital)
        points.append(
            SweepPoint(
                gross_tvpi=tvpi,
                cost_a=fees_a + wa.gp_carry_total,
                cost_b=fees_b + wb.gp_carry_total,
                net_tvpi_a=(wa.lp_total - fees_a) / fund.lp_commitment,
                net_tvpi_b=(wb.lp_total - fees_b) / fund.lp_commitment,
            )
        )
    return points


def tvpi_grid(low: Decimal, high: Decimal, step: Decimal) -> list[Decimal]:
    """Evenly spaced gross TVPI values from ``low`` to ``high`` inclusive."""
    if step <= 0:
        raise InputError("TVPI step must be greater than 0.")
    if low < 0 or high <= low:
        raise InputError("TVPI range must satisfy 0 <= from < to.")
    if (high - low) / step > 5000:
        raise InputError("TVPI range has too many steps (max. 5,000). Increase the step size.")
    values = []
    current = low
    while current < high:
        values.append(current)
        current += step
    values.append(high)
    return values


def break_even_tvpis(
    fund: FundParams,
    a: ClassTerms,
    b: ClassTerms,
    low: Decimal,
    high: Decimal,
    step: Decimal = Decimal("0.05"),
) -> list[Decimal]:
    """Gross TVPIs in [low, high] at which the cheaper class switches.

    Scans the grid for sign changes of ``cost_a - cost_b`` and refines each by bisection.
    Returns an empty list if one class is cheaper throughout the range.
    """
    fees_a = fee_schedule(fund, a)[-1].cumulative
    fees_b = fee_schedule(fund, b)[-1].cumulative

    def diff(tvpi: Decimal) -> Decimal:
        return _total_cost(fund, a, fees_a, tvpi) - _total_cost(fund, b, fees_b, tvpi)

    grid = tvpi_grid(low, high, step)
    diffs = [diff(t) for t in grid]
    crossings = []
    last = None  # index of the most recent grid point where the costs differ
    for i, d in enumerate(diffs):
        if d == 0:
            continue  # tie: neither class is cheaper here, keep looking for a sign change
        if last is not None and diffs[last] * d < 0:
            if i - last > 1:
                crossings.append(grid[last + 1])  # costs are exactly equal on grid points in between
            else:
                lo, hi = grid[last], grid[i]
                for _ in range(60):
                    mid = (lo + hi) / 2
                    if diff(lo) * diff(mid) <= 0:
                        hi = mid
                    else:
                        lo = mid
                crossings.append(((lo + hi) / 2).quantize(Decimal("0.0001")))
        last = i
    return crossings
