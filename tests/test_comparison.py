"""Share class comparison and break-even tests."""

from decimal import Decimal as D

import pytest

from pe_waterfall.comparison import break_even_tvpis, compare, sweep, tvpi_grid
from pe_waterfall.models import ClassTerms, InputError
from pe_waterfall.presets import CLASS_A, CLASS_B, FUND, PROCEEDS


def test_case_study_comparison_at_2_5x():
    result = compare(FUND, CLASS_A, CLASS_B, PROCEEDS)
    assert result.a.total_cost == D("3950000")
    assert result.b.total_cost == D("3400000")
    assert result.cheaper == "Class B"
    assert result.saving == D("550000")


def test_class_a_cheaper_at_low_performance():
    result = compare(FUND, CLASS_A, CLASS_B, PROCEEDS.__class__("tvpi", "1.5"))
    assert result.cheaper == "Class A"
    assert result.a.total_cost == D("950000")  # fees only, no carry below the hurdle
    assert result.b.total_cost == D("1900000")


def test_break_even_is_single_crossing_inside_class_a_catchup_zone():
    crossings = break_even_tvpis(FUND, CLASS_A, CLASS_B, D("0"), D("4"))
    assert len(crossings) == 1
    # Analytical solution inside A's catch-up zone: E - 16.958 M = 0.9 M + 0.1 E  =>  TVPI ~ 1.984
    assert crossings[0] == pytest.approx(D("1.984"), abs=D("0.001"))


def test_costs_are_equal_at_break_even_and_ordered_around_it():
    be = break_even_tvpis(FUND, CLASS_A, CLASS_B, D("0"), D("4"))[0]
    below, at, above = sweep(FUND, CLASS_A, CLASS_B, [be - D("0.1"), be, be + D("0.1")])
    assert abs(at.cost_a - at.cost_b) < D("1000")  # break-even is rounded to 0.0001x TVPI = 1,000 of proceeds
    assert below.cheaper_is_a is True
    assert above.cheaper_is_a is False


def test_no_break_even_when_one_class_dominates():
    cheap = ClassTerms("Cheap", "0.01", "0.01", "0.10")
    dear = ClassTerms("Dear", "0.02", "0.02", "0.20")
    assert break_even_tvpis(FUND, cheap, dear, D("0"), D("4")) == []


def test_identical_classes_never_cross():
    assert break_even_tvpis(FUND, CLASS_A, CLASS_A, D("0"), D("4")) == []
    assert compare(FUND, CLASS_A, CLASS_A, PROCEEDS).cheaper is None


def test_sweep_returns_one_point_per_grid_value():
    grid = tvpi_grid(D("1"), D("3"), D("0.5"))
    assert grid == [D("1"), D("1.5"), D("2"), D("2.5"), D("3")]
    points = sweep(FUND, CLASS_A, CLASS_B, grid)
    assert [p.gross_tvpi for p in points] == grid
    assert points[3].cost_a == D("3950000") and points[3].cost_b == D("3400000")
    assert points[3].net_tvpi_a == D("2.1") and points[3].net_tvpi_b == D("2.15")


@pytest.mark.parametrize("args", [(D("2"), D("1"), D("0.1")), (D("-1"), D("2"), D("0.1")), (D("0"), D("2"), D("0")), (D("0"), D("10000"), D("0.001"))])
def test_tvpi_grid_rejects_bad_ranges(args):
    with pytest.raises(InputError):
        tvpi_grid(*args)
