"use strict";
const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const { Coordinator } = require("../runtime30/coordinator.js"),
  { Scheduler, PriorityMutex } = require("../runtime30/scheduler.js"),
  { validateConfig, DEFAULT_EXIT } = require("../runtime30/types.js"),
  { availableSize, exitDecision, fills } = require("../runtime30/policy.js"),
  { Plugins } = require("../runtime30/plugins.js"),
  { server } = require("../runtime30/server.js"),
  { Market } = require("../runtime30/market.js");
const {
  MemoryStore,
  FakeBroker,
  config,
  ready,
  signal,
  prepare,
} = require("./xxx_fixtures.cjs");
const wait = (ms) => new Promise((r) => setTimeout(r, ms));
test("catalog preserves 58 inherited plugins and adds 3 option strategies", () => {
  const p = new Plugins(new MemoryStore(), config());
  assert.equal(p.catalog.length, 61);
  assert.deepEqual(
    p.catalog.reduce((n, p) => ((n[p.book] = (n[p.book] || 0) + 1), n), {}),
    { equity: 22, etf: 22, crypto: 14, options: 3 },
  );
  assert.throws(() => p.validateSelection(["fake"]));
});
for (const [label, mutate] of [
  ["live", (c) => (c.mode = "live")],
  ["risk", (c) => (c.riskFraction = 0.1)],
  ["NaN exit", (c) => (c.exit.tp1Fraction = NaN)],
  ["bad universe", (c) => (c.universe[0].symbol = "../account")],
  ["inconsistent exposure", (c) => (c.assetExposure = 0.8)],
  ["option feed", (c) => (c.optionFeed = "indicative")],
])
  test("reject invalid config: " + label, () => {
    const c = config();
    mutate(c);
    assert.throws(() => validateConfig(c));
  });
for (const book of ["equity", "etf", "crypto", "options"])
  test(
    book + ": entry, broker protection, confirmed cancel, TP and re-protection",
    async () => {
      const { e, api } = await ready(),
        s = signal(book);
      prepare(e, s);
      await e.entries(book);
      assert.equal(api.posts().length, 1);
      assert.equal(
        api.posts()[0].body.time_in_force,
        book === "crypto" ? "gtc" : "day",
      );
      if (book === "options")
        assert.equal(api.posts()[0].body.position_intent, "buy_to_open");
      await e.reconcile();
      await e.manage();
      assert.equal(api.posts().length, 2);
      assert.equal(
        api.posts()[1].body.type,
        book === "crypto" ? "stop_limit" : "stop",
      );
      await e.reconcile();
      const c = e.active()[0],
        entry = fills(c, e.state.intents).entry;
      assert(entry > 0);
      e.market.quotes[s.symbol] = {
        bid: entry + 4 * c.risk,
        ask: entry + 4 * c.risk + 0.01,
        at: Date.now(),
        received: Date.now(),
      };
      await e.manage();
      assert.equal(api.posts().length, 2, "cancel must precede TP");
      await e.reconcile();
      await e.manage();
      assert.equal(api.posts().length, 3);
      assert(["tp1", "tp2"].includes(e.state.intents.at(-1).kind));
      assert.equal(api.posts()[2].body.side, "sell");
      if (book === "options")
        assert.equal(api.posts()[2].body.position_intent, "sell_to_close");
      await e.reconcile();
      await e.manage();
      if (e.active().length)
        assert.equal(e.state.intents.at(-1).kind, "protect");
    },
  );
test("paused entries still take profit; plugin OFF does not orphan campaign", async () => {
  const { e, api } = await ready(),
    s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  await e.control("pause");
  await e.control("plugins", { enabled: [] });
  const c = e.active()[0];
  e.market.quotes.AAPL = {
    bid: 110,
    ask: 110.01,
    at: Date.now(),
    received: Date.now(),
  };
  await e.manage();
  assert.equal(api.posts().at(-1).body.side, "sell");
  assert.equal(e.state.paused, true);
  assert.equal(c.policy.tp1R, 1.5);
});
test("global allocation serializes simultaneous books", async () => {
  const { e, api } = await ready(),
    a = signal(),
    b = signal("crypto");
  prepare(e, a);
  prepare(e, b);
  e.plugins.evaluate = (book) => [book === "crypto" ? b : a];
  await Promise.all([e.entries("equity"), e.entries("crypto")]);
  assert.equal(api.posts().length, 1);
});
test("unknown POST persists before send and cannot duplicate after restart", async () => {
  const { e, api, store } = await ready(),
    s = signal();
  prepare(e, s);
  api.mode = "timeout-before";
  await e.entries("equity");
  assert.equal(e.state.intents[0].status, "UNKNOWN");
  const before = await store.get(e.key);
  assert.equal(before.intents.length, 1);
  const next = new Coordinator(store, api, config());
  await next.initialize(true);
  prepare(next, s);
  await next.entries("equity");
  assert.equal(api.posts().length, 1);
  assert.match(next.reconcileError, /UNCERTAIN/);
});
test("timeout after accepted reconciles existing client_order_id", async () => {
  const { e, api } = await ready(),
    s = signal();
  prepare(e, s);
  api.mode = "timeout-after";
  await e.entries("equity");
  api.mode = "fill";
  await e.reconcile();
  assert.equal(e.state.intents[0].status, "filled");
  await e.entries("equity");
  assert.equal(api.posts().length, 1);
});
test("journal persistence failure prevents POST", async () => {
  const { e, api, store } = await ready(),
    s = signal();
  prepare(e, s);
  store.fail = true;
  await assert.rejects(e.entries("equity"), /disk full/);
  assert.equal(api.posts().length, 0);
});
test("lost lease prevents broker mutation", async () => {
  const { e, api, store } = await ready(),
    s = signal();
  prepare(e, s);
  store.leased = false;
  await assert.rejects(e.entries("equity"), /authority/);
  assert.equal(api.posts().length, 0);
});
test("first deployment refuses unrelated inventory", async () => {
  const api = new FakeBroker();
  api.positions.set("AAPL", { symbol: "AAPL", qty: "1", market_value: "100" });
  const e = new Coordinator(new MemoryStore(), api, config());
  await assert.rejects(e.initialize(true), /empty dedicated/);
});
test("external orders and positions block new entries", async () => {
  const { e, api } = await ready();
  api.positions.set("TSLA", { symbol: "TSLA", qty: "1", market_value: "200" });
  await e.reconcile();
  assert.match(e.reconcileError, /EXTERNAL_POSITION/);
  prepare(e, signal());
  await e.entries("equity");
  assert.equal(api.posts().length, 0);
});
test("account ID mismatch refuses start", async () => {
  const api = new FakeBroker();
  api.account.id = "OTHER";
  await assert.rejects(
    new Coordinator(new MemoryStore(), api, config()).initialize(),
    /binding/,
  );
});
test("pause survives restart", async () => {
  const { e, api, store } = await ready();
  await e.control("pause");
  const next = new Coordinator(store, api, config());
  await next.initialize(true);
  assert.equal(next.state.paused, true);
});
test("risk configuration mutation cannot overwrite persistent account limits", async () => {
  const { api, store } = await ready();
  const c = config();
  c.totalExposure = 0.49;
  await assert.rejects(
    new Coordinator(store, api, c).initialize(),
    /differs from journal/,
  );
});
test("session closure blocks securities and permits crypto", async () => {
  const { e, api } = await ready();
  api.open = false;
  await e.sessions();
  prepare(e, signal());
  await e.entries("equity");
  assert.equal(api.posts().length, 0);
  prepare(e, signal("crypto"));
  await e.entries("crypto");
  assert.equal(api.posts().length, 1);
});
test("missing options permission fails closed", async () => {
  const { e, api } = await ready();
  delete e.account.options_trading_level;
  prepare(e, signal("options"));
  await e.entries("options");
  assert.equal(api.posts().length, 0);
});
test("stale quote blocks entry", async () => {
  const { e, api } = await ready();
  const s = signal();
  prepare(e, s);
  e.market.quotes.AAPL.at -= 16000;
  await e.entries("equity");
  assert.equal(api.posts().length, 0);
});
test("daily loss latches and exit management remains enabled", async () => {
  const { e, api } = await ready();
  prepare(e, signal());
  await e.entries("equity");
  await e.reconcile();
  api.equity = 19000;
  await e.reconcile();
  assert.equal(e.state.halt, "DAILY_LOSS");
  await e.manage();
  assert.equal(api.posts().at(-1).body.side, "sell");
  await assert.rejects(e.control("resume"), /risk/);
});
test("cancellation acknowledgement is not treated as cancellation confirmation", async () => {
  const { e, api } = await ready();
  prepare(e, signal());
  await e.entries("equity");
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  api.cancelImmediate = false;
  e.market.quotes.AAPL = {
    bid: 110,
    ask: 110.01,
    at: Date.now(),
    received: Date.now(),
  };
  await e.manage();
  await e.reconcile();
  await e.manage();
  assert.equal(api.posts().length, 2);
  assert.equal(e.pending().filter((i) => i.kind === "protect").length, 1);
});
test("options sizing reserves whole premium times multiplier", () => {
  const c = config(),
    a = {
      symbol: "OPT",
      book: "options",
      factor: "sp500",
      leverage: 1,
      multiplier: 100,
      step: 1,
      minQty: 1,
      tick: 0.01,
      tradable: true,
    },
    s = { ...signal("options"), entry: 10, stop: 9.99 };
  const qty = availableSize(
    s,
    a,
    c,
    {
      equity: 20000,
      cash: 20000,
      buying_power: 20000,
      options_buying_power: 20000,
    },
    [],
    [],
    [],
  );
  assert.equal(
    qty,
    0,
    "$1000 premium exceeds $50 risk budget despite tiny modeled stop",
  );
});
function campaign(book = "equity", qty = 8) {
  const s = signal(book),
    c = {
      id: "test",
      symbol: s.symbol,
      book,
      plugin: s.plugin,
      created: Date.now(),
      instrument: {
        symbol: s.symbol,
        book,
        multiplier: book === "options" ? 100 : 1,
        step: 1,
        minQty: 1,
        tick: 0.01,
        leverage: 1,
        factor: "test",
        tradable: true,
      },
      policy: { ...DEFAULT_EXIT },
      risk: 2,
      peak: 100,
      stop: 98,
      closed: false,
      intents: ["b"],
      entryCeiling: 100,
    };
  return {
    c,
    intents: [
      {
        id: "b",
        symbol: c.symbol,
        campaign: "test",
        kind: "entry",
        at: Date.now(),
        payload: {},
        status: "filled",
        order: { filled_qty: String(qty), filled_avg_price: "100" },
      },
    ],
  };
}
test("take profit uses net-of-configured-friction bid", () => {
  const { c, intents } = campaign("crypto"),
    cfg = config(),
    q = { bid: 103, ask: 103.01, at: Date.now(), received: Date.now() };
  assert.equal(exitDecision(c, intents, q, 8, Date.now(), cfg), null);
  q.bid = 104;
  q.ask = 104.01;
  assert.equal(exitDecision(c, intents, q, 8, Date.now(), cfg).kind, "tp1");
});
test("one option contract exits whole at TP2", () => {
  const { c, intents } = campaign("options", 1),
    q = { bid: 107, ask: 107.01, at: Date.now(), received: Date.now() };
  assert.deepEqual(exitDecision(c, intents, q, 1, Date.now(), config()), {
    kind: "tp2",
    qty: 1,
  });
});
test("partial TP fills count cumulatively; no duplicate 25 percent sale", () => {
  const { c, intents } = campaign();
  intents.push({
    id: "s",
    symbol: c.symbol,
    campaign: "test",
    kind: "tp1",
    at: Date.now(),
    payload: {},
    status: "canceled",
    order: { filled_qty: "1", filled_avg_price: "104" },
  });
  const q = { bid: 104, ask: 104.01, at: Date.now(), received: Date.now() };
  assert.deepEqual(exitDecision(c, intents, q, 7, Date.now(), config()), {
    kind: "tp1",
    qty: 1,
  });
});
test("ratchet never lowers stop after quote retracement", () => {
  const { c, intents } = campaign(),
    q = { bid: 110, ask: 110.01, at: Date.now(), received: Date.now() };
  exitDecision(c, intents, q, 8, Date.now(), config());
  const stop = c.stop;
  q.bid = 109;
  exitDecision(c, intents, q, 8, Date.now(), config());
  assert(c.stop >= stop);
});
test("deadline and expiration continue without a quote", () => {
  const { c, intents } = campaign();
  c.created -= 73 * 3600000;
  assert.equal(
    exitDecision(c, intents, undefined, 8, Date.now(), config()).kind,
    "time",
  );
  c.created = Date.now();
  c.instrument.expiry = new Date(Date.now() + 12 * 3600000)
    .toISOString()
    .slice(0, 10);
  assert.equal(
    exitDecision(c, intents, undefined, 8, Date.now(), config()).kind,
    "expiry",
  );
});
test("stale quote is never used to invent a take profit", () => {
  const { c, intents } = campaign(),
    q = { bid: 1000, ask: 1001, at: Date.now() - 60000, received: Date.now() };
  assert.equal(exitDecision(c, intents, q, 8, Date.now(), config()), null);
});
test("slow or failed research cannot stop exits/quotes or overlap itself", async () => {
  const s = new Scheduler();
  let release,
    count = 0,
    research = 0;
  const waitResearch = new Promise((r) => (release = r));
  let confirmProgress, timeout;
  const exitsProgress = new Promise((r) => (confirmProgress = r));
  s.add("research", 5, async () => {
    research++;
    await waitResearch;
    throw Error("budget exhausted");
  });
  s.add("exits", 5, async () => {
    count++;
    if (count >= 3) confirmProgress();
  });
  s.start();
  try {
    await Promise.race([exitsProgress, new Promise((_, reject) => {
      timeout = setTimeout(() => reject(Error("Exit lane did not progress while research was pending")), 2000);
    })]);
    assert(count >= 3);
    assert.equal(research, 1);
  } finally {
    clearTimeout(timeout);
    release();
    await s.stop();
  }
  assert.equal(s.lanes[0].failures, 1);
});
test("priority mutex schedules queued exits ahead of queued entries", async () => {
  const m = new PriorityMutex(),
    order = [];
  let release;
  const p = m.run(1, () => new Promise((r) => (release = r)));
  const entry = m.run(2, async () => order.push("entry")),
    exit = m.run(0, async () => order.push("exit"));
  release();
  await Promise.all([p, entry, exit]);
  assert.deepEqual(order, ["exit", "entry"]);
});
test("stock data error does not erase working crypto quote", async () => {
  const m = new Market(
    {
      request: async () => {
        throw Error("403 SIP");
      },
    },
    config(),
  );
  m.assets["AAPL"] = config().universe[0];
  m.quotes["BTC/USD"] = {
    bid: 1,
    ask: 2,
    at: Date.now(),
    received: Date.now(),
  };
  await assert.rejects(m.quotesFor("equity"));
  assert.equal(m.quotes["BTC/USD"].bid, 1);
});
test("bar pagination returns all pages and rejects repeated tokens", async () => {
  let n = 0;
  const m = new Market(
    {
      request: async () =>
        ++n === 1
          ? {
              bars: {
                AAPL: [{ t: "2026-01-01", o: 1, h: 2, l: 1, c: 2, v: 1 }],
              },
              next_page_token: "p",
            }
          : {
              bars: {
                AAPL: [{ t: "2026-01-02", o: 1, h: 2, l: 1, c: 2, v: 1 }],
              },
            },
    },
    config(),
  );
  assert.equal(
    (await m.fetchBars(["AAPL"], false, "1Day", 0, 1)).AAPL.length,
    2,
  );
  m.api = { request: async () => ({ bars: {}, next_page_token: "same" }) };
  await assert.rejects(m.fetchBars(["AAPL"], false, "1Day", 0, 1), /Repeated/);
});
test("HTTP panel authentication, CSRF gate, controls and export", async () => {
  const { e } = await ready(),
    password = "x".repeat(40),
    app = server(
      e,
      password,
      fs.readFileSync(
        path.join(__dirname, "../deploy/dashboard30.html"),
        "utf8",
      ),
    );
  await new Promise((r) => app.listen(0, "127.0.0.1", r));
  const base = "http://127.0.0.1:" + app.address().port,
    headers = {
      Authorization:
        "Basic " + Buffer.from("trader:" + password).toString("base64"),
    };
  try {
    assert.equal((await fetch(base + "/v1/state")).status, 401);
    assert.equal((await fetch(base + "/v1/state", { headers })).status, 200);
    assert.equal(
      (
        await fetch(base + "/v1/control", {
          method: "POST",
          headers: { ...headers, "Content-Type": "application/json" },
          body: '{"action":"pause"}',
        })
      ).status,
      403,
    );
    assert.equal(
      (
        await fetch(base + "/v1/control", {
          method: "POST",
          headers: {
            ...headers,
            "Content-Type": "application/json",
            "X-Harpoon-Action": "1",
          },
          body: '{"action":"pause"}',
        })
      ).status,
      200,
    );
    assert.equal(e.state.paused, true);
    const html = await fetch(base + "/", { headers });
    assert.match(html.headers.get("content-security-policy"), /sha256/);
    const exported = await fetch(base + "/v1/export", { headers });
    assert.equal(exported.status, 200);
    assert(Array.isArray((await exported.json()).history.intents));
  } finally {
    await new Promise((r) => app.close(r));
  }
});
test("evidence retains fills and campaigns after a position is closed", async () => {
  const { e } = await ready(),
    s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  await e.control("flatten");
  await e.manage();
  await e.reconcile();
  assert.equal(e.view().positions.length, 0);
  const evidence = e.evidence();
  assert.equal(evidence.history.campaigns.length, 1);
  assert.equal(evidence.history.campaigns[0].closed, true);
  assert.equal(evidence.history.intents.length, 2);
  assert(evidence.history.intents.every((i) => Number(i.order.filled_qty) > 0));
  evidence.history.intents.length = 0;
  assert.equal(e.state.intents.length, 2);
});
test("SQLite journal survives closing/reopening and enforces shared-file lease", async () => {
  const { DurableStore } = require("../runtime/runner.cjs"),
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "h30-test-")),
    db = path.join(dir, "test.sqlite"),
    a = await new DurableStore(db).open(),
    b = await new DurableStore(db).open();
  try {
    assert.equal(await a.lease("account"), true);
    assert.equal(await b.lease("account"), false);
    await a.put("check", { source: "SYNTHETIC_TEST", n: 42 });
    assert.deepEqual(await b.get("check"), { source: "SYNTHETIC_TEST", n: 42 });
    await a.lease("account", true);
    assert.equal(await b.lease("account"), true);
  } finally {
    await a.close();
    await b.close();
  }
});
test("legacy R2 option lane is scheduled outside research and enabled gate", () => {
  const source = fs.readFileSync(
      path.join(__dirname, "../src/autonomy_adapter3.js"),
      "utf8",
    ),
    pulse = source.slice(source.indexOf("async pulse(force"));
  assert(
    pulse.indexOf("this.task('options'") <
      pulse.indexOf("if(!this.policy.enabled)return"),
  );
  assert(pulse.includes("()=>e.optionsPulse3()"));
});
test("72-hour limit rolls back to executable Friday close if it falls on weekend", () => {
  const { deadlineFor } = require("../runtime30/policy.js"),
    thu = Date.parse("2026-10-15T16:00:00Z"),
    fri = {
      open: Date.parse("2026-10-16T13:30:00Z"),
      close: Date.parse("2026-10-16T20:00:00Z"),
    },
    mon = {
      open: Date.parse("2026-10-19T13:30:00Z"),
      close: Date.parse("2026-10-19T20:00:00Z"),
    };
  assert.equal(deadlineFor("equity", thu, 72, [fri, mon]), fri.close - 600000);
  assert.equal(deadlineFor("crypto", thu, 72, []), thu + 72 * 3600000);
});
test("malformed market OHLCV is rejected before signal generation", async () => {
  const m = new Market(
    {
      request: async () => ({
        bars: {
          AAPL: [{ t: "2026-01-01", o: 100, h: 50, l: 1, c: 100, v: 1 }],
        },
      }),
    },
    config(),
  );
  await assert.rejects(
    m.fetchBars(["AAPL"], false, "1Day", 0, 1),
    /Invalid OHLCV/,
  );
});
test("negative or mismatched broker fills cannot be reconciled into owned inventory", async () => {
  const { e, api } = await ready();
  prepare(e, signal());
  await e.entries("equity");
  const intent = e.state.intents[0];
  intent.status = "new";
  api.orders.get(intent.id).filled_qty = "999999";
  await e.reconcile();
  assert.equal(intent.status, "UNKNOWN");
  assert.match(e.reconcileError, /UNCERTAIN/);
});
test("real crypto trend plugin produces a signal only from closed daily breakout bars", async () => {
  const cfg = config(),
    p = new Plugins(new MemoryStore(), cfg),
    m = new Market({}, cfg),
    end = Math.floor(Date.now() / 86400000) * 86400000;
  for (const symbol of ["BTC/USD", "ETH/USD"]) {
    m.daily[symbol] = Array.from({ length: 50 }, (_, i) => ({
      t: new Date(end - (50 - i) * 86400000).toISOString(),
      o: 100,
      h: i === 49 ? 105 : 101,
      l: 99,
      c: i === 49 ? 104 : 100,
      v: 100,
    }));
    m.quotes[symbol] = {
      bid: 104,
      ask: 104.01,
      at: Date.now(),
      received: Date.now(),
    };
  }
  const s = p.evaluate("crypto", m, ["crypto-canonical-host"]);
  assert.equal(s.length, 2);
  for (const symbol of ["BTC/USD", "ETH/USD"])
    m.daily[symbol].at(-1).t = new Date(end).toISOString();
  assert.equal(p.evaluate("crypto", m, ["crypto-canonical-host"]).length, 0);
});
for (const direction of ["call-breakout", "put-breakdown", "call-pullback"])
  test(
    "real options plugin evaluates " +
      direction +
      " using bounded OPRA contract",
    () => {
      const cfg = config();
      cfg.optionUnderlyings = ["SPY"];
      const p = new Plugins(new MemoryStore(), cfg),
        m = new Market({}, cfg),
        now = Date.now(),
        bear = direction === "put-breakdown",
        under = bear ? 90 : 102,
        symbol = "SPY261218" + (bear ? "P" : "C") + "00600000";
      m.daily.SPY = Array.from({ length: 25 }, (_, i) => ({
        t: new Date(now - (26 - i) * 86400000).toISOString(),
        o: 100,
        h: 105,
        l: 80,
        c: bear ? 100 : 90,
        v: 100,
      }));
      m.bars.SPY = Array.from({ length: 22 }, (_, i) => ({
        t: new Date(now - (23 - i) * 300000).toISOString(),
        o: 100,
        h: 101,
        l: 90,
        c:
          direction === "call-pullback"
            ? i === 20
              ? 99
              : i === 21
                ? 101
                : 100
            : i === 21
              ? bear
                ? 89
                : 102
              : 100,
        v: 100,
      }));
      m.quotes.SPY = { bid: under, ask: under + 0.01, at: now, received: now };
      m.assets[symbol] = {
        symbol,
        book: "options",
        underlying: "SPY",
        expiry: new Date(now + 30 * 86400000).toISOString().slice(0, 10),
        tradable: true,
      };
      m.metadata[symbol] = { type: bear ? "put" : "call", open_interest: 1000 };
      m.snapshots[symbol] = {
        observedAt: now,
        greeks: { delta: bear ? -0.5 : 0.5 },
      };
      m.quotes[symbol] = { bid: 1, ask: 1.01, at: now, received: now };
      const output = p.evaluate("options", m, ["options-" + direction], now);
      assert.equal(output.length, 1);
      assert.equal(output[0].symbol, symbol);
      m.quotes[symbol].at = now - 16000;
      assert.equal(
        p.evaluate("options", m, ["options-" + direction], now).length,
        0,
      );
    },
  );
function protocol() {
  const end = new Date(
      Date.UTC(new Date().getUTCFullYear(), new Date().getUTCMonth(), 1),
    ),
    start = new Date(Date.UTC(end.getUTCFullYear(), end.getUTCMonth() - 11, 1));
  return {
    schema: "HARPOON-WARROOM-CAMPAIGN-3",
    id: "XXX-TEST-RESEARCH",
    start: +start,
    end: +end,
  };
}
test("research error consumes bounded run and never disables position management", async () => {
  const { e } = await ready();
  await e.queueResearch({
    protocol: protocol(),
    data: { source: "SYNTHETIC_TEST" },
  });
  await e.research();
  assert.equal(e.state.research.runs, 1);
  assert.equal(e.state.research.status, "ERROR");
  assert.equal(e.state.paused, false);
  assert(e.scheduler.lanes.some((l) => l.name === "positions-and-take-profit"));
});
test("injected holdout lock is rejected without internal training evidence", async () => {
  const { e } = await ready();
  await assert.rejects(
    e.queueResearch({
      protocol: protocol(),
      stage: "holdout",
      data: { source: "SYNTHETIC_TEST" },
      lock: { selected: "C3", models: {} },
    }),
    /internally computed/,
  );
  assert.equal(e.state.research.runs, 0);
});
test("research budget cannot be increased by an incoming request", async () => {
  const { e } = await ready();
  e.state.research.runs = e.cfg.researchMaxRuns;
  await assert.rejects(e.queueResearch({ maxRuns: 999 }), /budget exhausted/);
});
