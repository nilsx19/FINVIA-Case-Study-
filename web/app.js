"use strict";
/*
 * Frontend for the distribution waterfall & fee calculator.
 * It only collects inputs, calls the JSON API (/api/calculate, /api/irr) and renders results.
 * All financial logic lives in the Python package `pe_waterfall`.
 */

const $ = (id) => document.getElementById(id);

const FUND_FIELDS = ["committed_capital", "lp_share_pct", "hurdle_pct", "hold_years", "investment_period_years", "catchup_pct"];
const TERMS_FIELDS = ["fee_investment_pct", "fee_after_pct", "carry_pct"];
const COLORS = { lp: "#2563eb", gp: "#0f9d8a", carry: "#e07a1f", a: "#4f46e5", b: "#d9480f", s1: "#64748b", s2: "#a78bfa", s3: "#38bdf8" };

let defaults = null;
let last = null; // last successful response
let timer = null;
let requestCounter = 0;

// ------------------------------------------------------------------ formatting
const nf = (digits) => new Intl.NumberFormat("de-DE", { minimumFractionDigits: digits, maximumFractionDigits: digits });
const money = (n) => nf(2).format(n);
const pct = (n, d = 2) => nf(d).format(n) + " %";
const mult = (n) => nf(2).format(n) + "x";
const short = (n) => (n >= 1e6 ? nf(n % 1e6 === 0 ? 0 : 1).format(n / 1e6) + " M" : n >= 1e3 ? nf(0).format(n / 1e3) + " k" : nf(0).format(n));

// -------------------------------------------------------------------- inputs
function num(id) {
  const raw = $(id).value.trim();
  return raw === "" ? "" : Number(raw);
}
function currentMode() {
  return document.querySelector('input[name="mode"]:checked').value;
}
function buildPayload() {
  const pick = (ids, prefix = "") => Object.fromEntries(ids.map((k) => [k, num(prefix + k)]));
  return {
    fund: pick(FUND_FIELDS),
    terms: pick(TERMS_FIELDS),
    proceeds: { mode: currentMode(), value: num("proceeds_value") },
    compare: {
      class_a: pick(TERMS_FIELDS, "a_"),
      class_b: pick(TERMS_FIELDS, "b_"),
      tvpi_from: num("tvpi_from"),
      tvpi_to: num("tvpi_to"),
      tvpi_step: num("tvpi_step"),
    },
  };
}
function setValues(prefix, values) {
  for (const [k, v] of Object.entries(values)) $(prefix + k).value = v;
}
function applyPreset(p) {
  setValues("", p.fund);
  setValues("", p.terms);
  setMode(p.proceeds.mode);
  $("proceeds_value").value = p.proceeds.value;
  calculate();
}
const MODE_LABELS = { amount: "Proceeds (amount)", tvpi: "Gross TVPI (x)", irr: "Gross IRR (% p.a.)" };
function setMode(mode) {
  document.querySelector(`input[name="mode"][value="${mode}"]`).checked = true;
  $("proceeds_label").textContent = MODE_LABELS[mode];
}
function syncGpShare() {
  const lp = num("lp_share_pct");
  $("gp_share_pct").value = lp === "" ? "" : Math.round((100 - lp) * 1e6) / 1e6;
}

// ----------------------------------------------------------------- API calls
async function postJson(url, body) {
  const resp = await fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
  const data = await resp.json();
  if (!resp.ok) throw new Error(data.error || "Request failed.");
  return data;
}

function scheduleCalculate() {
  clearTimeout(timer);
  timer = setTimeout(calculate, 200);
}

async function calculate() {
  const ticket = ++requestCounter; // ignore responses that arrive out of order
  try {
    const data = await postJson("/api/calculate", buildPayload());
    if (ticket !== requestCounter) return;
    last = data;
    showError(null);
    render(data);
  } catch (err) {
    if (ticket !== requestCounter) return;
    showError(err.message);
  }
}

function showError(message) {
  const box = $("error");
  box.hidden = !message;
  box.textContent = message || "";
  document.querySelectorAll(".panel").forEach((p) => p.classList.toggle("stale", Boolean(message)));
}

// ------------------------------------------------------------------ rendering
function render(data) {
  const a = data.analysis;
  renderWaterfall(a);
  renderFees(a);
  renderCompare(data);
  updateProceedsHint(a);
}

function updateProceedsHint(a) {
  $("proceeds_hint").textContent = `= ${money(a.proceeds)} proceeds · ${mult(a.gross.tvpi)} gross TVPI · ${pct(a.gross.irr_pct)} gross IRR`;
}

function kpi(cls, label, value, sub) {
  return `<div class="kpi ${cls}"><div class="label">${label}</div><div class="value">${value}</div><div class="sub">${sub || "&nbsp;"}</div></div>`;
}

function renderWaterfall(a) {
  const t = a.totals;
  $("wf-kpis").innerHTML =
    kpi("", "Proceeds", money(a.proceeds), `${mult(a.gross.tvpi)} gross TVPI`) +
    kpi("lp", "LP", money(t.lp.amount), pct(t.lp.pct, 1) + " of proceeds") +
    kpi("gp", "GP (Equity)", money(t.gp_equity.amount), pct(t.gp_equity.pct, 1) + " of proceeds") +
    kpi("carry", "GP (Carry)", money(t.gp_carry.amount), pct(t.gp_carry.pct, 1) + " of proceeds");

  const c = a.check;
  $("wf-check").innerHTML = c.ok
    ? `<div class="banner ok"><strong>Check passed:</strong> sum of all stages = LP + GP (Equity) + GP (Carry) = proceeds (${money(c.proceeds)}), difference ${money(c.difference)}.</div>`
    : `<div class="banner error"><strong>Check failed:</strong> stages sum to ${money(c.stage_sum)}, recipients to ${money(c.party_sum)}, proceeds are ${money(c.proceeds)}.</div>`;

  const row = (cls, name, tot, lp, gp, carry) =>
    `<tr class="${cls}"><td>${name}</td><td>${tot}</td><td>${lp}</td><td>${gp}</td><td>${carry}</td></tr>`;
  let html = "<thead><tr><th>Position</th><th>Total</th><th>LP</th><th>GP (Equity)</th><th>GP (Carry)</th></tr></thead><tbody>";
  html += row("sub", "Preferred return (hurdle, for reference)", money(a.preferred_return), "", "", "");
  for (const s of a.stages) html += row("", s.name, money(s.total), money(s.lp), money(s.gp_equity), money(s.gp_carry));
  html += row("total", "Total", money(a.proceeds), money(t.lp.amount), money(t.gp_equity.amount), money(t.gp_carry.amount));
  html += row("sub", "Share of proceeds", "100,0 %", pct(t.lp.pct, 1), pct(t.gp_equity.pct, 1), pct(t.gp_carry.pct, 1));
  $("wf-table").innerHTML = html + "</tbody>";

  $("wf-chart").innerHTML = distributionChart(a);
}

function renderFees(a) {
  $("fee-kpis").innerHTML =
    kpi("", "Management fees", money(a.total_fees), `over ${a.fees.length} years`) +
    kpi("carry", "Carried interest", money(a.carried_interest)) +
    kpi("", "Total cost to investor", money(a.total_cost), "fees + carry") +
    kpi("lp", "Net to LP", money(a.net.to_lp), "LP distribution − fees");

  $("net-table").innerHTML =
    "<thead><tr><th>Metric</th><th>Gross</th><th>Net</th><th>Cost of fees &amp; carry</th></tr></thead><tbody>" +
    `<tr><td>TVPI</td><td>${mult(a.gross.tvpi)}</td><td>${mult(a.net.tvpi)}</td><td>${nf(2).format(a.drag.tvpi)}x</td></tr>` +
    `<tr><td>IRR</td><td>${pct(a.gross.irr_pct)}</td><td>${pct(a.net.irr_pct)}</td><td>${nf(2).format(a.drag.irr_pct)} pp</td></tr>` +
    "</tbody>";

  let html = "<thead><tr><th>Year</th><th>Fee rate</th><th>Fee</th><th>Cumulative</th></tr></thead><tbody>";
  for (const f of a.fees) html += `<tr><td>${f.year}</td><td>${pct(f.rate_pct)}</td><td>${money(f.fee)}</td><td>${money(f.cumulative)}</td></tr>`;
  html += `<tr class="total"><td>Total</td><td></td><td>${money(a.total_fees)}</td><td></td></tr></tbody>`;
  $("fee-table").innerHTML = html;
  $("fee-chart").innerHTML = feeChart(a.fees);
}

function renderCompare(data) {
  const err = $("cmp-error");
  err.hidden = !data.comparison_error;
  err.textContent = data.comparison_error || "";
  const c = data.comparison;
  const ids = ["cmp-verdict", "cmp-table", "be-text", "cmp-chart"];
  if (!c) {
    ids.forEach((id) => ($(id).innerHTML = ""));
    return;
  }
  const a = c.a, b = c.b;
  const x = mult(a.gross.tvpi);
  $("cmp-verdict").innerHTML = c.cheaper
    ? `<div class="banner info"><strong>At ${x} gross TVPI, ${c.cheaper} is cheaper for the investor by ${money(c.saving)}.</strong><small>Total cost = management fees + carried interest: Class A ${money(a.total_cost)} vs. Class B ${money(b.total_cost)}.</small></div>`
    : `<div class="banner info"><strong>At ${x} gross TVPI both classes cost the same.</strong></div>`;

  const better = (va, vb, lowerIsBetter) => (va === vb ? ["", ""] : (va < vb) === lowerIsBetter ? ["best", ""] : ["", "best"]);
  const line = (label, va, vb, fmt, lowerIsBetter) => {
    const [ca, cb] = lowerIsBetter === null ? ["", ""] : better(va, vb, lowerIsBetter);
    return `<tr><td>${label}</td><td class="${ca}">${fmt(va)}</td><td class="${cb}">${fmt(vb)}</td></tr>`;
  };
  $("cmp-table").innerHTML =
    "<thead><tr><th>Position</th><th>Class A</th><th>Class B</th></tr></thead><tbody>" +
    line("Management fees (total)", a.total_fees, b.total_fees, money, true) +
    line("Carried interest", a.carried_interest, b.carried_interest, money, true) +
    line("<strong>Total cost (fees + carry)</strong>", a.total_cost, b.total_cost, money, true) +
    line("Net to LP", a.net.to_lp, b.net.to_lp, money, false) +
    line("Net TVPI", a.net.tvpi, b.net.tvpi, mult, false) +
    line("Net IRR", a.net.irr_pct, b.net.irr_pct, (v) => pct(v), false) +
    line("Gross TVPI / IRR (identical)", a.gross.tvpi, b.gross.tvpi, () => `${mult(a.gross.tvpi)} / ${pct(a.gross.irr_pct)}`, null) +
    "</tbody>";

  const first = c.sweep[0].tvpi, lastX = c.sweep[c.sweep.length - 1].tvpi;
  const other = (name) => (name === "Class A" ? "Class B" : "Class A");
  let text;
  if (c.break_even.length === 0) {
    text = c.cheaper_at_start
      ? `${c.cheaper_at_start} is cheaper across the whole range (${mult(first)} to ${mult(lastX)}); there is no break-even.`
      : "Both classes cost the same across the whole range.";
  } else {
    let name = c.cheaper_at_start;
    const parts = [`below ${mult(c.break_even[0])}: ${name}`];
    c.break_even.forEach((be, i) => {
      name = other(name);
      const next = c.break_even[i + 1];
      parts.push(next === undefined ? `above ${mult(be)}: ${name}` : `${mult(be)} to ${mult(next)}: ${name}`);
    });
    text = `Break-even at ${c.break_even.map(mult).join(", ")} gross TVPI. Cheaper class: ${parts.join(" · ")}.`;
  }
  $("be-text").textContent = text;
  $("cmp-chart").innerHTML = costChart(c);
}

// --------------------------------------------------------------------- charts
function niceStep(raw) {
  const mag = 10 ** Math.floor(Math.log10(raw));
  const n = raw / mag;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 5 ? 5 : 10) * mag;
}
function ticksUpTo(max, count = 5) {
  if (!(max > 0)) return [0, 1];
  const step = niceStep(max / count);
  const ticks = [];
  for (let v = 0, i = 0; i < 50; v += step, i++) {
    ticks.push(v);
    if (v >= max) break;
  }
  return ticks;
}
function legend(items) {
  return `<div class="legend">${items.map(([color, label]) => `<span><i style="background:${color}"></i>${label}</span>`).join("")}</div>`;
}

function stackedBar(y, label, segments, total, x0, width) {
  let x = x0, out = `<text x="${x0 - 10}" y="${y + 19}" text-anchor="end" font-size="13" fill="#627084">${label}</text>`;
  for (const seg of segments) {
    const w = total > 0 ? (seg.value / total) * width : 0;
    if (w <= 0) continue;
    out += `<rect x="${x}" y="${y}" width="${w}" height="28" fill="${seg.color}"><title>${seg.name}: ${money(seg.value)} (${pct((seg.value / total) * 100, 1)})</title></rect>`;
    if (w > 54) out += `<text x="${x + w / 2}" y="${y + 18}" text-anchor="middle" font-size="12" fill="#fff" font-weight="600">${pct((seg.value / total) * 100, 1)}</text>`;
    x += w;
  }
  return out;
}

function distributionChart(a) {
  if (a.proceeds <= 0) return '<p class="hint">No proceeds to distribute.</p>';
  const [s1, s2, s3] = a.stages;
  const stageColors = [COLORS.s1, COLORS.s2, COLORS.s3];
  const byStage = a.stages.map((s, i) => ({ name: s.name, value: s.total, color: stageColors[i] }));
  const byParty = [
    { name: "LP", value: a.totals.lp.amount, color: COLORS.lp },
    { name: "GP (Equity)", value: a.totals.gp_equity.amount, color: COLORS.gp },
    { name: "GP (Carry)", value: a.totals.gp_carry.amount, color: COLORS.carry },
  ];
  const svg = `<svg viewBox="0 0 720 100" width="100%" role="img" aria-label="Proceeds by stage and by recipient">
    ${stackedBar(8, "By stage", byStage, a.proceeds, 100, 600)}
    ${stackedBar(56, "By recipient", byParty, a.proceeds, 100, 600)}
  </svg>`;
  return legend([[COLORS.s1, "Stage 1"], [COLORS.s2, "Stage 2 (catch-up)"], [COLORS.s3, "Stage 3"]]) + legend([[COLORS.lp, "LP"], [COLORS.gp, "GP (Equity)"], [COLORS.carry, "GP (Carry)"]]) + svg;
}

function feeChart(fees) {
  const W = 720, H = 230, m = { l: 62, r: 10, t: 10, b: 28 };
  const ticks = ticksUpTo(Math.max(...fees.map((f) => f.fee)));
  const top = ticks[ticks.length - 1];
  const sy = (v) => H - m.b - (v / top) * (H - m.t - m.b);
  const slot = (W - m.l - m.r) / fees.length;
  let out = ticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${sy(t)}" y2="${sy(t)}" stroke="#e5e8ee"/><text x="${m.l - 8}" y="${sy(t) + 4}" text-anchor="end" font-size="12" fill="#627084">${short(t)}</text>`).join("");
  fees.forEach((f, i) => {
    const x = m.l + i * slot + slot * 0.15, w = slot * 0.7;
    out += `<rect x="${x}" y="${sy(f.fee)}" width="${w}" height="${H - m.b - sy(f.fee)}" fill="${COLORS.lp}" rx="2"><title>Year ${f.year}: ${money(f.fee)} (${pct(f.rate_pct)})</title></rect>`;
    out += `<text x="${x + w / 2}" y="${H - 9}" text-anchor="middle" font-size="12" fill="#627084">${f.year}</text>`;
  });
  return `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Management fee per year">${out}</svg>`;
}

function costChart(c) {
  const W = 720, H = 320, m = { l: 62, r: 16, t: 16, b: 40 };
  const xs = c.sweep.map((p) => p.tvpi);
  const xmin = xs[0], xmax = xs[xs.length - 1];
  const ticks = ticksUpTo(Math.max(...c.sweep.map((p) => Math.max(p.cost_a, p.cost_b))));
  const top = ticks[ticks.length - 1];
  const sx = (v) => m.l + ((v - xmin) / (xmax - xmin)) * (W - m.l - m.r);
  const sy = (v) => H - m.b - (v / top) * (H - m.t - m.b);

  let out = ticks.map((t) => `<line x1="${m.l}" x2="${W - m.r}" y1="${sy(t)}" y2="${sy(t)}" stroke="#e5e8ee"/><text x="${m.l - 8}" y="${sy(t) + 4}" text-anchor="end" font-size="12" fill="#627084">${short(t)}</text>`).join("");
  const xstep = niceStep((xmax - xmin) / 7);
  for (let v = Math.ceil(xmin / xstep) * xstep; v <= xmax + 1e-9; v += xstep) {
    out += `<text x="${sx(v)}" y="${H - 20}" text-anchor="middle" font-size="12" fill="#627084">${nf(xstep < 1 ? 1 : 0).format(v)}x</text>`;
  }
  out += `<text x="${(m.l + W - m.r) / 2}" y="${H - 3}" text-anchor="middle" font-size="12" fill="#627084">Gross TVPI</text>`;

  const path = (key) => c.sweep.map((p, i) => `${i ? "L" : "M"}${sx(p.tvpi).toFixed(1)},${sy(p[key]).toFixed(1)}`).join("");
  out += `<path d="${path("cost_a")}" fill="none" stroke="${COLORS.a}" stroke-width="2.5"><title>Class A total cost</title></path>`;
  out += `<path d="${path("cost_b")}" fill="none" stroke="${COLORS.b}" stroke-width="2.5"><title>Class B total cost</title></path>`;

  for (const be of c.break_even) {
    out += `<line x1="${sx(be)}" x2="${sx(be)}" y1="${m.t}" y2="${H - m.b}" stroke="#14213d" stroke-dasharray="5 4"/>`;
    out += `<text x="${sx(be) + 5}" y="${m.t + 12}" font-size="12" font-weight="600" fill="#14213d">Break-even ${mult(be)}</text>`;
  }
  if (c.current_tvpi >= xmin && c.current_tvpi <= xmax) {
    const cx = sx(c.current_tvpi);
    out += `<line x1="${cx}" x2="${cx}" y1="${m.t}" y2="${H - m.b}" stroke="#94a3b8" stroke-dasharray="2 3"/>`;
    out += `<circle cx="${cx}" cy="${sy(c.a.total_cost)}" r="4.5" fill="${COLORS.a}"/><circle cx="${cx}" cy="${sy(c.b.total_cost)}" r="4.5" fill="${COLORS.b}"/>`;
  }
  return legend([[COLORS.a, "Class A total cost"], [COLORS.b, "Class B total cost"], ["#94a3b8", "selected proceeds"]]) +
    `<svg viewBox="0 0 ${W} ${H}" width="100%" role="img" aria-label="Total cost of both share classes by gross TVPI">${out}</svg>`;
}

// -------------------------------------------------------------------- CSV export
function toCsv(rows) {
  return rows.map((r) => r.map((v) => (typeof v === "string" && /[",\n;]/.test(v) ? `"${v.replace(/"/g, '""')}"` : v)).join(",")).join("\n");
}
function downloadCsv(kind) {
  if (!last) return;
  const a = last.analysis;
  let rows, name;
  if (kind === "waterfall") {
    name = "waterfall.csv";
    rows = [["Stage", "Total", "LP", "GP (Equity)", "GP (Carry)"], ...a.stages.map((s) => [s.name, s.total, s.lp, s.gp_equity, s.gp_carry]),
      ["Total", a.proceeds, a.totals.lp.amount, a.totals.gp_equity.amount, a.totals.gp_carry.amount]];
  } else if (kind === "fees") {
    name = "management_fees.csv";
    rows = [["Year", "Fee rate (%)", "Fee", "Cumulative"], ...a.fees.map((f) => [f.year, f.rate_pct, f.fee, f.cumulative])];
  } else {
    if (!last.comparison) return;
    name = "class_comparison.csv";
    rows = [["Gross TVPI", "Cost Class A", "Cost Class B", "Net TVPI Class A", "Net TVPI Class B"],
      ...last.comparison.sweep.map((p) => [p.tvpi, p.cost_a, p.cost_b, p.net_tvpi_a, p.net_tvpi_b])];
  }
  const url = URL.createObjectURL(new Blob([toCsv(rows)], { type: "text/csv" }));
  const link = Object.assign(document.createElement("a"), { href: url, download: name });
  link.click();
  URL.revokeObjectURL(url);
}

// ----------------------------------------------------------------- cash-flow IRR
async function calculateIrr() {
  const out = $("irr-result");
  const parts = $("cashflows").value.split(/[\s,;]+/).filter(Boolean);
  const flows = parts.map(Number);
  if (flows.length === 0 || flows.some(Number.isNaN)) {
    out.textContent = "Please enter numbers only, separated by commas, spaces or new lines.";
    return;
  }
  try {
    const data = await postJson("/api/irr", { cashflows: flows });
    out.textContent = `IRR: ${pct(data.irr_pct)} p.a.`;
  } catch (err) {
    out.textContent = err.message;
  }
}

// ------------------------------------------------------------------------ init
function switchTab(name) {
  document.querySelectorAll(".tabs button").forEach((b) => b.setAttribute("aria-selected", String(b.dataset.tab === name)));
  document.querySelectorAll(".panel").forEach((p) => (p.hidden = p.id !== "tab-" + name));
}

async function init() {
  defaults = await (await fetch("/api/defaults")).json();
  $("presets").innerHTML = defaults.presets.map((p, i) => `<button type="button" data-preset="${i}">Load ${p.label}</button>`).join("");
  $("presets").addEventListener("click", (e) => {
    const btn = e.target.closest("button[data-preset]");
    if (btn) applyPreset(defaults.presets[Number(btn.dataset.preset)]);
  });

  const c = defaults.compare;
  setValues("a_", c.class_a);
  setValues("b_", c.class_b);
  $("tvpi_from").value = c.tvpi_from;
  $("tvpi_to").value = c.tvpi_to;
  $("tvpi_step").value = c.tvpi_step;

  document.querySelectorAll(".tabs button").forEach((b) => b.addEventListener("click", () => switchTab(b.dataset.tab)));
  document.querySelectorAll("button[data-csv]").forEach((b) => b.addEventListener("click", () => downloadCsv(b.dataset.csv)));
  $("irr-btn").addEventListener("click", calculateIrr);

  document.addEventListener("input", (e) => {
    if (e.target.matches('input[type="number"]')) {
      syncGpShare();
      scheduleCalculate();
    }
  });
  document.querySelectorAll('input[name="mode"]').forEach((r) =>
    r.addEventListener("change", () => {
      const mode = currentMode();
      if (last) {
        const g = last.analysis;
        const value = mode === "amount" ? g.proceeds : mode === "tvpi" ? g.gross.tvpi : g.gross.irr_pct;
        $("proceeds_value").value = Math.round(value * 1e10) / 1e10; // keep the same scenario when switching units
      }
      setMode(mode);
      calculate();
    }),
  );

  applyPreset(defaults.presets[0]);
  syncGpShare();
}
init();
