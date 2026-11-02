"use strict";
// Synthetic numerical/lifecycle fixtures only. Not proof of financial acceptance.
const test = require("node:test"),
  assert = require("node:assert/strict"),
  fs = require("node:fs"),
  os = require("node:os"),
  path = require("node:path");
const {
    ready,
    MemoryStore,
    FakeBroker,
    config,
  } = require("./xxx_fixtures.cjs"),
  { Coordinator } = require("../runtime30/coordinator.js"),
  { assertSelectorModel } = require("../runtime30/validators.js"),
  { fitRows } = require("../runtime/selector30.cjs"),
  { DurableStore } = require("../runtime/store30.cjs");
const feature = (book = "equity", n = 0) => ({
  symbol: book === "equity" ? "AAPL" : "SPY",
  book,
  bar_end: new Date(Date.now() - 90000).toISOString(),
  bid: 100,
  ask: 100.01,
  atr: 1,
  rvol: 1 + n * 0.002,
  momentum_bps: 20 + (n % 11),
  spread_bps: 1,
  volume_acceleration: 1.2,
  atr_pct: 0.01,
  vwap_distance: 0.2,
  sector_relative_bps: 15 + (n % 9),
  session_minutes: 40 + (n % 120),
});
function data(book = "equity") {
  const now = Date.now() - 100000,
    day = new Date(now).toISOString().slice(0, 10);
  return {
    source: "SYNTHETIC_TEST",
    samples: [
      {
        id: "sample-1",
        at: new Date(now).toISOString(),
        feature: {
          ...feature(book),
          bar_end: new Date(now - 60000).toISOString(),
        },
        day,
      },
    ],
    events: [
      {
        id: "event-1",
        kind: "COTIZACIONES",
        at: new Date(now).toISOString(),
        data: {
          quotes: [[book === "equity" ? "AAPL" : "SPY", now, 100, 100.01]],
        },
      },
    ],
    sessions: {
      [day]: {
        open: now - 20000000,
        close: now - 1,
        first: now - 20000000,
        last: now - 1,
        gap: 20000,
        market_return: 0.001,
      },
    },
  };
}
async function trial(book = "equity") {
  const x = await ready();
  const id = await x.e.selectors.register(book, {
    confirmed: true,
    dataUsd: 10,
    infraUsd: 5,
  });
  return { ...x, id };
}
function rows() {
  const start = Date.now() - 100 * 86400000;
  return Array.from({ length: 480 }, (_, n) => {
    const at = start + Math.floor(n / 8) * 86400000 + (n % 8) * 600000;
    return {
      at,
      end: at + 300000,
      day: new Date(at).toISOString().slice(0, 10),
      feature: feature("equity", n),
      target: 0.4 + (n % 11) * 0.03,
    };
  });
}
test("Ridge registration binds actual catalog recipe, risk policy, costs and server timestamp", async () => {
  const { e, id } = await trial();
  const t = e.selectors.trial(id);
  assert.equal(t.recipe.selection_filter, "ridge_lcb");
  assert.equal(t.reference.selection_filter, "none");
  assert.equal(t.cfg.risk_pct, e.cfg.riskFraction);
  assert.equal(t.cfg.capital_limit, e.cfg.capitalLimit);
  assert.equal(t.cfg.xi.external_costs_confirmed, true);
  assert(Date.now() - Date.parse(t.registered_at) < 1000);
  assert.equal(t.binding, e.selectors.binding());
  await assert.rejects(e.selectors.register("__proto__"));
  await assert.rejects(e.selectors.register("equity"), /active trial/);
});
test("selector data rejects future, cross-book, duplicate events and invalid feature values", async () => {
  const { e, id } = await trial();
  for (const mutate of [
    (x) => (x.samples[0].at = new Date(Date.now() + 1e6).toISOString()),
    (x) => (x.samples[0].feature.book = "etf"),
    (x) => (x.samples[0].feature.rvol = null),
    (x) => x.events.push(x.events[0]),
    (x) => (x.events[0].data.quotes[0][2] = 101),
  ]) {
    const x = data();
    mutate(x);
    await assert.rejects(e.selectors.importData(id, x));
  }
  assert(e.validators.checks["selector-dataset"].failed >= 5);
});
test("historical import is immutable and idempotent; synthetic provenance is retained", async () => {
  const { e, id } = await trial(),
    d = data();
  const first = await e.selectors.importData(id, d),
    second = await e.selectors.importData(id, d);
  assert.equal(first.hash, second.hash);
  assert.equal(first.source, "SYNTHETIC_TEST");
  d.events[0].data.quotes[0][2] = 99;
  await assert.rejects(e.selectors.importData(id, d), /immutable/);
  const out = await e.selectors.dataset(id);
  assert.equal(out.prospectiveVerified, false);
  assert.equal(out.source, "SYNTHETIC_TEST");
});
test("operator imports after the registered cutoff cannot manufacture prospective observations", async () => {
  const { e, id } = await trial();
  e.selectors.trial(id).registered_at = new Date(
    Date.now() - 200000,
  ).toISOString();
  await e.selectors.importData(id, data());
  const d = await e.selectors.dataset(id);
  assert.equal(d.samples.length, 0);
  assert.equal(d.events.length, 0);
  assert.equal(d.prospectiveVerified, false);
});
test("capture persists actual supplied quote tuples and never creates prices without observations", async () => {
  const { e, id, store } = await trial(),
    now = Date.now(),
    day = e.plugins.legacy.ny(now).day;
  e.market.calendar = [{ date: day, open: now - 100000, close: now + 100000 }];
  e.market.quotes.SPY = { bid: 200, ask: 200.01, at: now, received: now };
  e.market.quotes.AAPL = { bid: 100, ask: 100.01, at: now, received: now };
  await e.selectors.capture(e.market, [feature()], { is_open: true }, now);
  const d = await e.selectors.dataset(id);
  assert(
    d.events.some((x) =>
      x.data.quotes.some((q) => q[0] === "AAPL" && q[2] === 100),
    ),
  );
  assert.equal(e.selectors.state.events, 1);
  assert.equal(e.selectors.view().capturedSamples, 1);
  await e.selectors.capture(
    e.market,
    [feature()],
    { is_open: true },
    now + 1000,
  );
  assert.equal(e.selectors.state.events, 1);
  delete e.market.quotes.SPY;
  await e.selectors.capture(
    e.market,
    [feature()],
    { is_open: true },
    now + 30000,
  );
  assert.equal(e.selectors.state.events, 1);
  assert([...store.data.keys()].some((k) => k.includes("-sample-")));
});
test("actual Ridge fitter computes finite coefficients and purges labels crossing cutoff", () => {
  const r = rows(),
    cutoff = Date.now() - 30 * 86400000,
    m = fitRows(r, cutoff);
  assertSelectorModel(m);
  assert.equal(m.n, 480);
  assert.equal(m.days, 60);
  assert(m.weights.some((x) => Math.abs(x) > 1e-6));
  const extra = { ...r[0], end: cutoff + 1, target: 19 };
  const purged = fitRows([...r, extra], cutoff);
  assert.deepEqual(
    JSON.parse(JSON.stringify(m)),
    JSON.parse(JSON.stringify(purged)),
  );
  assert.equal(fitRows(r.slice(0, 100), cutoff), null);
});
test("model validator rejects fabricated shape, feature drift and future training", () => {
  const m = fitRows(rows(), Date.now() - 30 * 86400000);
  for (const bad of [
    { ...m, weights: [1] },
    { ...m, features: ["price"] },
    { ...m, through: Date.now() + 1 },
    { ...m, n: 1 },
    { ...m, scales: [0, ...m.scales.slice(1)] },
  ])
    assert.throws(() => assertSelectorModel(bad));
});
test("selector worker runs real research and reports insufficient evidence instead of successful training", async () => {
  const { e, id, api } = await trial();
  await e.selectors.importData(id, data());
  await e.queueResearch({
    operation: "selector",
    trialId: id,
    diagnostic: true,
    report: { status: "ACEPTADA" },
  });
  assert.equal(
    e.pendingResearch.selectorInput.trial.recipe.selection_filter,
    "ridge_lcb",
  );
  assert.equal(e.pendingResearch.selectorInput.prospectiveVerified, false);
  await e.research();
  assert.equal(e.state.research.status, "COMPLETE", e.state.research.error);
  const t = e.selectors.trial(id);
  assert.equal(t.status, "WAIT_DATA");
  assert.equal(t.report.status, "EVIDENCIA_INSUFICIENTE");
  assert.equal(t.report.trainingLabels, 0);
  assert.equal(e.state.research.runs, 1);
  assert.equal(api.posts().length, 0);
  assert.deepEqual(e.selectors.state.models, {});
  await assert.rejects(e.selectors.install(id, "INSTALAR SELECTOR PAPER"));
});
test("install rejects synthetic, non-prospective and incomplete acceptance reports", async () => {
  const { e, id, store } = await trial(),
    t = e.selectors.trial(id);
  t.status = "READY_TO_INSTALL";
  for (const result of [
    {
      schema: "HARPOON-SELECTOR-30-1",
      report: { status: "ACEPTADA", gates: {} },
      source: "SYNTHETIC_TEST",
      prospectiveVerified: true,
    },
    {
      report: { status: "ACEPTADA", diagnostic_only: false, gates: {} },
      source: "ALPACA_OBSERVED",
      prospectiveVerified: false,
    },
    {
      report: { status: "ACEPTADA", diagnostic_only: false, gates: {} },
      source: "ALPACA_OBSERVED",
      prospectiveVerified: true,
    },
  ]) {
    await store.put(
      e.key.replace("xxx-", "selector30-") + "-report-" + id,
      result,
    );
    await assert.rejects(
      e.selectors.install(id, "INSTALAR SELECTOR PAPER"),
      /prospective report/,
    );
  }
  assert.deepEqual(e.selectors.state.models, {});
  await assert.rejects(e.selectors.install(id, "yes"), /confirmation/);
});
test("retirement and model revocation actually update persistent state", async () => {
  const { e, id, store } = await trial();
  e.selectors.state.models.equity = { trialId: id };
  await e.selectors.retire(id);
  assert.equal(e.selectors.trial(id).status, "RETIRED");
  assert.equal(e.selectors.state.models.equity, undefined);
  await e.selectors.revoke("etf");
  assert.equal(
    (await store.get("selector30-" + e.cfg.expected_account_id)).trials[0]
      .status,
    "RETIRED",
  );
});
test("interrupted queued trial recovers durably and preserves account binding after restart", async () => {
  const { e, id, store, api } = await trial();
  e.selectors.trial(id).status = "QUEUED";
  await e.selectors.save();
  const next = new Coordinator(store, api, e.cfg);
  await next.initialize();
  assert.equal(next.selectors.trial(id).status, "INTERRUPTED");
  assert.equal(
    (await store.get("selector30-" + e.cfg.expected_account_id)).trials[0]
      .status,
    "INTERRUPTED",
  );
});
test("dataset preparation cannot hold broker authority while SQLite scans run", async () => {
  const { e, id } = await trial();
  let release;
  const original = e.selectors.dataset.bind(e.selectors);
  e.selectors.dataset = async (x) => {
    await new Promise((r) => (release = r));
    return original(x);
  };
  const queued = e.queueResearch({ operation: "selector", trialId: id });
  await new Promise((r) => setImmediate(r));
  let exited = false;
  await e.mutex.run(0, async () => {
    exited = true;
  });
  assert.equal(exited, true);
  await assert.rejects(
    e.queueResearch({ operation: "selector", trialId: id }),
    /busy/,
  );
  release();
  await queued;
  assert.equal(e.pendingResearch.operation, "selector");
});
test("selector data persists through real SQLite scans and process reopen", async () => {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "xxx-selector-")),
    db = path.join(dir, "state.sqlite"),
    cfg = config();
  let store = await new DurableStore(db).open();
  const e = new Coordinator(store, new FakeBroker(), cfg);
  try {
    await e.initialize();
    const id = await e.selectors.register("etf");
    await e.selectors.importData(id, data("etf"));
    await store.put(
      "selector30-" + cfg.expected_account_id + "-sample-observed",
      { id: "observed", at: new Date().toISOString(), feature: feature("etf") },
    );
    await store.lease(e.leaseName, true);
    await store.close();
    store = await new DurableStore(db).open();
    const next = new Coordinator(store, new FakeBroker(), cfg);
    await next.initialize();
    const d = await next.selectors.dataset(id);
    assert.equal(d.samples.length, 2);
    assert.equal(d.source, "SYNTHETIC_TEST");
    await store.lease(next.leaseName, true);
  } finally {
    await store.close();
    fs.rmSync(dir, { recursive: true, force: true });
  }
});
test("an invalid optional model is revoked on restart without preventing position supervision", async () => {
  const { e, store, api } = await ready();
  e.selectors.state.models.equity = {
    model: { weights: [1] },
    binding: "changed",
  };
  await e.selectors.save();
  const next = new Coordinator(store, api, e.cfg);
  await next.initialize();
  assert.equal(next.selectors.state.models.equity, undefined);
  assert.equal(next.selectors.state.status, "MODEL_INVALIDATED");
  assert.equal(next.reconcileError, "");
  assert(next.syncAt > 0);
  assert.equal(
    (await store.get("selector30-" + e.cfg.expected_account_id)).models.equity,
    undefined,
  );
});
test("installation persistence and evaluation boundary work with an explicit internal acceptance test double", async () => {
  // Financial acceptance is injected ONLY inside this isolated unit test. The fitter is real.
  const { e, id, store, api } = await trial(),
    t = e.selectors.trial(id),
    m = fitRows(rows(), Date.now() - 30 * 86400000),
    holdoutEnd = new Date(Date.now() - 86400000).toISOString().slice(0, 10);
  const gates = Object.fromEntries(
    [
      "integer_event_model",
      "same_risk",
      "prospective_holdout",
      "annual_oos",
      "oos_samples",
      "holdout_samples",
      "selector_fitted",
      "positive_net",
      "net_improvement",
      "holdout_improvement",
      "holdout_positive",
      "sharpe_minimum",
      "sharpe_improvement",
      "sortino_improvement",
      "alpha_improvement",
      "alpha_positive",
      "drawdown",
      "stable_folds",
      "stress_oos",
      "stress_holdout",
      "dsr_oos",
      "dsr_holdout",
      "neighbors_positive",
      "external_costs_declared",
      "net_economic_positive",
    ].map((k) => [k, true]),
  );
  e.selectors.state.sessions[holdoutEnd] = { close: Date.now() - 86400000 };
  t.status = "READY_TO_INSTALL";
  await store.put("selector30-" + e.cfg.expected_account_id + "-report-" + id, {
    schema: "HARPOON-SELECTOR-30-1",
    source: "CONTROLLED_INTERNAL_ACCEPTANCE_TEST_DOUBLE",
    prospectiveVerified: true,
    report: {
      status: "ACEPTADA",
      diagnostic_only: false,
      gates,
      folds: Array.from({ length: 12 }, (_, n) => ({ index: n })),
      candidate: { sessions: 252 },
      holdout: { sessions: 63 },
      holdout_end: holdoutEnd,
      frozen_selector: m,
    },
  });
  const selection = [...e.state.plugins];
  await e.control("selector-install", {
    trialId: id,
    confirmation: "INSTALAR SELECTOR PAPER",
  });
  assert.deepEqual(e.state.plugins, selection);
  assert.equal(
    e.view().plugins.find((p) => p.id === t.plugin).modelReady,
    true,
  );
  assert.equal(
    e.plugins.legacy.HXII.selection(
      feature(),
      e.plugins.selectors.equity.model,
      Date.now(),
    ).eligible,
    true,
  );
  const next = new Coordinator(store, api, e.cfg);
  await next.initialize();
  assert.equal(next.selectors.state.models.equity.model.n, 480);
  assert.equal(
    next.view().plugins.find((p) => p.id === t.plugin).modelReady,
    true,
  );
  await next.control("selector-revoke", { book: "equity" });
  assert.equal(
    next.view().plugins.find((p) => p.id === t.plugin).modelReady,
    false,
  );
  assert.equal(api.posts().length, 0);
});
test("a sufficiently observed prospective holdout is consumed even by diagnostic inspection", async () => {
  const { e, id } = await trial(),
    start = Date.now() - 500 * 86400000,
    sessions = {};
  for (let n = 0; n < 384; n++) {
    const open = start + n * 86400000,
      day = new Date(open).toISOString().slice(0, 10);
    sessions[day] = {
      open,
      close: open + 20000000,
      first: open,
      last: open + 20000000,
      gap: 20000,
      market_return: 0.001,
    };
  }
  e.selectors.dataset = async () => ({
    sessions,
    samples: Array.from({ length: 1000 }, (_, id) => ({ id })),
    events: [{ id: "controlled" }],
    source: "CONTROLLED_UNIT_DATA",
    prospectiveVerified: true,
  });
  const a = await e.selectors.prepare(id, true);
  assert.equal(a.selectorInput.diagnostic, true);
  const consumed = e.selectors.state.sealedThrough.equity;
  assert(consumed);
  e.selectors.trial(id).status = "WAIT_DATA";
  await assert.rejects(e.selectors.prepare(id, false), /already consumed/);
});
test("actual selector worker evaluates all 12 folds and holdout on complete synthetic no-fill paths", async () => {
  const { e, id, api } = await trial(),
    samples = [],
    events = [],
    sessions = {},
    start = Date.now() - 500 * 86400000;
  for (let n = 0; n < 384; n++) {
    const day = new Date(start + n * 86400000).toISOString().slice(0, 10),
      open = e.plugins.legacy.HX.nyTime(day, "09:30"),
      close = e.plugins.legacy.HX.nyTime(day, "16:00");
    sessions[day] = {
      open,
      close,
      first: open,
      last: close,
      gap: 20000,
      market_return: ((n % 7) - 3) * 0.001,
    };
    for (let k = 0; k < 3; k++) {
      const at = open + (30 + 60 * k) * 60000;
      samples.push({
        id: "full-" + n + "-" + k,
        day,
        at: new Date(at).toISOString(),
        feature: {
          ...feature("equity", n),
          base: 99.5,
          perf5: 0.02,
          rvol: 3,
          momentum_bps: 50,
          factor: "technology",
          leverage: 1,
          bar_end: new Date(at - 60000).toISOString(),
        },
      });
      const received = at + 31000;
      events.push({
        id: "q-" + n + "-" + k,
        kind: "COTIZACIONES",
        at: new Date(received).toISOString(),
        data: { quotes: [["AAPL", received, 101, 101.01]] },
      });
    }
  }
  await e.selectors.importData(id, {
    source: "SYNTHETIC_TEST",
    samples,
    events,
    sessions,
  });
  await e.queueResearch({
    operation: "selector",
    trialId: id,
    diagnostic: true,
  });
  await e.research();
  assert.equal(e.state.research.status, "COMPLETE", e.state.research.error);
  const r = await e.store.get(
    "selector30-" + e.cfg.expected_account_id + "-report-" + id,
  );
  assert.equal(r.source, "SYNTHETIC_TEST");
  assert.equal(r.report.status, "RECHAZADA");
  assert.equal(r.report.folds.length, 12);
  assert.equal(r.report.candidate.sessions, 252);
  assert.equal(r.report.holdout.sessions, 63);
  assert.equal(r.report.gates.selector_fitted, false);
  assert.equal(r.report.gates.positive_net, false);
  assert.equal(api.posts().length, 0);
  assert.equal(e.selectors.state.models.equity, undefined);
});
