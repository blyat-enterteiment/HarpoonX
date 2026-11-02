"use strict";
// Synthetic accounting/execution contracts only. No fitted model or financial trial.
const test = require("node:test"), assert = require("node:assert/strict"), path = require("node:path");
const runtime = process.env.HARPOON_HISTORICAL_TEST_RUNTIME || path.join(__dirname, "../runtime30");
const R = require(path.join(runtime, "ultimate_replay.js"));
const C = require(path.join(runtime, "ultimate_contracts.js"));
const B = require(path.join(runtime, "ultimate_reservations.js"));
const BAR = 300000, DAY = 86400000;
function fixture(count = 1, days = 8) {
  const sessions = Array.from({length: days}, (_, i) => {
    const open = Date.UTC(2025, 0, 1, 14, 30) + i * DAY;
    return {date: new Date(open).toISOString().slice(0, 10), open, close: open + 78 * BAR};
  });
  const series = Array.from({length: count}, (_, i) => ({symbol: "ASSET" + i, root: "ASSET" + i,
    pointValue: 1, tick: .01, bars: sessions.flatMap(s => Array.from({length: 78}, (_, j) => ({
      t: s.open + j * BAR, end: s.open + (j + 1) * BAR, availableAt: s.open + (j + 1) * BAR + 1000,
      o: 100, h: 100.1, l: 99.9, c: 100, v: 1000})))}));
  const protocol = {...C.defaultProtocol("ALPACA_PROXY"), universe: series.map(s => s.symbol), purgeHours: 0,
    costs: {spreadBps: 0, slippageBps: 0, perSideUsd: 0}};
  const data = {schema: "HARPOON-ULTIMATE-DATA-1", kind: "ALPACA_PROXY", sessions, series, splitEvents: []};
  const signal = (i, day = 0, changes = {}) => {
    const at = sessions[day].open + 2 * BAR + 1000;
    const s = {id: `S${i}:${day}`, symbol: series[i].symbol, hypothesis: "OPENING_BREAKOUT", direction: 1,
      at, index: 0, stopDistance: 2, regime: .4, ...changes};
    s.plannedEntryAt ??= R.planSignalEntryAt(s.at, sessions);
    return s;
  };
  return {sessions, series, protocol, data, signal, signals: [signal(0)],
    folds: [{test: sessions, selected: "ALL:BASELINE"}]};
}
function run(f, options = {}) {
  return R.replayFundedPortfolio(f.signals, f.data, f.protocol, f.folds, f.sessions,
    R.DEFAULT_REPLAY_LIMITS, options);
}
function flatPrice(bar, price) { Object.assign(bar, {o: price, h: price + .1, l: price - .1, c: price}); }
function dividend(f, changes = {}) {
  return {id: "DIV1", symbol: f.series[0].symbol, exAt: f.sessions[1].open,
    payableAt: f.sessions[4].close, amountPerShare: 1, ...changes};
}
function closeEnough(actual, expected) { assert(Math.abs(actual - expected) < 1e-8, `${actual} != ${expected}`); }

test("legacy replay without options is byte-equivalent to the frozen control", {
  skip: !process.env.HARPOON_LEGACY_RUNTIME,
}, () => {
  const old = require(path.join(process.env.HARPOON_LEGACY_RUNTIME, "ultimate_replay.js"));
  const f = fixture(2); f.folds[0].selected = "OPENING_BREAKOUT:BASELINE";
  f.signals = [f.signal(0), f.signal(1), f.signal(0, 1)];
  flatPrice(f.series[0].bars.find(b => b.t === f.sessions[0].close - BAR), 101);
  const args = [f.signals, f.data, f.protocol, f.folds, f.sessions];
  assert.equal(JSON.stringify(R.replayFundedPortfolio(...args)), JSON.stringify(old.replayFundedPortfolio(...args)));
  assert.equal(JSON.stringify(R.replayCampaign(f.signals[0], f.series[0], f.data, f.protocol, "BASELINE")),
    JSON.stringify(old.replayCampaign(f.signals[0], f.series[0], f.data, f.protocol, "BASELINE")));
  assert.equal(JSON.stringify(R.opportunities(f.data, f.protocol)), JSON.stringify(old.opportunities(f.data, f.protocol)));
});

test("ALL:BASELINE admits all fixed native hypotheses only under explicit options", () => {
  const f = fixture(3);
  f.signals = [f.signal(0), f.signal(1, 0, {hypothesis: "CLOSED_CHANNEL"}),
    f.signal(2, 0, {hypothesis: "VWAP_REVERSION"})];
  const out = run(f);
  assert.equal(out.funded.length, 3);
  assert.deepEqual(out.funded.map(t => t.hypothesis), C.HYPOTHESES.slice().sort((a, b) =>
    f.signals.findIndex(s => s.hypothesis === a) - f.signals.findIndex(s => s.hypothesis === b)));
  assert(out.funded.every(t => t.policy === "BASELINE"));
  assert.throws(() => R.replayFundedPortfolio(f.signals, f.data, f.protocol, f.folds, f.sessions),
    /frozen policy selection/);
});

test("continuous mode preserves a position and capital across adjacent fold boundaries", () => {
  const f = fixture(2, 9); f.protocol.purgeHours = 72;
  f.signals = [f.signal(0, 1, {hypothesis: "CLOSED_CHANNEL"}), f.signal(1, 2), f.signal(1, 8)];
  f.folds = [{test: f.sessions.slice(0, 2), selected: "ALL:BASELINE"},
    {test: f.sessions.slice(2), selected: "ALL:BASELINE"}];
  const out = run(f, {continuous: true, externalCostPerSessionUsd: 2});
  assert.equal(out.funded.length, 2);
  assert.equal(out.states[1].reservationBefore.opened, 1);
  assert.equal(out.states[1].equity, 20000 - 6);
  assert.equal(out.portfolio.skipped.GLOBAL_TERMINAL_ENTRY_CUTOFF, 1);
  assert.equal(out.curve[2].equity_start_usd, out.curve[1].equity_end_usd);
  closeEnough(out.curve.reduce((e, row) => e * (1 + row.portfolio_return), 20000), out.curve.at(-1).equity_end_usd);
  assert.equal(out.accounting.modeledExternalCostsUsd, 18);
});

test("continuous account cannot drop an intervening evaluation session", () => {
  const f = fixture(); f.sessions = f.sessions.filter((_, i) => i !== 2);
  f.folds = [{test: f.sessions, selected: "ALL:BASELINE"}];
  assert.throws(() => run(f, {continuous: true}), /cannot omit intervening calendar sessions/);
});

test("a missing entire tape session preserves open exposure as an incident", () => {
  const f = fixture(); f.signals[0].hypothesis = "CLOSED_CHANNEL";
  f.series[0].bars = f.series[0].bars.filter(b => b.t < f.sessions[1].open || b.t >= f.sessions[1].close);
  assert.throws(() => run(f, {cashDividends: true}), error => {
    assert.equal(error.code, "UNRESOLVED_HOLDING_EXPOSURE");
    assert.equal(error.details.cause.reason, "MISSING_SESSION_WITH_OPEN_EXPOSURE");
    assert.equal(error.details.economicPnlUsd, null);
    assert.equal(error.details.reservationBook.reservations.length, 1); return true;
  });
});

test("each external session cost debits equity and cash once before sizing, including inactive sessions", () => {
  const f = fixture(); f.signals = [f.signal(0), f.signal(0, 1)];
  const out = run(f, {externalCostPerSessionUsd: 10});
  assert.equal(out.states[0].equity, 19990);
  assert.equal(out.states[0].cashPoolUsd, 19990);
  assert.equal(out.funded[0].quantity, 23);
  assert.equal(out.states[1].equity, 19980);
  assert.equal(out.accounting.modeledExternalCostsUsd, 80);
  assert.equal(out.accounting.netEconomicUsd, -80);
  assert(out.curve.every(row => row.external_costs_usd === 10 && row.modeled_trading_pnl_usd === 0));
  assert.equal(out.curve.at(-1).equity_end_usd, 19920);
  closeEnough(out.accounting.reconciliationResidualUsd, 0);
});

test("missing external costs remain null and cannot become complete economic profitability", () => {
  const f = fixture(), out = run(f);
  assert.equal(out.accounting.modeledExternalCostsUsd, null);
  assert.equal(out.accounting.netEconomicUsd, null);
  assert.equal(out.metadata.externalCostCoverage, "NOT_SUPPLIED");
  assert(out.curve.every(row => row.external_costs_usd === null));
  assert.throws(() => run(f, {externalCostPerSessionUsd: null}), /external session cost/);
  assert.throws(() => run(f, {externalCostPerSessionUsd: -1}), /external session cost/);
});

test("external costs can cause insolvency even with no trades; equity is not clipped", () => {
  const f = fixture(); f.signals = [];
  assert.throws(() => run(f, {externalCostPerSessionUsd: 20001}), error => {
    assert.equal(error.code, "FUNDED_INSOLVENCY");
    assert.equal(error.details.curve[0].equity_end_usd, -1);
    assert.equal(error.details.curve[0].portfolio_return, null);
    assert.equal(error.details.economicPnlUsd, null); return true;
  });
});

test("admission rank only resolves simultaneous competition; missing and denied ids cannot enter", () => {
  const f = fixture();
  const first = f.signal(0, 0, {id: "LOW"}), high = {...first, id: "HIGH"};
  const later = f.signal(0, 1, {id: "LATER"});
  f.signals = [first, high, later, f.signal(0, 2, {id: "MISSING"}), f.signal(0, 3, {id: "DENIED"})];
  const admissions = new Map([["LOW", {allow: true, rank: 1}], ["HIGH", {allow: true, rank: 2}],
    ["LATER", {allow: true, rank: 100000}], ["DENIED", {allow: false, rank: 999999}]]);
  const out = run(f, {admissions});
  assert.deepEqual(out.funded.map(t => t.id), ["HIGH", "LATER"]);
  assert.equal(out.portfolio.skipped.SYMBOL_BUSY, 1);
  assert.equal(out.portfolio.skipped.MODEL_ADMISSION_UNAVAILABLE, 1);
  assert.equal(out.portfolio.skipped.MODEL_ADMISSION_REFUSED, 1);
  assert.equal(out.states[0].admission.rank, 2);
  assert.deepEqual(run(f, {admissions: Object.fromEntries(admissions)}), out);
});

test("a modeled IOC gap produces a zero-exposure resolution, never an unauthorized fill", () => {
  const f = fixture(), first = f.signals[0];
  flatPrice(f.series[0].bars.find(b => b.t === first.plannedEntryAt), 150);
  const out = run(f, {entryExecution: "IOC_LIMIT_TO_APPROVED_BUDGET", externalCostPerSessionUsd: 1});
  assert.equal(out.funded.length, 0); assert.equal(out.modeledNoFills.length, 1);
  assert.equal(out.modeledNoFills[0].modeledTradingPnlUsd, 0);
  assert.equal(out.reservationBook.reservations[0].observations[0].kind, "NO_FILL");
  assert.equal(out.modeledNoFills[0].resolutionAt, first.plannedEntryAt);
  assert.equal(out.accounting.netEconomicUsd, -f.sessions.length);
  assert.equal(B.snapshotFundedReservations(out.reservationBook, first.at).pending, 1);
  assert.equal(B.snapshotFundedReservations(out.reservationBook, first.plannedEntryAt).pending, 0);
});

test("IOC keeps capacity encumbered until resolution and missing opening remains an incident", () => {
  const f = fixture(), first = f.signals[0];
  flatPrice(f.series[0].bars.find(b => b.t === first.plannedEntryAt), 150);
  f.signals.push({...first, id: "PENDING", at: first.at + 1});
  f.signals.push(f.signal(0, 0, {id: "AFTER", at: first.plannedEntryAt + 1}));
  const out = run(f, {entryExecution: "IOC_LIMIT_TO_APPROVED_BUDGET"});
  assert.equal(out.portfolio.skipped.SYMBOL_BUSY, 1);
  assert.equal(out.funded.length, 1); assert.equal(out.funded[0].id, "AFTER");
  const missing = fixture(); missing.series[0].bars = missing.series[0].bars.filter(b => b.t !== missing.signals[0].plannedEntryAt);
  assert.throws(() => run(missing, {entryExecution: "IOC_LIMIT_TO_APPROVED_BUDGET"}), error => {
    assert.equal(error.code, "UNOBSERVED_ENTRY"); assert.equal(error.details.economicPnlUsd, null);
    assert.equal(error.details.reservationBook.reservations[0].observations.length, 0); return true;
  });
});

test("IOC price ceiling is fixed before a future opening and includes rounded stop and commissions", () => {
  const f = fixture(); f.protocol.costs = {spreadBps: 2, slippageBps: 2, perSideUsd: .3};
  f.signals[0].stopDistance = 2.001;
  const options = {entryExecution: "IOC_LIMIT_TO_APPROVED_BUDGET", externalCostPerSessionUsd: 0};
  const a = run(f, options), plan = a.states[0].iocPlan;
  closeEnough(plan.roundedStopDistance, 2.01);
  assert(plan.priceCeiling > 0);
  for (const t of a.funded) assert(t.entry <= plan.priceCeiling + 1e-8);
  flatPrice(f.series[0].bars.find(b => b.t === f.signals[0].plannedEntryAt), 1000);
  const b = run(f, options);
  assert.deepEqual(b.states[0].iocPlan, plan);
  assert.equal(b.funded.length, 0);
  const impossible = R.planFundedIocLimit(f.signals[0], f.series[0], f.protocol,
    {plannedQuantity: 20, riskBudgetUsd: 1, notionalBudgetUsd: 2400, cashBudgetUsd: 20000});
  assert.equal(impossible.status, "REFUSED_BEFORE_ENTRY"); assert.equal(impossible.priceCeiling, null);
});

test("NO_FILL cannot erase an observed position, release early or reopen a resolved reservation", () => {
  const f = fixture(), out = run(f, {entryExecution: "IOC_LIMIT_TO_APPROVED_BUDGET"});
  const record = out.reservationBook.reservations[0];
  const openOnly = {schema: out.reservationBook.schema, reservations: [{...record, observations: record.observations.slice(0, 1)}]};
  assert.throws(() => B.recordFundedReservationObservation(openOnly, {id: record.id, kind: "NO_FILL",
    at: record.observations[0].at, knownAt: record.observations[0].knownAt, remainingQuantity: 0, pendingQuantity: 0}),
    /NO_FILL_AFTER_OBSERVED_OPEN/);
  const pending = {schema: out.reservationBook.schema, reservations: [{...record, observations: []}]};
  const noFill = {id: record.id, kind: "NO_FILL", at: record.decisionAt + 100,
    knownAt: record.decisionAt + 200, remainingQuantity: 0, pendingQuantity: 0};
  const resolved = B.recordFundedReservationObservation(pending, noFill);
  assert.equal(B.snapshotFundedReservations(resolved, noFill.knownAt - 1).pending, 1);
  assert.equal(B.snapshotFundedReservations(resolved, noFill.knownAt).pending, 0);
  assert.deepEqual(B.recordFundedReservationObservation(resolved, noFill), resolved);
  assert.throws(() => B.recordFundedReservationObservation(resolved, {...noFill, kind: "OPENED", remainingQuantity: record.quantity}),
    /EXPOSURE_REPORTED_AFTER_COMPLETE_CLOSE/);
});

test("partial sales before ex date reduce the dividend right; economic label keeps price PnL separate", () => {
  const f = fixture(); const signal = f.signal(0, 0, {hypothesis: "CLOSED_CHANNEL"});
  f.data.cashDividends = [dividend(f)];
  Object.assign(f.series[0].bars.find(b => b.t === f.sessions[0].close - 2 * BAR), {h: 103.1});
  const trade = R.replayCampaign(signal, f.series[0], f.data, f.protocol, "BASELINE", 4, 1, {cashDividends: true});
  assert.equal(trade.quantity, 4); assert.equal(trade.dividendEntitlements[0].quantity, 3);
  assert.equal(trade.netUsd, 3); assert.equal(trade.dividendAccruedUsd, 3);
  assert.equal(trade.dividendPaidUsd, 0); assert.equal(trade.dividendReceivableUsd, 3);
  assert.equal(trade.netEconomicUsd, 6);
  assert.equal(trade.inventoryEvents.reduce((n, e) => n + e.quantityDelta, 0), 0);
});

test("ex-date ordering awards held shares before a same-time sale and excludes same-time purchase", () => {
  const f = fixture(), signal = f.signal(0, 0, {hypothesis: "CLOSED_CHANNEL"});
  const baseline = R.replayCampaign(signal, f.series[0], f.data, f.protocol, "BASELINE", 4);
  f.data.cashDividends = [dividend(f, {exAt: baseline.closed, payableAt: null})];
  const sold = R.replayCampaign(signal, f.series[0], f.data, f.protocol, "BASELINE", 4, 1, {cashDividends: true});
  assert.equal(sold.dividendAccruedUsd, 4);
  f.data.cashDividends[0].exAt = baseline.opened;
  const bought = R.replayCampaign(signal, f.series[0], f.data, f.protocol, "BASELINE", 4, 1, {cashDividends: true});
  assert.equal(bought.dividendAccruedUsd, 0);
});

test("dividend receivable changes equity at ex date, cash only on payment, with no second income", () => {
  const f = fixture(2); f.data.cashDividends = [dividend(f)];
  f.signals = [f.signal(0, 0, {hypothesis: "CLOSED_CHANNEL"}), f.signal(1, 2), f.signal(1, 5)];
  const out = run(f, {cashDividends: true, externalCostPerSessionUsd: 0});
  const right = out.funded[0].quantity;
  assert.equal(out.states[1].dividendAccruedUsd, right);
  assert.equal(out.states[1].dividendReceivableUsd, right);
  assert.equal(out.states[1].cashPoolUsd, 20000);
  assert.equal(out.states[1].equity, 20000 + right);
  assert.equal(out.states[2].cashPoolUsd, 20000 + right);
  assert.equal(out.curve[1].dividend_income_usd, right);
  assert.equal(out.curve[4].dividend_income_usd, 0);
  assert.equal(out.curve[4].dividend_cash_received_usd, right);
  assert.equal(out.accounting.netEconomicUsd, right);
  assert.equal(out.accounting.dividendReceivableUsd, 0);
  closeEnough(out.accounting.reconciliationResidualUsd, 0);
});

test("payment beyond terminal or unknown payment date leaves receivable without spendable cash", () => {
  for (const payableAt of [null, fixture().sessions.at(-1).close + DAY]) {
    const f = fixture(); f.signals = [f.signal(0, 0, {hypothesis: "CLOSED_CHANNEL"})];
    f.data.cashDividends = [dividend(f, {payableAt})];
    const out = run(f, {cashDividends: true, externalCostPerSessionUsd: 0});
    assert.equal(out.accounting.dividendPaidUsd, 0);
    assert.equal(out.accounting.dividendReceivableUsd, out.funded[0].quantity);
    assert.equal(out.accounting.terminalConservativeCashPoolUsd, 20000);
    assert.equal(out.accounting.netEconomicUsd, out.funded[0].quantity);
    assert.equal(B.snapshotFundedReservations(out.reservationBook, f.sessions.at(-1).close).opened, 0);
  }
});

test("future dividend and payment edits cannot change the earlier decision state", () => {
  const f = fixture(2); f.signals = [f.signal(0, 0, {hypothesis: "CLOSED_CHANNEL"}), f.signal(1)];
  f.data.cashDividends = [dividend(f)];
  const opts = {cashDividends: true, externalCostPerSessionUsd: 2};
  const before = run(f, opts).states;
  f.data.cashDividends[0].amountPerShare = 100;
  f.data.cashDividends[0].payableAt = null;
  assert.deepEqual(run(f, opts).states, before);
});

test("prices, explicit trading fees, external costs and dividend income reconcile separately", () => {
  const f = fixture(); f.protocol.costs.perSideUsd = .25;
  f.signals[0].hypothesis = "CLOSED_CHANNEL"; f.data.cashDividends = [dividend(f)];
  const out = run(f, {cashDividends: true, externalCostPerSessionUsd: 3});
  for (const row of out.curve) closeEnough(
    row.modeled_price_pnl_usd - row.modeled_trading_fees_usd + row.dividend_income_usd - row.external_costs_usd,
    row.equity_end_usd - row.equity_start_usd);
  closeEnough(out.accounting.modeledPricePnlUsd - out.accounting.modeledTradingFeesUsd +
    out.accounting.dividendAccruedUsd - out.accounting.modeledExternalCostsUsd, out.accounting.netEconomicUsd);
  assert(out.accounting.modeledTradingFeesUsd > 0);
});

test("malformed dividends cannot be silently interpreted as zero cash flows", () => {
  const f = fixture();
  for (const changes of [{amountPerShare: null}, {amountPerShare: -1}, {payableAt: undefined},
    {payableAt: f.sessions[0].open}, {symbol: "MISSING"}, {exAt: NaN}]) {
    f.data.cashDividends = [dividend(f, changes)];
    assert.throws(() => run(f, {cashDividends: true}), /cash dividend/);
  }
  f.data.cashDividends = [dividend(f), dividend(f)];
  assert.throws(() => run(f, {cashDividends: true}), /cash dividend/);
});

test("window filtering precedes daily fired quota and preserves the full causal prefix", () => {
  const f = fixture(1, 21), last = f.sessions.at(-1);
  for (const b of f.series[0].bars) {
    b.v = b.t >= last.open ? 10000 : 1000;
    if (b.t >= last.open + 30 * BAR) flatPrice(b, 102);
  }
  const unrestricted = R.opportunities(f.data, f.protocol).signals.filter(s => s.hypothesis === "OPENING_BREAKOUT");
  const closing = R.opportunities(f.data, f.protocol, {windows: ["CLOSE90"]}).signals
    .filter(s => s.hypothesis === "OPENING_BREAKOUT");
  assert.equal(unrestricted.length, 1); assert(unrestricted[0].at < last.close - 90 * 60000);
  assert.equal(closing.length, 1); assert(closing[0].at >= last.close - 90 * 60000);
  assert(closing[0].plannedEntryAt < last.close);
  const decision = closing[0].at;
  for (const b of f.series[0].bars) if (b.t > decision) { flatPrice(b, 500); b.v *= 20; }
  assert.deepEqual(R.opportunities(f.data, f.protocol, {windows: ["CLOSE90"]}).signals.filter(s => s.at <= decision), closing);
});

test("OPEN90 and CLOSE90 form a union without resetting the daily quota", () => {
  const f = fixture(1, 21), last = f.sessions.at(-1);
  for (const b of f.series[0].bars) if (b.t >= last.open) {
    b.v = 10000; if (b.t >= last.open + 3 * BAR) flatPrice(b, 102);
  }
  const out = R.opportunities(f.data, f.protocol, {windows: ["OPEN90", "CLOSE90"]});
  const breakout = out.signals.filter(s => s.hypothesis === "OPENING_BREAKOUT");
  assert.equal(breakout.length, 1); assert(breakout[0].at < last.open + 90 * 60000);
  assert.throws(() => R.opportunities(f.data, f.protocol, {windows: ["MIDDAY"]}), /opportunity windows/);
});
