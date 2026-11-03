"use strict";
// Internal adversarial review: actual local HTTP, Python and restarted SQLite.
// Every input is synthetic engineering. No broker or model-provider calls.
const assert = require("node:assert/strict");
const fs = require("node:fs");
const os = require("node:os");
const path = require("node:path");
const crypto = require("node:crypto");
const { DurableStore } = require("../runtime/store30.cjs");
const { Coordinator } = require("../runtime30/coordinator.js");
const { server } = require("../runtime30/server.js");
const { config } = require("./xxx_fixtures.cjs");
const { fixture } = require("./roadmap9_integration_fixture.cjs");

const ROOT = path.resolve(__dirname, "..");
const ORIGIN = "SYNTHETIC_ENGINEERING_ONLY";
const PASSWORD = "review-synthetic-api-password-at-least-32-characters";
const ROUTE = "/v1/roadmap9/offline";
const sourceFiles = [
  "tools/roadmap9_integration_adversarial.cjs", "tools/roadmap9_integration_fixture.cjs",
  "runtime/roadmap9_bridge.cjs", "runtime/store30.cjs", "runtime/store.py",
  "runtime30/server.js", "xxx/server.ts", "quant/harpoon_quant/roadmap9/integration.py",
  "quant/harpoon_quant/roadmap9/costs.py", "quant/harpoon_quant/roadmap9/execution.py",
  "quant/harpoon_quant/roadmap9/operations.py", "quant/harpoon_quant/roadmap9/portfolio.py",
];
const sourceHashes = () => Object.fromEntries(sourceFiles.map(name => [name,
  crypto.createHash("sha256").update(fs.readFileSync(path.join(ROOT, name))).digest("hex")]));

async function openApi() {
  const directory = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-r2-adversarial-"));
  const database = path.join(directory, "review.sqlite");
  const cfg = config();
  let store, engine, app, brokerCalls = 0;
  const start = async () => {
    store = await new DurableStore(database).open();
    engine = new Coordinator(store, { async request() {
      brokerCalls++;
      throw Error("BROKER_FORBIDDEN_DURING_REVIEW");
    } }, structuredClone(cfg));
    app = server(engine, PASSWORD, "<html></html>", undefined, { roadmap9Offline: true });
    await new Promise((resolve, reject) => {
      app.once("error", reject);
      app.listen(0, "127.0.0.1", resolve);
    });
  };
  const stop = async () => {
    app.closeAllConnections();
    await new Promise(resolve => app.close(resolve));
    await store.close();
  };
  await start();
  return {
    get store() { return store; },
    get key() { return "ROADMAP9_OFFLINE:" + engine.key; },
    get brokerCalls() { return brokerCalls; },
    async call(command) {
      const response = await fetch("http://127.0.0.1:" + app.address().port + ROUTE, {
        method: command === undefined ? "GET" : "POST",
        headers: { authorization: "Basic " + Buffer.from("trader:" + PASSWORD).toString("base64"),
          "content-type": "application/json", "x-harpoon-action": "1" },
        ...(command === undefined ? {} : { body: JSON.stringify({ origin: ORIGIN, command }) }),
      });
      return { status: response.status, body: await response.json() };
    },
    async restartDatabaseAndController() { await stop(); await start(); },
    async close() {
      await stop();
      fs.rmSync(directory, { recursive: true, force: true });
      assert.equal(brokerCalls, 0, "offline API invoked broker transport");
    },
  };
}

async function accepted(api, command) {
  const response = await api.call(command);
  assert.equal(response.status, 200, JSON.stringify(response));
  assert.equal(response.body.execution_allowed, false);
  assert.equal(response.body.orders_allowed, false);
  assert.equal(response.body.financial_acceptance_allowed, false);
  assert.equal(response.body.real_fills_present, false);
  assert.equal(response.body.origin, ORIGIN);
  return response.body;
}

function reconcile(view, id) {
  return { kind: "RECONCILE", command_id: id, balances: view.ledger.balances,
    inventory: Object.fromEntries(Object.entries(view.inventory_reconciliation)
      .map(([name, row]) => [name, row.execution_net_quantity])) };
}

async function seed(api) {
  const f = fixture();
  await accepted(api, f.init);
  await accepted(api, f.market);
  const view = await accepted(api, f.predictor);
  return { f, view: await accepted(api, reconcile(view, "review:seed-reconciled")) };
}

async function statusClockReview() {
  const api = await openApi();
  const originalNow = Date.now;
  try {
    const empty = await accepted(api);
    assert.equal(empty.alive, false, "enabled route cannot manufacture a live market");
    const { f, view } = await seed(api);
    assert.equal(view.alive, true);
    assert.equal(view.simulated_entries_ready, true);
    const prior = await api.store.get(api.key);
    const attacks = [
      { ...f.predictor, command_id: "review:clock", received_at_ms: 0 },
      { ...f.predictor, command_id: "review:now", now_ms: 0 },
      { ...f.predictor, command_id: "review:snapshot", snapshot: { alive: true } },
      { ...f.predictor, command_id: "review:llm", llm: { execution_allowed: true } },
      { kind: "PLAN", command_id: "review:old-forecast", forecast: {
        ...f.forecast, for_decision_at: new Date(originalNow() - 3600000).toISOString(),
      } },
    ];
    const rejections = [];
    for (const attack of attacks) {
      const response = await api.call(attack);
      assert.equal(response.status, 422, JSON.stringify(response));
      assert.deepEqual(await api.store.get(api.key), prior);
      rejections.push({ command_id: attack.command_id, status: response.status, error: response.body.error });
    }
    // Advance the actual server clock in this isolated Node test process, not
    // a client-supplied clock. No market event or journal mutation is added.
    const future = originalNow() + 15001;
    Date.now = () => future;
    let stale;
    try { stale = await accepted(api); } finally { Date.now = originalNow; }
    assert.equal(stale.alive, false);
    assert.equal(stale.simulated_entries_ready, false);
    assert.equal(stale.health.owned_inventory_management, "RECONCILE_ONLY");
    assert(stale.health.ages_ms.market_event_at >= 15001);
    assert.equal(stale.storage.revision, view.storage.revision);
    assert.deepEqual(await api.store.get(api.key), prior);
    return { name: "server_clock_status_and_client_authority_rejection", passed: true,
      synthetic_server_clock_advance_ms: 15001, journal_unchanged: true,
      enabled_empty_alive: empty.alive, fresh_alive: view.alive, stale_alive: stale.alive,
      stale_simulated_entries_ready: stale.simulated_entries_ready, rejections,
      ui_visual_integration_tested: false, broker_calls: api.brokerCalls };
  } finally { Date.now = originalNow; await api.close(); }
}

async function failedFillAndDebtReview() {
  const api = await openApi();
  try {
    const { f } = await seed(api);
    let view = await accepted(api, { kind: "PLAN", command_id: "review:plan", forecast: f.forecast });
    const [intent] = view.last_decision.simulated_intents;
    assert.equal(Number(intent.qty), 2);
    const cid = intent.client_order_id, deadline = intent.deadline_at;
    await accepted(api, { kind: "EVENT", command_id: "review:submitted", event: {
      kind: "SUBMITTED", event_id: "submitted", client_order_id: cid,
    } });
    await accepted(api, { kind: "EVENT", command_id: "review:ack", event: {
      kind: "ACK", event_id: "ack", client_order_id: cid, broker_order_id: "SIMULATED-REVIEW",
    } });
    const freshAt = Date.now();
    await accepted(api, { ...f.market, command_id: "review:fresh", quotes: f.market.quotes
      .map(row => ({ ...row, event_at_ms: freshAt })) });
    const fill = { kind: "EVENT", command_id: "review:failed-fill", event: {
      kind: "FILL", event_id: "fill", client_order_id: cid, execution_id: "review-execution",
      qty: "2", price: "100", liquidity_role: "taker", executed_at: Date.now(), cumulative_qty: "2",
    } };
    const before = await api.store.get(api.key);
    const rpc = api.store.rpc.bind(api.store);
    api.store.rpc = async request => {
      if (request.op === "cas") throw Error("REVIEW_DISK_FULL_NO_COMMIT_OR_FAULT_FLAG");
      return rpc(request);
    };
    const failed = await api.call(fill);
    assert.equal(failed.status, 503);
    assert.deepEqual(await api.store.get(api.key), before);
    api.store.rpc = rpc;
    // Real store-process shutdown/reopen, new Coordinator and new API controller.
    await api.restartDatabaseAndController();
    view = await accepted(api);
    const ageAtRestart = view.health.ages_ms.market_event_at;
    assert(ageAtRestart < 15000, "test must distinguish recovery hold from quote expiry");
    assert.equal(view.storage.recovery_required, true);
    assert.equal(view.simulated_entries_ready, false);
    assert.equal(Number(view.inventory_reconciliation.AAPL.execution_net_quantity), 0);
    assert.equal(Number(view.ledger.balances.USD), 20000);
    const blocked = await api.call({ kind: "PLAN", command_id: "review:forbidden-plan", forecast: f.forecast });
    assert.equal(blocked.status, 409);
    assert.equal(blocked.body.error, "ROADMAP9_RECONCILIATION_REQUIRED");
    view = await accepted(api, fill);
    assert.equal(Number(view.inventory_reconciliation.AAPL.execution_net_quantity), 2);
    assert.equal(Number(view.ledger.balances.USD), 19800);
    assert.equal(view.storage.recovery_required, true);
    const filledRevision = view.storage.revision;
    const duplicate = await accepted(api, fill);
    assert.equal(duplicate.storage.revision, filledRevision);
    assert.deepEqual(duplicate.ledger, view.ledger);
    const fee = { kind: "FEE", command_id: "review:fee", activity_type: "FEE",
      activity_id: "review-fee", fill_id: "review-execution", fee_asset: "USD", total_fee: "0.21" };
    view = await accepted(api, fee);
    assert.equal(Number(view.equity_usd), 19999.79);
    const duplicateFee = await accepted(api, fee);
    assert.equal(duplicateFee.storage.revision, view.storage.revision);
    assert.deepEqual(duplicateFee.ledger, view.ledger);
    view = await accepted(api, reconcile(view, "review:source-reconciled"));
    assert.equal(view.storage.recovery_required, false);
    assert.equal(view.campaigns.AAPL.original_deadline, deadline);
    const protectedState = await api.store.get(api.key);
    assert.equal((await api.call({ ...f.init, command_id: "review:reset-init" })).status, 409);
    assert.equal((await api.call({ kind: "RESET", command_id: "review:reset" })).status, 422);
    assert.deepEqual(await api.store.get(api.key), protectedState);
    const recoveryResult = { name: "failed_fill_cas_real_restart_and_exactly_once_replay", passed: true,
      failed_fill_http_status: failed.status, durable_record_unchanged_after_failure: true,
      quote_age_at_restart_ms: ageAtRestart, restarted_sqlite_process_and_controller: true,
      first_retry_shares: 2, duplicate_fill_and_fee_no_additional_revision: true,
      final_equity_after_fee_usd: view.equity_usd, deadline_preserved: true,
      rearm_requires_explicit_matching_reconciliation: true, broker_calls: api.brokerCalls };
    const correction = { ...fee, command_id: "review:fee-debt", activity_id: "review-fee-debt",
      corrects_activity_id: "review-fee", total_fee: "25000" };
    view = await accepted(api, correction);
    assert.equal(Number(view.ledger.balances.USD), -5200);
    assert.equal(Number(view.equity_usd), -5000);
    assert.equal(Number(view.inventory_reconciliation.AAPL.execution_net_quantity), 2);
    assert.equal(view.simulated_entries_ready, false);
    const debtRevision = view.storage.revision;
    const duplicateDebt = await accepted(api, correction);
    assert.equal(duplicateDebt.storage.revision, debtRevision);
    assert.deepEqual(duplicateDebt.ledger, view.ledger);
    await api.restartDatabaseAndController();
    const debtRestored = await accepted(api);
    assert.equal(Number(debtRestored.ledger.balances.USD), -5200);
    assert.equal(Number(debtRestored.equity_usd), -5000);
    assert.equal(debtRestored.simulated_entries_ready, false);
    assert.equal(debtRestored.storage.recovery_required, true);
    return [recoveryResult, { name: "fee_exceeding_provision_persists_debt_across_restart", passed: true,
      total_synthetic_corrected_fee_usd: "25000", settled_usd: debtRestored.ledger.balances.USD,
      equity_usd: debtRestored.equity_usd, inventory_shares: "2", duplicate_fee_idempotent: true,
      account_not_reset: true, entries_blocked: true, broker_calls: api.brokerCalls }];
  } finally { await api.close(); }
}

async function main() {
  const output = path.resolve(process.argv[2] || path.join(ROOT, "evidence/roadmap9/integration_r2/adversarial_api_review.json"));
  const before = sourceHashes();
  const report = { schema: "HARPOON_ROADMAP9_INTERNAL_ADVERSARIAL_API_REVIEW_1", origin: ORIGIN,
    started_at_utc: new Date().toISOString(), base_commit: "b48f38d23fce08bd68428fe3f7896a66a8548b7a",
    source_revision_scope: "CURRENT_SOURCE_BYTES_IDENTIFIED_BY_HASH;BASE_COMMIT_IS_PRE_R2_NOT_THE_REVIEWED_CODE_IDENTITY",
    source_sha256: before, tests: [], errors: [], execution_allowed: false,
    new_economic_measurements: 0, real_fills_present: false, external_review_completed: false,
    scope: "INTERNAL_REVIEW_OF_LOCAL_HTTP_SQLITE_AND_PYTHON_ON_SYNTHETIC_RECEIPTS;NOT_LIVE_EXECUTION_OR_VISUAL_UI" };
  try {
    report.tests.push(await statusClockReview());
    report.tests.push(...await failedFillAndDebtReview());
  } catch (error) { report.errors.push(error.stack || String(error)); }
  report.source_hashes_after = sourceHashes();
  report.sources_unchanged = JSON.stringify(report.source_hashes_after) === JSON.stringify(before);
  if (!report.sources_unchanged) report.errors.push("REVIEWED_SOURCE_CHANGED_DURING_TEST");
  report.finished_at_utc = new Date().toISOString();
  report.passed = report.errors.length === 0 && report.tests.length === 3;
  fs.mkdirSync(path.dirname(output), { recursive: true });
  fs.writeFileSync(output, JSON.stringify(report, null, 2) + "\n");
  console.log(JSON.stringify({ output, passed: report.passed, tests: report.tests.length,
    sources_unchanged: report.sources_unchanged, errors: report.errors }));
  if (!report.passed) process.exitCode = 1;
}

main().catch(error => { console.error(error); process.exitCode = 1; });
