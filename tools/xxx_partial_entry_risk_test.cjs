"use strict";
// SYNTHETIC fault-injection only: in-memory broker, no external requests or keys.
const test = require("node:test"), assert = require("node:assert/strict");
const { Coordinator } = require("../runtime30/coordinator.js");
const { assertJournal } = require("../runtime30/validators.js");
const { MemoryStore, FakeBroker, config, signal, prepare } = require("./xxx_fixtures.cjs");

class PartialBroker extends FakeBroker {
  constructor() { super(); this.cancelImmediate = false; this.failOrderSnapshot = false; }
  async request(path, method = "GET", body, market = false) {
    if (path.startsWith("/v2/orders?") && this.failOrderSnapshot)
      throw Error("SYNTHETIC_ORDER_SNAPSHOT_UNAVAILABLE");
    if (path === "/v2/orders" && method === "POST" && body.side === "buy" && body.symbol === "AAPL") {
      this.calls.push({ path, method, body: structuredClone(body), market });
      const order = { ...body, id: "partial-entry-" + this.orders.size, filled_qty: "0", filled_avg_price: null, status: "new" };
      this.orders.set(order.client_order_id, order);
      return structuredClone(order);
    }
    return super.request(path, method, body, market);
  }
  fillEntry(id, amount) {
    const order = this.orders.get(id), prior = Number(order.filled_qty);
    assert(amount > 0 && prior + amount <= Number(order.qty));
    order.filled_qty = String(prior + amount);
    order.filled_avg_price = "100";
    order.status = prior + amount === Number(order.qty) ? "filled" : "partially_filled";
    const held = Number(this.positions.get(order.symbol)?.qty || 0) + amount;
    this.positions.set(order.symbol, { symbol: order.symbol, qty: String(held), market_value: String(held * 100), avg_entry_price: "100" });
  }
}

async function fixture(t, anotherPosition = false, firstFill = 3) {
  t.mock.timers.enable({ apis: ["Date"], now: Date.parse("2026-10-15T15:30:00Z") });
  const store = new MemoryStore(), api = new PartialBroker(), cfg = { ...config(), orderTtlMs: 5000 };
  const e = new Coordinator(store, api, cfg);
  await e.initialize(true);
  await e.market.catalog();
  for (const symbol of anotherPosition ? ["AAPL", "MSFT"] : ["AAPL"]) {
    const s = signal("equity", symbol); prepare(e, s);
    const c = { id: "partial-risk-" + symbol, symbol, book: "equity", plugin: s.plugin,
      created: Date.now(), instrument: structuredClone(e.market.assets[symbol]),
      policy: structuredClone(s.exit), risk: 2, peak: 100, stop: 98, closed: false,
      intents: [], entryCeiling: 100, deadline: Date.now() + 3600000 };
    e.state.campaigns.push(c);
    await e.submit(c, "entry", { symbol, qty: "8", side: "buy", type: "limit", limit_price: "100", time_in_force: "day" });
  }
  const c = e.active().find((x) => x.symbol === "AAPL"), entry = e.pending(c).find((x) => x.kind === "entry");
  api.fillEntry(entry.id, firstFill);
  await e.reconcile();
  await e.pulse();
  return { e, api, store, cfg, c, entry };
}
const riskRow = (e, c) => e.exitCoverage().positions.find((p) => p.campaign === c.id)?.partialEntryRisk;
const riskEvents = (e, kind) => e.state.events.filter((x) => x.kind === kind);
const sells = (api, symbol = "AAPL") => api.posts().filter((x) => x.body.side === "sell" && x.body.symbol === symbol);

test("partial-entry risk: pending cancellation exposes reconciled inventory and a config-based deadline without selling", async (t) => {
  const { e, api, c, entry, cfg } = await fixture(t);
  assert(c.partialEntryRisk, "Partial inventory awaiting cancellation must have durable risk telemetry");
  const risk = riskRow(e, c);
  assert.equal(risk.source, "BROKER_RECONCILIATION");
  assert.equal(risk.status, "WAIT_CANCEL");
  assert.equal(risk.heldQty, 3); assert.equal(risk.coveredQty, 0);
  assert.equal(risk.entryId, entry.id);
  assert.equal(risk.deadlineAt - risk.firstObservedAt, cfg.orderTtlMs);
  assert.equal(risk.overdue, false); assert.equal(risk.observationFresh, true);
  assert.equal(e.entryReady(), false); assert.equal(e.exitCoverage().entrySafe, false);
  assert.match(e.exitCoverage().detail, /PARTIAL_ENTRY_UNPROTECTED/);
  assert.equal(sells(api).length, 0, "No new protective or liquidation order while entry cancellation is unresolved");
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_UNPROTECTED").length, 1);
});

test("partial-entry risk: timeout and cancel retries do not reset the exposure clock or repeat overdue events", async (t) => {
  const { e, api, c, entry, cfg } = await fixture(t);
  assert(c.partialEntryRisk);
  const first = c.partialEntryRisk.firstObservedAt, firstCancel = c.partialEntryRisk.cancelRequestedAt;
  const observation = c.partialEntryRisk.lastObservedAt;
  t.mock.timers.tick(cfg.orderTtlMs / 2);
  await e.manage();
  assert.equal(c.partialEntryRisk.lastObservedAt, observation, "A management pass cannot refresh the broker observation timestamp");
  t.mock.timers.tick(cfg.orderTtlMs / 2);
  assert.equal(riskRow(e, c).overdue, true, "Read-side projection must show a reached deadline before a new sample");
  await e.reconcile(); await e.pulse();
  assert.equal(c.partialEntryRisk.firstObservedAt, first);
  assert.equal(c.partialEntryRisk.cancelRequestedAt, firstCancel);
  assert(entry.cancelAt > firstCancel, "The fixture must actually retry cancellation");
  assert.equal(c.partialEntryRisk.overdue, true);
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_PROTECTION_OVERDUE").length, 1);
  t.mock.timers.tick(cfg.orderTtlMs);
  await e.reconcile(); await e.pulse();
  assert.equal(c.partialEntryRisk.firstObservedAt, first);
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_PROTECTION_OVERDUE").length, 1);
  assert.equal(sells(api).length, 0);
});

test("partial-entry risk: restart preserves deadline and late fills update known inventory without duplicate orders", async (t) => {
  const { e, api, store, cfg, c, entry } = await fixture(t);
  assert(c.partialEntryRisk);
  const first = c.partialEntryRisk.firstObservedAt;
  t.mock.timers.tick(cfg.orderTtlMs + 1);
  await e.reconcile(); await e.pulse(); await e.save();
  const next = new Coordinator(store, api, cfg);
  await next.initialize(true);
  const restored = next.active().find((x) => x.id === c.id);
  assert.equal(restored.partialEntryRisk.firstObservedAt, first);
  assert.equal(restored.partialEntryRisk.deadlineAt, first + cfg.orderTtlMs);
  assert.equal(restored.partialEntryRisk.overdue, true);
  api.fillEntry(entry.id, 2);
  await next.reconcile(); prepare(next, signal("equity", "AAPL")); await next.pulse();
  assert.equal(restored.partialEntryRisk.heldQty, 5);
  assert.equal(restored.partialEntryRisk.coveredQty, 0);
  assert.equal(restored.partialEntryRisk.firstObservedAt, first);
  assert.equal(next.entryReady(), false);
  assert.equal(api.posts().filter((x) => x.body.side === "buy").length, 1);
  assert.equal(sells(api).length, 0);
  assert.equal(riskEvents(next, "PARTIAL_ENTRY_PROTECTION_OVERDUE").length, 1);
});

test("partial-entry risk: stale snapshots, local emptiness and UNKNOWN orders cannot resolve or fabricate a flat position", async (t) => {
  const { e, api, c, entry } = await fixture(t);
  assert(c.partialEntryRisk);
  const observed = c.partialEntryRisk.lastObservedAt;
  e.syncAt = 0; e.positions = [];
  await e.manage();
  assert.equal(riskRow(e, c).status, "UNVERIFIED");
  assert.equal(riskRow(e, c).observationFresh, false);
  assert.equal(c.partialEntryRisk.heldQty, 3, "Retain explicitly last-reconciled inventory when current data is absent");
  assert.equal(c.partialEntryRisk.lastObservedAt, observed);
  assert.equal(c.partialEntryRisk.resolvedAt, undefined);
  await e.reconcile();
  entry.status = "UNKNOWN"; e.positions = []; e.syncAt = Date.now();
  await e.manage();
  assert.equal(riskRow(e, c).status, "UNVERIFIED");
  assert.equal(c.partialEntryRisk.resolvedAt, undefined);
  api.failOrderSnapshot = true;
  await assert.rejects(e.reconcile(), /SYNTHETIC_ORDER_SNAPSHOT_UNAVAILABLE/);
  assert.equal(riskRow(e, c).status, "UNVERIFIED");
  assert.equal(e.entryReady(), false);
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_PROTECTION_RESOLVED").length, 0);
  assert.equal(sells(api).length, 0);
});

test("partial-entry risk: confirmed cancellation alone stays open until broker-confirmed protection covers late fills", async (t) => {
  const { e, api, c, entry } = await fixture(t);
  assert(c.partialEntryRisk);
  api.fillEntry(entry.id, 1);
  api.orders.get(entry.id).status = "canceled";
  await e.reconcile();
  assert.equal(c.partialEntryRisk.status, "WAIT_PROTECTION");
  assert.equal(c.partialEntryRisk.heldQty, 4);
  assert.equal(c.partialEntryRisk.resolvedAt, undefined);
  assert.equal(e.entryReady(), false);
  await e.pulse();
  assert.equal(c.partialEntryRisk.status, "RESOLVED");
  assert.equal(c.partialEntryRisk.resolution, "CONFIRMED_PROTECTION");
  assert.equal(c.partialEntryRisk.heldQty, 4);
  assert.equal(c.partialEntryRisk.coveredQty, 4);
  assert.equal(c.partialEntryRisk.overdue, false);
  assert.equal(sells(api).length, 1);
  assert.equal(sells(api)[0].body.type, "stop");
  assert.equal(Number(sells(api)[0].body.qty), 4);
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_PROTECTION_RESOLVED").length, 1);
  await e.reconcile(); await e.pulse();
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_PROTECTION_RESOLVED").length, 1);
});

test("partial-entry risk: another urgent position progresses and only reconciled terminal inventory resolves the tracked exposure", async (t) => {
  const { e, api, c, entry } = await fixture(t, true);
  assert(c.partialEntryRisk);
  e.active().find((x) => x.symbol === "MSFT").flatten = true;
  api.cancelImmediate = true;
  // Keep AAPL cancellation unresolved while allowing the other campaign to progress.
  const request = api.request.bind(api);
  api.request = async (path, method = "GET", body, market = false) => {
    if (method === "DELETE" && path.endsWith("/" + entry.order.id)) return null;
    return request(path, method, body, market);
  };
  await e.pulse();
  assert.equal(api.positions.has("MSFT"), false);
  assert.equal(c.partialEntryRisk.status, "WAIT_CANCEL");
  assert.equal(sells(api).length, 0);
  api.orders.get(entry.id).status = "canceled";
  await e.reconcile();
  c.flatten = true; // Exercise the existing, explicitly requested mock exit policy.
  await e.pulse();
  assert.equal(c.closed, true);
  assert.equal(c.partialEntryRisk.status, "RESOLVED");
  assert.equal(c.partialEntryRisk.resolution, "CONFIRMED_FLAT");
  assert.equal(c.partialEntryRisk.heldQty, 0);
  assert.equal(Number(sells(api)[0].body.qty), 3);
  assert.equal(sells(api).length, 1, "Telemetry must not add orders or bypass the existing sell-reservation guard");
});

test("partial-entry risk: journal rejects malformed clocks and a risk reference to another intent", async (t) => {
  const { e, c } = await fixture(t);
  assert(c.partialEntryRisk);
  const badTime = structuredClone(e.state);
  badTime.campaigns[0].partialEntryRisk.firstObservedAt = NaN;
  assert.throws(() => assertJournal(badTime, e.state.accountId), /partial-entry-risk/);
  const badId = structuredClone(e.state);
  badId.campaigns[0].partialEntryRisk.entryId = "not-a-campaign-entry";
  assert.throws(() => assertJournal(badId, e.state.accountId), /partial-entry-risk/);
});

test("partial-entry risk: sub-step inventory stays visible and cannot be rounded into confirmed flatness", async (t) => {
  const { e, api, c, entry } = await fixture(t, false, 0.5);
  assert(c.partialEntryRisk);
  assert(c.instrument.step > 0.5, "The fixture must hold less than one executable order step");
  assert.equal(c.partialEntryRisk.heldQty, 0.5);
  api.orders.get(entry.id).status = "canceled";
  await e.reconcile(); await e.pulse();
  assert.equal(c.partialEntryRisk.heldQty, 0.5);
  assert.equal(c.partialEntryRisk.status, "WAIT_PROTECTION");
  assert.equal(c.partialEntryRisk.resolvedAt, undefined);
  assert.equal(e.entryReady(), false);
  assert.equal(c.closed, false);
  assert.equal(riskEvents(e, "PARTIAL_ENTRY_PROTECTION_RESOLVED").length, 0);
  assert.equal(sells(api).length, 0, "Telemetry cannot bypass existing precision and inventory guards to dispose of a remainder");
});
