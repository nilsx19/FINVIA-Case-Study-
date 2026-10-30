"""Tests for the JSON facade and the HTTP server (no browser needed)."""

import http.client
import json
import threading

import pytest

from app import make_server
from pe_waterfall import api
from pe_waterfall.models import InputError


def payload(**overrides):
    base = {
        "fund": {"committed_capital": 10_000_000, "lp_share_pct": 95, "hurdle_pct": 6, "hold_years": 10,
                 "investment_period_years": 5, "catchup_pct": 100},
        "terms": {"fee_investment_pct": 1.25, "fee_after_pct": 0.75, "carry_pct": 20},
        "proceeds": {"mode": "tvpi", "value": 2.5},
        "compare": {
            "class_a": {"fee_investment_pct": 1.25, "fee_after_pct": 0.75, "carry_pct": 20},
            "class_b": {"fee_investment_pct": 2.5, "fee_after_pct": 1.5, "carry_pct": 10},
            "tvpi_from": 0.5, "tvpi_to": 4, "tvpi_step": 0.05,
        },
    }
    base.update(overrides)
    return base


def test_calculate_returns_case_study_values_in_ui_units():
    out = api.calculate(payload())
    a = out["analysis"]
    assert a["proceeds"] == 25_000_000
    assert a["totals"]["lp"] == {"amount": 20_900_000.0, "pct": pytest.approx(83.6)}
    assert a["totals"]["gp_carry"]["amount"] == 3_000_000
    assert a["check"]["ok"] and a["check"]["difference"] == 0
    assert a["total_fees"] == 950_000 and a["total_cost"] == 3_950_000
    assert a["net"]["tvpi"] == pytest.approx(2.1) and a["net"]["irr_pct"] == pytest.approx(7.70, abs=0.005)
    assert a["gross"]["irr_pct"] == pytest.approx(9.60, abs=0.005)
    assert len(a["fees"]) == 10 and a["fees"][-1]["cumulative"] == 950_000


def test_comparison_part():
    cmp = api.calculate(payload())["comparison"]
    assert cmp["cheaper"] == "Class B" and cmp["saving"] == 550_000
    assert cmp["a"]["total_cost"] == 3_950_000 and cmp["b"]["total_cost"] == 3_400_000
    assert cmp["break_even"] == [pytest.approx(1.984, abs=0.001)]
    assert cmp["cheaper_at_start"] == "Class A" and cmp["cheaper_at_end"] == "Class B"
    assert len(cmp["sweep"]) == 71


@pytest.mark.parametrize("mode,value", [("amount", 25_000_000), ("tvpi", 2.5), ("irr", 9.6)])
def test_all_proceeds_modes(mode, value):
    out = api.calculate(payload(proceeds={"mode": mode, "value": value}))
    assert out["analysis"]["proceeds"] == pytest.approx(25_000_000, rel=1e-3)
    assert out["analysis"]["check"]["ok"]


def test_invalid_main_input_raises_readable_error():
    bad = payload()
    bad["fund"]["lp_share_pct"] = 120
    with pytest.raises(InputError, match="LP share"):
        api.calculate(bad)


def test_missing_and_empty_fields_are_reported():
    bad = payload()
    bad["fund"]["hurdle_pct"] = ""
    with pytest.raises(InputError, match="Hurdle rate is required"):
        api.calculate(bad)
    with pytest.raises(InputError, match="required"):
        api.calculate({})


def test_invalid_comparison_input_does_not_break_main_result():
    bad = payload()
    bad["compare"]["tvpi_step"] = 0
    out = api.calculate(bad)
    assert out["comparison"] is None and "step" in out["comparison_error"]
    assert out["analysis"]["check"]["ok"]


def test_cashflow_irr():
    assert api.cashflow_irr({"cashflows": [-100] + [0] * 9 + [250]})["irr_pct"] == pytest.approx(9.60, abs=0.01)
    with pytest.raises(InputError):
        api.cashflow_irr({"cashflows": [100, 200]})
    with pytest.raises(InputError):
        api.cashflow_irr({"cashflows": "abc"})


def test_defaults_contain_both_test_cases():
    d = api.defaults()
    assert [p["label"] for p in d["presets"]] == ["Test case 1 (Class A)", "Test case 2 (Class B)"]
    assert d["presets"][1]["terms"] == {"fee_investment_pct": 2.5, "fee_after_pct": 1.5, "carry_pct": 10}
    assert d["presets"][0]["proceeds"] == {"mode": "tvpi", "value": 2.5}


@pytest.fixture()
def server():
    srv = make_server("127.0.0.1", 0)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    yield srv.server_address[1]
    srv.shutdown()
    srv.server_close()


def request(port, method, path, body=None):
    conn = http.client.HTTPConnection("127.0.0.1", port)
    conn.request(method, path, body=body, headers={"Content-Type": "application/json"} if body else {})
    resp = conn.getresponse()
    data = resp.read()
    conn.close()
    return resp.status, data


def test_server_serves_ui_and_api(server):
    status, html = request(server, "GET", "/")
    assert status == 200 and b"Waterfall" in html
    assert request(server, "GET", "/app.js")[0] == 200
    assert request(server, "GET", "/style.css")[0] == 200
    assert request(server, "GET", "/../app.py")[0] == 404
    status, data = request(server, "POST", "/api/calculate", json.dumps(payload()))
    assert status == 200 and json.loads(data)["analysis"]["check"]["ok"]


def test_server_returns_400_with_message_for_invalid_input(server):
    bad = payload()
    bad["fund"]["committed_capital"] = -5
    status, data = request(server, "POST", "/api/calculate", json.dumps(bad))
    assert status == 400 and "Committed capital" in json.loads(data)["error"]
    status, data = request(server, "POST", "/api/calculate", "not json")
    assert status == 400 and "JSON" in json.loads(data)["error"]
    assert request(server, "POST", "/api/nope", "{}")[0] == 404
