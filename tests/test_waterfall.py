"""Waterfall tests: the two case-study test cases plus edge cases."""

from decimal import Decimal as D

import pytest

from pe_waterfall.models import ClassTerms, FundParams, InputError, Proceeds
from pe_waterfall.presets import CLASS_A, CLASS_B, FUND, PROCEEDS
from pe_waterfall.waterfall import compute_waterfall, run_waterfall

EXPECTED = {
    "A": {
        "pref": D("7908476.97"),
        "stage1": D("17908476.97"),
        "stage2": D("1977119.24"),
        "stage3_lp": D("3886946.88"),
        "stage3_gp_equity": D("204576.15"),
        "stage3_carry": D("1022880.76"),
        "lp": D("20900000.00"),
        "gp_equity": D("1100000.00"),
        "carry": D("3000000.00"),
    },
    "B": {
        "pref": D("7908476.97"),
        "stage1": D("17908476.97"),
        "stage2": D("878719.66"),
        "stage3_lp": D("5311946.88"),
        "stage3_gp_equity": D("279576.15"),
        "stage3_carry": D("621280.34"),
        "lp": D("22325000.00"),
        "gp_equity": D("1175000.00"),
        "carry": D("1500000.00"),
    },
}


@pytest.mark.parametrize("key,terms", [("A", CLASS_A), ("B", CLASS_B)])
def test_case_study_waterfall(key, terms):
    exp = EXPECTED[key]
    result = run_waterfall(FUND, terms, PROCEEDS)
    s1, s2, s3 = result.stages

    assert result.proceeds == D("25000000.00")
    assert result.preferred_return == exp["pref"]
    assert s1.total == exp["stage1"]
    assert s2.total == exp["stage2"]
    assert s3.lp == exp["stage3_lp"]
    assert s3.gp_equity == exp["stage3_gp_equity"]
    assert s3.gp_carry == exp["stage3_carry"]
    assert result.lp_total == exp["lp"]
    assert result.gp_equity_total == exp["gp_equity"]
    assert result.gp_carry_total == exp["carry"]
    assert result.check_ok


def test_case_study_percentages_of_proceeds():
    result = run_waterfall(FUND, CLASS_A, PROCEEDS)
    assert round(result.share_of_proceeds(result.lp_total) * 100, 1) == D("83.6")
    assert round(result.share_of_proceeds(result.gp_equity_total) * 100, 1) == D("4.4")
    assert round(result.share_of_proceeds(result.gp_carry_total) * 100, 1) == D("12.0")


def test_carry_is_20_percent_of_profit_after_full_catchup():
    # With 100 % catch-up and enough proceeds, carry = carry_rate * total profit.
    result = run_waterfall(FUND, CLASS_A, PROCEEDS)
    profit = result.proceeds - FUND.committed_capital
    assert result.gp_carry_total == CLASS_A.carry_rate * profit


def test_proceeds_modes_are_equivalent():
    by_amount = run_waterfall(FUND, CLASS_A, Proceeds("amount", 25_000_000))
    by_tvpi = run_waterfall(FUND, CLASS_A, Proceeds("tvpi", "2.5"))
    by_irr = run_waterfall(FUND, CLASS_A, Proceeds("irr", D("2.5") ** (D(1) / 10) - 1))
    assert by_amount == by_tvpi
    # Resolving an IRR goes through a root, so allow a one-cent rounding difference.
    assert abs(by_irr.proceeds - by_amount.proceeds) <= D("0.01")
    assert by_irr.check_ok


def test_proceeds_below_paid_in_capital():
    # 6,000,000 on 10,000,000 invested: everything is return of capital, no carry.
    result = compute_waterfall(FUND, CLASS_A.carry_rate, D("6000000"))
    assert result.check_ok
    assert result.gp_carry_total == 0
    assert result.lp_total == D("5700000.00")
    assert result.gp_equity_total == D("300000.00")
    assert result.stages[1].total == 0
    assert result.stages[2].total == 0


def test_proceeds_between_capital_and_hurdle():
    # Above capital but below capital + preferred return: still no carry.
    result = compute_waterfall(FUND, CLASS_A.carry_rate, D("15000000"))
    assert result.check_ok
    assert result.gp_carry_total == 0
    assert result.stages[0].total == D("15000000.00")


def test_zero_proceeds():
    result = compute_waterfall(FUND, CLASS_A.carry_rate, D("0"))
    assert result.check_ok
    assert result.lp_total == result.gp_equity_total == result.gp_carry_total == 0
    assert result.share_of_proceeds(result.lp_total) == 0  # no division by zero


def test_hurdle_rate_zero():
    fund = FundParams(10_000_000, "0.95", 0, 10, 5, 1)
    result = compute_waterfall(fund, D("0.2"), D("25000000"))
    assert result.preferred_return == 0
    assert result.stages[1].total == 0  # no catch-up needed without a hurdle
    assert result.check_ok
    # Carry is simply 20 % of the 15,000,000 profit.
    assert result.gp_carry_total == D("3000000.00")
    assert result.lp_total + result.gp_equity_total == D("22000000.00")


def test_gp_equity_zero():
    fund = FundParams(10_000_000, 1, "0.06", 10, 5, 1)
    result = compute_waterfall(fund, D("0.2"), D("25000000"))
    assert result.check_ok
    assert result.gp_equity_total == 0
    assert result.gp_carry_total == D("3000000.00")
    assert result.lp_total == D("22000000.00")


def test_hurdle_zero_and_gp_equity_zero_and_loss_combined():
    fund = FundParams(10_000_000, 1, 0, 10, 5, 1)
    result = compute_waterfall(fund, D("0.2"), D("4000000"))
    assert result.check_ok
    assert result.lp_total == D("4000000.00")
    assert result.gp_carry_total == 0


def test_partial_catchup_ends_when_carry_reaches_target_share():
    # 50 % catch-up, 20 % carry: tier X = 0.2 * pref / (0.5 - 0.2); GP gets 0.5 * X.
    fund = FundParams(10_000_000, "0.95", "0.06", 10, 5, "0.5")
    result = compute_waterfall(fund, D("0.2"), D("40000000"))
    profit_distributed = result.preferred_return + result.stages[1].total
    assert abs(result.stages[1].gp_carry / profit_distributed - D("0.2")) < D("0.000001")
    # Past the tier the GP keeps exactly 20 % of the total profit.
    assert abs(result.gp_carry_total - D("0.2") * D("30000000")) <= D("0.02")
    assert result.check_ok


def test_no_catchup():
    fund = FundParams(10_000_000, "0.95", "0.06", 10, 5, 0)
    result = compute_waterfall(fund, D("0.2"), D("25000000"))
    assert result.stages[1].total == 0
    # Carry only on the residual above capital + preferred return.
    expected = D("0.2") * (D("25000000") - result.stages[0].total)
    assert abs(result.gp_carry_total - expected) <= D("0.01")
    assert result.check_ok


def test_sum_check_holds_over_many_scenarios():
    for proceeds in range(0, 60_000_001, 1_234_567):
        for lp_share in ("0.95", "0.8", "1"):
            fund = FundParams(10_000_000, lp_share, "0.06", 10, 5, 1)
            for carry in ("0.2", "0.1", "0"):
                assert compute_waterfall(fund, D(carry), D(proceeds) + D("0.337")).check_ok


@pytest.mark.parametrize(
    "factory, message",
    [
        (lambda: FundParams(0, "0.95", "0.06", 10, 5, 1), "Committed capital"),
        (lambda: FundParams(10, "1.2", "0.06", 10, 5, 1), "LP share"),
        (lambda: FundParams(10, "0", "0.06", 10, 5, 1), "LP share"),
        (lambda: FundParams(10, "0.95", "-0.01", 10, 5, 1), "Hurdle"),
        (lambda: FundParams(10, "0.95", "0.06", 0, 5, 1), "Holding period"),
        (lambda: FundParams(10, "0.95", "0.06", 10, -1, 1), "Investment period"),
        (lambda: FundParams(10, "0.95", "0.06", 10, 5, 1.5), "catch-up"),
        (lambda: FundParams("abc", "0.95", "0.06", 10, 5, 1), "number"),
        (lambda: ClassTerms("X", "0.01", "0.01", "1"), "Carried interest"),
        (lambda: ClassTerms("X", "-0.01", "0.01", "0.2"), "Management fee"),
        (lambda: Proceeds("amount", -1), "Proceeds"),
        (lambda: Proceeds("tvpi", -1), "TVPI"),
        (lambda: Proceeds("irr", "-1.5"), "IRR"),
        (lambda: Proceeds("percent", 1), "mode"),
    ],
)
def test_invalid_inputs_raise_readable_errors(factory, message):
    with pytest.raises(InputError, match=message):
        factory()


def test_catchup_not_above_carry_is_rejected():
    fund = FundParams(10_000_000, "0.95", "0.06", 10, 5, "0.2")
    with pytest.raises(InputError, match="catch-up"):
        compute_waterfall(fund, D("0.2"), D("25000000"))
