"use strict";
// SYNTHETIC operational regression fixtures only. No broker/network requests,
// credentials, execution authority, or trading-performance evidence are used.
const test = require("node:test"),
  assert = require("node:assert/strict");
const { Coordinator } = require("../runtime30/coordinator.js");
const { fills } = require("../runtime30/policy.js");
const { protectionSnapshot } = require("../runtime30/exits.js");
const { MemoryStore, FakeBroker, config, signal, prepare } = require("./xxx_fixtures.cjs");

class OperationalBroker extends FakeBroker {
  constructor() {
    super();
    this.rejectProtection = new Set();
    this.rejectExits = new Set();
    this.holdLimits = new Set();
    this.uncertainExits = new Set();
    this.holdBuys = new Set();
  }
  async request(path, method = "GET", body, market = false) {
    if (path === "/v2/orders" && method === "POST" && body.side === "buy" && this.holdBuys.has(body.symbol)) {
      this.calls.push({ path, method, body: structuredClone(body), market });
      const order = { ...body, id: "entry-held-" + this.orders.size, filled_qty: "0", filled_avg_price: null, status: "new" };
      this.orders.set(order.client_order_id, order);
      return structuredClone(order);
    }
    if (path === "/v2/orders" && method === "POST" && body.side === "sell") {
      const protective = ["stop", "stop_limit", "trailing_stop"].includes(body.type);
      if ((protective && this.rejectProtection.has(body.symbol)) ||
          (!protective && this.rejectExits.has(body.symbol))) {
        this.calls.push({ path, method, body: structuredClone(body), market });
        throw Object.assign(Error("SYNTHETIC_DEFINITIVE_REJECTION:" + body.symbol), { status: 422 });
      }
      if (!protective && this.uncertainExits.has(body.symbol)) {
        this.calls.push({ path, method, body: structuredClone(body), market });
        throw Error("SYNTHETIC_AMBIGUOUS_TIMEOUT:" + body.symbol);
      }
      if (body.type === "limit" && this.holdLimits.has(body.symbol)) {
        this.calls.push({ path, method, body: structuredClone(body), market });
        const order = { ...body, id: "held-" + this.orders.size, filled_qty: "0", filled_avg_price: null, status: "new" };
        this.orders.set(order.client_order_id, order);
        return structuredClone(order);
      }
    }
    return super.request(path, method, body, market);
  }
  fillEntry(id, amount, price) {
    const order = this.orders.get(id);
    assert(order && order.side === "buy");
    const prior = Number(order.filled_qty), qty = Number(order.qty);
    assert(amount > 0 && prior + amount <= qty);
    order.filled_qty = String(prior + amount);
    order.filled_avg_price = String((prior * Number(order.filled_avg_price || 0) + amount * price) / (prior + amount));
    order.status = prior + amount === qty ? "filled" : "partially_filled";
    this.positions.set(order.symbol, { symbol: order.symbol, qty: order.filled_qty, market_value: String(Number(order.filled_qty) * price), avg_entry_price: order.filled_avg_price });
  }
  fill(id, amount, price) {
    const order = this.orders.get(id), position = this.positions.get(order?.symbol);
    assert(order && position, "Partial fill requires an existing fixture order and position");
    assert.equal(order.side, "sell");
    const prior = Number(order.filled_qty), total = Number(order.qty), held = Number(position.qty);
    assert(amount > 0 && prior + amount <= total && amount <= held);
    order.filled_qty = String(prior + amount);
    order.filled_avg_price = String((prior * Number(order.filled_avg_price || 0) + amount * price) / (prior + amount));
    order.status = prior + amount === total ? "filled" : "partially_filled";
    if (held === amount) this.positions.delete(order.symbol);
    else {
      position.qty = String(held - amount);
      position.market_value = String((held - amount) * price);
    }
  }
}

function quote(e, symbol, bid = 100, at = Date.now()) {
  e.market.quotes[symbol] = { bid, ask: bid + 0.01, at, received: at };
}

async function ready(symbols = ["AAPL", "MSFT"], api = new OperationalBroker(), overrides = {}) {
  const store = new MemoryStore(), cfg = { ...config(), ...overrides }, e = new Coordinator(store, api, cfg);
  await e.initialize(true);
  await e.market.catalog();
  for (const symbol of symbols) {
    if (/\d{6}[CP]\d{8}$/.test(symbol)) prepare(e, signal("options", symbol));
    const asset = e.market.assets[symbol];
    assert(asset, "Fixture symbol must exist in the validated catalog");
    const s = signal(asset.book, symbol);
    prepare(e, s);
    const c = {
      id: "operational-" + symbol.replace(/[^A-Z0-9]/g, ""),
      symbol,
      book: asset.book,
      plugin: s.plugin,
      created: Date.now(),
      instrument: structuredClone(asset),
      policy: structuredClone(s.exit),
      risk: 2,
      peak: 100,
      stop: 98,
      closed: false,
      intents: [],
      entryCeiling: 100,
      deadline: Date.now() + 24 * 3600000,
    };
    e.state.campaigns.push(c);
    // Establish controlled inventory through the real submit/journal path.
    // Direct fixture setup intentionally bypasses new-entry allocation policy.
    await e.submit(c, "entry", {
      symbol, qty: "8", side: "buy", type: "limit", limit_price: "100",
      time_in_force: c.book === "crypto" ? "gtc" : "day",
      ...(c.book === "options" ? { position_intent: "buy_to_open" } : {}),
    });
    quote(e, symbol);
  }
  await e.reconcile();
  assert.equal(e.reconcileError, "");
  api.calls.length = 0;
  return { e, api, store, cfg };
}

const sells = (api, symbol) => api.posts().filter((x) => x.body.side === "sell" && (!symbol || x.body.symbol === symbol));
const evaluation = (e, symbol) => {
  const row = e.exitCoverage().positions.find((x) => x.symbol === symbol);
  assert(row, "Every held campaign must have an explicit coverage row: " + symbol);
  return row;
};
const exitsComponent = (e) => e.view().health.components.find((x) => x.id === "exit-decisions");

for (const urgent of ["stop", "flatten", "time", "signal"]) {
  test("first-campaign protection rejection cannot starve later " + urgent + " exit", async () => {
    const { e, api } = await ready(), first = e.active()[0], later = e.active()[1];
    api.rejectProtection.add(first.symbol);
    await e.manage();
    await e.reconcile();
    assert(e.state.intents.some((i) => i.campaign === first.id && i.kind === "protect" && i.status === "rejected"));
    if (urgent === "stop") quote(e, later.symbol, 97);
    if (urgent === "flatten") later.flatten = true;
    if (urgent === "time") later.deadline = Date.now() - 1;
    if (urgent === "signal") later.strategyClose = "SYNTHETIC_STRATEGY_EXIT";
    api.calls.length = 0;
    await e.pulse();
    assert.equal(api.positions.has(later.symbol), false, "Later urgent campaign must close in the bounded pulse");
    assert.equal(sells(api)[0].body.symbol, later.symbol, "Urgent exit must precede routine protection retries");
    assert.equal(sells(api, later.symbol).filter((x) => x.body.type === "market").length, 1);
    assert.equal(e.state.intents.findLast((i) => i.campaign === later.id && i.kind !== "protect").kind, urgent);
    assert(sells(api, first.symbol).length <= 1, "Definitive rejection must not consume all pulse steps");
  });
}

test("rejected first protection does not monopolize routine protection for later campaigns", async () => {
  const { e, api } = await ready(["AAPL", "MSFT", "NVDA"]);
  api.rejectProtection.add("AAPL");
  await e.pulse();
  assert(sells(api, "AAPL").length <= 1, "A rejected campaign gets bounded attempts per pulse");
  for (const symbol of ["MSFT", "NVDA"]) {
    assert.equal(sells(api, symbol).filter((x) => x.body.type === "stop").length, 1);
    assert(e.confirmedProtection(e.active().find((c) => c.symbol === symbol)));
  }
  const coverage = e.exitCoverage();
  assert.equal(coverage.total, 3);
  assert(coverage.positions.every((p) => p.lastAttempt > 0), "Every held campaign is individually observed");
  assert.notEqual(coverage.state, "ALIVE", "Unresolved rejection cannot present complete healthy management");
  assert.notEqual(exitsComponent(e).state, "ALIVE");
});

test("one stale position remains visibly unmonitored while another position completes", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const { e } = await ready();
  await e.pulse();
  const before = evaluation(e, "AAPL").lastCompleted;
  assert(before > 0);
  t.mock.timers.tick(16000);
  await e.sessions();
  quote(e, "MSFT");
  await e.reconcile();
  await e.pulse();
  const stale = evaluation(e, "AAPL"), healthy = evaluation(e, "MSFT");
  assert(stale.lastAttempt > before);
  assert.equal(stale.lastCompleted, before, "A stale quote must not manufacture a completed price-dependent check");
  assert(healthy.lastCompleted > before);
  assert.notEqual(stale.state, "ALIVE");
  assert.equal(healthy.state, "ALIVE");
  assert.notEqual(e.exitCoverage().state, "ALIVE");
  assert.notEqual(exitsComponent(e).state, "ALIVE");
});

test("per-position evaluation failure preserves prior completion and cannot be masked by later success", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const { e } = await ready();
  await e.pulse();
  const prior = evaluation(e, "AAPL").lastCompleted;
  t.mock.timers.tick(1000);
  e.plugins.manageSignal = (c) => { if (c.symbol === "AAPL") throw Error("SYNTHETIC_POSITION_EVALUATION_FAILURE"); };
  await e.pulse();
  const failed = evaluation(e, "AAPL"), healthy = evaluation(e, "MSFT");
  assert(failed.lastAttempt > prior);
  assert.equal(failed.lastCompleted, prior);
  assert.equal(failed.state, "ERROR");
  assert.match(failed.detail, /SYNTHETIC_POSITION_EVALUATION_FAILURE/);
  assert(healthy.lastCompleted > prior);
  assert.equal(exitsComponent(e).state, "ERROR");
});

test("restart never treats persisted position evaluations as current-run monitoring", async () => {
  const { e, api, store, cfg } = await ready();
  await e.pulse();
  assert(e.exitCoverage().positions.every((p) => p.lastCompleted > 0));
  const durable = await store.get(e.key);
  assert(durable.campaigns.every((c) => c.evaluation), "Diagnostics must be durably recorded");
  const restarted = new Coordinator(store, api, cfg);
  await restarted.initialize(true);
  const before = restarted.exitCoverage();
  assert.equal(before.total, 2);
  assert.equal(before.fresh, 0);
  assert(before.positions.every((p) => p.lastCompleted === 0));
  assert.notEqual(exitsComponent(restarted).state, "ALIVE");
  assert.equal(restarted.entryReady(), false);
  for (const c of restarted.active()) quote(restarted, c.symbol);
  await restarted.pulse();
  assert.equal(restarted.exitCoverage().fresh, 2);
  assert.equal(restarted.exitCoverage().state, "ALIVE");
});

test("UNKNOWN exit blocks duplicate submission across pulses and restart without starving another urgent campaign", async () => {
  const { e, api, store, cfg } = await ready();
  for (const c of e.active()) c.flatten = true;
  api.uncertainExits.add("AAPL");
  await e.pulse();
  assert.equal(sells(api, "AAPL").length, 1);
  assert.equal(api.positions.has("MSFT"), false);
  assert.match(e.reconcileError, /UNCERTAIN_ORDER/);
  assert.equal(e.entryReady(), false);
  await e.pulse();
  assert.equal(sells(api, "AAPL").length, 1);
  const restarted = new Coordinator(store, api, cfg);
  await restarted.initialize(true);
  quote(restarted, "AAPL");
  await restarted.pulse();
  assert.equal(sells(api, "AAPL").length, 1, "An unknown order must be reconciled, never replaced blindly");
  assert.equal(restarted.pending().filter((i) => i.symbol === "AAPL" && i.kind === "flatten").length, 1);
  assert.notEqual(exitsComponent(restarted).state, "ALIVE");
});

test("young TP cancellation and partial fill reconcile before one urgent remainder sale", async () => {
  const { e, api } = await ready();
  await e.pulse();
  api.holdLimits.add("MSFT");
  quote(e, "MSFT", 104.5);
  await e.pulse();
  const campaign = e.active().find((c) => c.symbol === "MSFT"),
    tp = e.pending(campaign).find((i) => i.kind === "tp1");
  assert(tp);
  api.cancelImmediate = false;
  quote(e, "MSFT", 97);
  const before = sells(api, "MSFT").length;
  await e.pulse();
  assert(tp.cancelAt);
  assert.equal(sells(api, "MSFT").length, before, "Pending cancellation must not release reserved inventory");
  assert.notEqual(exitsComponent(e).state, "ALIVE");
  api.fill(tp.id, 1, 104.5);
  api.orders.get(tp.id).status = "canceled";
  await e.reconcile();
  const held = Number(e.position("MSFT").qty), start = api.calls.length;
  api.cancelImmediate = true;
  api.holdLimits.clear();
  await e.pulse();
  const close = api.calls.slice(start).filter((x) => x.method === "POST" && x.body.symbol === "MSFT" && x.body.type === "market");
  assert.equal(close.length, 1);
  assert.equal(Number(close[0].body.qty), held);
  assert.equal(api.positions.has("MSFT"), false);
  assert.equal(fills(campaign, e.state.intents).sold, 8);
});

test("pause and disabled plugins preserve per-campaign urgent exits", async () => {
  const { e, api } = await ready();
  await e.control("pause");
  await e.control("plugins", { enabled: [] });
  quote(e, "AAPL", 97);
  quote(e, "MSFT", 97);
  await e.pulse();
  assert.equal(e.state.paused, true);
  assert.equal(api.positions.size, 0);
  assert.equal(sells(api).filter((x) => x.body.type === "market").length, 2);
  assert.equal(api.posts().filter((x) => x.body.side === "buy").length, 0);
});

test("tick-scale protection drift remains visible and prevents risk expansion until reconciled", async () => {
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  const c = e.active()[0], p = e.pending(c).find((i) => i.kind === "protect");
  c.stop = Number(p.payload.stop_price) + c.instrument.tick;
  c.protectionChangedAt = Date.now() - 6000;
  assert.equal(protectionSnapshot(c, e.state.intents, 8, Date.now()).aligned, false);
  prepare(e, signal("equity", "MSFT"));
  const buys = api.posts().filter((x) => x.body.side === "buy").length;
  await e.entries("equity");
  assert.equal(api.posts().filter((x) => x.body.side === "buy").length, buys);
  await e.pulse();
  assert.equal(protectionSnapshot(c, e.state.intents, 8, Date.now()).aligned, true);
  assert.equal(Number(e.pending(c).find((i) => i.kind === "protect").payload.stop_price), c.stop);
});

test("definitive rejection retry is bounded, persisted, capped and recovered after broker acceptance", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const env = await ready();
  let e = env.e;
  const { api, store, cfg } = env;
  const id = e.active().find((c) => c.symbol === "AAPL").id;
  e.active().find((c) => c.id === id).flatten = true;
  api.rejectExits.add("AAPL");
  await e.pulse();
  let campaign = e.active().find((c) => c.id === id), retry = campaign.orderRetry.urgent;
  assert.equal(retry.failures, 1);
  assert.equal(retry.nextAt - retry.lastAt, 2000);
  assert.equal(sells(api, "AAPL").length, 1);
  assert(e.confirmedProtection(e.active().find((c) => c.symbol === "MSFT")), "Another campaign continues to be protected during urgent rejection backoff");
  const saved = (await store.get(e.key)).campaigns.find((c) => c.id === id).orderRetry.urgent;
  assert.deepEqual(saved, retry);
  e = new Coordinator(store, api, cfg);
  await e.initialize(true);
  for (const c of e.active()) quote(e, c.symbol);
  await e.pulse();
  assert.equal(sells(api, "AAPL").length, 1, "Restart must preserve the rejection cooldown");
  campaign = e.active().find((c) => c.id === id);
  let previousDelay = 0;
  for (let failures = 2; failures <= 8; failures++) {
    retry = campaign.orderRetry.urgent;
    t.mock.timers.tick(retry.nextAt - Date.now() - 1);
    await e.sessions();
    for (const c of e.active()) quote(e, c.symbol);
    await e.reconcile();
    await e.pulse();
    assert.equal(sells(api, "AAPL").length, failures - 1, "No retry before its durable deadline");
    t.mock.timers.tick(1);
    await e.pulse();
    retry = campaign.orderRetry.urgent;
    assert.equal(sells(api, "AAPL").length, failures);
    assert.equal(retry.failures, failures);
    const delay = retry.nextAt - retry.lastAt;
    assert(delay >= previousDelay && delay <= 60000 && delay > 0, "Backoff must increase monotonically with a finite one-minute cap");
    previousDelay = delay;
  }
  assert.equal(previousDelay, 60000);
  api.rejectExits.delete("AAPL");
  t.mock.timers.tick(campaign.orderRetry.urgent.nextAt - Date.now());
  await e.sessions();
  for (const c of e.active()) quote(e, c.symbol);
  await e.reconcile();
  await e.pulse();
  assert.equal(api.positions.has("AAPL"), false);
  assert.equal(campaign.orderRetry?.urgent, undefined);
  assert.equal(e.reconcileError, "");
});

test("a protection rejection cooldown never delays a new urgent exit in that campaign", async () => {
  const { e, api } = await ready(["AAPL"]);
  api.rejectProtection.add("AAPL");
  await e.pulse();
  const campaign = e.active()[0];
  assert(campaign.orderRetry.protect.nextAt > Date.now());
  campaign.flatten = true;
  await e.pulse();
  assert.equal(api.positions.has("AAPL"), false);
  assert.equal(sells(api).filter((p) => p.body.type === "market").length, 1);
});

test("stale global reconciliation records attempts without completing checks or mutating broker state", async () => {
  const { e, api } = await ready();
  e.syncAt = Date.now() - 10001;
  await e.manage();
  const coverage = e.exitCoverage();
  assert.equal(sells(api).length, 0);
  assert.equal(coverage.completed, 0);
  assert(coverage.positions.every((p) => p.lastAttempt > 0 && p.lastCompleted === 0));
  assert(coverage.positions.every((p) => p.outcome === "STALE_RECONCILIATION"));
  assert.notEqual(exitsComponent(e).state, "ALIVE");
  assert.equal(e.entryReady(), false);
});

test("closed equity sessions stay visibly incomplete while crypto urgent exits remain active", async () => {
  const { e, api } = await ready(["AAPL", "BTC/USD"]);
  e.clock.is_open = false;
  e.active().find((c) => c.symbol === "BTC/USD").flatten = true;
  await e.pulse();
  const row = evaluation(e, "AAPL");
  assert.equal(row.outcome, "MARKET_CLOSED");
  assert.equal(row.lastCompleted, 0);
  assert.notEqual(row.state, "ALIVE");
  assert.equal(sells(api, "AAPL").length, 0);
  assert.equal(api.positions.has("BTC/USD"), false);
  assert.equal(e.entryReady(), false);
});

test("stale OPRA data cannot manufacture a completed option check or an executable option close", async () => {
  const symbol = "SPY261218C00600000", { e, api } = await ready(["AAPL", symbol]);
  e.active().find((c) => c.symbol === symbol).flatten = true;
  quote(e, symbol, 100, Date.now() - 16000);
  await e.pulse();
  const row = evaluation(e, symbol);
  assert.equal(row.lastCompleted, 0);
  assert.notEqual(row.state, "ALIVE");
  assert.equal(sells(api, symbol).length, 0, "Option close requires a fresh OPRA quote even for flatten");
  assert(e.confirmedProtection(e.active().find((c) => c.symbol === "AAPL")));
  assert.equal(e.entryReady(), false);
});

test("fresh global reconciliation cannot refresh stale per-position coverage or permit new allocation", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  assert.equal(e.entryReady(), true);
  const previous = evaluation(e, "AAPL").lastCompleted;
  t.mock.timers.tick(e.exitCoverage().deadlineMs + 1);
  await e.reconcile();
  quote(e, "AAPL");
  prepare(e, signal("equity", "MSFT"));
  assert.equal(evaluation(e, "AAPL").lastCompleted, previous);
  assert.equal(e.entryReady(), false);
  await e.entries("equity");
  assert.equal(api.posts().filter((p) => p.body.side === "buy").length, 0);
  await e.pulse();
  assert.equal(e.entryReady(), true);
  await e.entries("equity");
  assert.equal(api.posts().filter((p) => p.body.side === "buy").length, 1, "A genuinely completed fresh guard pass reopens allocation");
});

test("a remembered TP cannot become a stale-quote market sale after protection cancellation", async () => {
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  quote(e, "AAPL", 104.5);
  await e.manage();
  const c = e.active()[0], plan = structuredClone(c.exitPlan);
  assert.equal(plan.kind, "tp1");
  await e.reconcile();
  assert.equal(e.pending(c).length, 0);
  quote(e, "AAPL", 104.5, Date.now() - 16000);
  const before = sells(api).length;
  await e.pulse();
  assert.equal(sells(api).length, before, "No price-dependent TP may be submitted without fresh observed bid");
  assert.equal(c.exitPlan.id, plan.id, "The original TP decision remains durable while waiting for data");
  assert.notEqual(evaluation(e, "AAPL").state, "ALIVE");
  quote(e, "AAPL", 104.5);
  await e.pulse();
  const tp = e.state.intents.find((i) => i.campaign === c.id && i.kind === "tp1");
  assert(tp);
  assert.equal(tp.payload.type, "limit");
  assert(Number(tp.payload.limit_price) >= plan.minimumPrice);
  assert.equal(fills(c, e.state.intents).tpSold, 2);
  assert(e.confirmedProtection(c));
});

test("partial entry waits for confirmed cancellation and reconciles late fills before urgent sale", async () => {
  const api = new OperationalBroker();
  api.holdBuys.add("AAPL");
  const { e } = await ready(["AAPL", "MSFT"], api);
  const c = e.active().find((x) => x.symbol === "AAPL"),
    entry = e.pending(c).find((i) => i.kind === "entry");
  assert(entry);
  api.fillEntry(entry.id, 3, 100);
  await e.reconcile();
  for (const campaign of e.active()) campaign.flatten = true;
  api.cancelImmediate = false;
  await e.pulse();
  assert(entry.cancelAt);
  assert.equal(sells(api, "AAPL").length, 0, "Pending entry cancellation must not permit a sell against unresolved inventory");
  assert.equal(api.positions.has("MSFT"), false, "Another urgent exit must still complete");
  assert.equal(e.entryReady(), false);
  api.fillEntry(entry.id, 1, 100);
  api.orders.get(entry.id).status = "canceled";
  await e.reconcile();
  assert.equal(Number(e.position("AAPL").qty), 4);
  await e.pulse();
  const close = sells(api, "AAPL").filter((x) => x.body.type === "market");
  assert.equal(close.length, 1, "Urgent inventory close submissions: " + JSON.stringify(close.map((x) => x.body)));
  assert.equal(Number(close[0].body.qty), 4);
  assert.equal(api.positions.has("AAPL"), false);
  assert.equal(fills(c, e.state.intents).bought, 4);
  assert.equal(fills(c, e.state.intents).sold, 4);
  assert.equal(e.reconcileError, "");
});

test("an eight-campaign pulse observes every position before mutation and stops at its work budget", async () => {
  const symbols = ["AAPL", "MSFT", "NVDA", "SPY", "SPXL", "SPXS", "BTC/USD", "ETH/USD"],
    { e, api } = await ready(symbols), request = api.request.bind(api);
  for (const c of e.active()) c.flatten = true;
  let checked = false;
  api.request = async (path, method = "GET", body, market = false) => {
    if (!checked && path === "/v2/orders" && method === "POST") {
      checked = true;
      assert(symbols.every((symbol) => evaluation(e, symbol).lastAttempt > 0), "All campaign observations precede the first broker mutation");
    }
    return request(path, method, body, market);
  };
  await e.pulse();
  assert(checked);
  assert.equal(sells(api).length, 8, "Bounded pulse must issue at most one sell for each of eight urgent campaigns");
  assert.equal(api.positions.size, 0);
  assert.equal(e.syncAt, 0, "The final mutation remains unconfirmed until a subsequent reconciliation");
  assert.notEqual(exitsComponent(e).state, "ALIVE", "Work-budget exhaustion must never certify an unreconciled run");
  await e.pulse();
  assert.equal(sells(api).length, 8);
  assert.equal(e.active().length, 0);
  assert.equal(e.reconcileError, "");
});

test("cancel-pending native protection still reserves inventory at the final submit guard", async () => {
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  const c = e.active()[0], protect = e.pending(c).find((i) => i.kind === "protect");
  api.cancelImmediate = false;
  await e.cancel(protect);
  await e.reconcile();
  const count = api.posts().length;
  await assert.rejects(e.submit(c, "stop", e.payload(c, "stop", 8, e.market.quotes.AAPL)), /reserved|reservation|inventory|oversell/i);
  assert.equal(api.posts().length, count, "Unsafe sale is refused before any broker POST");
  assert.equal(Number(api.positions.get("AAPL").qty), 8);
});

test("more campaigns than the pulse budget receive fair work across bounded successive pulses", async () => {
  // Deliberately overfill the fixture to stress historical/recovered inventory;
  // production new-entry allocation still retains its validated position limit.
  const symbols = ["AAPL", "MSFT", "NVDA", "SPY", "SPXL", "SPXS", "BTC/USD", "ETH/USD", "SPY261218C00600000", "AAPL261218C00100000"],
    { e, api } = await ready(symbols);
  await e.pulse();
  assert.equal(sells(api).length, 8, "A pulse cannot grow unbounded with campaign count");
  assert(e.exitCoverage().positions.every((p) => p.lastAttempt > 0), "Observation coverage spans even campaigns awaiting a mutation slot");
  assert.equal(e.entryReady(), false);
  await e.pulse();
  assert.equal(sells(api).length, symbols.length);
  for (const symbol of symbols) {
    assert.equal(sells(api, symbol).length, 1);
    assert(e.confirmedProtection(e.active().find((c) => c.symbol === symbol)));
  }
  assert.equal(e.exitCoverage().fresh, symbols.length);
  assert.equal(e.exitCoverage().state, "ALIVE");
});

test("concurrent pulse wakeups coalesce and cannot duplicate urgent exits", async () => {
  const { e, api } = await ready(["AAPL", "MSFT", "NVDA"]);
  for (const c of e.active()) c.flatten = true;
  const jobs = Array.from({ length: 12 }, () => e.pulse());
  assert(jobs.every((job) => job === jobs[0]), "Concurrent wakeups share one bounded pulse");
  await Promise.all(jobs);
  assert.equal(sells(api).length, 3);
  assert.equal(api.positions.size, 0);
  assert.equal(e.active().length, 0);
  assert.equal(e.reconcileError, "");
});

test("standalone held stop is not confirmed protection and cannot unlock new allocation", async () => {
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  const c = e.active()[0], stop = e.pending(c).find((i) => i.kind === "protect");
  api.orders.get(stop.id).status = "held";
  await e.reconcile();
  await e.pulse();
  assert.equal(stop.status, "held");
  assert.equal(e.confirmedProtection(c), false);
  assert.equal(protectionSnapshot(c, e.state.intents, 8, Date.now()).aligned, false);
  assert.notEqual(e.exitCoverage().state, "ALIVE");
  prepare(e, signal("equity", "MSFT"));
  await e.entries("equity");
  assert.equal(api.posts().filter((p) => p.body.side === "buy").length, 0);
});

test("held OCO stop leg requires its same-campaign live uncanceled OCO parent", async () => {
  const { e } = await ready(["AAPL"]), c = e.active()[0];
  const parent = {
    id: "SYNTHETIC-OCO-PARENT", campaign: c.id, symbol: c.symbol, kind: "protect",
    payload: { side: "sell", type: "limit", order_class: "oco", qty: "8" },
    status: "new", at: Date.now(),
    order: { id: "SYNTHETIC-BROKER-PARENT", qty: "8", filled_qty: "0", type: "limit" },
  }, child = {
    id: "SYNTHETIC-OCO-STOP", parentId: parent.id, campaign: c.id, symbol: c.symbol, kind: "protect",
    payload: { side: "sell", type: "stop", qty: "8", stop_price: "98" },
    status: "held", at: Date.now(),
    order: { id: "SYNTHETIC-BROKER-CHILD", qty: "8", filled_qty: "0", type: "stop", stop_price: "98" },
  };
  for (const status of ["new", "accepted", "partially_filled"])
    assert.equal(protectionSnapshot(c, [{ ...parent, status }, child], 8, Date.now()).aligned, true);
  for (const invalid of [
    [],
    [{ ...parent, status: "held" }],
    [{ ...parent, status: "pending_cancel" }],
    [{ ...parent, status: "canceled" }],
    [{ ...parent, cancelAt: Date.now() }],
    [{ ...parent, campaign: "ANOTHER-CAMPAIGN" }],
    [{ ...parent, payload: { ...parent.payload, order_class: "simple" } }],
  ])
    assert.equal(protectionSnapshot(c, [...invalid, child], 8, Date.now()).quantityCovered, false);
});

class OcoRunnerBroker extends OperationalBroker {
  constructor() {
    super();
    this.rejectRunner = true;
  }
  async request(path, method = "GET", body, market = false) {
    if (path === "/v2/orders" && method === "POST" && body.order_class === "oco") {
      this.calls.push({ path, method, body: structuredClone(body), market });
      const order = { ...body, id: "oco-" + this.orders.size, filled_qty: "0", filled_avg_price: null, status: "new" };
      const stop = {
        id: order.id + "-stop", client_order_id: order.client_order_id + "-stop", symbol: order.symbol,
        side: "sell", qty: order.qty, type: "stop", stop_price: body.stop_loss.stop_price,
        time_in_force: "gtc", filled_qty: "0", filled_avg_price: null, status: "held",
      };
      order.legs = [stop];
      this.orders.set(order.client_order_id, order);
      this.orders.set(stop.client_order_id, stop);
      return structuredClone(order);
    }
    if (path === "/v2/orders" && method === "POST" && body.type === "stop" && this.rejectRunner) {
      this.calls.push({ path, method, body: structuredClone(body), market });
      throw Object.assign(Error("SYNTHETIC_RUNNER_ONLY_REJECTION"), { status: 422 });
    }
    return super.request(path, method, body, market);
  }
}

test("accepted OCO siblings cannot clear a rejected runner cooldown across reconciliation and restart", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const api = new OcoRunnerBroker(), env = await ready(["AAPL"], api, { nativeProtection: "oco" });
  let e = env.e;
  await e.pulse();
  let c = e.active()[0];
  const rejected = e.state.intents.find((i) => i.nativeRole === "runner");
  assert.equal(rejected.status, "rejected");
  assert.equal(sells(api).filter((x) => x.body.order_class === "oco").length, 2);
  assert.equal(sells(api).filter((x) => x.body.type === "stop").length, 1);
  assert.equal(c.orderRetry.protect.failures, 1);
  assert.equal(c.orderRetry.protect.lastIntent, rejected.id);
  assert.match(c.orderRetry.protect.requestKey, /runner/);
  const retry = structuredClone(c.orderRetry.protect);
  await e.pulse();
  await e.reconcile();
  await e.pulse();
  assert.equal(sells(api).length, 3, "Accepted TP1/TP2 re-observations cannot reset the runner retry deadline");
  assert.deepEqual(c.orderRetry.protect, retry);
  e = new Coordinator(env.store, api, env.cfg);
  await e.initialize(true);
  quote(e, "AAPL");
  await e.pulse();
  c = e.active()[0];
  assert.deepEqual(c.orderRetry.protect, retry);
  assert.equal(sells(api).length, 3);
  t.mock.timers.tick(retry.nextAt - Date.now());
  api.rejectRunner = false;
  await e.pulse();
  assert.equal(sells(api).filter((x) => x.body.type === "stop").length, 2);
  assert.equal(sells(api).filter((x) => x.body.order_class === "oco").length, 2);
  assert.equal(c.orderRetry.protect, undefined, "A newer accepted retry of the same runner form clears its own cooldown");
  assert(e.confirmedProtection(c));
  assert.equal(e.exitCoverage().state, "ALIVE");
});

test("freshly verified protected closed equity permits independent crypto entry without fake price completion", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T19:59:00Z") });
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  const completed = evaluation(e, "AAPL").lastCompleted;
  t.mock.timers.tick(16000);
  api.open = false;
  await e.sessions();
  await e.reconcile();
  await e.pulse();
  const coverage = e.exitCoverage(), row = evaluation(e, "AAPL");
  assert.equal(row.outcome, "MARKET_CLOSED");
  assert.equal(row.state, "MARKET_CLOSED");
  assert.equal(row.lastCompleted, completed, "A closed-session check must not manufacture a price-dependent completion");
  assert.equal(coverage.completed, 0);
  assert.equal(coverage.fresh, 0);
  assert.equal(coverage.sessionGated, 1);
  assert.notEqual(coverage.state, "ALIVE");
  assert.equal(coverage.entrySafe, true);
  assert.equal(e.entryReady(), true);
  prepare(e, signal("crypto"));
  await e.entries("crypto");
  assert.equal(api.posts().filter((p) => p.body.side === "buy" && p.body.symbol === "BTC/USD").length, 1);
  assert.equal(evaluation(e, "AAPL").lastCompleted, completed);
});

test("stale closed-session clock and reopening transition block crypto allocation until a current evaluation", async (t) => {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T19:59:00Z") });
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  api.open = false;
  await e.sessions();
  await e.pulse();
  assert.equal(e.exitCoverage().entrySafe, true);
  t.mock.timers.tick(45001);
  await e.reconcile();
  await e.pulse();
  assert.equal(evaluation(e, "AAPL").outcome, "STALE_SESSION");
  assert.equal(e.exitCoverage().entrySafe, false);
  prepare(e, signal("crypto"));
  await e.entries("crypto");
  assert.equal(api.posts().filter((p) => p.body.side === "buy").length, 0);
  await e.sessions();
  assert.equal(e.exitCoverage().entrySafe, false, "Refreshing the clock alone cannot replace the missing per-position check");
  await e.pulse();
  assert.equal(e.exitCoverage().entrySafe, true);
  api.open = true;
  await e.sessions();
  assert.equal(e.exitCoverage().entrySafe, false, "A previously closed check cannot authorize entries after the opening transition");
  await e.entries("crypto");
  assert.equal(api.posts().filter((p) => p.body.side === "buy").length, 0);
  quote(e, "AAPL");
  await e.pulse();
  assert.equal(evaluation(e, "AAPL").outcome, "EVALUATED");
  assert.equal(e.exitCoverage().entrySafe, true);
  prepare(e, signal("crypto"));
  await e.entries("crypto");
  assert.equal(api.posts().filter((p) => p.body.side === "buy").length, 1);
});

test("closed-session entry safety still rejects stop drift, cancellation, unresolved exits and retry backoff", async () => {
  const { e, api } = await ready(["AAPL"]);
  await e.pulse();
  api.open = false;
  await e.sessions();
  await e.pulse();
  const c = e.active()[0], stop = e.pending(c).find((i) => i.kind === "protect"),
    desiredStop = c.stop;
  const blocked = (reason) => {
    assert.equal(e.exitCoverage().entrySafe, false, reason);
    assert.equal(e.entryReady(), false, reason);
  };
  assert.equal(e.exitCoverage().entrySafe, true);
  c.stop += c.instrument.tick;
  blocked("Closed markets do not excuse stale native stop alignment");
  c.stop = desiredStop;
  stop.cancelAt = Date.now();
  blocked("A cancel-requested stop is no longer confirmed coverage");
  delete stop.cancelAt;
  for (const status of ["held", "pending_cancel", "UNKNOWN"]) {
    stop.status = status;
    blocked("Closed-session safety rejects protective status " + status);
  }
  stop.status = "new";
  const pendingExit = {
    ...structuredClone(stop), id: "SYNTHETIC-PENDING-CLOSED-EXIT", kind: "tp1",
    payload: { symbol: c.symbol, side: "sell", type: "limit", qty: "1", limit_price: "104", time_in_force: "day" },
    order: { ...structuredClone(stop.order), id: "SYNTHETIC-PENDING-CLOSED-EXIT-BROKER", qty: "1", type: "limit" },
  };
  e.state.intents.push(pendingExit);
  c.intents.push(pendingExit.id);
  blocked("A closed position with unresolved exit inventory cannot authorize expansion");
  e.state.intents.pop();
  c.intents.pop();
  c.orderRetry = { protect: { failures: 1, lastAt: Date.now(), nextAt: Date.now() + 2000,
    lastError: "SYNTHETIC_REJECTION", lastIntent: stop.id, requestKey: "protect::stop:" } };
  blocked("Rejection cooldown remains a risk gate even while the market is closed");
  delete c.orderRetry;
  assert.equal(e.exitCoverage().entrySafe, true);
  assert.equal(evaluation(e, "AAPL").state, "MARKET_CLOSED");
});
