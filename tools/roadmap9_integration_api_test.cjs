"use strict";
// SYNTHETIC_ENGINEERING_ONLY: real local HTTP/SQLite/Python, no broker adapter.
const test = require("node:test");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const { DurableStore } = require("../runtime/store30.cjs");
const { Coordinator } = require("../runtime30/coordinator.js");
const { server } = require("../runtime30/server.js");
const { config } = require("./xxx_fixtures.cjs");
const { OfflineRoadmap } = require("../runtime/roadmap9_bridge.cjs");
const { fixture } = require("./roadmap9_integration_fixture.cjs");

const PASSWORD = "synthetic-offline-panel-password-at-least-32";
const ROUTE = "/v1/roadmap9/offline";
const ORIGIN = "SYNTHETIC_ENGINEERING_ONLY";

async function setup(enabled = true) {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-roadmap-http-"));
  const store = await new DurableStore(path.join(directory, "session.sqlite")).open();
  let brokerCalls = 0;
  const noBroker = { async request() { brokerCalls++; throw Error("BROKER_FORBIDDEN_IN_OFFLINE_TEST"); } };
  const engine = new Coordinator(store, noBroker, config());
  let app;
  const start = async () => {
    app = server(engine, PASSWORD, "<html></html>", undefined, { roadmap9Offline: enabled });
    await new Promise((resolve, reject) => { app.once("error", reject); app.listen(0, "127.0.0.1", resolve); });
  };
  await start();
  return {
    directory, store, engine,
    get brokerCalls() { return brokerCalls; },
    async call(command, overrides = {}) {
      const method = overrides.method || (command === undefined ? "GET" : "POST");
      const headers = {
        authorization: "Basic " + Buffer.from("trader:" + PASSWORD).toString("base64"),
        "content-type": "application/json", "x-harpoon-action": "1", ...overrides.headers,
      };
      if (overrides.authenticated === false) delete headers.authorization;
      const raw = overrides.raw === undefined
        ? JSON.stringify({ origin: ORIGIN, command }) : overrides.raw;
      const response = await fetch("http://127.0.0.1:" + app.address().port + ROUTE, {
        method, headers, ...(method === "GET" ? {} : { body: raw }),
      });
      return { status: response.status, body: await response.json() };
    },
    async restart() {
      app.closeAllConnections();
      await new Promise(resolve => app.close(resolve));
      await start();
    },
    async close() {
      app.closeAllConnections();
      await new Promise(resolve => app.close(resolve));
      await store.close();
      fs.rmSync(directory, { recursive: true, force: true });
      assert.equal(brokerCalls, 0, "offline route must never call the injected broker interface");
    },
  };
}

test("HTTP guards require opt-in, authentication, origin and bounded explicit JSON", async () => {
  const disabled = await setup(false);
  try {
    assert.equal((await disabled.call()).status, 404);
    assert.equal((await disabled.call(undefined, { authenticated: false })).status, 401);
  } finally { await disabled.close(); }
  const api = await setup();
  try {
    const init = { kind: "INIT", command_id: "guard:init" };
    assert.equal((await api.call(init, { authenticated: false })).status, 401);
    assert.equal((await api.call(init, { headers: { origin: "https://foreign.invalid" } })).status, 403);
    assert.equal((await api.call(init, { headers: { "x-harpoon-action": "0" } })).status, 403);
    assert.equal((await api.call(init, { headers: { "content-type": "text/plain" } })).status, 403);
    assert.equal((await api.call(init, { raw: "{" })).status, 400);
    assert.equal((await api.call(init, { raw: "null" })).status, 422);
    assert.equal((await api.call(init, { raw: JSON.stringify({ origin: "OBSERVED", command: init }) })).status, 422);
    assert.equal((await api.call({ ...init, execution_allowed: true })).status, 422);
    assert.equal((await api.call({ ...init, received_at_ms: Date.now() })).status, 422);
    assert.equal((await api.call(init, { raw: JSON.stringify({ origin: ORIGIN, command: init, session: {} }) })).status, 422);
    assert.equal((await api.call(init, { raw: JSON.stringify({ padding: "x".repeat(1024 * 1024) }) })).status, 413);
    assert.equal(await api.store.get("ROADMAP9_OFFLINE:" + api.engine.key), null);
  } finally { await api.close(); }
});

test("offline bridge refuses a store without compare-and-swap", () => {
  assert.throws(() => new OfflineRoadmap({ get: async () => null, put: async () => true }, "x"), /COMPARE_AND_SWAP/);
});

async function accepted(api, command) {
  const result = await api.call(command);
  assert.equal(result.status, 200, (command?.kind || "GET") + ":" + JSON.stringify(result.body));
  assert.equal(result.body.execution_allowed, false);
  assert.equal(result.body.orders_allowed, false);
  assert.equal(result.body.financial_acceptance_allowed, false);
  assert.equal(result.body.real_fills_present, false);
  return result.body;
}
const inventory = view => Object.fromEntries(Object.entries(view.inventory_reconciliation)
  .map(([symbol, row]) => [symbol, row.execution_net_quantity]));
const reconciliation = (view, id) => ({ kind: "RECONCILE", command_id: id,
  balances: view.ledger.balances, inventory: inventory(view) });
async function seeded(api, crypto = false) {
  const f = fixture(Date.now(), crypto);
  await accepted(api, f.init);
  await accepted(api, f.market);
  const view = await accepted(api, f.predictor);
  return { f, view: await accepted(api, reconciliation(view, "seed:reconcile")) };
}
async function event(api, cid, kind, id, more = {}) {
  return accepted(api, { kind: "EVENT", command_id: "command:" + id,
    event: { kind, event_id: id, client_order_id: cid, ...more } });
}

test("HTTP lifecycle joins allocation, cancellation, late fill, restart, fee and exact equity", async () => {
  const api = await setup();
  try {
    const { f } = await seeded(api);
    let view = await accepted(api, { kind: "PLAN", command_id: "entry:plan", forecast: f.forecast });
    assert.equal(view.last_decision.decision.status, "OFFLINE_PROPOSAL");
    const [intent] = view.last_decision.simulated_intents;
    assert.equal(Number(intent.qty), 2);
    assert.equal(intent.simulated, true);
    const deadline = intent.deadline_at, cid = intent.client_order_id;
    await event(api, cid, "SUBMITTED", "entry:submitted");
    await event(api, cid, "ACK", "entry:ack", { broker_order_id: "SIMULATED-ENTRY-ORDER" });
    await event(api, cid, "CANCEL_REQUEST", "entry:cancel-request");
    const cancelAt = Date.now();
    view = await event(api, cid, "CANCEL_ACK", "entry:cancel-ack", { cumulative_qty: "2", executed_at: cancelAt });
    assert.equal(view.orders[cid].missing_fill_reports, true);
    await api.restart();
    view = await accepted(api);
    assert.equal(view.storage.recovery_required, true);
    assert.equal(view.alive, false);
    assert.equal(view.simulated_entries_ready, false);
    const fill = { kind: "EVENT", command_id: "entry:late-fill",
      event: { kind: "FILL", event_id: "entry:fill-receipt", client_order_id: cid,
        execution_id: "entry:execution", qty: "2", price: "100", liquidity_role: "taker",
        executed_at: cancelAt - 1, cumulative_qty: "2" } };
    view = await accepted(api, fill);
    assert.equal(view.inventory_reconciliation.AAPL.execution_net_quantity, "2");
    assert.equal(view.ledger.balances.USD, "19800");
    assert.equal(Number(view.ledger.pending_native_fees.USD), 0.21);
    const revision = view.storage.revision;
    const duplicate = await accepted(api, fill);
    assert.equal(duplicate.storage.revision, revision);
    assert.equal(duplicate.duplicate_command, true);
    assert.deepEqual(duplicate.ledger, view.ledger);
    view = await accepted(api, { kind: "FEE", command_id: "entry:fee", activity_type: "FEE",
      activity_id: "entry:fee-activity", fill_id: "entry:execution", fee_asset: "USD", total_fee: "0.21" });
    assert.equal(Number(view.ledger.balances.USD), 19799.79);
    assert.equal(Number(view.equity_usd), 19999.79);
    assert.equal(view.ledger.pending_fee_count, 0);
    view = await accepted(api, reconciliation(view, "recovery:reconciled"));
    assert.equal(view.storage.recovery_required, false);
    assert.equal(view.alive, true);
    assert.equal(view.campaigns.AAPL.original_deadline, deadline);
    assert.equal((await api.call(f.init)).status, 409, "INIT cannot reset a campaign or account");
    const before = view.ledger;
    assert.equal((await api.call({ ...f.predictor, command_id: "llm:override", llm: { execution_allowed: true } })).status, 422);
    view = await accepted(api, { ...f.predictor, command_id: "predictor:outage", ready: false });
    assert.deepEqual(view.ledger, before);
    assert.equal(view.simulated_entries_ready, false);
    assert.equal(view.health.owned_inventory_management, "REDUCTION_READY");
    view = await accepted(api, { kind: "REDUCE", command_id: "risk:reduce", symbol: "AAPL" });
    const reduction = view.last_decision.simulated_intents[0];
    assert.equal(reduction.side, "sell");
    assert.equal(Number(reduction.qty), 2);
    assert.equal(reduction.deadline_at, deadline);
  } finally { await api.close(); }
});

test("native CFEE after restart exposes reservation deficit and preserves corrected net inventory", async () => {
  const api = await setup();
  try {
    const { f } = await seeded(api, true);
    let view = await accepted(api, { ...f.predictor, command_id: "predictor:off", ready: false });
    const deadline = view.campaigns["BTC/USD"].original_deadline;
    assert.equal(view.inventory_reconciliation["BTC/USD"].available_native_quantity, "0.9975");
    assert.equal((await api.call({ kind: "REDUCE", command_id: "oversell", symbol: "BTC/USD", qty: "1" })).status, 422);
    view = await accepted(api, { kind: "REDUCE", command_id: "crypto:reduce", symbol: "BTC/USD" });
    const [intent] = view.last_decision.simulated_intents;
    assert.equal(Number(intent.qty), 0.9975);
    await event(api, intent.client_order_id, "SUBMITTED", "crypto:submit");
    await event(api, intent.client_order_id, "ACK", "crypto:ack", { broker_order_id: "SIMULATED-REDUCTION" });
    await api.restart();
    const fee = { kind: "FEE", command_id: "crypto:fee", activity_type: "CFEE", activity_id: "native-fee-1",
      fill_id: "opening-execution", fee_asset: "BTC", total_fee: "0.003" };
    view = await accepted(api, fee);
    const row = view.inventory_reconciliation["BTC/USD"];
    assert.equal(Number(row.gross_fill_quantity), 1);
    assert.equal(Number(row.posted_native_fee_quantity), 0.003);
    assert.equal(Number(row.execution_net_quantity), 0.997);
    assert.equal(Number(row.ledger_settled_quantity), 0.997);
    assert(view.simulation_blockers.includes("RESERVED_NATIVE_ASSET_DEFICIT"));
    assert.equal(view.alive, false);
    const duplicate = await accepted(api, fee);
    assert.equal(duplicate.storage.revision, view.storage.revision);
    assert.deepEqual(duplicate.inventory_reconciliation, view.inventory_reconciliation);
    await event(api, intent.client_order_id, "CANCEL_REQUEST", "crypto:cancel-request");
    view = await event(api, intent.client_order_id, "CANCEL_ACK", "crypto:cancel-ack", { cumulative_qty: "0", executed_at: Date.now() });
    view = await accepted(api, { kind: "FEE", command_id: "crypto:fee-correction", activity_type: "CFEE",
      activity_id: "native-fee-2", corrects_activity_id: "native-fee-1", fill_id: "opening-execution",
      fee_asset: "BTC", total_fee: "0.0028" });
    assert.equal(Number(view.inventory_reconciliation["BTC/USD"].execution_net_quantity), 0.9972);
    assert.equal(Number(view.inventory_reconciliation["BTC/USD"].posted_native_fee_quantity), 0.0028);
    view = await accepted(api, reconciliation(view, "crypto:reconciled"));
    assert.equal(view.storage.recovery_required, false);
    view = await accepted(api, { ...f.predictor, command_id: "predictor:on", ready: true });
    view = await accepted(api, { kind: "PLAN", command_id: "crypto:allocation-blocked", forecast: f.forecast });
    assert.equal(view.last_decision.decision.status, "BLOCKED");
    assert.equal(view.last_decision.simulated_intents.length, 0);
    view = await accepted(api, { ...f.predictor, command_id: "predictor:off-again", ready: false });
    view = await accepted(api, { kind: "REDUCE", command_id: "crypto:correct-reduction", symbol: "BTC/USD" });
    assert.equal(Number(view.last_decision.simulated_intents[0].qty), 0.9972);
    assert.equal(view.last_decision.simulated_intents[0].deadline_at, deadline);
  } finally { await api.close(); }
});

test("failed CAS and lost ACK preserve authoritative journal and require a new reconciliation", async () => {
  const api = await setup();
  try {
    const { f } = await seeded(api);
    const key = "ROADMAP9_OFFLINE:" + api.engine.key;
    const before = await api.store.get(key);
    const original = api.store.rpc.bind(api.store);
    api.store.rpc = async request => {
      if (request.op === "cas") throw Error("SYNTHETIC_DISK_FULL_BEFORE_COMMIT");
      return original(request);
    };
    assert.equal((await api.call({ ...f.market, command_id: "storage:failed" })).status, 503);
    assert.deepEqual(await api.store.get(key), before);
    assert.equal((await api.call({ kind: "PLAN", command_id: "must-not-plan", forecast: f.forecast })).status, 409);
    api.store.rpc = original;
    let view = await accepted(api);
    assert.equal(view.simulated_entries_ready, false);
    view = await accepted(api, reconciliation(view, "storage:reconciled"));
    assert.equal(view.storage.recovery_required, false);
    let once = true;
    api.store.rpc = async request => {
      const result = await original(request);
      if (request.op === "cas" && once) { once = false; throw Error("SYNTHETIC_ACK_LOST_AFTER_COMMIT"); }
      return result;
    };
    const changed = { ...f.market, command_id: "storage:committed-no-ack",
      quotes: f.market.quotes.map(q => ({ ...q, event_at_ms: Date.now() })) };
    assert.equal((await api.call(changed)).status, 503);
    api.store.rpc = original;
    const committed = await api.store.get(key);
    assert(committed.session.commands.some(c => c.command_id === changed.command_id));
    await api.restart();
    view = await accepted(api, changed);
    assert.equal(view.storage.revision, committed.revision);
    assert.equal(view.storage.recovery_required, true);
    assert.equal(view.simulated_entries_ready, false);
    assert.equal((await api.call({ kind: "RECONCILE", command_id: "wrong-balance", balances: { USD: "20001" }, inventory: { AAPL: "0" } })).status, 422);
    view = await accepted(api, reconciliation(view, "storage:confirmed-after-loss"));
    assert.equal(view.storage.recovery_required, false);
    assert.equal(view.ledger.balances.USD, "20000");
  } finally { await api.close(); }
});

test("two controllers cannot both commit the same prior session revision", async () => {
  const api = await setup();
  const controllers = [];
  try {
    const { view } = await seeded(api);
    controllers.push(new OfflineRoadmap(api.store, api.engine.key), new OfflineRoadmap(api.store, api.engine.key));
    const result = await Promise.allSettled(controllers.map((controller, i) =>
      controller.request({ origin: ORIGIN, command: reconciliation(view, "race:" + i) })));
    assert.equal(result.filter(r => r.status === "fulfilled").length, 1);
    const failed = result.find(r => r.status === "rejected");
    assert.equal(failed.reason.code, "ROADMAP9_COMPARE_AND_SWAP_CONFLICT");
    let after = await accepted(api);
    assert.equal(after.storage.recovery_required, true);
    assert.equal(after.simulated_entries_ready, false);
    after = await accepted(api, reconciliation(after, "race:authoritative-reconciled"));
    assert.equal(after.storage.recovery_required, false);
    assert.equal(after.ledger.balances.USD, "20000");
  } finally { controllers.forEach(c => c.close()); await api.close(); }
});

test("observed cost or calendar contract changes cannot be cleared by balance reconciliation", async () => {
  for (const contract of ["COST", "CALENDAR"]) {
    const api = await setup();
    try {
      const { f, view: before } = await seeded(api);
      let view = await accepted(api, { kind: "CONTRACT_CHANGE", command_id: "contract:" + contract,
        symbol: "AAPL", contract, observed_hash: "b".repeat(64) });
      assert.deepEqual(view.ledger, before.ledger);
      assert.equal(view.simulated_entries_ready, false);
      assert(view.simulation_blockers.includes("CONTRACT_CHANGED:" + contract + ":AAPL"));
      view = await accepted(api, reconciliation(view, "contract:account-reconciled"));
      assert.equal(view.simulated_entries_ready, false);
      const blocked = await api.call({ kind: "PLAN", command_id: "contract:no-plan", forecast: f.forecast });
      assert.equal(blocked.status, 422);
      assert(blocked.body.error.includes("CONTRACT_CHANGED:" + contract));
      assert.equal((await api.call({ ...f.init, command_id: "contract:no-reset" })).status, 409);
    } finally { await api.close(); }
  }
});

test("worker timeout cannot acknowledge mutation or revive entries after process restart", async () => {
  const api = await setup();
  const previous = process.env.HARPOON_QUANT_PYTHON;
  try {
    const { f } = await seeded(api);
    const key = "ROADMAP9_OFFLINE:" + api.engine.key;
    const before = await api.store.get(key);
    const program = path.join(api.directory, "stall-worker");
    fs.writeFileSync(program, "#!/usr/bin/python3\nimport time\ntime.sleep(30)\n", { mode: 0o700 });
    process.env.HARPOON_QUANT_PYTHON = program;
    await api.restart();
    const started = performance.now();
    const response = await api.call({ ...f.market, command_id: "timeout:market" });
    assert.equal(response.status, 503);
    assert.equal(response.body.error, "ROADMAP9_WORKER_TIMEOUT");
    assert(performance.now() - started >= 7900);
    assert.deepEqual(await api.store.get(key), before);
    if (previous === undefined) delete process.env.HARPOON_QUANT_PYTHON;
    else process.env.HARPOON_QUANT_PYTHON = previous;
    await api.restart();
    let view = await accepted(api);
    assert.equal(view.storage.recovery_required, true);
    assert.equal(view.simulated_entries_ready, false);
    assert.equal((await api.call({ kind: "PLAN", command_id: "timeout:no-new-risk", forecast: f.forecast })).status, 409);
    view = await accepted(api, { ...f.market, command_id: "timeout:new-market", quotes: f.market.quotes.map(q => ({ ...q, event_at_ms: Date.now() })) });
    view = await accepted(api, reconciliation(view, "timeout:confirmed-reconciled"));
    assert.equal(view.storage.recovery_required, false);
    assert.equal(view.ledger.balances.USD, "20000");
  } finally {
    if (previous === undefined) delete process.env.HARPOON_QUANT_PYTHON;
    else process.env.HARPOON_QUANT_PYTHON = previous;
    await api.close();
  }
});

async function boundaryPosition(api, base, deadline, predictorClock) {
  const f = fixture(base);
  f.init.opening_events = fixture(base, true).init.opening_events.map(row => ({ ...row,
    ...(row.kind === "INTENT" ? { symbol: "AAPL", deadline_at: deadline } : {}) }));
  if (predictorClock) {
    f.predictor[predictorClock.field] = predictorClock.at;
    f.forecast[predictorClock.field === "model_trained_at_ms" ? "model_asof" : "latest_label_at"] =
      new Date(predictorClock.at).toISOString();
    if (predictorClock.field === "model_trained_at_ms") {
      // Training cannot predate the labels used by that model.
      f.predictor.latest_label_at_ms = predictorClock.at;
      f.forecast.latest_label_at = new Date(predictorClock.at).toISOString();
    }
  }
  await accepted(api, f.init);
  await accepted(api, f.market);
  await accepted(api, f.predictor);
  const view = await accepted(api, { kind: "FEE", command_id: "boundary:opening-fee", activity_type: "FEE",
    activity_id: "boundary:fee-activity", fill_id: "opening-execution", fee_asset: "USD", total_fee: "0.205" });
  return { f, view: await accepted(api, reconciliation(view, "boundary:reconciled")) };
}

test("HTTP boundary rechecks campaign deadline at response and before PLAN or REDUCE commit", async t => {
  for (const kind of ["STATUS", "PLAN", "REDUCE"]) {
    const originalNow = Date.now, originalWorker = OfflineRoadmap.prototype.runWorker;
    const base = Date.UTC(2026, 8, 8, 12), deadline = base + 1000;
    let serverNow = base, captured, api;
    Date.now = () => serverNow;
    try {
      api = await setup();
      const { f, view: before } = await boundaryPosition(api, base, deadline);
      assert.equal(before.alive, true);
      assert.equal(before.simulated_entries_ready, true);
      assert.equal(before.campaign_exposures[0].original_deadline, deadline);
      const key = "ROADMAP9_OFFLINE:" + api.engine.key;
      const persistedBefore = await api.store.get(key);
      let casCalls = 0;
      const originalRpc = api.store.rpc.bind(api.store);
      api.store.rpc = async request => {
        if (request.op === "cas") casCalls++;
        return originalRpc(request);
      };
      const command = kind === "STATUS" ? undefined : { kind, command_id: "boundary:deadline:" + kind,
        ...(kind === "PLAN" ? { forecast: f.forecast } : { symbol: "AAPL", qty: "1" }) };
      OfflineRoadmap.prototype.runWorker = async function (packet) {
        const result = await originalWorker.call(this, packet);
        if ((kind === "STATUS" && packet.command === null) || packet.command?.command_id === command?.command_id) {
          captured = { packet, result: structuredClone(result) };
          serverNow = deadline;
        }
        return result;
      };
      serverNow = deadline - 1;
      const response = await api.call(command);
      assert(captured, "the actual Python worker must return a result before the clock advances");
      assert.equal(captured.packet.now_ms, deadline - 1);
      assert.equal(captured.result.view.evaluated_at_ms, deadline - 1);
      assert.equal(captured.result.view.valid_until_ms, deadline - 1);
      assert.deepEqual(captured.result.view.expired_campaigns, []);
      if (kind === "STATUS") {
        assert.equal(response.status, 200);
        assert.equal(captured.result.view.simulated_entries_ready, true);
        assert.equal(response.body.completed_at_ms, deadline);
        assert.equal(response.body.alive, false);
        assert.equal(response.body.simulated_entries_ready, false);
        assert.equal(response.body.health.alive, false);
        assert.equal(response.body.health.entries_ready, false);
        assert.equal(response.body.health.owned_inventory_management, "RECONCILE_ONLY");
        assert(response.body.simulation_blockers.includes("CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE"));
        assert(response.body.simulation_blockers.includes("INPUT_EXPIRED_BEFORE_RESPONSE"));
        assert(response.body.health.blocking_reasons.includes("CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE"));
        assert.deepEqual(response.body.expired_campaigns, captured.result.view.campaign_exposures);
        assert.deepEqual(response.body.ledger, before.ledger);
        assert.deepEqual(response.body.inventory_reconciliation, before.inventory_reconciliation);
        assert.deepEqual(response.body.orders, before.orders);
        assert.deepEqual(response.body.campaigns, before.campaigns);
      } else {
        assert.equal(captured.result.view.last_decision.simulated_intents.length, 1,
          "the real composite must prepare an intention that the transport refuses to commit");
        assert.equal(captured.result.view.last_decision.simulated_intents[0].deadline_at, deadline);
        assert.equal(response.status, 503);
        assert.equal(response.body.error, "ROADMAP9_INPUT_EXPIRED_BEFORE_COMMIT");
        assert.equal(response.body.recovery_required, true);
      }
      assert.equal(response.body.execution_allowed, false);
      assert.equal(casCalls, 0, "an intention computed before the deadline must not enter CAS after the deadline");
      assert.deepEqual(await api.store.get(key), persistedBefore);
      assert.equal(api.brokerCalls, 0);
      t.diagnostic(JSON.stringify({ origin: ORIGIN, boundary: "CAMPAIGN_DEADLINE", kind,
        evaluated_at_ms: captured.packet.now_ms, completed_at_ms: serverNow, deadline_at_ms: deadline,
        worker_intents: kind === "STATUS" ? 0 : captured.result.view.last_decision.simulated_intents.length,
        cas_calls: casCalls, inventory_preserved: true, revision_preserved: persistedBefore.revision,
        http_status: response.status, broker_calls: api.brokerCalls, execution_allowed: false }));
    } finally {
      Date.now = originalNow;
      OfflineRoadmap.prototype.runWorker = originalWorker;
      if (api) await api.close();
    }
  }
});

test("HTTP boundary expires model and label entry TTL without blocking deterministic reductions", async t => {
  for (const field of ["model_trained_at_ms", "latest_label_at_ms"]) {
    for (const kind of ["STATUS", "PLAN"]) {
      const originalNow = Date.now, originalWorker = OfflineRoadmap.prototype.runWorker;
      const base = Date.UTC(2026, 8, 8, 12), entryDeadline = base + 1000, deadline = base + 3600000;
      let serverNow = base, captured, api;
      Date.now = () => serverNow;
      try {
        api = await setup();
        const { f, view: before } = await boundaryPosition(api, base, deadline,
          { field, at: entryDeadline - 168 * 3600000 });
        assert.equal(before.alive, true);
        assert.equal(before.simulated_entries_ready, true);
        assert.equal(before.health.owned_inventory_management, "REDUCTION_READY");
        const key = "ROADMAP9_OFFLINE:" + api.engine.key;
        const persistedBefore = await api.store.get(key);
        let casCalls = 0;
        const originalRpc = api.store.rpc.bind(api.store);
        api.store.rpc = async request => {
          if (request.op === "cas") casCalls++;
          return originalRpc(request);
        };
        const command = kind === "STATUS" ? undefined : { kind: "PLAN", command_id: "boundary:entry:" + field,
          forecast: f.forecast };
        OfflineRoadmap.prototype.runWorker = async function (packet) {
          const result = await originalWorker.call(this, packet);
          if ((kind === "STATUS" && packet.command === null) || packet.command?.command_id === command?.command_id) {
            captured = { packet, result: structuredClone(result) };
            serverNow = entryDeadline;
            captured.atExactLimit = this.publicView(result.view, persistedBefore.revision, true);
            serverNow = entryDeadline + 1;
          }
          return result;
        };
        serverNow = entryDeadline - 1;
        const response = await api.call(command);
        assert(captured);
        assert.equal(captured.packet.now_ms, entryDeadline - 1);
        assert.equal(captured.result.view.entry_valid_until_ms, entryDeadline);
        assert(captured.result.view.valid_until_ms > entryDeadline + 1);
        if (kind === "STATUS") {
          assert.equal(response.status, 200);
          assert.equal(captured.atExactLimit.simulated_entries_ready, true, "exactly 168 hours remains permitted");
          assert.equal(captured.result.view.simulated_entries_ready, true);
          assert.equal(response.body.completed_at_ms, entryDeadline + 1);
          assert.equal(response.body.simulated_entries_ready, false);
          assert.equal(response.body.health.entries_ready, false);
          assert.equal(response.body.alive, true);
          assert.equal(response.body.health.alive, true);
          assert.equal(response.body.health.owned_inventory_management, "REDUCTION_READY");
          assert(response.body.simulation_blockers.includes("ENTRY_INPUT_EXPIRED_BEFORE_RESPONSE"));
          assert(!response.body.simulation_blockers.includes("INPUT_EXPIRED_BEFORE_RESPONSE"));
          assert.equal(response.body.storage.recovery_required, false);
          assert.deepEqual(response.body.ledger, before.ledger);
          assert.deepEqual(response.body.orders, before.orders);
          assert.deepEqual(response.body.campaigns, before.campaigns);
        } else {
          assert.equal(captured.result.view.last_decision.simulated_intents.length, 1);
          assert.equal(response.status, 503);
          assert.equal(response.body.error, "ROADMAP9_ENTRY_INPUT_EXPIRED_BEFORE_COMMIT");
          assert.equal(response.body.recovery_required, false, "entry expiry must not disable inventory management");
        }
        assert.equal(response.body.execution_allowed, false);
        assert.equal(casCalls, 0);
        assert.deepEqual(await api.store.get(key), persistedBefore);
        OfflineRoadmap.prototype.runWorker = originalWorker;
        const reduced = await accepted(api, { kind: "REDUCE", command_id: "boundary:reduce-after-entry-expiry",
          symbol: "AAPL", qty: "1" });
        assert.equal(reduced.last_decision.decision.status, "DETERMINISTIC_REDUCTION");
        assert.equal(reduced.last_decision.simulated_intents[0].deadline_at, deadline);
        assert.equal(reduced.storage.recovery_required, false);
        assert.equal(reduced.storage.revision, persistedBefore.revision + 1);
        assert.deepEqual(reduced.ledger, before.ledger);
        assert.equal(casCalls, 1, "only the subsequent reduction may commit");
        assert.equal(api.brokerCalls, 0);
        t.diagnostic(JSON.stringify({ origin: ORIGIN, boundary: "ENTRY_TTL_168_HOURS", field, kind,
          evaluated_at_ms: captured.packet.now_ms, completed_at_ms: serverNow, entry_valid_until_ms: entryDeadline,
          before_age_ms: 168 * 3600000 - 1, completed_age_ms: 168 * 3600000 + 1,
          rejected_entry_cas_calls: 0, subsequent_reduction_cas_calls: casCalls,
          subsequent_reduction_status: reduced.last_decision.decision.status,
          inventory_preserved: true, deadline_preserved: deadline,
          http_status: response.status, broker_calls: api.brokerCalls, execution_allowed: false }));
      } finally {
        Date.now = originalNow;
        OfflineRoadmap.prototype.runWorker = originalWorker;
        if (api) await api.close();
      }
    }
  }
});

module.exports = { setup, ORIGIN };
