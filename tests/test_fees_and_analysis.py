"""Fee schedule, gross/net metrics and cost: the case-study values for both test cases."""

from decimal import Decimal as D

import pytest

from pe_waterfall.analysis import analyze
from pe_waterfall.fees import fee_schedule
from pe_waterfall.irr import irr_from_cashflows, irr_from_multiple
from pe_waterfall.models import ClassTerms, FundParams, InputError, Proceeds
from pe_waterfall.presets import CLASS_A, CLASS_B, FUND, PROCEEDS

EXPECTED = {
    "A": dict(fee_early=D("118750"), fee_late=D("71250"), fees=D("950000"), cost=D("3950000"),
              net=D("19950000"), net_tvpi=D("2.10"), net_irr=D("0.0770")),
    "B": dict(fee_early=D("237500"), fee_late=D("142500"), fees=D("1900000"), cost=D("3400000"),
              net=D("20425000"), net_tvpi=D("2.15"), net_irr=D("0.0796")),
}


@pytest.mark.parametrize("key,terms", [("A", CLASS_A), ("B", CLASS_B)])
def test_case_study_fees_and_costs(key, terms):
    exp = EXPECTED[key]
    result = analyze(FUND, terms, PROCEEDS)

    assert len(result.fee_years) == 10
    assert all(y.fee == exp["fee_early"] for y in result.fee_years[:5])
    assert all(y.fee == exp["fee_late"] for y in result.fee_years[5:])
    assert result.total_fees == exp["fees"]
    assert result.total_cost == exp["cost"]
    assert result.net_to_lp == exp["net"]
    assert round(result.net_tvpi, 2) == exp["net_tvpi"]
    assert round(result.net_irr, 4) == exp["net_irr"]


def test_gross_metrics_match_case_study():
    result = analyze(FUND, CLASS_A, PROCEEDS)
    assert result.gross_tvpi == D("2.5")
    assert round(result.gross_irr, 4) == D("0.0960")
    assert result.tvpi_drag == D("2.5") - result.net_tvpi
    assert result.irr_drag > 0


def test_cumulative_fees_are_running_sum():
    years = fee_schedule(FUND, CLASS_A)
    assert years[0].cumulative == D("118750")
    assert years[4].cumulative == D("593750")
    assert years[9].cumulative == D("950000")


def test_fee_base_is_lp_commitment_not_total_capital():
    fund = FundParams(10_000_000, "0.5", "0.06", 10, 5, 1)
    assert fee_schedule(fund, CLASS_A)[0].fee == D("62500")  # 5,000,000 * 1.25 %


def test_fractional_holding_period_pro_rates_last_year():
    fund = FundParams(10_000_000, "0.95", "0.06", "6.5", 5, 1)
    years = fee_schedule(fund, CLASS_A)
    assert len(years) == 7
    assert years[6].fee == D("35625.00")  # half of 71,250


def test_investment_period_longer_than_hold_uses_early_rate_throughout():
    fund = FundParams(10_000_000, "0.95", "0.06", 4, 10, 1)
    assert {y.rate for y in fee_schedule(fund, CLASS_A)} == {D("0.0125")}


def test_loss_scenario_net_figures():
    result = analyze(FUND, CLASS_A, Proceeds("tvpi", "0.5"))
    assert result.carried_interest == 0
    assert result.net_to_lp == D("4750000") - D("950000")
    assert result.net_irr < 0


def test_total_loss_gives_minus_100_percent_and_negative_net():
    result = analyze(FUND, CLASS_A, Proceeds("amount", 0))
    assert result.gross_irr == -1
    assert result.net_tvpi < 0
    assert result.net_irr == -1  # multiple <= 0 is reported as total loss


def test_irr_from_multiple():
    assert round(irr_from_multiple(D("2.5"), D(10)), 4) == D("0.0960")
    assert irr_from_multiple(D("1"), D(10)) == 0


def test_irr_from_cashflows_matches_multiple_based_irr():
    flows = [-100.0] + [0.0] * 9 + [250.0]
    assert irr_from_cashflows(flows) == pytest.approx(0.0960, abs=1e-4)


def test_irr_from_cashflows_with_interim_flows():
    # -100 now, +60 after 1 and 2 years: IRR is about 13.07 %.
    assert irr_from_cashflows([-100, 60, 60]) == pytest.approx(0.1307, abs=1e-4)


@pytest.mark.parametrize("flows", [[100, 50], [-100, -50], [-100]])
def test_irr_from_cashflows_rejects_undefined_cases(flows):
    with pytest.raises(InputError):
        irr_from_cashflows(flows)
