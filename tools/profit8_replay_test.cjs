"use strict";
// SYNTHETIC_ENGINEERING_ONLY. No historical strategy matrix or broker calls.
const test = require("node:test"), assert = require("node:assert/strict");
const R = require("../runtime30/profit8_replay.js");
const legacy = require("../runtime30/ultimate_replay_roadmap9.js");
const C = require("../runtime30/ultimate_contracts.js");
const reservations = require("../runtime30/ultimate_reservations.js");
const bridge = require("./profit8_replay.cjs");
const BAR = 300000, DAY = 86400000;
const near = (actual, expected, tolerance = 1e-8) => assert(Math.abs(actual - expected) <= tolerance,
  `${actual} != ${expected}`);
function fixture(symbols = 1, days = 8, offsets) {
  const sessions = Array.from({ length: days }, (_, i) => {
    const open = Date.UTC(2025, 0, 3, 14, 30) + (offsets?.[i] ?? i) * DAY;
    return { date: new Date(open).toISOString().slice(0, 10), open, close: open + 78 * BAR };
  });
  const series = Array.from({ length: symbols }, (_, i) => ({ symbol: ["AAPL", "MSFT"][i],
    root: ["AAPL", "MSFT"][i], tick: .01, pointValue: 1,
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
  const signal = (i = 0, horizon = 72, day = 0, changes = {}) => {
    const at = sessions[day].open + 3600000 + 1000;
    return { id: `${series[i].symbol}:${horizon}:${day}`, symbol: series[i].symbol,
      hypothesis: "CLOSED_CHANNEL", direction: 1, at, index: 0,
      plannedEntryAt: R.planSignalEntryAt(at, sessions), stopDistance: 2, regime: .4,
      metadata: { roadmapHorizonHours: horizon }, ...changes };
  };
  return { sessions, series, p, data, signal, signals: [signal()],
    folds: [{ test: sessions, selected: "ALL:BASELINE" }] };
}
function barAt(f, at, symbol = 0) { return f.series[symbol].bars.find(b => b.t === at); }
function price(bar, px) { Object.assign(bar, { o: px, h: px + .1, l: px - .1, c: px }); }
function options(mode = "NATIVE_MAX") {
  return { continuous: true, cashDividends: true, entryExecution: "IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd: 0, calendarCostPerDayUsd: 1, profit8: { mode } };
}
function run(f, mode = "NATIVE_MAX", limits = R.PROFIT8_REPLAY_LIMITS) {
  return R.replayFundedPortfolio(f.signals, f.data, f.p, f.folds, f.sessions, limits, options(mode));
}
function forecast(signal, mean = [.001, .001], covariance = [[.0001, 0], [0, .0001]],
  meanCovariance = [[0, 0], [0, 0]]) {
  signal.metadata.profit8Forecast = { basis_order: ["E", "T"], mean, covariance,
    mean_covariance: meanCovariance, normalizer_price: 100,
    trained_through: signal.at - DAY, available_at: signal.at, model_id: "SYNTHETIC_FIXED_MODEL" };
  return signal;
}

test("disabled new options preserve the frozen replay byte for byte", () => {
  const f = fixture(2), s = f.signal();
  // Keep the no-IOC legacy fixture within its original ex-ante budgets.
  f.signals[0].stopDistance = 3;
  const baseOptions = { continuous: true, cashDividends: true,
    entryExecution: "IOC_LIMIT_TO_APPROVED_BUDGET", externalCostPerSessionUsd: 0, calendarCostPerDayUsd: 1 };
  const args = [f.signals, f.data, f.p, f.folds, f.sessions, legacy.DEFAULT_REPLAY_LIMITS, baseOptions];
  assert.equal(JSON.stringify(R.replayFundedPortfolio(...args)), JSON.stringify(legacy.replayFundedPortfolio(...args)));
  const campaignArgs = [s, f.series[0], f.data, f.p, "BASELINE", 5, 1];
  assert.equal(JSON.stringify(R.replayCampaign(...campaignArgs)), JSON.stringify(legacy.replayCampaign(...campaignArgs)));
  assert.equal(JSON.stringify(R.replayCampaign(...campaignArgs, { cashDividends: true })),
    JSON.stringify(legacy.replayCampaign(...campaignArgs, { cashDividends: true })));
  assert.equal(JSON.stringify(R.opportunities(f.data, f.p)), JSON.stringify(legacy.opportunities(f.data, f.p)));
  const oldFolds = [{ test: f.sessions, selected: "CLOSED_CHANNEL:BASELINE" }];
  const noOptionArgs = [f.signals, f.data, f.p, oldFolds, f.sessions];
  assert.equal(JSON.stringify(R.replayFundedPortfolio(...noOptionArgs)), JSON.stringify(legacy.replayFundedPortfolio(...noOptionArgs)));
});

for (const horizon of [24, 72]) for (const path of ["TIME", "ONE_TARGET", "TWO_TARGETS", "STOP", "TRAIL", "GAP_STOP", "DIVIDEND_AFTER_PARTIAL"])
  test(`two teacher bases reproduce quantities 1..12: ${path}, ${horizon}h`, () => {
    const f = fixture(), s = f.signal(0, horizon), first = s.plannedEntryAt;
    if (["ONE_TARGET", "TWO_TARGETS", "DIVIDEND_AFTER_PARTIAL"].includes(path))
      barAt(f, first + BAR).h = path === "TWO_TARGETS" ? 106.1 : 103.1;
    if (path === "STOP") barAt(f, first + BAR).l = 97;
    if (path === "TRAIL") {
      Object.assign(barAt(f, first + BAR), { h: 106.2, c: 106.1 });
      Object.assign(barAt(f, first + 2 * BAR), { o: 106, h: 106.1, l: 103, c: 104 });
    }
    if (path === "GAP_STOP") price(barAt(f, f.sessions[1].open), 90);
    if (path === "DIVIDEND_AFTER_PARTIAL") f.data.cashDividends = [{ id: "DIV", symbol: "AAPL",
      exAt: f.sessions[1].open, payableAt: f.sessions[5].close, amountPerShare: 1.25 }];
    const label = R.replayProfit8Teacher(s, f.series[0], f.data, f.p);
    assert.equal(label.status, "OBSERVED_MODELED_PATH");
    const target = barAt(f, label.label_end);
    assert(label.label_known_at >= target.availableAt);
    for (let q = 1; q <= 12; q++) {
      const trade = R.replayCampaign(s, f.series[0], f.data, f.p, "BASELINE", q, 1,
        { cashDividends: true, profit8Trace: true });
      const [a, b] = R.profit8BasisWeights(q);
      near(trade.netEconomicUsd, a * label.E_usd + b * label.T_usd);
      assert.equal(trade.entry, label.entry_price);
      assert.equal(trade.closed, label.policy_closed_at);
      assert.equal(trade.inventoryEvents.at(-1).filledPrice, label.terminal_exit_price);
      assert.equal(trade.holdingDeadlineAt, label.label_end);
    }
    if (path === "DIVIDEND_AFTER_PARTIAL") {
      near(label.quantity1_dividend_usd, 1.25);
      near(label.quantity4_dividend_usd, 3.75);
    }
  });

test("gross deadline and net policy targets share cohort maturity even after early STOP", () => {
  const f = fixture(), s = f.signal(0, 24);
  barAt(f, s.plannedEntryAt).l = 97;
  const holding = R.planCalendarHolding(s, s.plannedEntryAt, f.data, f.p);
  price(barAt(f, holding.deadlineAt), 107);
  const label = R.replayProfit8Teacher(s, f.series[0], f.data, f.p);
  assert(label.T_usd < 0); near(label.gross_deadline_return, .07);
  assert(label.policy_closed_at < label.label_end);
  assert.equal(label.label_known_at, barAt(f, holding.deadlineAt).availableAt);
  assert(label.quantity1_trace.maximum_policy_known_at < label.label_known_at);
});

test("common IOC is independent of quantity and future opening", () => {
  const f = fixture(), s = f.signals[0]; forecast(s);
  const old = run(f, "MAX_POSITIVE"), firstPlan = old.states[0].plan;
  for (const q of [1, 2, 3, 4, old.states[0].quantity]) {
    const ioc = R.planProfit8IocLimit(s, f.series[0], f.p, { plannedQuantity: q,
      riskBudgetUsd: firstPlan.riskBudgetUsd, notionalBudgetUsd: firstPlan.notionalBudgetUsd,
      cashBudgetUsd: firstPlan.cashBudgetUsd });
    near(ioc.priceCeiling, 100.3);
  }
  price(barAt(f, s.plannedEntryAt), 110);
  const changed = run(f, "MAX_POSITIVE");
  assert.deepEqual(changed.states[0].plan, firstPlan);
  assert.deepEqual(changed.states[0].profit8Sizing, old.states[0].profit8Sizing);
  assert.equal(changed.funded.length, 0); assert.equal(changed.modeledNoFills.length, 1);
  const label = R.replayProfit8Teacher(s, f.series[0], f.data, f.p);
  assert.equal(label.status, "MODELED_IOC_NO_FILL"); assert.equal(label.fill, false);
  assert.deepEqual(label.net_basis, [0, 0]); assert.equal(label.gross_deadline_return, 0);
  assert.equal(label.label_known_at, barAt(f, label.label_end).availableAt);
  assert.equal(reservations.snapshotFundedReservations(changed.reservationBook, s.at).pending, 1);
  assert.equal(reservations.snapshotFundedReservations(changed.reservationBook, s.plannedEntryAt).pending, 0);
});

test("missing observations and unmodeled split remain blocked, never zero labels", () => {
  for (const missing of ["ENTRY", "DEADLINE", "INTERMEDIATE", "SPLIT"]) {
    const f = fixture(), s = f.signal();
    const holding = R.planCalendarHolding(s, s.plannedEntryAt, f.data, f.p);
    if (missing === "SPLIT") f.data.splitEvents.push({ symbol: s.symbol, at: f.sessions[1].open, ratio: 2 });
    else {
      const at = missing === "ENTRY" ? s.plannedEntryAt : missing === "DEADLINE" ? holding.deadlineAt : s.plannedEntryAt + BAR;
      f.series[0].bars = f.series[0].bars.filter(b => b.t !== at);
    }
    const label = R.replayProfit8Teacher(s, f.series[0], f.data, f.p);
    assert.equal(label.status, "BLOCKED_UNOBSERVED_PATH", missing);
    assert.equal(label.net_basis, null); assert.equal(label.gross_deadline_return, null);
    assert.equal(label.fill, null);
  }
});

test("H2 selects positive net qMax without a second trading cost hurdle", () => {
  const f = fixture(), s = forecast(f.signals[0], [.000001, .000001]);
  const plan = R.planProfit8FundedEntry(s, f.series[0], f.p, R.PROFIT8_REPLAY_LIMITS,
    { equity: 20000, openRisk: 0, notional: 0, cashBudgetUsd: 20000 });
  const positive = R.selectProfit8Quantity(s, plan.quantity, 20000, 100, "MAX_POSITIVE");
  assert.equal(positive.quantity, plan.quantity); assert(positive.chosen.meanUsd > 0);
  assert(positive.chosen.meanUsd < 2 * plan.quantity * f.p.costs.perSideUsd);
  forecast(s, [-.001, -.001]);
  assert.equal(R.selectProfit8Quantity(s, plan.quantity, 20000, 100, "MAX_POSITIVE").quantity, 0);
});

test("H3 enumerates integer lot discontinuities, can choose q3 and can stay in cash", () => {
  const f = fixture(), s = forecast(f.signals[0], [-.1, .01], [[0, 0], [0, 0]]);
  const chosen = R.selectProfit8Quantity(s, 23, 20000, 100, "ROBUST_LOG");
  assert.equal(chosen.quantity, 3); assert.equal(chosen.candidates.length, 24);
  assert.deepEqual(chosen.candidates[3].basisWeights, [0, 3]);
  assert.deepEqual(chosen.candidates[4].basisWeights, [2, 2]);
  forecast(s, [.001, .001], [[0, 0], [0, 0]], [[.01, 0], [0, .01]]);
  assert.equal(R.selectProfit8Quantity(s, 23, 20000, 100, "ROBUST_LOG").quantity, 0);
  forecast(s, [0, 0], [[0, 0], [0, 0]]);
  assert.equal(R.selectProfit8Quantity(s, 23, 20000, 100, "ROBUST_LOG").quantity, 0);
});

test("H3 objective uses USD variance and expected squared payoff at fixed rho1", () => {
  const f = fixture(), s = forecast(f.signals[0], [.1, .1], [[4, 4], [4, 4]]);
  const out = R.selectProfit8Quantity(s, 23, 20000, 100, "ROBUST_LOG");
  assert.equal(out.quantity, 5);
  const row = out.chosen; near(row.meanUsd, 50); near(row.varianceUsd2, 1000000);
  near(row.utility, 50 / 20000 - .5 * (1000000 + 2500) / (20000 * 20000));
  assert.equal(out.uncertaintyPenalty, 1);
});

test("forecast units, chronology and PSD failures cannot silently trade", () => {
  for (const mutate of [f => { f.normalizer_price = 101; }, f => { f.trained_through += 2 * DAY; },
    f => { f.available_at++; }, f => { f.basis_order.reverse(); },
    f => { f.covariance = [[1, 2], [2, 1]]; }, f => { f.mean_covariance[0][0] = -1; }]) {
    const f = fixture(), s = forecast(f.signals[0]); mutate(s.metadata.profit8Forecast);
    assert.throws(() => R.selectProfit8Quantity(s, 10, 20000, 100, "ROBUST_LOG"), /PROFIT8_/);
  }
});

test("committed worst-price reservations allow sequential allocation without early release", () => {
  const f = fixture(2); f.signals = [f.signal(0), f.signal(1)];
  f.signals.forEach(s => forecast(s, [-.1, .01], [[0, 0], [0, 0]]));
  const out = run(f, "ROBUST_LOG");
  assert.deepEqual(out.funded.map(t => t.quantity), [3, 3]);
  assert.equal(out.states[1].reservationBefore.pending, 1);
  assert(out.states[1].profit8Sizing.qMax < out.states[0].profit8Sizing.qMax);
  for (const state of out.states) {
    const committed = state.profit8CommittedReservation;
    near(committed.notionalUsd, state.quantity * state.iocPlan.priceCeiling);
    near(committed.cashUsd, state.quantity * (state.iocPlan.priceCeiling + f.p.costs.perSideUsd));
    near(committed.riskUsd, state.quantity * state.plan.riskUnit);
    assert(state.reservationAfter.notionalUsd <= state.equity * .12 + 1e-8);
    assert(state.reservationAfter.riskUsd <= state.equity * .0025 + 1e-8);
    assert(state.reservationAfter.cashUsd <= state.cashPoolUsd + 1e-8);
  }
  near(out.accounting.reconciliationResidualUsd, 0);
  near(out.accounting.modeledExternalCostsUsd, 8);
  assert(out.profit8RiskEventSummary.valuationObservations > 0);
  assert.equal(out.profit8RiskEventSummary.commitmentObservations, 2);
  near(out.profit8RiskEventSummary.maximumReservedNotionalUsd, 6 * 100.3);
});

test("terminal admission follows each calendar horizon instead of a blanket72h cutoff", () => {
  const f = fixture(); f.signals = [f.signal(0, 24, 6)];
  const allowed = run(f); assert.equal(allowed.funded.length, 1);
  assert(allowed.funded[0].closed <= f.sessions.at(-1).close);
  f.signals = [f.signal(0, 72, 6)];
  // Calendar coverage failure is an ex-ante refusal, never an invented close.
  const denied = run(f); assert.equal(denied.funded.length, 0);
  assert.equal(denied.preEntryRefusals[0].reason, "CALENDAR_HORIZON_NOT_COVERED");
  const g = fixture(1, 12); g.sessions = g.sessions.slice(0, 8);
  g.folds = [{ test: g.sessions, selected: "ALL:BASELINE" }];
  g.signals = [g.signal(0, 72, 6)];
  const cutoff = run(g); assert.equal(cutoff.funded.length, 0);
  assert.equal(cutoff.preEntryRefusals[0].reason, "TERMINAL_CALENDAR_DEADLINE_CUTOFF");
});

test("common IOC sizing includes rounded stop, cash and modeled fill verification", () => {
  const f = fixture(), s = f.signals[0]; s.stopDistance = 2.001;
  const plan = R.planProfit8FundedEntry(s, f.series[0], f.p, R.PROFIT8_REPLAY_LIMITS,
    { equity: 20000, openRisk: 0, notional: 0, cashBudgetUsd: 250 });
  near(plan.roundedStopDistance, 2.01); assert.equal(plan.quantity, 2);
  assert(plan.quantity * (plan.priceCeiling + f.p.costs.perSideUsd) <= 250);
  const report = run(f); assert.equal(report.funded.length, 1);
  assert.equal(report.states[0].fillBudgetReceipt.status, "VERIFIED");
  assert(report.funded[0].entry <= report.states[0].iocPlan.priceCeiling);
});

test("new branch rejects raised or omitted limits and unregistered clocks and exits", () => {
  const f = fixture();
  assert.throws(() => run(f, "NATIVE_MAX", legacy.DEFAULT_REPLAY_LIMITS), /PROFIT8_LIMITS/);
  assert.throws(() => R.replayFundedPortfolio(f.signals, f.data, f.p, f.folds, f.sessions, undefined, options()), /PROFIT8_LIMITS/);
  for (const change of [s => { s.at++; }, s => { s.metadata.roadmapHorizonHours = 48; },
    s => { s.metadata.roadmapExit = "VALUE_TOTAL"; }, s => { s.metadata.researchExit = "ANY"; }]) {
    const g = fixture(); change(g.signals[0]); assert.throws(() => run(g), /PROFIT8_FIXED_SIGNAL/);
  }
});

test("calendar closure shortens 24h cohort without extending original deadline", () => {
  const f = fixture(1, 8, [0, 3, 4, 5, 6, 7, 10, 11]), s = f.signal(0, 24);
  const label = R.replayProfit8Teacher(s, f.series[0], f.data, f.p);
  near((label.label_end - s.plannedEntryAt) / 3600000, 5.25);
  assert(label.policy_closed_at <= label.label_end);
  assert(label.label_end <= s.at + 24 * 3600000);
});

test("bridge preserves target flags and continuous-account summary with explicit limits", () => {
  const f = fixture(1, 220), s = f.signal(0, 24);
  const protocol = { origin: "HISTORICAL", live_approved: false, universe: ["AAPL"],
    limits: { ...R.PROFIT8_REPLAY_LIMITS }, periods: { evaluation_start: f.sessions[0].date,
      evaluation_end: f.sessions[7].date, validation_start: f.sessions[0].date,
      validation_end: f.sessions[3].date, test_start: f.sessions[4].date, test_end: f.sessions[7].date },
    scenarios: { NOMINAL: { spread_bps: 2, slippage_bps: 2,
      commission_usd_per_share_per_side: .005, external_cost_usd_per_calendar_day: 1 } },
    reporting_windows: { SEEN: { start: f.sessions[0].date, end: f.sessions[3].date } } };
  const labels = bridge.prepareTeachers(protocol, f.data, { signals: [s] }, "NOMINAL");
  assert.equal(labels.labels[0].known_at, labels.labels[0].label_known_at);
  assert.equal(labels.labels[0].status, "OBSERVED_MODELED_PATH");
  const report = bridge.run(protocol, f.data, { signals: { NOMINAL: { CONT_24: [s] } } }, "CONT_24", "NOMINAL");
  assert.equal(report.native_control, "NATIVE_HISTORICAL_ULTIMATE_PROFIT8");
  assert.equal(report.summary.CONTINUOUS.sessions, 8);
  assert.equal(report.descriptive_windows.SEEN.sessions, 4);
  assert.equal(report.accounting.modeledExternalCostsUsd, 8);
  assert.equal(report.summary.TEST.capital_at_phase_start, report.curve[4].equity_start_usd);
  assert.equal(report.financial_acceptance_allowed, false);
});
