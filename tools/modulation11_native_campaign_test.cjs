"use strict";
// M11 phase1: integrated, deterministic engineering fixtures only. No optimization.
const test = require("node:test");
const assert = require("node:assert/strict");
const R = require("../runtime30/profit8_replay.js");
const C = require("../runtime30/ultimate_contracts.js");
const M = require("../runtime30/modulation9_exit.cjs");
const E = require("../runtime30/modulation11_execution_equivalence.cjs");
const RES = require("../runtime30/ultimate_reservations.js");
const BAR = 300000;
const DAY = 86400000;
const near = (a, b) => assert(Math.abs(a - b) < 1e-7, String(a) + " != " + String(b));

function fixture() {
  const sessions = Array.from({length: 5}, (_, i) => {
    const open = Date.UTC(2025, 0, 3, 14, 30) + i * DAY;
    return {date: new Date(open).toISOString().slice(0, 10), open, close: open + 78 * BAR};
  });
  const series = [{symbol: "SYNA", root: "SYNA", tick: .01, pointValue: 1,
    bars: sessions.flatMap(s => Array.from({length: 78}, (_, k) => ({
      t: s.open + k * BAR, end: s.open + (k + 1) * BAR,
      availableAt: s.open + (k + 1) * BAR + 1000,
      o: 100, h: 100.1, l: 99.9, c: 100, v: 1000
    })))}];
  const data = {schema: "HARPOON-ULTIMATE-DATA-1", kind: "ALPACA_PROXY", sessions, series,
    splitEvents: [], cashDividends: [], provenance: {execution: "MODELED_OHLCV",
      source: "SYNTHETIC_ENGINEERING_ONLY", feed: "SYNTHETIC_FIXTURE",
      files: [{name: "fixture", sha256: "0".repeat(64)}]}};
  const p = {...C.defaultProtocol("ALPACA_PROXY"), universe: ["SYNA"],
    costs: {spreadBps: 2, slippageBps: 2, perSideUsd: .005}};
  const at = sessions[0].open + 60 * 60000 + 1000;
  const signal = {id: "M11_NATIVE_CAMPAIGN", symbol: "SYNA", hypothesis: "CLOSED_CHANNEL",
    direction: 1, at, index: 0, plannedEntryAt: R.planSignalEntryAt(at, sessions),
    stopDistance: 2, regime: .4,
    metadata: {roadmapHorizonHours: 72, modulation9: {profile: "NATIVE72"}}};
  return {sessions, series, data, p, signal};
}
function setSteps(b, prices) {
  assert.equal(prices.length, 8);
  b.h = Math.max(b.o, ...prices);
  b.l = Math.min(b.o, ...prices);
  b.c = prices.at(-1);
  E.checkGrid(b, prices);
}
function campaign(f) {
  return R.replayCampaign(f.signal, f.series[0], f.data, f.p, "BASELINE", 8, 1,
    {cashDividends: true, profit8Trace: true, researchModulation: true});
}
const costs = {friction: .0003, perSideUsd: .005, tick: .01};

test("M11 phase1: full native campaign TP then STOP, same clocks, cash and inventory", () => {
  const f = fixture();
  const first = f.series[0].bars.find(b => b.t === f.signal.plannedEntryAt);
  const next = f.series[0].bars[f.series[0].bars.indexOf(first) + 1];
  const p1 = [100.2, 102.1, 103.5, 103.1, 102.8, 102.6, 102.2, 102];
  const p2 = [101.8, 101.2, 99.9, 97.5, 98, 98.6, 98.9, 99];
  setSteps(first, p1);
  next.o = first.c;
  setSteps(next, p2);
  const t = campaign(f);
  const exits = t.inventoryEvents.filter(e => e.kind === "EXIT");
  assert.equal(exits.length, 2);
  assert.deepEqual(exits.map(x => -x.quantityDelta), [2, 6]);
  assert.deepEqual(exits.map(x => x.reason), ["TP1", "STOP"]);
  assert.deepEqual(exits.map(x => x.knownAt), [first.availableAt, next.availableAt]);
  assert.deepEqual(exits.map(x => x.at), [first.end, next.end]);
  near(t.entry, 100.03);
  const pos1 = {entry: t.entry, quantity: 8, stop: t.entry - 2, distance: 2,
    targetsR: [1.5, 3]};
  const a = E.nativeBarExits(first, p1, pos1, costs);
  const b = E.nativeBarExits(next, p2, {...pos1, quantity: 6, targetsR: [null, null]}, costs);
  const nativeFills = [...a.fills, ...b.fills];
  assert.deepEqual(nativeFills.map(x => x.quantity), exits.map(x => -x.quantityDelta));
  assert.deepEqual(nativeFills.map(x => x.fillPrice), exits.map(x => x.filledPrice));
  const subA = E.substepBarExits(first, p1, pos1, costs);
  const subB = E.substepBarExits(next, p2, {...pos1, quantity: subA.remainingQuantity,
    targetsR: [null, null]}, costs);
  assert.deepEqual([subA.fills[0].reason, subB.fills[0].reason], ["TP1", "STOP"]);
  // Counterfactual uses identical staged shares but realized first-cross prices.
  const nativeCash = E.incrementalCashLedger(pos1, nativeFills, costs);
  const subCash = E.incrementalCashLedger(pos1, [...subA.fills, ...subB.fills], costs);
  assert.equal(nativeCash.inventory, 0);
  assert.equal(subCash.inventory, 0);
  near(t.netUsd, nativeCash.markedPnlUsd);
  assert(subCash.markedPnlUsd !== nativeCash.markedPnlUsd);
  near(nativeCash.markedPnlUsd, -6.34);
  near(subCash.markedPnlUsd, -8.58);
  assert(t.closed <= t.holdingDeadlineAt);
  assert(t.chronology.terminalKnownAt >= next.availableAt);
});

test("M11 phase1: reservation observations remain committed at each native clock", () => {
  const cap = {equity: 20000, cashAvailableUsd: 20000, riskFraction: .0025,
    openRiskFraction: .0025, grossFraction: .12, assetFraction: .12};
  const proposal = {id: "M11_IOC", symbol: "SYNA", decisionAt: 1000,
    quantity: 8, riskUsd: 16, notionalUsd: 800, cashUsd: 800.04};
  const reserved = RES.reserveFundedEntry(RES.emptyFundedReservationBook(), proposal, cap);
  assert.equal(reserved.status, "RESERVED");
  const opened = RES.recordFundedReservationObservation(reserved.book, {
    id: proposal.id, kind: "OPENED", at: 1299, knownAt: 1300,
    remainingQuantity: 6, pendingQuantity: 0});
  for (const clock of [1000, 1299, 1300, 1301]) {
    const snap = RES.snapshotFundedReservations(opened, clock);
    near(snap.notionalUsd, 800);
    near(snap.riskUsd, 16);
    assert(snap.notionalUsd <= cap.grossFraction * cap.equity);
  }
  const closed = RES.recordFundedReservationObservation(opened, {
    id: proposal.id, kind: "CLOSED", at: 1600, knownAt: 1601,
    remainingQuantity: 0, pendingQuantity: 0});
  assert.equal(RES.snapshotFundedReservations(closed, 1600).pending, 0);
  near(RES.snapshotFundedReservations(closed, 1600).notionalUsd, 800);
  near(RES.snapshotFundedReservations(closed, 1601).notionalUsd, 0);
});

test("M11 phase1: actual funded native IOC and reservation ledger agree at every event", () => {
  const f = fixture();
  const result = R.replayFundedPortfolio([f.signal], f.data, f.p,
    [{test: f.sessions, selected: "ALL:BASELINE"}], f.sessions, R.PROFIT8_REPLAY_LIMITS,
    {continuous: true, cashDividends: true, entryExecution: "IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd: 0, calendarCostPerDayUsd: 1,
      profit8: {mode: "NATIVE_MAX"}, researchModulation: true});
  const state = result.states[0];
  assert.equal(state.status, "MODELED_CAMPAIGN");
  assert.equal(state.reservationStatus, "RESERVED");
  assert.equal(state.fillBudgetReceipt.status, "VERIFIED");
  assert.equal(result.reservationBook.reservations.length, 1);
  const r = result.reservationBook.reservations[0];
  assert.equal(r.decisionAt, f.signal.at);
  assert.deepEqual(r.observations.map(x => x.kind), ["OPENED", "CLOSED"]);
  const reserve = state.profit8CommittedReservation;
  assert.equal(reserve.quantity, state.quantity);
  assert(reserve.notionalUsd <= state.equity * .12 + 1e-8);
  assert(reserve.riskUsd <= state.equity * .0025 + 1e-8);
  assert(reserve.cashUsd <= state.cashPoolUsd);
  assert.equal(state.reference.sourceAvailableAt <= f.signal.at, true);
  assert.equal(state.iocPlan.decisionAt, f.signal.at);
  assert.equal(state.iocPlan.plannedEntryAt, f.signal.plannedEntryAt);
  assert(state.fillBudgetReceipt.actualEntryNotionalUsd <= reserve.notionalUsd + 1e-8);
  assert.equal(result.funded.length, 1);
  const closed = result.funded[0];
  assert.equal(closed.quantity, state.quantity);
  assert.equal(closed.opened, state.modeledOpenedAt);
  assert(closed.closed <= closed.holdingDeadlineAt);
  for (const observation of r.observations) {
    assert(observation.knownAt >= observation.at);
    const prev = RES.snapshotFundedReservations(result.reservationBook, observation.knownAt - 1);
    near(prev.notionalUsd, reserve.notionalUsd);
    const after = RES.snapshotFundedReservations(result.reservationBook, observation.knownAt);
    if (observation.kind === "CLOSED") near(after.notionalUsd, 0);
    else near(after.notionalUsd, reserve.notionalUsd);
  }
  const beforeEntry = RES.snapshotFundedReservations(result.reservationBook, f.signal.at);
  near(beforeEntry.notionalUsd, reserve.notionalUsd);
  const afterClose = RES.snapshotFundedReservations(result.reservationBook, state.modeledCloseKnownAt);
  near(afterClose.notionalUsd, 0);
  assert(result.accounting);
  assert(result.profit8RiskEventSummary.commitmentObservations >= 1);
  // The native summary is observable only at receipt/valuation events, not at each substep.
  assert.equal(result.profit8RiskEventSummary.scope.includes("ADMISSION_CAPS_UNCHANGED"), true);
});
