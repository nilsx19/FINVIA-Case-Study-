"""Distribution waterfall with preferred return, GP catch-up and carried interest.

Stages (European / whole-fund style, single distribution at the end of the holding period):

1. Return of capital plus preferred return, split pro rata between LP and GP equity.
2. GP catch-up: the GP receives ``catchup_rate`` of every euro until its carry equals
   ``carry_rate`` of all profit distributed so far (preferred return + catch-up tier).
   The remainder of the tier (if catch-up < 100 %) is split pro rata between LP and GP equity.
3. Residual split: ``carry_rate`` to the GP as carried interest, the rest pro rata
   between LP and GP equity.

Money is rounded to cents per stage. The last stage takes the residual, and inside
each stage LP takes the residual, so rounding never creates or destroys a cent.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import ROUND_HALF_UP, Decimal

from .models import ZERO, ClassTerms, FundParams, InputError, Proceeds

CENT = Decimal("0.01")


def quantize(amount: Decimal) -> Decimal:
    return amount.quantize(CENT, rounding=ROUND_HALF_UP)


@dataclass(frozen=True)
class Stage:
    name: str
    total: Decimal
    lp: Decimal
    gp_equity: Decimal
    gp_carry: Decimal


@dataclass(frozen=True)
class WaterfallResult:
    proceeds: Decimal
    preferred_return: Decimal
    stages: tuple[Stage, ...]
    lp_total: Decimal
    gp_equity_total: Decimal
    gp_carry_total: Decimal
    # Explicit integrity checks required by the case study.
    stage_sum: Decimal
    party_sum: Decimal
    check_ok: bool

    def share_of_proceeds(self, amount: Decimal) -> Decimal:
        """Amount as a fraction of the proceeds (0 if there are no proceeds)."""
        return amount / self.proceeds if self.proceeds else ZERO


def catchup_capacity(preferred_return: Decimal, carry_rate: Decimal, catchup_rate: Decimal) -> Decimal:
    """Size of the catch-up tier.

    During the tier the GP gets ``catchup_rate * X``. It ends once
    ``catchup_rate * X == carry_rate * (preferred_return + X)``, hence
    ``X = carry_rate * pref / (catchup_rate - carry_rate)``.
    With 100 % catch-up and 20 % carry: X = 0.25 * pref.
    """
    if catchup_rate == 0 or carry_rate == 0 or preferred_return == 0:
        return ZERO
    return carry_rate * preferred_return / (catchup_rate - carry_rate)


def compute_waterfall(fund: FundParams, carry_rate: Decimal, proceeds_amount: Decimal) -> WaterfallResult:
    """Run the distribution waterfall for a given amount of proceeds."""
    if proceeds_amount < 0:
        raise InputError("Proceeds must not be negative.")
    if carry_rate > 0 and 0 < fund.catchup_rate <= carry_rate:
        raise InputError(
            "GP catch-up must be 0 % (no catch-up) or higher than the carried interest rate, "
            "otherwise the catch-up tier never ends."
        )

    capital = fund.committed_capital
    gp_share = fund.gp_share
    proceeds = quantize(proceeds_amount)

    # Preferred return: hurdle rate compounded annually on the total capital (LP + GP equity).
    preferred_return = quantize(capital * ((1 + fund.hurdle_rate) ** fund.hold_years - 1))

    # Stage 1: capital + preferred return, pro rata.
    s1_total = quantize(min(proceeds, capital + preferred_return))
    s1_gp = quantize(s1_total * gp_share)
    stage1 = Stage("Stage 1: Capital + Preferred Return", s1_total, s1_total - s1_gp, s1_gp, ZERO)
    remaining = proceeds - s1_total

    # Stage 2: GP catch-up.
    capacity = catchup_capacity(preferred_return, carry_rate, fund.catchup_rate)
    s2_total = quantize(min(remaining, capacity))
    s2_carry = quantize(s2_total * fund.catchup_rate)
    s2_other = s2_total - s2_carry
    s2_gp = quantize(s2_other * gp_share)
    stage2 = Stage("Stage 2: GP Catch-Up", s2_total, s2_other - s2_gp, s2_gp, s2_carry)
    remaining -= s2_total

    # Stage 3: residual split between carry and pro-rata distribution.
    s3_total = remaining
    s3_carry = quantize(s3_total * carry_rate)
    s3_other = s3_total - s3_carry
    s3_gp = quantize(s3_other * gp_share)
    stage3 = Stage("Stage 3: Residual Split", s3_total, s3_other - s3_gp, s3_gp, s3_carry)

    stages = (stage1, stage2, stage3)
    lp_total = sum((s.lp for s in stages), ZERO)
    gp_equity_total = sum((s.gp_equity for s in stages), ZERO)
    gp_carry_total = sum((s.gp_carry for s in stages), ZERO)
    stage_sum = sum((s.total for s in stages), ZERO)
    party_sum = lp_total + gp_equity_total + gp_carry_total

    return WaterfallResult(
        proceeds=proceeds,
        preferred_return=preferred_return,
        stages=stages,
        lp_total=lp_total,
        gp_equity_total=gp_equity_total,
        gp_carry_total=gp_carry_total,
        stage_sum=stage_sum,
        party_sum=party_sum,
        check_ok=(stage_sum == proceeds and party_sum == proceeds),
    )


def run_waterfall(fund: FundParams, terms: ClassTerms, proceeds: Proceeds) -> WaterfallResult:
    """Convenience wrapper: resolve proceeds (amount / TVPI / IRR) and run the waterfall."""
    return compute_waterfall(fund, terms.carry_rate, proceeds.amount(fund))
