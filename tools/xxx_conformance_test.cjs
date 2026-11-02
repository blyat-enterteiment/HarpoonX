"use strict";
// Synthetic regression fixtures only. These tests never contact Alpaca.
const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs");
const { alpaca } = require("../runtime30/broker.js");
const { exitDecision, observeExit, fills } = require("../runtime30/policy.js");
const { Plugins } = require("../runtime30/plugins.js");
const { Market } = require("../runtime30/market.js");
const {
  ready,
  signal,
  prepare,
  MemoryStore,
  config,
} = require("./xxx_fixtures.cjs");
test("connected selectors can be selected but require installed evidence before an entry", async () => {
  const { e, api } = await ready();
  for (const id of ["equity-strategy-14", "etf-strategy-14"]) {
    await e.control("plugins", { enabled: [id] });
    const p = e.view().plugins.find((p) => p.id === id);
    assert.equal(p.executionAvailable, true);
    assert.equal(p.modelReady, false);
    await e.entries(p.book);
  }
  assert.equal(api.posts().length, 0);
});
test("strict audit requires connected selector lifecycle and still disclaims external certification", () => {
  const run = require("node:child_process").spawnSync(
    process.execPath,
    [require("node:path").join(__dirname, "xxx_audit.cjs")],
    { encoding: "utf8" },
  );
  assert.equal(run.status, 0, run.stderr);
  const report = JSON.parse(run.stdout);
  assert.equal(
    report.acceptanceStatus,
    "STATIC_REVIEW_ONLY_EXTERNAL_VALIDATION_PENDING",
  );
  assert.deepEqual(report.blockedSelectors, []);
  assert.equal(report.staticChecks.unexplainedEmptyBodies, 0);
});
test("production transport uses Alpaca hosts and credentials, without local fill fabrication", async () => {
  const previous = global.fetch,
    seen = [];
  global.fetch = async (url, options) => {
    seen.push({ url, options });
    return new Response(
      JSON.stringify({ brokerMarker: "CONTROLLED_TEST_RESPONSE" }),
      { status: 200 },
    );
  };
  try {
    const api = alpaca("SYNTHETIC-KEY", "SYNTHETIC-SECRET");
    const response = await api.request("/v2/account");
    assert.equal(response.brokerMarker, "CONTROLLED_TEST_RESPONSE");
    await api.request("/v2/orders", "POST", {
      symbol: "AAPL",
      side: "buy",
      qty: "1",
      type: "limit",
      limit_price: "100",
      time_in_force: "day",
    });
    await api.request(
      "/v2/stocks/quotes/latest?symbols=AAPL",
      "GET",
      undefined,
      true,
    );
    assert.equal(seen[0].url, "https://paper-api.alpaca.markets/v2/account");
    assert.equal(seen[1].options.headers["APCA-API-KEY-ID"], "SYNTHETIC-KEY");
    assert.equal(JSON.parse(seen[1].options.body).qty, "1");
    assert(seen[2].url.startsWith("https://data.alpaca.markets/"));
    assert.equal(response.filled_qty, undefined);
  } finally {
    global.fetch = previous;
  }
});
test("production transport rejects failure and does not synthesize a successful order", async () => {
  const previous = global.fetch;
  let posts = 0;
  global.fetch = async () => {
    posts++;
    throw Error("CONTROLLED_NETWORK_FAILURE");
  };
  try {
    const api = alpaca("SYNTHETIC-KEY", "SYNTHETIC-SECRET");
    await assert.rejects(
      api.request("/v2/orders", "POST", { side: "sell" }),
      /no confirmada/,
    );
    assert.equal(posts, 1);
  } finally {
    global.fetch = previous;
  }
});
test("stagnation closes through the broker path while entries are paused", async () => {
  const { e, api } = await ready(),
    s = signal();
  s.exit = { ...s.exit, stagnationMinutes: 10, progressR: 0.5 };
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  const c = e.active()[0];
  c.stagnationMs = 11 * 60000;
  await e.control("pause");
  await e.manage();
  assert.equal(e.state.intents.at(-1).kind, "stagnation");
  assert.equal(api.posts().at(-1).body.type, "market");
  await e.reconcile();
  assert.equal(e.active().length, 0);
});
test("stagnation clock excludes closed sessions and resets on an observed high", async () => {
  const { e } = await ready(),
    s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  const c = e.active()[0],
    now = Date.now();
  c.created = now - 2 * 3600000;
  c.lastMark = c.created;
  c.peak = 102;
  c.stagnationMs = 0;
  const q = { bid: 101, ask: 101.1, at: now, received: now };
  observeExit(
    c,
    q,
    now,
    [{ open: now - 20 * 60000, close: now - 5 * 60000 }],
    e.plugins.legacy,
  );
  assert.equal(c.stagnationMs, 15 * 60000);
  observeExit(
    c,
    { ...q, bid: 103, ask: 103.1 },
    now + 1000,
    [],
    e.plugins.legacy,
  );
  assert.equal(c.stagnationMs, 0);
});
test("volatility trailing changes after observed quotes and never loosens an existing stop", async () => {
  const { e } = await ready(),
    s = signal();
  s.entryAtr = 2;
  s.exit = { ...s.exit, trailingMode: "realized_vol", lockFraction: 0.1 };
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  const c = e.active()[0],
    now = Date.now();
  c.peak = 105;
  for (let j = 0; j < 15; j++)
    observeExit(
      c,
      { bid: 105, ask: 105.01, at: now + j * 1000, received: now + j * 1000 },
      now + j * 1000,
      [],
      e.plugins.legacy,
    );
  assert.equal(c.dynamicAtr, 1);
  const fixed = structuredClone(c);
  fixed.policy.trailingMode = "entry_atr";
  const q = { bid: 105, ask: 105.01, at: now + 15000, received: now + 15000 };
  exitDecision(c, e.state.intents, q, 20, now + 15000, e.cfg);
  exitDecision(fixed, e.state.intents, q, 20, now + 15000, e.cfg);
  assert(c.stop > fixed.stop);
  const stop = c.stop;
  c.dynamicAtr = 4;
  exitDecision(c, e.state.intents, q, 20, now + 15000, e.cfg);
  assert.equal(c.stop, stop);
});
for (const enabled of [true, false])
  test(
    "reentry policy " + enabled + " is honored after a confirmed close",
    async () => {
      const { e, api } = await ready(),
        s = signal();
      prepare(e, s);
      await e.entries("equity");
      await e.reconcile();
      await e.control("flatten");
      await e.manage();
      await e.reconcile();
      const old = e.state.campaigns[0];
      assert(old.closedAt);
      old.closedAt = Date.now() - 31 * 60000;
      await e.control("resume");
      const again = signal();
      again.entry = 105;
      again.stop = 103;
      again.exit = { ...again.exit, reentry: enabled };
      again.reentryFeature = {
        ask: 105,
        atr: 1,
        volume_acceleration: 1.2,
        consolidation_atr: 1,
        reentry_trigger: 104,
        bar_end: new Date(Date.now() - 60000).toISOString(),
      };
      prepare(e, again);
      await e.entries("equity");
      assert.equal(api.posts().length, enabled ? 3 : 2);
    },
  );
function observedShape() {
  const cfg = config(),
    p = new Plugins(new MemoryStore(), cfg),
    m = new Market({}, cfg),
    now = Date.parse("2026-10-15T15:30:10Z"),
    open = Date.parse("2026-10-15T13:30:00Z");
  // Thirteen synthetic trading sessions, not thirteen consecutive calendar days.
  // The old fixture counted weekends as RVOL history; session filtering correctly
  // removed those bars and exposed fewer than ten comparable prior sessions.
  m.calendar = [
    "2026-09-29", "2026-09-30", "2026-10-01", "2026-10-02",
    "2026-10-05", "2026-10-06", "2026-10-07", "2026-10-08",
    "2026-10-09", "2026-10-12", "2026-10-13", "2026-10-14",
    "2026-10-15",
  ].map((date) => ({
    date,
    open: Date.parse(date + "T13:30:00Z"),
    close: Date.parse(date + "T20:00:00Z"),
  }));
  for (const symbol of ["AAPL", "SPY", "XLK"]) {
    m.bars[symbol] = [];
    for (const session of m.calendar)
      for (let j = 0; j < 24; j++) {
        const c =
          symbol === "XLK"
            ? 100 + j * 0.2
            : symbol === "SPY"
              ? 100
              : 100 + j * 0.08;
        m.bars[symbol].push({
          t: new Date(session.open + j * 300000).toISOString(),
          o: c,
          h: c + 0.15,
          l: c - 0.15,
          c,
          v: session.open === open ? 3000 : 1000,
          vw: c,
        });
      }
    m.daily[symbol] = Array.from({ length: 30 }, (_, j) => ({
      t: new Date(open - (30 - j) * 86400000).toISOString(),
      o: 95,
      h: 96,
      l: 94,
      c: 95,
      v: 10000,
      vw: 95,
    }));
    m.quotes[symbol] = { bid: 101.1, ask: 101.11, at: now, received: now };
  }
  return { p, m, now };
}
test("sector evidence is calculated from XLK and never silently substituted with SPY", () => {
  const { p, m, now } = observedShape(),
    f = p.features(m, now).find((x) => x.symbol === "AAPL");
  assert(f);
  assert.equal(f.sector_proxy, "XLK");
  assert.notEqual(f.sector_relative_bps, f.relative_bps);
  delete m.bars.XLK;
  assert.equal(
    p.features(m, now).find((x) => x.symbol === "AAPL").sector_relative_bps,
    null,
  );
});
test("strategy variants pass their actual exit parameters into executable signals", () => {
  const { p, m, now } = observedShape();
  for (const variant of [
    p.catalog.find(
      (x) => x.book === "equity" && x.params.trailing_mode === "realized_vol",
    ),
    p.catalog.find(
      (x) => x.book === "equity" && x.params.stagnation_minutes === 10,
    ),
    p.catalog.find((x) => x.book === "equity" && x.params.reentry === true),
  ]) {
    const signals = p.evaluate("equity", m, [variant.id], now);
    assert(signals.length, JSON.stringify(p.diagnostics));
    assert.equal(signals[0].exit.trailingMode, variant.params.trailing_mode);
    assert.equal(
      signals[0].exit.stagnationMinutes,
      variant.params.stagnation_minutes,
    );
    assert.equal(signals[0].exit.reentry, variant.params.reentry);
    assert(signals[0].entryAtr > 0);
  }
});
test("missing observed VWAP blocks equity features instead of manufacturing VWAP from closes", () => {
  const { p, m, now } = observedShape();
  for (const b of m.bars.AAPL) delete b.vw;
  assert(!p.features(m, now).some((f) => f.symbol === "AAPL"));
  assert(
    p.diagnostics.some((d) => d.reason.includes("OBSERVED_BAR_VWAP_REQUIRED")),
  );
});
test("native closed daily crypto channel generates an actual exit intent", async () => {
  const { e, api } = await ready(),
    s = signal("crypto");
  prepare(e, s);
  await e.entries("crypto");
  await e.reconcile();
  const end = Math.floor(Date.now() / 86400000) * 86400000;
  e.market.daily[s.symbol] = Array.from({ length: 50 }, (_, j) => ({
    t: new Date(end - (50 - j) * 86400000).toISOString(),
    o: 100,
    h: 101,
    l: j === 49 ? 94 : 99,
    c: j === 49 ? 95 : 100,
    v: 1000,
  }));
  await e.manage();
  assert.equal(e.state.intents.at(-1).kind, "signal");
  assert.equal(api.posts().at(-1).body.type, "market");
});
