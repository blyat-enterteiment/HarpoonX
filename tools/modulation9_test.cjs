"use strict";
// Engineering fixtures only: deterministic price paths, no strategy selection.
const test = require("node:test"), assert = require("node:assert/strict");
const { spawnSync } = require("node:child_process");
const R = require("../runtime30/profit8_replay.js");
const C = require("../runtime30/ultimate_contracts.js");
const M = require("../runtime30/modulation9_exit.cjs");
const B = require("./modulation9_bridge.cjs");
const BAR = 300000, DAY = 86400000, HOUR = 3600000;
const near = (a, b, tol = 1e-7) => assert(Math.abs(a - b) <= tol, `${a} != ${b}`);

function fixture(days = 8, symbols = 1, offsets) {
  const sessions = Array.from({ length: days }, (_, i) => {
    const open = Date.UTC(2025, 0, 3, 14, 30) + (offsets?.[i] ?? i) * DAY;
    return { date: new Date(open).toISOString().slice(0, 10), open, close: open + 78 * BAR };
  });
  const series = Array.from({ length: symbols }, (_, i) => ({
    symbol: ["SYNA", "SYNB", "SYNM"][i], root: ["SYNA", "SYNB", "SYNM"][i],
    tick: .01, pointValue: 1,
    bars: sessions.flatMap(s => Array.from({ length: 78 }, (_, j) => ({
      t: s.open + j * BAR, end: s.open + (j + 1) * BAR,
      availableAt: s.open + (j + 1) * BAR + 1000,
      o: 100, h: 100.1, l: 99.9, c: 100, v: 1000 }))) }));
  const p = { ...C.defaultProtocol("ALPACA_PROXY"), universe: series.map(s => s.symbol),
    costs: { spreadBps: 2, slippageBps: 2, perSideUsd: .005 } };
  const data = { schema: "HARPOON-ULTIMATE-DATA-1", kind: "ALPACA_PROXY", sessions, series,
    splitEvents: [], cashDividends: [], provenance: { execution: "MODELED_OHLCV",
      source: "SYNTHETIC_ENGINEERING_ONLY", feed: "SYNTHETIC_FIXTURE",
      files: [{ name: "synthetic_fixture", sha256: "0".repeat(64) }] } };
  const signal = (profile = "NATIVE72", day = 0, symbol = 0, minute = 60) => {
    const at = sessions[day].open + minute * 60000 + 1000;
    return { id: `${series[symbol].symbol}:${day}:${minute}`, symbol: series[symbol].symbol,
      hypothesis: "CLOSED_CHANNEL", direction: 1, at, index: 0,
      plannedEntryAt: R.planSignalEntryAt(at, sessions), stopDistance: 2, regime: .4,
      metadata: { roadmapHorizonHours: M.PROFILES[profile].horizonHours,
        modulation9: { profile } } };
  };
  return { sessions, series, p, data, signal };
}
function options(research = true) {
  return { continuous: true, cashDividends: true, entryExecution: "IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd: 0, calendarCostPerDayUsd: 1, profit8: { mode: "NATIVE_MAX" },
    ...(research ? { researchModulation: true } : {}) };
}
function bar(f, at, symbol = 0) { return f.series[symbol].bars.find(b => b.t === at); }
function campaign(f, s, q = 8) {
  return R.replayCampaign(s, f.series.find(x => x.symbol === s.symbol), f.data, f.p,
    "BASELINE", q, 1, { cashDividends: true, profit8Trace: true, researchModulation: true });
}
function funded(f, signals, research = true) {
  return R.replayFundedPortfolio(signals, f.data, f.p,
    [{ test: f.sessions, selected: "ALL:BASELINE" }], f.sessions,
    R.PROFIT8_REPLAY_LIMITS, options(research));
}
function untag(s) {
  const clone = structuredClone(s);
  delete clone.metadata.modulation9;
  return clone;
}
function bridgeInput(f, variants) {
  return { dataset: f.data, protocol: { origin: "SYNTHETIC", live_approved: false,
    execution_allowed: false, universe: f.p.universe, limits: { ...R.PROFIT8_REPLAY_LIMITS },
    periods: { evaluation_start: f.sessions[0].date, evaluation_end: f.sessions.at(-1).date },
    scenarios: { NOMINAL: { spread_bps: 2, slippage_bps: 2,
      commission_usd_per_share_per_side: .005, external_cost_usd_per_calendar_day: 1 },
    STRESS: { spread_bps: 4, slippage_bps: 4,
      commission_usd_per_share_per_side: .01, external_cost_usd_per_calendar_day: 2 } } },
    signals: { CONFIRMED: [untag(f.signal())] },
    variants: variants ?? [{ id: "CURRENT", entry: "CONFIRMED", exit: "NATIVE72", risk: .0025 },
      { id: "CASH", entry: "CASH", exit: "NATIVE72", risk: .0025 }] };
}

for (const profile of Object.keys(M.PROFILES)) test(`${profile}: adverse intrabar stop precedes targets`, () => {
  const f = fixture(), s = f.signal(profile), b = bar(f, s.plannedEntryAt);
  Object.assign(b, { h: 108, l: 97, c: 102 });
  const t = campaign(f, s);
  assert.equal(t.reason, "STOP");
  assert.equal(t.inventoryEvents.filter(e => e.kind === "EXIT").length, 1);
  assert.equal(t.inventoryEvents.at(-1).quantityDelta, -8);
  assert.equal(t.ambiguousBars, 1);
  assert.equal(t.inventoryEvents.at(-1).knownAt, b.availableAt);
});

for (const path of ["FLAT", "PARTIALS", "TRAIL", "GAP", "DIVIDEND"])
  test(`NATIVE72 matches unmodulated native campaign and funded ledger exactly: ${path}`, () => {
    const f = fixture(), tagged = f.signal(), start = tagged.plannedEntryAt;
    if (path === "PARTIALS") bar(f, start).h = 106.2;
    if (path === "TRAIL") {
      Object.assign(bar(f, start), { h: 106.2, c: 106.1 });
      Object.assign(bar(f, f.sessions[1].open), { o: 104, h: 104.1, l: 103, c: 104 });
    }
    if (path === "GAP") Object.assign(bar(f, f.sessions[1].open), { o: 90, h: 90.1, l: 89.9, c: 90 });
    if (path === "DIVIDEND") f.data.cashDividends = [{ id: "D", symbol: "SYNA",
      exAt: f.sessions[1].open, payableAt: f.sessions[5].open, amountPerShare: 1.25 }];
    const plain = untag(tagged);
    assert.equal(JSON.stringify(campaign(f, tagged)), JSON.stringify(R.replayCampaign(plain,
      f.series[0], f.data, f.p, "BASELINE", 8, 1, { cashDividends: true, profit8Trace: true })));
    const modified = funded(f, [tagged]), baseline = funded(f, [plain], false);
    for (const state of modified.states) delete state.opportunity.metadata.modulation9;
    assert.equal(JSON.stringify(modified), JSON.stringify(baseline));
  });

test("NATIVE72 transparently preserves the native delayed-stop replacement behavior", () => {
  const f = fixture(), s = f.signal(), first = s.plannedEntryAt;
  Object.assign(bar(f, first), { o: 100, h: 104.1, l: 99.9, c: 104 });
  for (const b of f.series[0].bars) if (first < b.t && b.t < f.sessions[0].close)
    Object.assign(b, { o: 104, h: 104.1, l: 101.8, c: 104 });
  // An old native pending stop is overwritten before its end+1s receipt can
  // activate at a bar opening. It finally activates across the overnight gap.
  // This fixture records the legacy limitation; the NATIVE72 control is exact.
  const t = campaign(f, s);
  assert.equal(t.reason, "STOP");
  assert.equal(t.closed, f.sessions[1].open + BAR);
  assert.equal(JSON.stringify(t), JSON.stringify(R.replayCampaign(untag(s),
    f.series[0], f.data, f.p, "BASELINE", 8, 1,
    { cashDividends: true, profit8Trace: true })));
});

test("metadata cannot enable research implicitly and cannot change an enum or horizon", () => {
  const f = fixture(), s = f.signal();
  assert.throws(() => funded(f, [s], false), /OPT_IN_REQUIRED/);
  assert.throws(() => R.replayCampaign(s, f.series[0], f.data, f.p, "BASELINE", 8, 1,
    { cashDividends: true, profit8Trace: true }), /OPT_IN_REQUIRED/);
  s.metadata.modulation9.profile = "OPTIMIZE_ME";
  assert.throws(() => funded(f, [s]), /EXPLICIT_FIXED_PROFILE/);
  s.metadata.modulation9.profile = "PROTECT48";
  assert.throws(() => funded(f, [s]), /PROFILE_HORIZON_BINDING/);
  s.metadata.roadmapHorizonHours = 48;
  s.metadata.modulation9.extra = 42;
  assert.throws(() => funded(f, [s]), /EXPLICIT_FIXED_PROFILE/);
});

test("new clock and horizon are accepted only in explicit native research", () => {
  const f = fixture(), s = f.signal("PROTECT48", 0, 0, 90);
  assert.equal(funded(f, [s]).funded.length, 1);
  assert.throws(() => funded(f, [untag(s)], false), /FIXED_SIGNAL_CLOCK_POLICY_AND_HORIZON/);
  const wrongClock = f.signal("PROTECT48", 0, 0, 75);
  assert.throws(() => funded(f, [wrongClock]), /FIXED_SIGNAL_CLOCK_POLICY_AND_HORIZON/);
  const wrongMode = options(); wrongMode.profit8.mode = "ROBUST_LOG";
  assert.throws(() => R.replayFundedPortfolio([s], f.data, f.p,
    [{ test: f.sessions, selected: "ALL:BASELINE" }], f.sessions,
    R.PROFIT8_REPLAY_LIMITS, wrongMode), /NATIVE_MODE_REQUIRED/);
});

test("PROTECT48 cannot use a completed close before availableAt, or lose it to a newer bar", () => {
  const f = fixture(), s = f.signal("PROTECT48"), first = s.plannedEntryAt;
  Object.assign(bar(f, first), { o: 100, h: 102.6, l: 99.9, c: 102.5 });
  Object.assign(bar(f, first + BAR), { o: 102.5, h: 102.7, l: 100.7, c: 102.6 });
  Object.assign(bar(f, first + 2 * BAR), { o: 102.6, h: 102.7, l: 101, c: 102 });
  const t = campaign(f, s);
  assert.equal(t.reason, "STOP");
  assert.equal(t.closed, first + 3 * BAR);
  assert.equal(t.inventoryEvents.at(-1).knownAt, first + 3 * BAR + 1000);
  assert(t.inventoryEvents.at(-1).filledPrice > t.entry);
});

test("ready stop queue activates the old receipt while retaining the new unreceived stop", () => {
  const state = M.createState(M.PROFILES.PROTECT48);
  M.queueStop(state, 101, 300001, 98, 1);
  M.queueStop(state, 102, 600001, 98, 1);
  assert.equal(M.advance(state, 600000, 98, 1), 101);
  assert.equal(state.pendingStops.length, 1);
  assert.equal(M.advance(state, 900000, 101, 1), 102);
  assert.equal(state.pendingStops.length, 0);
});

test("custom stops never loosen; breakeven trigger covers modeled round-trip fees", () => {
  for (const profile of [M.PROFILES.PROTECT48, M.PROFILES.RUNNER72]) {
    let stop = 98;
    for (const peak of [100, 102, 105, 104, 102, 99, 110]) {
      const next = M.nextStop(profile, 1, stop, 100, peak, 2, .0003, .005, 1, .01);
      assert(next >= stop); stop = next;
    }
  }
  const entry = 100.03, trigger = M.costBreakeven(entry, 1, .0003, .005, 1, .01);
  const exit = Math.floor(trigger * (1 - .0003) / .01 + 1e-8) * .01;
  assert(exit - entry - .01 >= -1e-8);
});

test("RUNNER72 takes only one integer quarter at 2R and leaves the rest to trailing", () => {
  const f = fixture(), s = f.signal("RUNNER72"), first = s.plannedEntryAt;
  Object.assign(bar(f, first), { o: 100, h: 107, l: 99.9, c: 104.4 });
  const t = campaign(f, s), exits = t.inventoryEvents.filter(e => e.kind === "EXIT");
  assert.equal(exits.filter(e => e.reason.startsWith("TP")).length, 1);
  assert.equal(exits[0].reason, "TP1");
  assert.equal(exits[0].quantityDelta, -2);
  assert.equal(exits.at(-1).quantityDelta, -6);
  assert.equal(t.inventoryEvents.reduce((sum, e) => sum + e.quantityDelta, 0), 0);
});

for (const q of [1, 2, 3, 4, 5, 7, 8]) test(`integer partials conserve quantity ${q}`, () => {
  const f = fixture(), s = f.signal("PROTECT48");
  bar(f, s.plannedEntryAt).h = 107;
  const t = campaign(f, s, q), exits = t.inventoryEvents.filter(e => e.kind === "EXIT");
  assert(exits.every(e => Number.isInteger(e.quantityDelta) && e.quantityDelta < 0));
  assert.equal(exits.reduce((sum, e) => sum - e.quantityDelta, 0), q);
});

test("FAST24 exits at next session open after six elapsed hours using completed-close peak", () => {
  const f = fixture(), s = f.signal("FAST24");
  // Intrabar high is not the locked completed-close stall criterion.
  bar(f, s.plannedEntryAt).h = 101.2;
  const t = campaign(f, s);
  assert.equal(t.reason, "MODULATION9_STALLED");
  assert.equal(t.closed, f.sessions[1].open);
  assert(t.closed - t.opened >= 6 * HOUR);
  assert.equal(t.inventoryEvents.at(-1).knownAt, t.closed);
});

test("FAST24 cannot erase an earlier qualifying completed-close excursion", () => {
  const f = fixture(), s = f.signal("FAST24");
  Object.assign(bar(f, s.plannedEntryAt), { h: 101.3, c: 101.2 });
  const t = campaign(f, s);
  assert.equal(t.reason, "TIME");
  assert.equal(t.closed, t.holdingDeadlineAt);
});

test("FAST24 cannot see a favorable close that will arrive after the decision opening", () => {
  const f = fixture(), s = f.signal("FAST24");
  const last = bar(f, f.sessions[0].close - BAR);
  Object.assign(last, { h: 102.1, c: 102, availableAt: f.sessions[1].open + 1000 });
  const t = campaign(f, s);
  assert.equal(t.reason, "MODULATION9_STALLED");
  assert.equal(t.closed, f.sessions[1].open);
});

for (const profile of Object.keys(M.PROFILES)) test(`${profile}: overnight gap is not capped at nominal stop`, () => {
  const f = fixture(), s = f.signal(profile);
  Object.assign(bar(f, f.sessions[1].open), { o: 90, h: 90.1, l: 89.9, c: 90 });
  const t = campaign(f, s);
  assert.equal(t.reason, "STOP");
  assert(t.inventoryEvents.at(-1).filledPrice < 90);
  assert(t.netUsd < -t.riskUsd);
});

for (const profile of Object.keys(M.PROFILES)) test(`${profile}: calendar deadline is bounded by its declared horizon`, () => {
  const f = fixture(8, 1, [0, 3, 4, 5, 6, 7, 10, 11]), s = f.signal(profile);
  const t = campaign(f, s);
  assert(t.closed <= s.at + M.PROFILES[profile].horizonHours * HOUR);
  assert(t.closed <= t.holdingDeadlineAt);
  assert.equal(t.inventoryEvents.reduce((sum, e) => sum + e.quantityDelta, 0), 0);
});

test("missing bar with open exposure fails closed instead of deleting a position", () => {
  const f = fixture(), s = f.signal("PROTECT48");
  f.series[0].bars = f.series[0].bars.filter(b => b.t !== s.plannedEntryAt + BAR);
  assert.throws(() => campaign(f, s), /MISSING_BAR_WITH_OPEN_EXPOSURE|MISSING_SESSION_WITH_OPEN_EXPOSURE/);
});

test("bridge shares calendar overhead with cash and independently reconciles fill cash", () => {
  const f = fixture(150), input = bridgeInput(f);
  input.detailed = ["CURRENT"];
  const before = JSON.stringify(input);
  const out = B.runBatch(input);
  assert.equal(out.origin, "SYNTHETIC");
  assert.equal(out.account_executions, 4);
  assert(out.all_terminal_reconciled);
  assert.equal(JSON.stringify(input), before);
  for (const scenario of ["NOMINAL", "STRESS"]) {
    const current = out.accounts.find(a => a.id === "CURRENT" && a.scenario === scenario);
    const cash = out.accounts.find(a => a.id === "CASH" && a.scenario === scenario);
    assert.equal(current.summary.fixed_costs_usd, cash.summary.fixed_costs_usd);
    assert.equal(cash.summary.net_pnl_usd, -cash.summary.fixed_costs_usd);
    assert.equal(cash.summary.closed_campaigns, 0);
    near(cash.summary.max_event_drawdown, cash.summary.fixed_costs_usd / 20000);
    assert(current.summary.max_event_drawdown + 1e-12 >= current.summary.max_session_drawdown);
    assert.equal(cash.summary.max_signal_to_exit_hours, 0);
    assert(Number.isFinite(current.summary.max_signal_to_exit_hours));
    near(current.summary.cash_reconciliation_error, 0);
    assert.equal(current.summary.closed_campaigns, 1);
    assert.equal(current.summary.terminal_inventory_quantity, 0);
    assert.equal(current.summary.terminal_reservations, 0);
    assert.equal(current.detail.metadata.executionNature, "SYNTHETIC_MODELED_OHLCV;NOT_BROKER_RECEIPTS");
    assert(current.detail.states.every(s => !s.positionOpened || s.fillBudgetReceipt.status === "VERIFIED"));
    for (const row of current.curve) {
      assert(Number.isFinite(row.portfolio_log_return));
      assert.equal(row.date.length, 10);
    }
  }
});

test("independent ledger audit catches a missing exit share and handles accrued dividends", () => {
  const f = fixture(), s = f.signal();
  f.data.cashDividends = [{ id: "D", symbol: "SYNA", exAt: f.sessions[1].open,
    payableAt: null, amountPerShare: 1.25 }];
  const result = funded(f, [s]);
  assert(B.ledgerAudit(result, f.sessions, 20000).terminal_reconciled);
  assert(result.accounting.dividendReceivableUsd > 0);
  result.funded[0].inventoryEvents.at(-1).quantityDelta += 1;
  const bad = B.ledgerAudit(result, f.sessions, 20000);
  assert.equal(bad.terminal_reconciled, false);
  assert.equal(bad.terminal_inventory_quantity, 1);
});

test("bridge rejects disguised provenance and raised risk instead of evaluating them", () => {
  const f = fixture(150), input = bridgeInput(f);
  input.protocol.origin = "HISTORICAL";
  assert.throws(() => B.prepareInput(input), /SYNTHETIC_OFFLINE_ONLY/);
  input.protocol.origin = "SYNTHETIC";
  input.dataset.provenance.source = "HISTORICAL_SOURCE";
  assert.throws(() => B.prepareInput(input), /SYNTHETIC_PROVENANCE_REQUIRED/);
  input.dataset.provenance.source = "SYNTHETIC_ENGINEERING_ONLY";
  input.variants[0].risk = .003;
  assert.throws(() => B.prepareInput(input), /VARIANT_CONTRACT/);
});

test("research price index exactly matches the native full scan, including delayed bars and ties", () => {
  const f = fixture(4, 2), first = f.series[0].bars[0];
  // These extra direct-helper fault inputs intentionally exceed dataset rules.
  // The optimized lookup still reproduces the native scan's public contract.
  f.series[0].bars.push({ ...first, availableAt: first.availableAt + DAY, c: 999 });
  f.series[0].bars.push({ ...first, t: NaN, c: 888 });
  f.series[0].bars[77].availableAt += DAY;
  f.series[0].bars[70].c = NaN;
  const lookup = M.causalPriceLookup(f.series, R.causalReferencePrice);
  const times = [-1, 0, NaN, Infinity, ...f.series[0].bars.flatMap(b =>
    [b.t, b.end, b.availableAt - 1, b.availableAt, b.availableAt + 1])];
  for (const series of f.series) for (const at of times)
    assert.deepEqual(lookup({ at }, series), R.causalReferencePrice({ at }, series));
  const outside = { bars: [{ ...first }] };
  assert.deepEqual(lookup({ at: first.availableAt }, outside),
    R.causalReferencePrice({ at: first.availableAt }, outside));
});

test("bridge NDJSON mode reuses one process and produces machine-readable complete responses", () => {
  const input = bridgeInput(fixture(150), [{ id: "CASH", entry: "CASH", exit: "NATIVE72", risk: .0025 }]);
  input.scenario_names = ["NOMINAL"];
  const child = spawnSync(process.execPath, [require.resolve("./modulation9_bridge.cjs"), "--stream"],
    { input: JSON.stringify(input) + "\n" + JSON.stringify(input) + "\n", encoding: "utf8", maxBuffer: 2000000 });
  assert.equal(child.status, 0, child.stderr);
  const rows = child.stdout.trim().split("\n").map(line => JSON.parse(line));
  assert.equal(rows.length, 2);
  assert(rows.every(row => row.account_executions === 1 && row.all_terminal_reconciled));
  assert.deepEqual(rows[0], rows[1]);
});

module.exports = { fixture, bridgeInput };
