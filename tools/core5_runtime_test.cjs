"use strict";
// SYNTHETIC_ENGINEERING_ONLY: deterministic in-memory fault injection, no external orders.
const test = require("node:test");
const assert = require("node:assert/strict");
const { Coordinator } = require("../runtime30/coordinator.js");
const { protectionSnapshot } = require("../runtime30/exits.js");
const { MemoryStore, FakeBroker, config, signal, prepare } = require("./xxx_fixtures.cjs");

async function ready(t, broker = new FakeBroker()) {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const e = new Coordinator(new MemoryStore(), broker, config());
  await e.initialize(true);
  await e.market.catalog();
  prepare(e, signal());
  await e.entries("equity");
  await e.reconcile();
  return { e, broker, c: e.active()[0] };
}

function nativeParent(e, c) {
  const qty = String(e.position(c.symbol).qty);
  const parent = {
    id: "SYNTHETIC-CORE5-OCO", campaign: c.id, symbol: c.symbol, kind: "protect",
    payload: { symbol: c.symbol, qty, side: "sell", type: "limit", order_class: "oco", limit_price: "110" },
    status: "new", at: Date.now(),
    order: { id: "SYNTHETIC-CORE5-OCO-BROKER", client_order_id: "SYNTHETIC-CORE5-OCO",
      symbol: c.symbol, qty, side: "sell", type: "limit", order_class: "oco",
      filled_qty: "0", filled_avg_price: null, status: "new" },
  };
  const nested = {
    id: "SYNTHETIC-CORE5-STOP-BROKER", client_order_id: "SYNTHETIC-CORE5-STOP",
    symbol: c.symbol, qty, side: "sell", type: "stop", stop_price: "98",
    time_in_force: "gtc", filled_qty: "0", filled_avg_price: null, status: "held",
  };
  e.state.intents.push(parent); c.intents.push(parent.id);
  e.adoptLegs(parent, { ...parent.order, legs: [nested] });
  const child = e.state.intents.find(i => i.parentId === parent.id);
  return { parent, child, nested, qty: Number(qty) };
}

for (const terminal of ["canceled", "expired", "rejected", "replaced"]) {
  test("core5 native leg: delayed nested report cannot revive " + terminal + " protection", async t => {
    const { e, c } = await ready(t);
    const { parent, child, nested, qty } = nativeParent(e, c);
    child.status = terminal; child.order.status = terminal;
    for (const staleStatus of ["held", "new", "accepted", "partially_filled"]) {
      e.adoptLegs(parent, { ...parent.order, legs: [{ ...nested, status: staleStatus }] });
      assert.equal(child.status, terminal, "An unchanged cumulative fill cannot undo a terminal broker observation");
      assert.equal(e.pending(c).some(i => i.id === child.id), false);
      assert.equal(protectionSnapshot(c, e.state.intents, qty, Date.now()).quantityCovered, false);
    }
  });
}

test("core5 native leg: filled stop cannot become pending from equal-fill stale nested state", async t => {
  const { e, c } = await ready(t);
  const { parent, child, nested, qty } = nativeParent(e, c);
  child.status = "filled";
  child.order = { ...child.order, filled_qty: String(qty), filled_avg_price: "98", status: "filled" };
  e.adoptLegs(parent, { ...parent.order, legs: [{ ...nested, filled_qty: String(qty), filled_avg_price: "98", status: "partially_filled" }] });
  assert.equal(child.status, "filled");
  assert.equal(e.pending(c).some(i => i.id === child.id), false);
});

test("core5 native leg: later cumulative fill is preserved after cancellation", async t => {
  const { e, c } = await ready(t);
  const { parent, child, nested } = nativeParent(e, c);
  child.status = "canceled"; child.order.status = "canceled";
  e.adoptLegs(parent, { ...parent.order, legs: [{ ...nested, filled_qty: "1", filled_avg_price: "98", status: "partially_filled" }] });
  assert.equal(child.status, "partially_filled");
  assert.equal(child.order.filled_qty, "1", "A true late fill must remain available for inventory reconciliation");
});

test("core5 native leg: regressed cumulative quantity never overwrites the newer fill", async t => {
  const { e, c } = await ready(t);
  const { parent, child, nested } = nativeParent(e, c);
  child.status = "canceled";
  child.order = { ...child.order, filled_qty: "2", filled_avg_price: "98", status: "canceled" };
  e.adoptLegs(parent, { ...parent.order, legs: [{ ...nested, filled_qty: "1", filled_avg_price: "98", status: "new" }] });
  assert.equal(child.status, "canceled"); assert.equal(child.order.filled_qty, "2");
});

test("core5 native leg: full reconciliation cannot turn a delayed parent snapshot into confirmed protection", async t => {
  const { e, broker, c } = await ready(t);
  const { parent, child, nested, qty } = nativeParent(e, c);
  child.status = "canceled"; child.order.status = "canceled";
  // The parent still carries an older nested child. The individually observed
  // terminal child is no longer part of the broker's open-order collection.
  broker.orders.set(parent.id, { ...parent.order, legs: [{ ...nested, status: "held" }] });
  broker.orders.set(child.id, { ...nested, status: "canceled" });
  await e.reconcile();
  assert.equal(e.reconcileError, "");
  assert.equal(child.status, "canceled");
  assert.equal(e.pending(c).some(i => i.id === child.id), false);
  assert.equal(protectionSnapshot(c, e.state.intents, qty, Date.now()).quantityCovered, false);
});

class PartialBroker extends FakeBroker {
  constructor() { super(); this.cancelImmediate = false; }
  async request(path, method = "GET", body, market = false) {
    if (path === "/v2/orders" && method === "POST" && body.side === "buy") {
      this.calls.push({ path, method, body: structuredClone(body), market });
      const order = { ...body, id: "SYNTHETIC-CORE5-PARTIAL", filled_qty: "3", filled_avg_price: "100", status: "partially_filled" };
      this.orders.set(body.client_order_id, order);
      this.positions.set(body.symbol, { symbol: body.symbol, qty: "3", market_value: "300", avg_entry_price: "100" });
      return structuredClone(order);
    }
    return super.request(path, method, body, market);
  }
}
async function closedPartial(t) {
  const fixture = await ready(t, new PartialBroker());
  fixture.broker.open = false;
  await fixture.e.sessions();
  delete fixture.e.market.quotes.AAPL;
  fixture.entry = fixture.e.pending(fixture.c).find(i => i.kind === "entry");
  return fixture;
}
const cancellations = broker => broker.calls.filter(c => c.method === "DELETE");

test("core5 closed session: cancels remaining partial entry without needing a quote or submitting a sale", async t => {
  const { e, broker, c, entry } = await closedPartial(t);
  await e.manage();
  assert.equal(e.positionEvaluations[c.id].outcome, "MARKET_CLOSED");
  assert.equal(cancellations(broker).length, 1, "Known remaining entry risk must still be cancelable outside the session");
  assert(cancellations(broker)[0].path.endsWith(entry.order.id));
  assert.equal(broker.posts().filter(p => p.body.side === "sell").length, 0);
  assert.equal(c.partialEntryRisk.status, "WAIT_CANCEL");
  assert.equal(e.syncAt, 0, "A cancel request still requires fresh reconciliation");
  assert.equal(e.entryReady(), false);
});

test("core5 closed session: pending cancellation preserves its retry interval and confirmed inventory", async t => {
  const { e, broker, c, entry } = await closedPartial(t);
  await e.manage(); await e.reconcile();
  const cancelAt = entry.cancelAt;
  await e.manage(); await e.manage();
  assert.equal(cancellations(broker).length, 1);
  assert.equal(entry.cancelAt, cancelAt);
  assert.equal(c.partialEntryRisk.status, "WAIT_CANCEL");
  assert.equal(c.partialEntryRisk.heldQty, 3);
  assert.equal(broker.posts().length, 1);
});

test("core5 closed session: confirmed cancellation waits for opening before protecting remaining inventory", async t => {
  const { e, broker, c, entry } = await closedPartial(t);
  broker.cancelImmediate = true;
  await e.manage(); await e.reconcile(); await e.manage();
  assert.equal(entry.status, "canceled");
  assert.equal(c.partialEntryRisk.status, "WAIT_PROTECTION");
  assert.equal(broker.posts().length, 1, "Closed session must not authorize a replacement or liquidation order");
  assert.equal(c.closed, false);
  broker.open = true; await e.sessions(); prepare(e, signal());
  await e.pulse();
  const sales = broker.posts().filter(p => p.body.side === "sell");
  assert.equal(sales.length, 1); assert.equal(sales[0].body.type, "stop");
  assert.equal(Number(sales[0].body.qty), 3);
  assert.equal(c.partialEntryRisk.status, "RESOLVED");
});

test("core5 closed session: fill during cancellation changes remaining protection only after reconciliation", async t => {
  const { e, broker, c, entry } = await closedPartial(t);
  await e.manage();
  broker.orders.get(entry.id).filled_qty = "4";
  broker.orders.get(entry.id).status = "canceled";
  broker.positions.get(c.symbol).qty = "4";
  broker.positions.get(c.symbol).market_value = "400";
  await e.reconcile(); await e.manage();
  assert.equal(c.partialEntryRisk.heldQty, 4);
  assert.equal(c.partialEntryRisk.status, "WAIT_PROTECTION");
  assert.equal(broker.posts().length, 1);
  broker.open = true; await e.sessions(); prepare(e, signal());
  await e.pulse();
  const sales = broker.posts().filter(p => p.body.side === "sell");
  assert.equal(sales.length, 1); assert.equal(Number(sales[0].body.qty), 4);
});

test("core5 closed session: uncertain ownership or stale reconciliation cannot authorize cancel mutations", async t => {
  const { e, broker, c, entry } = await closedPartial(t);
  entry.status = "UNKNOWN";
  await e.manage();
  assert.equal(e.positionEvaluations[c.id].outcome, "OWNERSHIP_UNCERTAIN");
  assert.equal(cancellations(broker).length, 0);
  entry.status = "partially_filled"; e.syncAt = Date.now() - 10001;
  await e.manage();
  assert.equal(e.positionEvaluations[c.id].outcome, "STALE_RECONCILIATION");
  assert.equal(cancellations(broker).length, 0);
});
