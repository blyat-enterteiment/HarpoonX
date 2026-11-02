"use strict";
// Controlled fault-injection tests. No broker network or trading performance claims.
const test = require("node:test"),
  assert = require("node:assert/strict");
const { ready, signal, prepare } = require("./xxx_fixtures.cjs"),
  {
    Validators,
    assertAccount,
    assertClock,
    assertPositions,
    assertOrder,
    assertIntent,
    assertSignal,
    assertJournal,
    assertFreshQuote,
    assertBars,
  } = require("../runtime30/validators.js"),
  { Scheduler } = require("../runtime30/scheduler.js"),
  { ObservedApi, RuntimeProbe } = require("../runtime30/health.js"),
  { server } = require("../runtime30/server.js");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
test("validators record the actual outcome, including asynchronous durable failure", async () => {
  const v = new Validators();
  let finish;
  const p = v.check("write", () => new Promise((r) => (finish = r)));
  assert.equal(v.checks.write.passed, 0);
  finish("ACK");
  assert.equal(await p, "ACK");
  assert.equal(v.checks.write.passed, 1);
  await assert.rejects(
    v.check("write", async () => {
      throw Error("disk full");
    }),
  );
  assert.equal(v.view()[0].status, "ERROR");
  assert.equal(v.checks.write.failed, 1);
  assert.equal(v.checks.write.passed, 1);
  v.run("write", () => true);
  assert.equal(v.view()[0].status, "VALIDATED");
  assert.equal(v.checks.write.failed, 1);
});
test("account contracts reject missing numeric values and wrong identities", () => {
  const a = {
    id: "A",
    status: "ACTIVE",
    equity: "100",
    cash: "0",
    buying_power: "100",
  };
  assertAccount(a, "A");
  for (const bad of [
    { ...a, equity: null },
    { ...a, cash: "" },
    { ...a, buying_power: "NaN" },
    { ...a, id: "B" },
  ])
    assert.throws(() => assertAccount(bad, "A"));
});
test("clock and quote contracts reject stale, future and crossed observations", () => {
  const now = Date.now();
  assertClock(
    {
      is_open: false,
      timestamp: new Date(now).toISOString(),
      next_close: new Date(now + 1e6).toISOString(),
    },
    now,
  );
  assert.throws(() =>
    assertClock(
      {
        is_open: true,
        timestamp: new Date(now - 16000).toISOString(),
        next_close: new Date(now + 1e6).toISOString(),
      },
      now,
    ),
  );
  for (const q of [
    { bid: 2, ask: 1, at: now, received: now },
    { bid: 1, ask: 2, at: now - 16000, received: now },
    { bid: 1, ask: 2, at: now + 3000, received: now },
  ])
    assert.throws(() => assertFreshQuote(q, now));
});
test("position and fill contracts reject duplicate inventory and impossible fills", () => {
  assert.throws(() =>
    assertPositions([
      { symbol: "BTC/USD", qty: "1", market_value: "1" },
      { symbol: "BTCUSD", qty: "1", market_value: "1" },
    ]),
  );
  const o = {
    id: "1",
    client_order_id: "C",
    symbol: "AAPL",
    side: "buy",
    status: "filled",
    qty: "2",
    filled_qty: "2",
    filled_avg_price: "100",
  };
  assertOrder(o, "C");
  for (const bad of [
    { ...o, filled_qty: "3" },
    { ...o, filled_avg_price: null },
    { ...o, client_order_id: "D" },
  ])
    assert.throws(() => assertOrder(bad, "C"));
});
test("order-intent and signal contracts enforce executable precision and exit bounds", async () => {
  const { e } = await ready(),
    s = signal(),
    i = e.cfg.universe.find((i) => i.symbol === s.symbol);
  assertSignal(s, i);
  assert.throws(() =>
    assertSignal({ ...s, exit: { ...s.exit, maxHoldHours: 73 } }, i),
  );
  assert.throws(() => assertSignal({ ...s, expires: Date.now() - 1 }, i));
  assertIntent(
    {
      symbol: i.symbol,
      side: "sell",
      qty: "1",
      type: "stop_limit",
      time_in_force: "day",
      stop_price: "99",
      limit_price: "98.99",
    },
    i,
  );
  assert.throws(() =>
    assertIntent(
      {
        symbol: i.symbol,
        side: "sell",
        qty: "1.1",
        type: "market",
        time_in_force: "day",
      },
      i,
    ),
  );
  assert.throws(() =>
    assertIntent(
      {
        symbol: i.symbol,
        side: "sell",
        qty: "1",
        type: "stop_limit",
        time_in_force: "day",
        stop_price: "99",
        limit_price: "100",
      },
      i,
    ),
  );
});
test("journal and bar contracts reject malformed stored execution state", async () => {
  const { e } = await ready();
  assertJournal(e.state, e.state.accountId);
  assert.throws(() =>
    assertJournal({ ...e.state, sequence: -1 }, e.state.accountId),
  );
  const b = { t: new Date().toISOString(), o: 10, h: 11, l: 9, c: 10, v: 1 };
  assertBars([b]);
  assert.throws(() => assertBars([b, b]));
  assert.throws(() => assertBars([{ ...b, h: 9 }]));
});
test("scheduler ALIVE requires completion; a failure cannot advance lastSuccess", async () => {
  const s = new Scheduler();
  let bad = false;
  s.add("guard", 1000, async () => {
    if (bad) throw Error("fault");
  });
  assert.equal(s.view()[0].health, "STARTING");
  await s.once(s.lanes[0]);
  const success = s.lanes[0].lastSuccess;
  assert.equal(s.view()[0].health, "ALIVE");
  bad = true;
  await s.once(s.lanes[0]);
  assert.equal(s.view()[0].health, "ERROR");
  assert.equal(s.lanes[0].lastSuccess, success);
  assert.equal(s.lanes[0].failures, 1);
  s.lanes[0].running = true;
  s.lanes[0].lastStart = Date.now() - 3100;
  assert.equal(s.view()[0].health, "STALLED");
  s.lanes[0].running = false;
  s.lanes[0].error = "";
  s.lanes[0].lastSuccess = Date.now() - 3100;
  assert.equal(s.view()[0].health, "STALE");
});
test("observed API reports actual latency, failures and inflight requests without secrets", async () => {
  let release;
  const transport = {
    keys: { secret: "NEVER_EXPORT" },
    mode: "paper",
    async request(p) {
      if (p === "/bad") throw Error("controlled transport failure");
      if (p === "/wait") await new Promise((r) => (release = r));
      return { from: "transport" };
    },
  };
  const a = new ObservedApi(transport);
  const p = a.request("/wait");
  assert.equal(a.snapshot().inflight, 1);
  assert.equal(a.snapshot().endpoints[0].successes, 0);
  release();
  assert.deepEqual(await p, { from: "transport" });
  await assert.rejects(a.request("/bad"));
  const x = a.snapshot();
  assert.equal(x.requests, 2);
  assert.equal(x.errors, 1);
  assert.equal(x.inflight, 0);
  assert(x.latencyP95Ms >= 0);
  assert(!JSON.stringify(x).includes("NEVER_EXPORT"));
});
test("runtime process metrics come from Node and have no seeded CPU/sample values", async () => {
  const p = new RuntimeProbe();
  let x = p.snapshot();
  assert.equal(x.probeActive, false);
  assert.equal(x.samples, 0);
  assert.equal(x.eventLoopP95Ms, null);
  p.start();
  await wait(110);
  x = p.snapshot();
  p.close();
  assert.equal(x.pid, process.pid);
  assert(x.rssBytes > 0);
  assert(x.samples > 0);
  assert(x.eventLoopP95Ms > 0);
  assert(x.cpuPercent >= 0);
});
test("system health exposes missing quotes, closed sessions, validator faults and broker staleness", async () => {
  const { e } = await ready();
  assert.equal(e.view().health.source, "RUNTIME_OBSERVED");
  assert.equal(e.view().health.status, "STARTING");
  assert(e.view().health.books.some((b) => b.dataState === "WAITING"));
  e.probe.start();
  await e.scheduler.once(
    e.scheduler.lanes.find((l) => l.name === "positions-and-take-profit"),
  );
  assert.equal(e.view().health.status, "WAIT_DATA");
  e.clock.is_open = false;
  assert.equal(
    e.healthBooks().find((b) => b.book === "equity").dataState,
    "MARKET_CLOSED",
  );
  try {
    e.validators.run("injected-contract", () => {
      throw Error("controlled invalid contract");
    });
  } catch (err) {
    assert.match(err.message, /controlled/);
  }
  assert.equal(e.view().health.status, "DEGRADED");
  e.syncAt = Date.now() - 16000;
  assert.equal(
    e.view().health.components.find((c) => c.id === "broker-sync").state,
    "STALE",
  );
  e.probe.close();
});
test("pending cancellation and undersized stop never count as confirmed native protection", async () => {
  const { e } = await ready(),
    s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  let h = e.view().health;
  assert.equal(h.protection.protected, 1);
  const i = e.pending().find((i) => i.kind === "protect");
  i.status = "pending_cancel";
  assert.equal(e.view().health.protection.protected, 0);
  i.status = "new";
  i.order.qty = "0.01";
  assert.equal(e.view().health.protection.protected, 0);
});
test("failed SQLite acknowledgement appears as ERROR and cannot report a fresh storage success", async () => {
  const { e, store } = await ready();
  const prior = e.validators.checks["journal-write"].lastSuccess;
  store.fail = true;
  await assert.rejects(e.save(), /disk full/);
  await e.saveQueue;
  const h = e.view().health;
  assert.equal(h.components.find((c) => c.id === "storage").state, "ERROR");
  assert.equal(e.validators.checks["journal-write"].lastSuccess, prior);
  assert.equal(h.status, "DEGRADED");
});
test("authenticated health endpoints return real process state and no credentials", async () => {
  const { e } = await ready(),
    password = "x".repeat(40),
    app = server(e, password, "<html>test fixture</html>", "http://127.0.0.1");
  await new Promise((r) => app.listen(0, "127.0.0.1", r));
  const base = "http://127.0.0.1:" + app.address().port;
  try {
    assert.equal((await fetch(base + "/v1/health")).status, 401);
    const h = await (await fetch(base + "/healthz")).json();
    assert.equal(h.status, "HTTP_ALIVE");
    assert(h.uptimeSeconds > 0);
    const r = await fetch(base + "/v1/health", {
      headers: {
        Authorization:
          "Basic " + Buffer.from("trader:" + password).toString("base64"),
      },
    });
    const x = await r.json();
    assert.equal(x.process.pid, process.pid);
    assert.equal(x.source, "RUNTIME_OBSERVED");
    assert(!JSON.stringify(x).includes(password));
    e.stopping = true;
    assert.equal((await fetch(base + "/healthz")).status, 503);
  } finally {
    await new Promise((r) => app.close(r));
  }
});
test("optional contracts are visible as NOT_RUN until actually exercised", async () => {
  const { e } = await ready(),
    v = e.view().validators.find((v) => v.name === "intent");
  assert.equal(v.status, "NOT_RUN");
  assert.equal(v.attempts, 0);
  assert.equal(v.lastSuccess, 0);
});
test("caught per-position exit failure remains visible in system health", async () => {
  const { e } = await ready(),
    s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  e.plugins.manageSignal = () => {
    throw Error("CONTROLLED_EXIT_FAILURE");
  };
  await e.manage();
  const h = e.view().health;
  assert.equal(
    h.components.find((c) => c.id === "exit-decisions").state,
    "ERROR",
  );
  assert.match(
    h.components.find((c) => c.id === "exit-decisions").detail,
    /CONTROLLED_EXIT_FAILURE/,
  );
  assert.equal(h.status, "DEGRADED");
});
test("new entry allocation waits for full confirmed protection, including pending-cancel transitions", async () => {
  const { e } = await ready(),
    s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  assert.equal(e.confirmedProtection(e.active()[0]), false);
  await e.manage();
  await e.reconcile();
  const c = e.active()[0],
    i = e.pending(c).find((i) => i.kind === "protect");
  assert.equal(e.confirmedProtection(c), true);
  i.status = "pending_cancel";
  assert.equal(e.confirmedProtection(c), false);
});
test("book coverage distinguishes expired observations and partially covered option watchlists", async () => {
  const { e } = await ready(),
    now = Date.now();
  for (const i of e.cfg.universe.filter((i) => i.book === "crypto"))
    e.market.quotes[i.symbol] = {
      bid: 100,
      ask: 101,
      at: now - 16000,
      received: now - 16000,
    };
  assert.equal(
    e.healthBooks(now).find((b) => b.book === "crypto").dataState,
    "STALE",
  );
  e.market.watched.options = ["AAPL261218C00100000", "AAPL261218C00110000"];
  e.market.quotes[e.market.watched.options[0]] = {
    bid: 1,
    ask: 1.01,
    at: now,
    received: now,
  };
  const opt = e.healthBooks(now).find((b) => b.book === "options");
  assert.equal(opt.watched, 2);
  assert.equal(opt.fresh, 1);
  assert.equal(opt.dataState, "DEGRADED");
});
