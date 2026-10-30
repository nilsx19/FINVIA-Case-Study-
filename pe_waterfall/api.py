"""JSON-friendly facade over the calculation logic, used by the web frontend.

The frontend sends plain numbers in "human" units (percentages as 6 for 6 %, TVPI as 2.5).
This module validates them, converts to the domain models, runs the calculations and
returns plain dicts (JSON-serialisable). It contains no HTTP code, so it is easy to test.
"""

from __future__ import annotations

from decimal import Decimal

from .analysis import Analysis, analyze
from .comparison import break_even_tvpis, compare, sweep, tvpi_grid
from .irr import irr_from_cashflows
from .models import ClassTerms, FundParams, InputError, Proceeds, to_decimal
from .presets import CLASS_A, CLASS_B, FUND, PRESETS


# --------------------------------------------------------------------------- parsing
def _require(data, key: str, label: str):
    if not isinstance(data, dict) or data.get(key) in (None, ""):
        raise InputError(f"{label} is required.")
    return data[key]


def _pct(data, key: str, label: str) -> Decimal:
    """Read a percentage field (6 = 6 %) as a fraction."""
    return to_decimal(_require(data, key, label), label) / 100


def parse_fund(data: dict) -> FundParams:
    return FundParams(
        committed_capital=_require(data, "committed_capital", "Committed capital"),
        lp_share=_pct(data, "lp_share_pct", "LP share"),
        hurdle_rate=_pct(data, "hurdle_pct", "Hurdle rate"),
        hold_years=_require(data, "hold_years", "Holding period"),
        investment_period_years=_require(data, "investment_period_years", "Investment period"),
        catchup_rate=_pct(data, "catchup_pct", "GP catch-up"),
    )


def parse_terms(data: dict, name: str) -> ClassTerms:
    return ClassTerms(
        name=name,
        fee_rate_investment_period=_pct(data, "fee_investment_pct", f"{name}: management fee (investment period)"),
        fee_rate_after=_pct(data, "fee_after_pct", f"{name}: management fee (after investment period)"),
        carry_rate=_pct(data, "carry_pct", f"{name}: carried interest"),
    )


def parse_proceeds(data: dict) -> Proceeds:
    mode = _require(data, "mode", "Proceeds mode")
    value = to_decimal(_require(data, "value", "Proceeds value"), "Proceeds value")
    if mode == "irr":
        value = value / 100  # entered as percent
    return Proceeds(mode, value)


# ------------------------------------------------------------------------ serialising
def _f(x: Decimal) -> float:
    return float(x)


def analysis_to_dict(a: Analysis, fund: FundParams) -> dict:
    wf = a.waterfall

    def party(amount: Decimal) -> dict:
        return {"amount": _f(amount), "pct": _f(wf.share_of_proceeds(amount) * 100)}

    return {
        "name": a.terms.name,
        "proceeds": _f(wf.proceeds),
        "preferred_return": _f(wf.preferred_return),
        "stages": [
            {"name": s.name, "total": _f(s.total), "lp": _f(s.lp), "gp_equity": _f(s.gp_equity), "gp_carry": _f(s.gp_carry)}
            for s in wf.stages
        ],
        "totals": {"lp": party(wf.lp_total), "gp_equity": party(wf.gp_equity_total), "gp_carry": party(wf.gp_carry_total)},
        "check": {
            "ok": wf.check_ok,
            "proceeds": _f(wf.proceeds),
            "stage_sum": _f(wf.stage_sum),
            "party_sum": _f(wf.party_sum),
            "difference": _f(abs(wf.stage_sum - wf.proceeds) + abs(wf.party_sum - wf.proceeds)),
        },
        "fees": [{"year": y.year, "rate_pct": _f(y.rate * 100), "fee": _f(y.fee), "cumulative": _f(y.cumulative)} for y in a.fee_years],
        "total_fees": _f(a.total_fees),
        "carried_interest": _f(a.carried_interest),
        "total_cost": _f(a.total_cost),
        "gross": {"tvpi": _f(a.gross_tvpi), "irr_pct": _f(a.gross_irr * 100)},
        "net": {"tvpi": _f(a.net_tvpi), "irr_pct": _f(a.net_irr * 100), "to_lp": _f(a.net_to_lp)},
        "lp_tvpi_before_fees": _f(a.lp_tvpi_before_fees),
        "drag": {"tvpi": _f(a.tvpi_drag), "irr_pct": _f(a.irr_drag * 100)},
        "lp_commitment": _f(fund.lp_commitment),
    }


# ------------------------------------------------------------------------- endpoints
def defaults() -> dict:
    """Presets (the two case-study test cases) and default comparison inputs, in UI units."""

    def terms_ui(t: ClassTerms) -> dict:
        return {
            "fee_investment_pct": _f(t.fee_rate_investment_period * 100),
            "fee_after_pct": _f(t.fee_rate_after * 100),
            "carry_pct": _f(t.carry_rate * 100),
        }

    fund_ui = {
        "committed_capital": _f(FUND.committed_capital),
        "lp_share_pct": _f(FUND.lp_share * 100),
        "hurdle_pct": _f(FUND.hurdle_rate * 100),
        "hold_years": _f(FUND.hold_years),
        "investment_period_years": _f(FUND.investment_period_years),
        "catchup_pct": _f(FUND.catchup_rate * 100),
    }
    return {
        "presets": [
            {"label": label, "fund": fund_ui, "terms": terms_ui(terms), "proceeds": {"mode": "tvpi", "value": _f(proceeds.value)}}
            for label, (_, terms, proceeds) in PRESETS.items()
        ],
        "compare": {
            "class_a": terms_ui(CLASS_A),
            "class_b": terms_ui(CLASS_B),
            "tvpi_from": 0.5,
            "tvpi_to": 4.0,
            "tvpi_step": 0.05,
        },
    }


def calculate(payload: dict) -> dict:
    """Run waterfall, fees and metrics for one class, and the class comparison if requested.

    Invalid main inputs raise ``InputError``. Invalid comparison inputs do not fail the whole
    request: the message is returned as ``comparison_error`` so the other tabs keep working.
    """
    if not isinstance(payload, dict):
        raise InputError("Request body must be a JSON object.")
    fund = parse_fund(payload.get("fund"))
    terms = parse_terms(payload.get("terms"), "Selected class")
    proceeds = parse_proceeds(payload.get("proceeds"))
    result = {"analysis": analysis_to_dict(analyze(fund, terms, proceeds), fund), "comparison": None, "comparison_error": None}

    cmp_in = payload.get("compare")
    if cmp_in:
        try:
            result["comparison"] = _comparison_to_dict(fund, proceeds, cmp_in)
        except InputError as err:
            result["comparison_error"] = str(err)
    return result


def _comparison_to_dict(fund: FundParams, proceeds: Proceeds, cmp_in: dict) -> dict:
    a = parse_terms(cmp_in.get("class_a"), "Class A")
    b = parse_terms(cmp_in.get("class_b"), "Class B")
    low = to_decimal(_require(cmp_in, "tvpi_from", "TVPI range start"), "TVPI range start")
    high = to_decimal(_require(cmp_in, "tvpi_to", "TVPI range end"), "TVPI range end")
    step = to_decimal(_require(cmp_in, "tvpi_step", "TVPI step"), "TVPI step")

    both = compare(fund, a, b, proceeds)
    grid = tvpi_grid(low, high, step)
    points = sweep(fund, a, b, grid)
    return {
        "a": analysis_to_dict(both.a, fund),
        "b": analysis_to_dict(both.b, fund),
        "cheaper": both.cheaper,
        "saving": _f(both.saving),
        "sweep": [
            {"tvpi": _f(p.gross_tvpi), "cost_a": _f(p.cost_a), "cost_b": _f(p.cost_b), "net_tvpi_a": _f(p.net_tvpi_a), "net_tvpi_b": _f(p.net_tvpi_b)}
            for p in points
        ],
        "break_even": [_f(x) for x in break_even_tvpis(fund, a, b, low, high, step)],
        "cheaper_at_start": _cheaper_name(points[0], a, b),
        "cheaper_at_end": _cheaper_name(points[-1], a, b),
        "current_tvpi": _f(both.a.gross_tvpi),
    }


def _cheaper_name(point, a: ClassTerms, b: ClassTerms) -> str | None:
    if point.cheaper_is_a is None:
        return None
    return a.name if point.cheaper_is_a else b.name


def cashflow_irr(payload: dict) -> dict:
    """Optional feature: IRR of an annual cash flow series (negative = paid in, positive = received)."""
    raw = payload.get("cashflows") if isinstance(payload, dict) else None
    if not isinstance(raw, list):
        raise InputError("Cash flows must be a list of numbers.")
    flows = [float(to_decimal(x, "Cash flow")) for x in raw]
    return {"irr_pct": irr_from_cashflows(flows) * 100}
