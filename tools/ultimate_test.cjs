"use strict";
// Synthetic contract and fault tests. No external broker orders or profitability evidence.
const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const {
  defaultProtocol,
  assertProtocol,
  assertDataset,
  digest,
} = require("../runtime30/ultimate_contracts.js");
const {
  bootstrapLower,
  metrics,
  deflatedSharpe,
  probabilityBacktestOverfit,
} = require("../runtime30/ultimate_stats.js");
const {
  opportunities,
  replayCampaign,
  nextTrailingStop,
  runStudy,
  DEFAULT_REPLAY_LIMITS,
} = require("../runtime30/ultimate_replay.js");
const { ResearchLab } = require("../runtime30/ultimate_lab.js");
const {
  FuturesGateway,
  IronbeamPaperApi,
  futuresSize,
  assertContract,
} = require("../runtime30/ultimate_futures.js");
const { paperAutostart, server } = require("../runtime30/server.js");
const { Validators } = require("../runtime30/validators.js");
const {
  MemoryStore,
  config,
  ready,
  signal,
  prepare,
} = require("./xxx_fixtures.cjs");
const {
  dataset,
  futureContract,
  SyntheticIronbeam,
} = require("./ultimate_fixtures.cjs");
test("failed durable registration and queue never report a committed success", async () => {
  const store = new MemoryStore(),
    validators = new Validators(),
    lab = new ResearchLab(store, "FAULT", validators, DEFAULT_REPLAY_LIMITS);
  await lab.load();
  store.fail = true;
  await assert.rejects(lab.register(dataset().protocol), /disk full/);
  assert.equal(lab.state.trials.length, 0);
  assert.equal(lab.state.spent, 0);
  store.fail = false;
  const t = await lab.register(dataset().protocol);
  await lab.importData(t.id, dataset().data);
  store.fail = true;
  await assert.rejects(lab.queue(t.id), /disk full/);
  assert.equal(lab.export(t.id).trial.status, "READY");
  assert.equal(validators.checks["ultimate-journal"].failed, 2);
});
test("autopilot blocks new allocations when the independent guardian heartbeat is stale", async () => {
  const { e } = await ready();
  e.autopilotStartedAt = Date.now();
  assert.equal(e.entryReady(), false);
  const lane = e.scheduler.lanes.find(
    (l) => l.name === "positions-and-take-profit",
  );
  await e.scheduler.once(lane);
  assert.equal(e.entryReady(), true);
  lane.lastSuccess = Date.now() - 5000;
  assert.equal(e.entryReady(), false);
  assert.equal(e.view().autopilot.state, "GUARDIAN_DEGRADED");
});
test("hashes are key-order independent and detect changed numerical content", () => {
  assert.equal(digest({ a: 1, b: 2 }), digest({ b: 2, a: 1 }));
  assert.notEqual(digest({ a: 1 }), digest({ a: 2 }));
});
test("protocol cannot reduce samples, purge or multiplicity below its universe", () => {
  assertProtocol(defaultProtocol());
  for (const patch of [
    { minOosCampaigns: 1 },
    { purgeHours: 0 },
    { familyTrials: 1 },
    { universe: ["MES", "MES"] },
    { costs: { spreadBps: 0, slippageBps: 1, perSideUsd: 0 } },
  ])
    assert.throws(() => assertProtocol({ ...defaultProtocol(), ...patch }));
});
test("dataset rejects future availability, duplicate bars, bad OHLC and absent checksums", () => {
  const { data, protocol } = dataset();
  assertDataset(data, protocol);
  for (const mutate of [
    (d) => (d.series[0].bars[0].availableAt = Date.now() + 1000),
    (d) => d.series[0].bars.splice(1, 0, d.series[0].bars[0]),
    (d) => (d.series[0].bars[0].l = 1000),
    (d) => (d.provenance.files = []),
  ]) {
    const d = structuredClone(data);
    mutate(d);
    assert.throws(() => assertDataset(d, protocol));
  }
});
test("proxy dataset cannot be presented as a dated futures dataset", () => {
  const { data } = dataset();
  assert.throws(() => assertDataset(data, defaultProtocol()));
});
test("features are causal when all subsequent sessions are changed", () => {
  const { data, protocol } = dataset(),
    cutoff = data.sessions[90].open;
  const a = opportunities(data, protocol).signals.filter((s) => s.at < cutoff);
  assert(a.length > 0);
  const d = structuredClone(data);
  for (const b of d.series[0].bars)
    if (b.t >= cutoff) for (const k of ["o", "h", "l", "c", "vw"]) b[k] *= 2;
  assert.deepEqual(
    opportunities(d, protocol).signals.filter((s) => s.at < cutoff),
    a,
  );
});
test("incomplete sessions are quarantined without interpolation", () => {
  const { data, protocol } = dataset();
  data.series[0].bars.splice(20, 1);
  const result = opportunities(data, protocol);
  assert.equal(result.funnel.incompleteSessions, 1);
});
test("long and short trailing never loosen and require progress", () => {
  assert.equal(nextTrailingStop(1, 99, 100, 101, 1, "RUNNER", 1), 99);
  assert(nextTrailingStop(1, 99, 100, 104, 1, "RUNNER", 1) >= 99);
  assert(nextTrailingStop(-1, 101, 100, 96, 1, "RUNNER", 1) <= 101);
});
test("ambiguous stop and target uses adverse stop before any profit", () => {
  const { data, protocol } = dataset(),
    series = data.series[0];
  series.bars[0] = { ...series.bars[0], o: 100, h: 105, l: 95, c: 100 };
  const s = {
    id: "X",
    symbol: "SPY",
    hypothesis: "OPENING_BREAKOUT",
    direction: 1,
    at: series.bars[0].t,
    index: 0,
    stopDistance: 1,
    regime: 0.8,
  };
  const result = replayCampaign(s, series, data, protocol, "BASELINE");
  assert(result.netR < 0);
  assert.equal(result.reason, "STOP");
  assert.equal(result.ambiguousBars, 1);
});
test("incomplete paths cannot become zero-PnL successful trades", () => {
  const { data, protocol } = dataset(),
    series = data.series[0];
  const index = series.bars.length - 1,
    b = series.bars[index];
  const result = replayCampaign(
    {
      id: "X",
      symbol: "SPY",
      hypothesis: "CLOSED_CHANNEL",
      direction: 1,
      at: b.t,
      index,
      stopDistance: 100,
      regime: 0.5,
    },
    series,
    data,
    protocol,
    "BASELINE",
  );
  assert.equal(result, null);
});
test("bootstrap is deterministic, insufficient evidence returns null, negative data fails", () => {
  const a = Array(100).fill(-0.1);
  assert(Math.abs(bootstrapLower(a, 500, 5, 72) + 0.1) < 1e-12);
  assert.equal(bootstrapLower([1, 2], 500, 5, 72), null);
  assert.equal(bootstrapLower(a, 500, 5, 72), bootstrapLower(a, 500, 5, 72));
});
test("metrics honor compounding, drawdown and zero-information DSR", () => {
  const m = metrics([0.1, -0.1], [1, -1]);
  assert(Math.abs(m.modelReturn + 0.01) < 1e-12);
  assert(Math.abs(m.maxDrawdown - 0.1) < 1e-12);
  assert.equal(deflatedSharpe([Array(100).fill(0)], 0, 72, 1).value, null);
  assert.equal(probabilityBacktestOverfit([[0], [1], [2]]).value, null);
});
test("actual study purges train/test labels, reports holdout reuse and never promotes", () => {
  const { data, protocol } = dataset(),
    r = runStudy(protocol, data, Date.now());
  assert.equal(r.rows.length, 9);
  assert(r.foldCount > 0);
  assert.equal(r.promotion, "NONE");
  assert(
    r.rows.every(
      (x) =>
        x.gates.untouchedHoldout === false &&
        x.gates.actualFutures === false &&
        x.gates.authenticatedExecution === false,
    ),
  );
  assert(r.selection.folds.every((f) => f.trainThrough < f.testFrom));
  assert(
    r.frequencyDiagnostics.every(
      (d) => d.through < data.sessions[protocol.trainSessions].open,
    ),
  );
});
test("registry locks data, consumes cumulative slots and forbids retuning or duplicate execution", async () => {
  const store = new MemoryStore(),
    lab = new ResearchLab(store, "X", new Validators(), DEFAULT_REPLAY_LIMITS),
    { data, protocol } = dataset();
  await lab.load();
  const t = await lab.register(protocol);
  await lab.importData(t.id, data);
  await assert.rejects(lab.importData(t.id, data));
  await lab.queue(t.id);
  await assert.rejects(lab.queue(t.id));
  await lab.tick();
  assert.equal(lab.export(t.id).trial.status, "COMPLETE");
  await assert.rejects(lab.queue(t.id));
  const reloaded = new ResearchLab(
    store,
    "X",
    new Validators(),
    DEFAULT_REPLAY_LIMITS,
  );
  await reloaded.load();
  assert.equal(reloaded.state.spent, 9);
});
test("registry survives actual SQLite reopen and rejects tampered protocol/chain", async () => {
  const { DurableStore } = require("../runtime/store30.cjs"),
    dir = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-ultimate-")),
    file = path.join(dir, "lab.sqlite");
  let store = await new DurableStore(file).open();
  const lab = new ResearchLab(
    store,
    "X",
    new Validators(),
    DEFAULT_REPLAY_LIMITS,
  );
  await lab.load();
  await lab.register(dataset().protocol);
  await store.close();
  store = await new DurableStore(file).open();
  const next = new ResearchLab(
    store,
    "X",
    new Validators(),
    DEFAULT_REPLAY_LIMITS,
  );
  await next.load();
  assert.equal(next.state.trials.length, 1);
  const raw = await store.get("ultimate-lab-X");
  raw.chain[0].valueHash = "tamper";
  await store.put("ultimate-lab-X", raw);
  await assert.rejects(
    new ResearchLab(store, "X", new Validators(), DEFAULT_REPLAY_LIMITS).load(),
    /integrity/,
  );
  await store.close();
  fs.rmSync(dir, { recursive: true });
});
test("registry has a cumulative stop rule and cannot understate total multiplicity", async () => {
  const lab = new ResearchLab(
      new MemoryStore(),
      "X",
      new Validators(),
      DEFAULT_REPLAY_LIMITS,
    ),
    p = dataset().protocol;
  await lab.load();
  await assert.rejects(lab.register({ ...p, familyTrials: 9 }), /cumulative/);
  for (let i = 0; i < 8; i++) await lab.register(p);
  await assert.rejects(lab.register(p), /exhausted/);
});
test("restart interrupts a queued attempt instead of silently recomputing", async () => {
  const store = new MemoryStore(),
    lab = new ResearchLab(store, "X", new Validators(), DEFAULT_REPLAY_LIMITS);
  await lab.load();
  const t = await lab.register(dataset().protocol);
  await lab.importData(t.id, dataset().data);
  await lab.queue(t.id);
  const next = new ResearchLab(
    store,
    "X",
    new Validators(),
    DEFAULT_REPLAY_LIMITS,
  );
  await next.load();
  assert.equal(next.export(t.id).trial.status, "INTERRUPTED");
});
test("future contract forbids continuous symbols, mismatched roots and delivery deadlines", () => {
  assertContract(futureContract());
  for (const c of [
    { ...futureContract(), symbol: "MES" },
    { ...futureContract(), root: "MNQ" },
    { ...futureContract(), lastTradeAt: Date.now() },
    { ...futureContract(), root: "MGC", symbol: "XCEC:MGC.Z27" },
  ])
    assert.throws(() => assertContract(c));
});
test("MNQ 30 point risk on USD20000 at 0.25 percent permits zero contracts", () => {
  const r = futuresSize({
    equity: 20000,
    available: 20000,
    entry: 20000,
    stop: 19970,
    root: "MNQ",
    margin: 2000,
    commission: 2,
    slippage: 1,
    cfg: config(),
  });
  assert.equal(r.quantity, 0);
  assert.equal(r.riskBudget, 50);
});
test("futures without credentials are NOT_CONFIGURED and cannot fabricate a plan", async () => {
  const f = new FuturesGateway(new MemoryStore(), config(), new Validators());
  await f.load();
  await f.refreshAccount();
  assert.equal(f.view().account.state, "NOT_CONFIGURED");
  assert.throws(() => f.plan({ symbol: "MES", side: "BUY" }));
});
async function gateway(fail = false, commission = 2) {
  const store = new MemoryStore(),
    api = new SyntheticIronbeam();
  api.failSubmit = fail;
  const f = new FuturesGateway(
    store,
    config(),
    new Validators(),
    api,
    "PAPER123",
    [futureContract()],
    true,
    commission,
  );
  await f.load();
  await f.refreshAccount();
  await f.refreshMarket();
  return { f, api, store };
}
test("futures validates fresh entitlement, loss gates and tick precision", async () => {
  const { f, api } = await gateway();
  assert(
    f.plan({ symbol: "XCME:MES.Z27", side: "BUY", stop: 99, target: 104 })
      .quantity > 0,
  );
  assert.throws(() =>
    f.plan({ symbol: "XCME:MES.Z27", side: "BUY", stop: 99.1, target: 104 }),
  );
  api.stale = true;
  await assert.rejects(f.refreshMarket(), /fresh quotes/);
  assert.throws(() =>
    f.plan({ symbol: "XCME:MES.Z27", side: "BUY", stop: 99, target: 104 }),
  );
});
test("uncertain futures submission is durable and never resent", async () => {
  const { f, api } = await gateway(true);
  const order = {
    id: "unique-paper-order",
    symbol: "XCME:MES.Z27",
    side: "BUY",
    stop: 99,
    target: 104,
    confirmation: "SEND_IRONBEAM_PAPER_BRACKET",
  };
  const i = await f.place(order);
  assert.equal(i.state, "UNKNOWN");
  await f.place(order);
  assert.equal(api.posts, 1);
  await assert.rejects(
    f.place({ ...order, id: "different-paper-id" }),
    /uncertain/,
  );
});
test("acknowledgment is not a fill; fills and partials come from reconciliation", async () => {
  const { f, api } = await gateway();
  const i = await f.place({
    id: "acknowledged-id1",
    symbol: "XCME:MES.Z27",
    side: "BUY",
    stop: 99,
    target: 104,
    confirmation: "SEND_IRONBEAM_PAPER_BRACKET",
  });
  assert.equal(i.state, "PENDING_ACK");
  api.orders[0].status = "PARTIALLY_FILLED";
  api.orders[0].fillQuantity = 1;
  await f.refreshAccount();
  assert.equal(f.view().intents[0].state, "PARTIALLY_FILLED");
});
test("unknown all-in commission prevents any futures submission", async () => {
  const { f, api } = await gateway(false, null);
  await assert.rejects(
    f.place({
      id: "commission-id01",
      confirmation: "SEND_IRONBEAM_PAPER_BRACKET",
    }),
    /commission/,
  );
  assert.equal(api.posts, 0);
});
test("Ironbeam transport fixes PAPER host, sends authorization and propagates failure", async () => {
  const calls = [],
    transport = async (url, opts) => {
      calls.push({ url, opts });
      return new Response(
        JSON.stringify(
          url.endsWith("/auth")
            ? { status: "OK", token: "synthetic-token-for-test" }
            : { status: "OK", positions: [] },
        ),
        { status: 200 },
      );
    };
  const api = new IronbeamPaperApi("test", "", "secret-test-only", transport);
  await api.request("/account/PAPER123/positions");
  assert(
    calls.every((c) => c.url.startsWith("https://demo.ironbeamapi.com/v2/")),
  );
  assert.equal(
    calls[1].opts.headers.Authorization,
    "Bearer synthetic-token-for-test",
  );
  assert(!JSON.stringify(api.metrics).includes("secret-test-only"));
  await assert.rejects(
    new IronbeamPaperApi(
      "test",
      "",
      "key",
      async () => new Response("", { status: 403 }),
    ).request("/account/PAPER123/positions"),
    /403/,
  );
});
test("API connection defaults to automatic PAPER and explicit operator opt-out persists", async () => {
  assert.equal(paperAutostart(undefined), true);
  assert.equal(paperAutostart("1"), true);
  assert.equal(paperAutostart("0"), false);
  assert.throws(() => paperAutostart("yes"));
  const { e, store, api } = await ready();
  await e.control("pause");
  const { Coordinator } = require("../runtime30/coordinator.js"),
    next = new Coordinator(store, api, config());
  await next.initialize(paperAutostart());
  assert.equal(next.state.paused, true);
});
test("autopilot exits and native protection run with entry and research pauses", async () => {
  const { e, api } = await ready();
  const s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  await e.control("pause");
  await e.control("research-pause", { paused: true });
  const before = api.posts().length;
  e.market.quotes.AAPL = {
    bid: 95,
    ask: 95.1,
    at: Date.now(),
    received: Date.now(),
  };
  await e.pulse();
  assert(
    api
      .posts()
      .slice(before)
      .some((x) => x.body.side === "sell" && x.body.type === "market"),
  );
  assert.equal(e.view().autopilot.protectionActiveWhenPaused, true);
});
test("research worker does not block an independent async heartbeat", async () => {
  const lab = new ResearchLab(
      new MemoryStore(),
      "X",
      new Validators(),
      DEFAULT_REPLAY_LIMITS,
    ),
    { data, protocol } = dataset();
  await lab.load();
  const t = await lab.register(protocol);
  await lab.importData(t.id, data);
  await lab.queue(t.id);
  let beats = 0;
  const timer = setInterval(() => beats++, 1);
  await lab.tick();
  clearInterval(timer);
  assert(beats > 2);
  assert.equal(lab.export(t.id).trial.status, "COMPLETE");
});
test("Ultimate HTTP requires authentication and explicit JSON action, including export", async () => {
  const { e } = await ready(),
    app = server(e, "x".repeat(40), "<html></html>", "http://127.0.0.1");
  await new Promise((r) => app.listen(0, "127.0.0.1", r));
  const origin = "http://127.0.0.1:" + app.address().port,
    headers = {
      Authorization:
        "Basic " + Buffer.from("trader:" + "x".repeat(40)).toString("base64"),
      "Content-Type": "application/json",
      "X-Harpoon-Action": "1",
    };
  try {
    assert.equal((await fetch(origin + "/v1/ultimate")).status, 401);
    const r = await fetch(origin + "/v1/ultimate", {
      method: "POST",
      headers,
      body: JSON.stringify({
        action: "register",
        protocol: dataset().protocol,
      }),
    });
    const t = await r.json();
    assert.equal(r.status, 201, JSON.stringify(t));
    assert.equal(
      (await fetch(origin + "/v1/ultimate/export?id=" + t.id, { headers }))
        .status,
      200,
    );
    assert.equal(
      (
        await fetch(origin + "/v1/ultimate", {
          method: "POST",
          headers,
          body: JSON.stringify({ action: "promote" }),
        })
      ).status,
      400,
    );
  } finally {
    await new Promise((r) => app.close(r));
  }
});
