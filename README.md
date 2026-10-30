# Distribution Waterfall & Fee Calculator

A Python tool for private equity funds that

- computes the **distribution waterfall** including preferred return (hurdle), GP catch-up and carried interest,
- models **management fees** over the fund life and derives **gross and net TVPI / IRR**,
- **compares two share classes** (fee/carry trade-off) and finds the **break-even gross TVPI** at which the cheaper class switches,
- offers a browser-based **frontend** for all of this.

The calculation logic (`pe_waterfall/`) is independent of the UI; the tests run against the logic only.

## Installation and start

Developed and tested with Python 3.13. The app itself needs no third-party packages.

```bash
pip install -r requirements.txt   # only installs pytest, needed for the tests
python app.py                     # starts the UI at http://127.0.0.1:8000 and opens the browser
```

Options: `python app.py --port 9000 --no-browser`.

Run the tests (they reproduce both case-study test cases and edge cases):

```bash
pytest
```

## Using the frontend

1. Click **Load Test case 1 (Class A)** or **Test case 2 (Class B)** to fill in the case-study inputs, or enter your own.
2. Enter the proceeds as **Amount**, **TVPI** or **IRR**. Switching the unit converts the current value, so the scenario stays the same.
3. Results update automatically:
   - **Waterfall**: amounts per stage, totals and percentages for LP, GP (Equity) and GP (Carry), and the result of the sum check.
   - **Fees & returns**: fee per year and cumulative, total cost, gross vs. net TVPI and IRR.
   - **Class comparison**: Class A vs. Class B at the selected proceeds, plus a cost curve over a TVPI range with the break-even point.
   - **Cash-flow IRR** (optional): IRR from an arbitrary yearly cash-flow series.
4. Invalid inputs (empty fields, LP share above 100 %, negative hurdle, ...) show a readable message instead of a result.
5. Tables can be exported as CSV.

## Example

Test case 1 (Class A): 10,000,000 committed (95 % LP / 5 % GP), hurdle 6 % p.a., 100 % catch-up, 20 % carry,
fee 1.25 % (years 1-5) / 0.75 % (years 6-10), 10 years, gross TVPI 2.50x (= 25,000,000 proceeds).

| Position | Result |
|---|---|
| Preferred return | 7,908,476.97 |
| Stage 1: capital + preferred return | 17,908,476.97 |
| Stage 2: GP catch-up | 1,977,119.24 |
| LP total | 20,900,000.00 (83.6 %) |
| GP (Equity) total | 1,100,000.00 (4.4 %) |
| Carried interest total | 3,000,000.00 (12.0 %) |
| Management fees total | 950,000.00 |
| Total cost (fees + carry) | 3,950,000.00 |
| Net TVPI / net IRR | 2.10x / 7.70 % |

For the same fund, Class B (2.5 % / 1.5 % fee, 10 % carry) costs 3,400,000.00, so it is cheaper at 2.50x.
Class A is cheaper below a gross TVPI of about **1.98x**, Class B above.

## How the waterfall works

All capital (LP and GP equity) is paid in at the start, and all proceeds arrive in one payment at the end of the holding period.
Money is rounded to cents.

1. **Stage 1: capital + preferred return.** The hurdle is compounded annually on the *total* committed capital:
   `pref = capital * ((1 + hurdle)^years - 1)`. The first `capital + pref` of the proceeds go to LP and GP equity pro rata
   (e.g. 95 / 5). If proceeds are lower, everything is distributed pro rata and no carry is paid.
2. **Stage 2: GP catch-up.** The GP receives `catch-up %` of each euro until its carry equals `carry %` of all profit
   distributed so far. The tier size is `X = carry * pref / (catch-up - carry)`; with 100 % catch-up and 20 % carry
   this is `0.25 * pref`. If the catch-up is below 100 %, the rest of the tier goes pro rata to LP and GP equity.
   With a 0 % hurdle, 0 % carry or 0 % catch-up the stage is empty.
3. **Stage 3: residual split.** `carry %` of the remainder goes to the GP as carried interest, the rest pro rata to LP and GP equity.

**Sum check:** the stage totals and the totals per recipient (LP, GP equity, GP carry) must both equal the proceeds exactly.
It is computed in `compute_waterfall` and shown in the UI. Rounding differences are absorbed by the LP part within a stage and by the
last stage, so no cent is created or lost.

## Fees, returns and cost

- **Management fee** = rate x **LP commitment** (not total capital), with one rate in the investment period and another after it.
  Fees run alongside the waterfall and do **not** reduce the distributable proceeds.
- **Gross TVPI** = proceeds / committed capital; **gross IRR** = `TVPI^(1/years) - 1`.
- **Net to LP** = LP waterfall total - management fees; **net TVPI** = net to LP / LP commitment; **net IRR** from net TVPI over the holding period.
- **Total cost** to the investor = management fees + carried interest. The difference between gross and net TVPI/IRR shows what fees and carry cost.
- **Class comparison:** both classes are evaluated on the same fund and proceeds. The break-even is found by scanning a TVPI grid for a change of the cheaper class and refining the crossing by bisection.

## Project structure

```
app.py                   HTTP server for the UI and the JSON API (standard library only)
web/                     Frontend: index.html, app.js, style.css (no build step, no dependencies)
pe_waterfall/
  models.py              Input dataclasses + validation (InputError with readable messages)
  waterfall.py           Waterfall stages, catch-up, sum check
  fees.py                Management fee schedule
  irr.py                 IRR from a multiple and from a cash-flow series
  analysis.py            One share class: waterfall + fees + gross/net metrics + cost
  comparison.py          Two-class comparison, TVPI sweep, break-even
  api.py                 JSON-friendly facade used by the server (percent in, dicts out)
  presets.py             The two case-study test cases
tests/                   pytest suite (logic, API and HTTP server)
```

## Known limitations

- Whole-fund (European) waterfall with a single distribution at the end. The optional **deal-by-deal waterfall with clawback is not implemented.**
- Capital is paid in fully at t = 0 and proceeds arrive at the end of the holding period, so there are no interim cash flows in the waterfall.
  The cash-flow IRR tab is a separate helper and is not linked to the waterfall.
- The hurdle is calculated on the total capital (LP + GP equity), and carried interest is taken from all profit above the hurdle, as in the case-study test cases. Other contract conventions (hurdle on LP capital only, carry on LP profits only) are not modelled.
- Fees are paid by the LP outside the waterfall and are not part of the hurdle base. Fee offsets, fee step-downs on invested capital and expenses are not modelled.
- If the holding period is not a whole number of years, the last fee year is charged pro rata.
- A net multiple of 0 or below (for example total loss plus fees) is reported as a net IRR of -100 %.
- The UI is in English with German number formatting (1.234.567,89) to match the case-study figures; export is CSV only. The server is meant for local use and has no authentication.
- The waterfall, fees and TVPI/IRR are calculated with `Decimal`. Floating point is used only for the cash-flow IRR and for the JSON hand-over to the UI.
