"use strict";
// Synthetic risk-accounting fixtures only: never market or profitability evidence.
const test = require("node:test"), assert = require("node:assert/strict");
const R = require("../runtime30/ultimate_replay.js");
const C = require("../runtime30/ultimate_contracts.js");
const BAR = 300000, DAY = 86400000;
function fixture() {
  const sessions = Array.from({length: 8}, (_, i) => {
    const open = Date.UTC(2025, 0, 1, 14, 30) + i * DAY;
    return {date: new Date(open).toISOString().slice(0, 10), open, close: open + 78 * BAR};
  });
  const series = [0, 1].map(i => ({symbol: "ASSET" + i, root: "ASSET" + i, pointValue: 1, tick: .01,
    bars: sessions.flatMap(s => Array.from({length: 78}, (_, j) => ({t: s.open + j * BAR,
      end: s.open + (j + 1) * BAR, availableAt: s.open + (j + 1) * BAR + 1000,
      o: 100, h: 100.1, l: 99.9, c: 100, v: 1000})))}));
  const protocol = {...C.defaultProtocol("ALPACA_PROXY"), universe: series.map(s => s.symbol), purgeHours: 0,
    costs: {spreadBps: 0, slippageBps: 0, perSideUsd: 0}};
  const data = {schema: "HARPOON-ULTIMATE-DATA-1", kind: "ALPACA_PROXY", sessions, series, splitEvents: []};
  const signal = (id, symbol, at) => ({id, symbol, at, direction: 1, hypothesis: "OPENING_BREAKOUT",
    plannedEntryAt: R.planSignalEntryAt(at, sessions), index: 0, stopDistance: 2, regime: .4});
  const signals = [signal("first", "ASSET0", sessions[0].open + 2 * BAR + 1000),
    signal("second", "ASSET1", sessions[0].open + 20 * BAR + 1000)];
  return {sessions, series, protocol, data, signals, signal};
}
function run(f, opts = {}) {
  return R.replayFundedPortfolio(f.signals, f.data, f.protocol,
    [{test: f.sessions, selected: "ALL:BASELINE"}], f.sessions,
    {...R.DEFAULT_REPLAY_LIMITS, maxDrawdown: .003}, {externalCostPerSessionUsd: 0, ...opts});
}
function gainThenLoss(f) {
  Object.assign(f.series[0].bars[4], {o: 100, h: 102.4, l: 99.9, c: 102.3});
  Object.assign(f.series[0].bars[5], {o: 100, h: 100.1, l: 97.9, c: 98});
}
test("known account peak between admitted signals enforces drawdown", () => {
  const f = fixture(); gainThenLoss(f); const out = run(f);
  assert.equal(out.funded.length, 1);
  const rejected = out.preEntryRefusals.find(x => x.signalId === "second");
  assert.equal(rejected.reason, "LOSS_LIMIT");
  assert(Math.abs(rejected.causalPeakEquityUsd - 20055.2) < 1e-8);
  assert.equal(rejected.equityUsd, 19952);
  assert(rejected.drawdownFromCausalPeak > .003);
});
test("adding a model-rejected signal at the peak cannot change risk enforcement", () => {
  const f = fixture(); gainThenLoss(f); const before = run(f);
  const rejected = f.signal("model-refused", "ASSET1", f.series[0].bars[4].availableAt);
  f.signals.splice(1, 0, rejected);
  const after = run(f, {admissions: Object.fromEntries(f.signals.map(s => [s.id,
    {allow: s.id !== "model-refused", rank: 0}]))});
  assert.deepEqual(after.funded, before.funded);
  assert.deepEqual(after.preEntryRefusals.find(x => x.signalId === "second"),
    before.preEntryRefusals.find(x => x.signalId === "second"));
});
test("future price peaks do not tighten a prior decision's drawdown threshold", () => {
  const f = fixture(); f.signals[1] = f.signal("second", "ASSET1", f.sessions[0].open + 4 * BAR + 1000);
  const before = run(f).states.find(s => s.opportunity.id === "second");
  Object.assign(f.series[0].bars[10], {o: 100, h: 120, l: 99.9, c: 119});
  const after = run(f).states.find(s => s.opportunity.id === "second");
  assert.equal(after.status, "MODELED_CAMPAIGN");
  assert.equal(after.causalPeakEquityUsd, before.causalPeakEquityUsd);
  assert.equal(after.equity, before.equity);
  assert.equal(after.quantity, before.quantity);
});
test("CASH still observes every session's external charge on the event clock", () => {
  const f = fixture(); f.signals = []; const out = run(f, {externalCostPerSessionUsd: 3});
  assert.equal(out.portfolio.netUsd, -24);
  assert.equal(out.metadata.causalPeakEquityUsd, 20000);
  assert(Math.abs(out.metadata.maximumObservedEventDrawdown - 24 / 20000) < 1e-12);
  assert.equal(out.metadata.observedValuationEvents, 8);
});
