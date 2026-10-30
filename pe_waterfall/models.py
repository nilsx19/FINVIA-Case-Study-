"""Input models and validation for the distribution waterfall and fee calculator.

All monetary values and rates are held as ``Decimal`` so that the waterfall can be
rounded to cents deterministically and the "sum of stages == proceeds" check is exact.
Rates are fractions (0.06 means 6 %), never percentages.
"""

from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation

ZERO = Decimal("0")
ONE = Decimal("1")

PROCEEDS_MODES = ("amount", "tvpi", "irr")


class InputError(ValueError):
    """Raised for invalid user input. The message is meant to be shown to the user."""


def to_decimal(value, name: str) -> Decimal:
    """Convert ``value`` to a finite Decimal or raise an ``InputError`` naming the field."""
    if isinstance(value, bool) or value is None:
        raise InputError(f"{name} must be a number.")
    try:
        result = Decimal(str(value).strip())
    except (InvalidOperation, ValueError):
        raise InputError(f"{name} must be a number, got {value!r}.") from None
    if not result.is_finite():
        raise InputError(f"{name} must be a finite number.")
    return result


def _set(obj, field: str, value) -> None:
    # Frozen dataclasses need object.__setattr__ to normalise values in __post_init__.
    object.__setattr__(obj, field, value)


@dataclass(frozen=True)
class FundParams:
    """Fund-level parameters shared by all share classes.

    committed_capital:       total subscribed capital (LP + GP equity), paid in at t = 0
    lp_share:                LP part of the committed capital (fraction, e.g. 0.95)
    hurdle_rate:             preferred return, compounded annually (fraction)
    hold_years:              holding period; proceeds arrive at the end of it
    investment_period_years: years during which the higher management fee applies
    catchup_rate:            share of distributions the GP receives during catch-up
                             (1.0 = full catch-up, 0 = no catch-up)
    """

    committed_capital: Decimal
    lp_share: Decimal
    hurdle_rate: Decimal
    hold_years: Decimal
    investment_period_years: Decimal
    catchup_rate: Decimal

    def __post_init__(self) -> None:
        names = {
            "committed_capital": "Committed capital",
            "lp_share": "LP share",
            "hurdle_rate": "Hurdle rate",
            "hold_years": "Holding period",
            "investment_period_years": "Investment period",
            "catchup_rate": "GP catch-up",
        }
        for field, label in names.items():
            _set(self, field, to_decimal(getattr(self, field), label))

        if self.committed_capital <= 0:
            raise InputError("Committed capital must be greater than 0.")
        if not (0 < self.lp_share <= 1):
            raise InputError("LP share must be greater than 0 % and at most 100 %.")
        if self.hurdle_rate < 0:
            raise InputError("Hurdle rate must not be negative.")
        if self.hold_years <= 0:
            raise InputError("Holding period must be greater than 0 years.")
        if self.investment_period_years < 0:
            raise InputError("Investment period must not be negative.")
        if not (0 <= self.catchup_rate <= 1):
            raise InputError("GP catch-up must be between 0 % and 100 %.")

    @property
    def gp_share(self) -> Decimal:
        return ONE - self.lp_share

    @property
    def lp_commitment(self) -> Decimal:
        return self.committed_capital * self.lp_share

    @property
    def gp_commitment(self) -> Decimal:
        return self.committed_capital * self.gp_share


@dataclass(frozen=True)
class ClassTerms:
    """Economic terms of one share class: management fee schedule and carried interest."""

    name: str
    fee_rate_investment_period: Decimal
    fee_rate_after: Decimal
    carry_rate: Decimal

    def __post_init__(self) -> None:
        names = {
            "fee_rate_investment_period": "Management fee (investment period)",
            "fee_rate_after": "Management fee (after investment period)",
            "carry_rate": "Carried interest",
        }
        for field, label in names.items():
            _set(self, field, to_decimal(getattr(self, field), label))

        if not (0 <= self.fee_rate_investment_period <= 1):
            raise InputError("Management fee (investment period) must be between 0 % and 100 %.")
        if not (0 <= self.fee_rate_after <= 1):
            raise InputError("Management fee (after investment period) must be between 0 % and 100 %.")
        if not (0 <= self.carry_rate < 1):
            raise InputError("Carried interest must be at least 0 % and below 100 %.")


@dataclass(frozen=True)
class Proceeds:
    """Realised proceeds, specified as an amount, a gross TVPI or a gross IRR.

    ``value`` is a currency amount for mode ``amount``, a multiple for ``tvpi``
    (2.5 = 2.50x) and a fraction for ``irr`` (0.096 = 9.6 % p.a.).
    """

    mode: str
    value: Decimal

    def __post_init__(self) -> None:
        if self.mode not in PROCEEDS_MODES:
            raise InputError(f"Proceeds mode must be one of {', '.join(PROCEEDS_MODES)}.")
        _set(self, "value", to_decimal(self.value, "Proceeds value"))
        if self.mode == "amount" and self.value < 0:
            raise InputError("Proceeds must not be negative.")
        if self.mode == "tvpi" and self.value < 0:
            raise InputError("TVPI must not be negative.")
        if self.mode == "irr" and self.value < -1:
            raise InputError("IRR must not be below -100 %.")

    def amount(self, fund: FundParams) -> Decimal:
        """Resolve to a currency amount (capital is paid in at t = 0, proceeds at the end)."""
        if self.mode == "amount":
            return self.value
        if self.mode == "tvpi":
            return self.value * fund.committed_capital
        return fund.committed_capital * (ONE + self.value) ** fund.hold_years
