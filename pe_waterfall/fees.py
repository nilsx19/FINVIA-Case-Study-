"""Management fee schedule.

The fee is charged on the LP commitment (not on invested or net asset value), at one
rate during the investment period and another rate afterwards. Fees run alongside the
waterfall: they are paid by the LP on top and do NOT reduce the distributable proceeds.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_CEILING, Decimal

from .models import ZERO, ClassTerms, FundParams
from .waterfall import quantize


@dataclass(frozen=True)
class FeeYear:
    year: int
    rate: Decimal
    fee: Decimal
    cumulative: Decimal


def fee_schedule(fund: FundParams, terms: ClassTerms) -> tuple[FeeYear, ...]:
    """Fee per year and cumulative over the holding period.

    Year ``t`` (1-based) uses the investment-period rate if ``t <= investment_period_years``,
    otherwise the later rate. If the holding period is not a whole number of years, the
    last year is charged pro rata.
    """
    n_years = int(fund.hold_years.to_integral_value(rounding=ROUND_CEILING))
    base = fund.lp_commitment
    rows = []
    cumulative = ZERO
    for year in range(1, n_years + 1):
        rate = terms.fee_rate_investment_period if year <= fund.investment_period_years else terms.fee_rate_after
        fraction = min(Decimal(1), fund.hold_years - (year - 1))
        fee = quantize(base * rate * fraction)
        cumulative += fee
        rows.append(FeeYear(year, rate, fee, cumulative))
    return tuple(rows)
