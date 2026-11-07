"use strict";
// Deterministic engineering fixtures only; no optimizer or economic sampling.
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), path = require("node:path");
const { spawnSync } = require("node:child_process");
const R = require("../runtime30/modulation10_replay.cjs");
const OLD = require("../runtime30/profit8_replay.js");
const C = require("../runtime30/ultimate_contracts.js");
const M = require("../runtime30/modulation9_exit.cjs");
const B = require("./modulation10_bridge.cjs");
const B9 = require("./modulation9_bridge.cjs");
const BAR = 300000, DAY = 86400000, HOUR = 3600000;
const SCHEDULES = { CONFIRMED: { minutes: [60], lag_ms: 1000, max_per_session: 1 },
  QUALITY: { minutes: [60], lag_ms: 1000, max_per_session: 1 },
  RETEST: { minutes: [90], lag_ms: 1000, max_per_session: 1 },
  MOM3_Z0: { minutes: [5], lag_ms: 1000, max_per_session: 1 },
  MOM3_Z075: { minutes: [5], lag_ms: 1000, max_per_session: 1 },
  MOM8_Z0: { minutes: [5], lag_ms: 1000, max_per_session: 1 },
  MOM8_Z075: { minutes: [5], lag_ms: 1000, max_per_session: 1 },
  SIMPLE: { minutes: [60], lag_ms: 1000, max_per_session: 1 } };
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
  const signal = (profile = "NATIVE72", day = 0, symbol = 0, entry = "CONFIRMED", minute) => {
    const at = sessions[day].open + (minute ?? SCHEDULES[entry].minutes[0]) * 60000 + 1000;
    return { id: `${series[symbol].symbol}:${day}:${at}`, symbol: series[symbol].symbol,
      hypothesis: "CLOSED_CHANNEL", direction: 1, at, index: 0, sourceAvailableAt: at,
      plannedEntryAt: R.planSignalEntryAt(at, sessions), stopDistance: 2, regime: .4,
      metadata: { roadmapHorizonHours: R.MODULATION10_PROFILES[profile].horizonHours,
        modulation10: { entry, profile } } };
  };
  return { sessions, series, p, data, signal };
}
function options(schedules = SCHEDULES) {
  return { continuous: true, cashDividends: true, entryExecution: "IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd: 0, calendarCostPerDayUsd: 1, profit8: { mode: "NATIVE_MAX" },
    researchModulation: true, researchModulation10: true, modulation10EntrySchedules: schedules };
}
function bar(f, at, symbol = 0) { return f.series[symbol].bars.find(b => b.t === at); }
function campaign(f, s, quantity = 8, schedules = SCHEDULES) {
  return R.replayCampaign(s, f.series.find(x => x.symbol === s.symbol), f.data, f.p,
    "BASELINE", quantity, 1, { ...options(schedules), profit8Trace: true });
}
function funded(f, signals, schedules = SCHEDULES, limits = R.PROFIT8_REPLAY_LIMITS) {
  return R.replayFundedPortfolio(signals, f.data, f.p,
    [{ test: f.sessions, selected: "ALL:BASELINE" }], f.sessions, limits, options(schedules));
}
function oldSignal(s) {
  const clone = structuredClone(s), profile = clone.metadata.modulation10.profile;
  delete clone.metadata.modulation10;
  clone.metadata.modulation9 = { profile };
  return clone;
}
function oldOptions() {
  const out = options(); delete out.researchModulation10; delete out.modulation10EntrySchedules;
  return out;
}
function bridgeInput(f, variants) {
  const base = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../research/modulation9/protocol.json")));
  return { dataset: f.data, protocol: { ...base, schema: "HARPOON_MODULATION10_PROTOCOL_1",
    universe: f.p.universe, entry_schedules: structuredClone(SCHEDULES),
    entry_rules: Object.fromEntries(Object.keys(SCHEDULES).map(key => [key, "FIXTURE_ONLY"])),
    periods: { evaluation_start: f.sessions[0].date, evaluation_end: f.sessions.at(-1).date } },
    signals: { CONFIRMED: [(() => { const s = f.signal(); delete s.metadata.modulation10; return s; })()] },
    variants: variants ?? [{ id: "CURRENT", entry: "CONFIRMED", exit: "NATIVE72", risk: .0025 },
      { id: "CASH", entry: "CASH", exit: "NATIVE72", risk: .0025 }] };
}

test("all 47 registered Modulation9 sources retain their original hashes", () => {
  assert.equal(R.verifyModulation9Sources().registered_source_files, 47);
  assert.equal(R.verifyModulation9Sources().all_registered_sources_verified, true);
});

test("without v2 opt-in campaign and portfolio delegate byte-exactly to frozen original", () => {
  const f = fixture(), s = oldSignal(f.signal()), opt = oldOptions();
  assert.equal(JSON.stringify(R.replayCampaign(s, f.series[0], f.data, f.p, "BASELINE", 8, 1,
    { ...opt, profit8Trace: true })), JSON.stringify(OLD.replayCampaign(s, f.series[0], f.data,
    f.p, "BASELINE", 8, 1, { ...opt, profit8Trace: true })));
  const args = [[s], f.data, f.p, [{ test: f.sessions, selected: "ALL:BASELINE" }],
    f.sessions, R.PROFIT8_REPLAY_LIMITS, opt];
  assert.equal(JSON.stringify(R.replayFundedPortfolio(...args)), JSON.stringify(OLD.replayFundedPortfolio(...args)));
});

for (const profile of Object.keys(M.PROFILES)) for (const shape of ["FLAT", "CLOSE_TREND", "GAP", "PARTIALS"])
  test(`${profile}: v2 preserves legacy campaign and complete ledger on ${shape}`, () => {
    const f = fixture(), s = f.signal(profile), first = s.plannedEntryAt;
    if (shape === "CLOSE_TREND") {
      for (const b of f.series[0].bars) if (b.t >= first && b.t < f.sessions[0].close)
        Object.assign(b, { o: b.t === first ? 100 : 104, h: 104.2, l: b.t === first ? 99.9 : 101.8, c: 104 });
    }
    if (shape === "GAP") Object.assign(bar(f, f.sessions[1].open), { o: 90, h: 90.1, l: 89.9, c: 90 });
    if (shape === "PARTIALS") bar(f, first).h = 108;
    const legacy = oldSignal(s), baseline = OLD.replayCampaign(legacy, f.series[0], f.data, f.p,
      "BASELINE", 8, 1, { ...oldOptions(), profit8Trace: true });
    assert.deepEqual(campaign(f, s), baseline);
    const current = funded(f, [s]), expected = OLD.replayFundedPortfolio([legacy], f.data, f.p,
      [{ test: f.sessions, selected: "ALL:BASELINE" }], f.sessions, R.PROFIT8_REPLAY_LIMITS, oldOptions());
    for (const state of current.states) state.opportunity.metadata = oldSignal(state.opportunity).metadata;
    assert.deepEqual(current, expected);
  });

test("queue-only profile retains every native mathematical parameter", () => {
  const native = R.MODULATION10_PROFILES.NATIVE72, queue = R.MODULATION10_PROFILES.NATIVE_QUEUE72;
  for (const key of Object.keys(native).filter(k => !["profile", "stopReceipt"].includes(k)))
    assert.deepEqual(queue[key], native[key], key);
  assert.equal(queue.stopReceipt, "QUEUED"); assert.equal(native.stopReceipt, "LEGACY");
});

test("queue-only activates received stop without overwriting it with an unread close", () => {
  const f = fixture(), s = f.signal("NATIVE_QUEUE72"), first = s.plannedEntryAt;
  Object.assign(bar(f, first), { o: 100, h: 104.1, l: 99.9, c: 104 });
  for (const b of f.series[0].bars) if (first < b.t && b.t < f.sessions[0].close)
    Object.assign(b, { o: 104, h: 104.1, l: 101.8, c: 104 });
  const queued = campaign(f, s), legacy = campaign(f, f.signal("NATIVE72"));
  assert.equal(queued.closed, first + 3 * BAR);
  assert.equal(legacy.closed, f.sessions[1].open + BAR);
  assert.deepEqual(queued.inventoryEvents.slice(0, 2), legacy.inventoryEvents.slice(0, 2));
  assert.equal(queued.inventoryEvents[1].reason, "TP1");
  assert.equal(queued.inventoryEvents[1].quantityDelta, -2);
  assert.equal(queued.inventoryEvents.at(-1).reason, "STOP");
  assert(queued.closed > bar(f, first).availableAt);
});

test("queue-only and native have identical targets and fees without a trail activation", () => {
  const f = fixture(), s = f.signal("NATIVE_QUEUE72");
  bar(f, s.plannedEntryAt).h = 107;
  assert.deepEqual(campaign(f, s), campaign(f, f.signal("NATIVE72")));
});

for (const profile of ["HOLD24", "HOLD72"]) {
  test(`${profile}: disables partials and trailing despite large favorable closes`, () => {
    const f = fixture(), s = f.signal(profile, 0, 0, "MOM3_Z0"), first = s.plannedEntryAt;
    for (const b of f.series[0].bars) if (b.t >= first)
      Object.assign(b, { o: b.t === first ? 100 : 110, h: 120, l: 99.5, c: 115 });
    const t = campaign(f, s, 12), exits = t.inventoryEvents.filter(e => e.kind === "EXIT");
    assert.equal(t.reason, "TIME"); assert.equal(exits.length, 1);
    assert.equal(exits[0].quantityDelta, -12);
    assert.equal(t.closed, t.holdingDeadlineAt);
    assert(t.closed - s.at <= R.MODULATION10_PROFILES[profile].horizonHours * HOUR);
  });
  test(`${profile}: adverse stop precedes favorable range and gaps retain slippage`, () => {
    const f = fixture(), s = f.signal(profile);
    Object.assign(bar(f, s.plannedEntryAt), { h: 120, l: 97, c: 105 });
    const t = campaign(f, s);
    assert.equal(t.reason, "STOP"); assert.equal(t.inventoryEvents.length, 2);
    const g = fixture(), gs = g.signal(profile);
    Object.assign(bar(g, g.sessions[1].open), { o: 90, h: 90.1, l: 89.9, c: 90 });
    const gt = campaign(g, gs);
    assert.equal(gt.reason, "STOP"); assert(gt.inventoryEvents.at(-1).filledPrice < 90);
    assert(gt.netUsd < -gt.riskUsd);
  });
}

for (const profile of ["NATIVE_QUEUE72", "HOLD24", "HOLD72", "PROTECT48"])
  test(`${profile}: calendar deadline never extends past its horizon over a weekend`, () => {
    const f = fixture(8, 1, [0, 3, 4, 5, 6, 7, 10, 11]), s = f.signal(profile);
    const t = campaign(f, s);
    assert(t.closed <= s.at + R.MODULATION10_PROFILES[profile].horizonHours * HOUR);
    assert.equal(t.inventoryEvents.reduce((n, event) => n + event.quantityDelta, 0), 0);
  });

for (const entry of ["MOM3_Z0", "MOM3_Z075", "MOM8_Z0", "MOM8_Z075"])
  test(`${entry}: decision at 5 minutes plus receipt lag plans opening at 10 minutes`, () => {
    const f = fixture(), s = f.signal("HOLD24", 0, 0, entry);
    assert.equal(s.plannedEntryAt, f.sessions[0].open + 2 * BAR);
    assert.equal(funded(f, [s]).funded.length, 1);
    const quote = OLD.causalReferencePrice(s, f.series[0]);
    assert.equal(quote.sourceAvailableAt, s.at); assert(quote.sourceAvailableAt <= s.at);
  });

test("future source availability and feature metadata are rejected before replay", () => {
  const f = fixture(), s = f.signal("HOLD24", 0, 0, "MOM3_Z0");
  s.sourceAvailableAt = s.at + 1;
  assert.throws(() => funded(f, [s]), /CAUSAL_SIGNAL_CLOCK_AND_PLAN/);
  s.sourceAvailableAt = s.at; s.metadata.featuresAvailableAt = s.at + 1;
  assert.throws(() => funded(f, [s]), /FUTURE_FEATURE_METADATA/);
  delete s.metadata.featuresAvailableAt;
  s.metadata.momentumFeature = { source_available_at: s.at + 1 };
  assert.throws(() => funded(f, [s]), /MOMENTUM_FEATURE_RECEIPT_BINDING/);
  delete s.metadata.momentumFeature; delete s.sourceAvailableAt;
  assert.throws(() => funded(f, [s]), /CAUSAL_SIGNAL_CLOCK_AND_PLAN/);
});

test("unregistered clocks, altered plans and multiple nominations fail closed", () => {
  const f = fixture(8, 2), wrongClock = f.signal("HOLD24", 0, 0, "MOM3_Z0", 10);
  assert.throws(() => funded(f, [wrongClock]), /CAUSAL_SIGNAL_CLOCK_AND_PLAN/);
  const s = f.signal("HOLD24", 0, 0, "MOM3_Z0"); s.plannedEntryAt += BAR;
  assert.throws(() => funded(f, [s]), /CAUSAL_SIGNAL_CLOCK_AND_PLAN/);
  assert.throws(() => funded(f, [f.signal("HOLD24", 0, 0, "MOM3_Z0"),
    f.signal("HOLD24", 0, 1, "MOM3_Z0")]), /MAX_NOMINATIONS_PER_SESSION/);
});

test("v2 metadata cannot silently enable research or mix exit policies", () => {
  const f = fixture(), s = f.signal();
  assert.throws(() => R.replayCampaign(s, f.series[0], f.data, f.p, "BASELINE", 8, 1,
    { ...oldOptions(), profit8Trace: true }), /OPT_IN_REQUIRED/);
  assert.throws(() => R.replayFundedPortfolio([s], f.data, f.p,
    [{ test: f.sessions, selected: "ALL:BASELINE" }], f.sessions,
    R.PROFIT8_REPLAY_LIMITS, oldOptions()), /OPT_IN_REQUIRED/);
  s.metadata.modulation9 = { profile: "NATIVE72" };
  assert.throws(() => funded(f, [s]), /NO_MIXED_POLICY_OR_FORECAST/);
});

test("registered multiple intraday slots reuse capital only after known inventory closure", () => {
  const f = fixture(), schedules = { ...SCHEDULES,
    MOM3_Z0: { minutes: [5, 120], lag_ms: 1000, max_per_session: 2 } };
  const signals = [f.signal("HOLD24", 0, 0, "MOM3_Z0", 5), f.signal("HOLD24", 0, 0, "MOM3_Z0", 120)];
  const occupied = funded(f, signals, schedules);
  assert.equal(occupied.funded.length, 1);
  assert(occupied.preEntryRefusals.some(row => JSON.stringify(row).includes("SYMBOL_BUSY")));
  Object.assign(bar(f, signals[0].plannedEntryAt), { l: 97 });
  assert.equal(funded(f, signals, schedules).funded.length, 2);
});

test("missing entry or holding bars remain unresolved exposures, never free exclusions", () => {
  const f = fixture(), s = f.signal("HOLD72", 0, 0, "MOM3_Z0");
  f.series[0].bars = f.series[0].bars.filter(b => b.t !== s.plannedEntryAt + BAR);
  assert.throws(() => campaign(f, s), /MISSING_BAR_WITH_OPEN_EXPOSURE|MISSING_SESSION_WITH_OPEN_EXPOSURE/);
  const g = fixture(), gs = g.signal("HOLD24", 0, 0, "MOM3_Z0");
  g.series[0].bars = g.series[0].bars.filter(b => b.t !== gs.plannedEntryAt);
  assert.throws(() => campaign(g, gs), /MISSING_PLANNED_ENTRY_BAR/);
});

test("risk caps remain unchanged and reject increased admission risk", () => {
  const f = fixture(), s = f.signal("HOLD72", 0, 0, "MOM3_Z0");
  assert.deepEqual(R.PROFIT8_REPLAY_LIMITS, OLD.PROFIT8_REPLAY_LIMITS);
  assert.throws(() => funded(f, [s], SCHEDULES, { ...R.PROFIT8_REPLAY_LIMITS,
    riskFraction: .003 }), /LIMITS_MUST_BE_EXPLICIT_AND_NOT_RAISED/);
  const result = funded(f, [s]);
  assert(result.funded[0].riskUsd <= 50);
  assert(result.funded[0].quantity * result.funded[0].entry <= 2400);
  assert(B.ledgerAudit(result, f.sessions, 20000).terminal_reconciled);
});

test("terminal evaluation refuses new campaigns whose deadline exceeds evaluation", () => {
  const f = fixture(), s = f.signal("HOLD72", 7, 0, "MOM3_Z0");
  const out = funded(f, [s]);
  assert.equal(out.funded.length, 0);
  assert.equal(out.preEntryRefusals.length, 1);
  assert(B.ledgerAudit(out, f.sessions, 20000).terminal_reconciled);
});

test("bridge retains controls, costs, curve and ledger byte-equivalent to M9", () => {
  const f = fixture(150), input = bridgeInput(f); input.detailed = ["CURRENT"];
  const before = JSON.stringify(input), out = B.runBatch(input), expected = B9.runBatch(input);
  assert.equal(JSON.stringify(input), before); assert.equal(out.account_executions, 4);
  assert.equal(out.source_binding.before.registered_source_files, 47);
  assert.deepEqual(out.source_binding.before, out.source_binding.after);
  for (let i = 0; i < out.accounts.length; i++) {
    const actual = out.accounts[i], legacy = expected.accounts[i];
    for (const field of ["summary", "curve", "trades", "event_risk"])
      assert.deepEqual(actual[field], legacy[field], field);
    assert(actual.terminal_reconciled);
    if (actual.id === "CASH") {
      near(actual.summary.net_pnl_usd, -actual.summary.fixed_costs_usd);
      near(actual.summary.max_event_drawdown, actual.summary.fixed_costs_usd / 20000);
      assert.equal(actual.summary.max_signal_to_exit_hours, 0);
    }
  }
});

test("bridge refuses changed costs, non-synthetic origin and unregistered entries", () => {
  const input = bridgeInput(fixture(150));
  input.protocol.scenarios.NOMINAL.spread_bps = 0;
  assert.throws(() => B.prepareInput(input), /COSTS_IDENTICAL/);
  input.protocol.scenarios.NOMINAL.spread_bps = 2; input.protocol.origin = "HISTORICAL";
  assert.throws(() => B.prepareInput(input), /SYNTHETIC_OFFLINE_ONLY/);
  input.protocol.origin = "SYNTHETIC"; delete input.protocol.entry_schedules.CONFIRMED;
  assert.throws(() => B.prepareInput(input), /REGISTERED_SCHEDULE_REQUIRED/);
});

test("registered 23-policy catalogue yields 46 reconciled accounts on a flat engineering tape", () => {
  const f = fixture(150), input = bridgeInput(f);
  const registered = JSON.parse(fs.readFileSync(path.resolve(__dirname, "../research/modulation10/protocol.json")));
  input.variants = registered.variants;
  for (const entry of new Set(input.variants.map(v => v.entry).filter(e => e !== "CASH"))) {
    const s = f.signal("NATIVE72", 0, 0, entry);
    delete s.metadata.modulation10;
    input.signals[entry] = [s];
  }
  const out = B.runBatch(input);
  assert.equal(out.account_executions, 46);
  assert.equal(out.accounts.filter(a => a.scenario === "NOMINAL").length, 23);
  assert.equal(out.accounts.filter(a => a.scenario === "STRESS").length, 23);
  assert(out.all_terminal_reconciled);
  assert(out.accounts.every(a => a.role === "candidate" || a.role === "control"));
});

test("bridge stream mode emits repeatable engineering results and terminal reconciliation", () => {
  const input = bridgeInput(fixture(150), [{ id: "CASH", entry: "CASH", exit: "NATIVE72", risk: .0025 }]);
  input.scenario_names = ["NOMINAL"];
  const child = spawnSync(process.execPath, [require.resolve("./modulation10_bridge.cjs"), "--stream"],
    { input: JSON.stringify(input) + "\n" + JSON.stringify(input) + "\n", encoding: "utf8", maxBuffer: 2000000 });
  assert.equal(child.status, 0, child.stderr);
  const rows = child.stdout.trim().split("\n").map(line => JSON.parse(line));
  assert.equal(rows.length, 2); assert.deepEqual(rows[0], rows[1]);
  assert.equal(rows[0].account_executions, 1); assert(rows[0].all_terminal_reconciled);
});

module.exports = { fixture, bridgeInput };
