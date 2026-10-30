"""The two test cases of the case study, usable as presets (frontend) and test fixtures."""

from __future__ import annotations

from .models import ClassTerms, FundParams, Proceeds

# Fund-level parameters are identical in both test cases.
FUND = FundParams(
    committed_capital=10_000_000,
    lp_share="0.95",
    hurdle_rate="0.06",
    hold_years=10,
    investment_period_years=5,
    catchup_rate=1,
)

CLASS_A = ClassTerms("Class A", "0.0125", "0.0075", "0.20")
CLASS_B = ClassTerms("Class B", "0.025", "0.015", "0.10")

# Both scenarios assume a gross TVPI of 2.50x (= 25,000,000 proceeds, 9.60 % gross IRR).
PROCEEDS = Proceeds("tvpi", "2.5")

PRESETS = {
    "Test case 1 (Class A)": (FUND, CLASS_A, PROCEEDS),
    "Test case 2 (Class B)": (FUND, CLASS_B, PROCEEDS),
}
