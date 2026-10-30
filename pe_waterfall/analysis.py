"""Full analysis of one share class: waterfall + fees + gross/net TVPI and IRR + total cost."""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from .fees import FeeYear, fee_schedule
from .irr import irr_from_multiple
from .models import ZERO, ClassTerms, FundParams, Proceeds
from .waterfall import WaterfallResult, compute_waterfall


@dataclass(frozen=True)
class Analysis:
    terms: ClassTerms
    waterfall: WaterfallResult
    fee_years: tuple[FeeYear, ...]
    total_fees: Decimal
    carried_interest: Decimal
    total_cost: Decimal  # management fees + carried interest
    gross_tvpi: Decimal  # proceeds / committed capital (fund level, before fees and carry)
    gross_irr: Decimal
    lp_tvpi_before_fees: Decimal  # LP distribution (after carry) / LP commitment
    net_to_lp: Decimal  # LP distribution minus management fees
    net_tvpi: Decimal  # net to LP / LP commitment
    net_irr: Decimal

    @property
    def tvpi_drag(self) -> Decimal:
        """Gross TVPI minus net TVPI: what fees and carry cost the investor, in multiple points."""
        return self.gross_tvpi - self.net_tvpi

    @property
    def irr_drag(self) -> Decimal:
        """Gross IRR minus net IRR."""
        return self.gross_irr - self.net_irr


def analyze(fund: FundParams, terms: ClassTerms, proceeds: Proceeds) -> Analysis:
    amount = proceeds.amount(fund)
    waterfall = compute_waterfall(fund, terms.carry_rate, amount)
    fees = fee_schedule(fund, terms)
    total_fees = fees[-1].cumulative if fees else ZERO

    gross_tvpi = waterfall.proceeds / fund.committed_capital
    lp_commitment = fund.lp_commitment
    net_to_lp = waterfall.lp_total - total_fees
    net_tvpi = net_to_lp / lp_commitment

    return Analysis(
        terms=terms,
        waterfall=waterfall,
        fee_years=fees,
        total_fees=total_fees,
        carried_interest=waterfall.gp_carry_total,
        total_cost=total_fees + waterfall.gp_carry_total,
        gross_tvpi=gross_tvpi,
        gross_irr=irr_from_multiple(gross_tvpi, fund.hold_years),
        lp_tvpi_before_fees=waterfall.lp_total / lp_commitment,
        net_to_lp=net_to_lp,
        net_tvpi=net_tvpi,
        net_irr=irr_from_multiple(net_tvpi, fund.hold_years),
    )
