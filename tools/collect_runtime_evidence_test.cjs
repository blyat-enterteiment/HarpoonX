"use strict";
// SYNTHETIC_ENGINEERING_ONLY. Actual runtime journal/ledger/server, local transport, no broker orders.
const test = require("node:test"), assert = require("node:assert/strict"), fs = require("node:fs"), path = require("node:path"), os = require("node:os");
const {once} = require("node:events"), {spawnSync} = require("node:child_process"), crypto = require("node:crypto");
const {collectRuntimeEvidence, endpoint, parseArgs, coordinatorExportIdentity, HARD} = require("./collect_runtime_evidence.cjs");
const {QuantObservationJournal} = require("../runtime30/quant_observations.js");
const {NetAccountLedger, netLedgerDigest, verifyNetLedgerHistoryBundle} = require("../runtime30/net_accounting.js");
const {server} = require("../runtime30/server.js");
const {ULTIMATE_VERSION} = require("../runtime30/version.js");
const {verifyManifest} = require("./export_observation_snapshot.cjs");
const ACCOUNT = "SYNTHETIC-COLLECTOR-ACCOUNT", T0 = Date.UTC(2026, 9, 15, 13, 30), MIN = 60000;
const PASSWORD = "synthetic-collector-password-32-characters-or-more";
const SELECTION = {kind: "FIRST_CAUSAL_FRAME_AT_OR_AFTER_LOCAL_GRID", timezone: "America/New_York", local_time: "10:50",
  max_selection_delay_ms: 90000, label_quote_max_age_ms: 15000, label_maturity_max_delay_ms: 300000};
class Store {
  constructor() { this.rows = new Map(); }
  async get(key) { return structuredClone(this.rows.get(key) ?? null); }
  async put(key, value) { this.rows.set(key, structuredClone(value)); return true; }
  async lease() { return true; }
}
async function fixture(t, fault = null) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-evidence-collector-test-"));
  const store = new Store(), brokerCalls = [], calls = [], originalBodies = new Map(), timers = [];
  const api = {request: async (route, method = "GET") => {
    assert.equal(method, "GET"); brokerCalls.push(route);
    if (route === "/v2/account") return {id: ACCOUNT, currency: "USD", cash: "20000", equity: "20000"};
    if (route === "/v2/positions" || route.startsWith("/v2/account/activities")) return [];
    throw Error("UNEXPECTED_SYNTHETIC_BROKER_ROUTE");
  }};
  const ledger = new NetAccountLedger(store, api, "N", ACCOUNT, {executionNature: "SYNTHETIC_ENGINEERING_ONLY", maxObservations: 8,
    archive: {enabled: true, maxSegments: 16, maxStoredBytes: 32*1024*1024, activityOverlapMs: MIN}});
  for (let i = 0; i < 3; i++) await ledger.refresh({now: T0+i*MIN, instruments: [], externalCosts: null});
  const journal = new QuantObservationJournal(store, "J", ACCOUNT, {maxFrames: 2}); await journal.load();
  for (let i = 0; i < 3; i++) {
    const at = T0+i*MIN;
    await journal.capture({now: at, config: {mode: "paper", expected_account_id: ACCOUNT, universe: []}, signals: [], market: {calendar: []}},
      {schema: "HARPOON_RUNTIME_OBSERVATION_1", status: "WAIT_FEATURE_DATA", asof: new Date(at).toISOString(),
        observations: [], rejected: {}, selected: [], execution_allowed: false, liveApproved: false});
  }
  const engine = {netLedger: ledger, quantObservations: journal, syncAt: Date.now(), reconcileError: null, storageError: null,
    validators: {checks: {"journal-write": {lastSuccess: Date.now()}}}, exitCoverage: () => ({entrySafe: true}),
    quantLastPlan: {}, quantEconomicGate: {}, cfg: {quant: {enabled: true}}, entryReady: () => false,
    discoveryHold: false, state: {paused: false, halt: false}, stopping: false,
    netAccountingError: null, quantObservationError: null, probe: {startedAt: Date.now()}};
  engine.evidence = () => ({version: ULTIMATE_VERSION, accountSuffix: ACCOUNT.slice(-4),
    netAccountLedger: ledger.view(), prospectiveQuantObservations: journal.view(),
    exportedAt: new Date().toISOString(), history: {campaigns: [], intents: [], recentEvents: []},
    forward_attribution: {schema: "HARPOON_FORWARD_COORDINATOR_EXPORT_1", account_id: ACCOUNT,
      execution_nature: "SYNTHETIC_ENGINEERING_ONLY", history_scope: "CURRENT_RETAINED_STATE_NOT_COMPLETE_JOURNAL"}});
  const app = server(engine, PASSWORD, "<html></html>");
  const originalHandler = app.listeners("request")[0]; app.removeAllListeners("request");
  let badState = null;
  if (fault === "rehashed_fake_pnl") {
    badState = await store.get("N"); badState.accounting.accountNetPnlUsd = 999;
    const copy = {...badState}; delete copy.integrity; badState.integrity = netLedgerDigest(copy);
  }
  app.on("request", (req, res) => {
    calls.push({method: req.method, path: req.url, authenticated: !!req.headers.authorization});
    assert.equal(req.method, "GET");
    const isOperational = req.url === "/v1/operational";
    if (fault === "redirect" && isOperational) {
      res.writeHead(302, {location: "https://never-requested.invalid/credentials", "content-type": "application/json"}); res.end("{}"); return;
    }
    if (fault === "timeout" && isOperational) return;
    if (fault === "deadline" && req.url === "/healthz") {
      timers.push(setTimeout(() => originalHandler(req, res), 150)); return;
    }
    if (fault === "oversized" && isOperational) {
      res.writeHead(200, {"content-type": "application/json", "content-length": "90000000"}); res.end("{}"); return;
    }
    if (fault === "chunk_oversized" && isOperational) {
      res.writeHead(200, {"content-type": "application/json"}); res.write('{"payload":"'); res.write("a".repeat(10000)); res.end('"}'); return;
    }
    if (fault === "password_echo" && isOperational) {
      res.writeHead(200, {"content-type": "application/json"}); res.end(JSON.stringify({echo: PASSWORD})); return;
    }
    if (fault === "authorization_echo" && isOperational) {
      res.writeHead(200, {"content-type": "application/json"}); res.end(JSON.stringify({echo: req.headers.authorization})); return;
    }
    if (fault === "escaped_password_echo" && isOperational) {
      res.writeHead(200, {"content-type": "application/json"});
      res.end('{"echo":"'+[...PASSWORD].map(c => "\\u"+c.charCodeAt(0).toString(16).padStart(4,"0")).join("")+'"}'); return;
    }
    if (fault === "duplicate_json" && isOperational) {
      res.writeHead(200, {"content-type": "application/json"}); res.end('{"schema":"x","schema":"HARPOON_OPERATIONAL_CAPABILITIES_1"}'); return;
    }
    const end = res.end.bind(res);
    res.end = (value, ...args) => {
      let body = JSON.parse(String(value));
      if (fault === "bad_frame" && req.url.startsWith("/v1/quant/observations?")) body.frames[0].runtime_input.now++;
      if (fault === "reordered_observation_page" && req.url.includes("snapshot_id=") && req.url.includes("offset=1&")) body.offset = 0;
      if (fault === "observation_wrong_account" && req.url.includes("snapshot_id=")) body.account_id = "OTHER_ACCOUNT";
      if (fault === "ledger_revision" && req.url.startsWith("/v1/accounting/history?") && !req.url.includes("offset=0&")) body.ledger_integrity = "f".repeat(64);
      if (fault === "reordered_ledger_page" && req.url.startsWith("/v1/accounting/history?") && !req.url.includes("offset=0&")) body.offset = 0;
      if (fault === "ledger_wrong_account" && req.url.startsWith("/v1/accounting/history?")) body.account_id = "OTHER_ACCOUNT";
      if (fault === "restart" && req.url === "/healthz" && calls.filter(c => c.path === "/healthz").length > 1) body.startedAt++;
      if (req.url === "/v1/export") {
        if (fault === "coordinator_wrong_version") body.version = "0.0.0";
        if (fault === "coordinator_wrong_account") body.netAccountLedger.accountId = "OTHER_ACCOUNT";
        if (fault === "coordinator_forward_wrong_account") body.forward_attribution.account_id = "OTHER_ACCOUNT";
        if (fault === "coordinator_missing_identity") body = {version: ULTIMATE_VERSION, accountSuffix: ACCOUNT.slice(-4), history: body.history};
        if (fault === "coordinator_password_echo") body.echo = PASSWORD;
        if (fault === "coordinator_oversized") body.payload = "a".repeat(50000);
      }
      if (badState && req.url.startsWith("/v1/accounting/history?")) {
        body.ledger_integrity = badState.integrity;
        for (const row of body.records) if (row.kind === "HEADER" && row.storage === "CONTROL") {
          const {observations, activities, externalCosts, ...header} = badState; row.value = header;
        }
      }
      const bytes = Buffer.from(JSON.stringify(body)); originalBodies.set(req.url + "#" + originalBodies.size, bytes);
      return end(bytes, ...args);
    };
    originalHandler(req, res);
  });
  app.listen(0, "127.0.0.1"); await once(app, "listening");
  const baseUrl = "http://127.0.0.1:" + app.address().port, outputDir = path.join(root, "collection");
  const options = {baseUrl, expectedAccount: ACCOUNT, expectedVersion: ULTIMATE_VERSION, outputDir,
    observationPageSize: 1, ledgerPageSize: 2, requestTimeoutMs: 1000, timeoutMs: 10000};
  const environment = {HARPOON_PANEL_PASSWORD: PASSWORD}; const callsBeforeCollection = brokerCalls.length;
  t.after(async () => {
    for (const timer of timers) clearTimeout(timer);
    app.closeAllConnections(); await new Promise(resolve => app.close(resolve));
    fs.rmSync(root, {recursive: true, force: true});
  });
  return {root, outputDir, options, environment, calls, originalBodies, brokerCalls, callsBeforeCollection};
}
function failed(f) {
  assert.equal(fs.existsSync(path.join(f.outputDir, "collection_receipt.json")), false);
  const report = JSON.parse(fs.readFileSync(path.join(f.outputDir, "collection_failed.json"), "utf8"));
  assert.equal(report.collection_complete, false); assert.equal(report.financial_acceptance_allowed, false);
  assert.equal(report.economic_score, null); assert.equal(report.automatic_restarts, 0);
  return report;
}
function noSecretFiles(dir) {
  const authorization = "Basic " + Buffer.from("trader:" + PASSWORD).toString("base64");
  for (const file of fs.readdirSync(dir)) {
    const text = fs.readFileSync(path.join(dir, file), "utf8");
    assert(!text.includes(PASSWORD)); assert(!text.includes(authorization));
  }
}

test("complete collection uses actual runtime capture, ledger and server and retains original bytes", async t => {
  const f = await fixture(t); const selectionFile = path.join(f.root, "selection.json");
  fs.writeFileSync(selectionFile, JSON.stringify(SELECTION, null, 2));
  const result = await collectRuntimeEvidence({...f.options, selectionFile}, f.environment);
  assert.equal(result.status, "COMPLETE_SOURCE_COLLECTION"); assert.equal(result.collection_complete, true);
  assert.equal(result.observation_verification.frames, 3); assert.equal(result.ledger_verification.observations, 3);
  assert.equal(result.ledger_verification.execution_nature, "SYNTHETIC_ENGINEERING_ONLY");
  assert.equal(result.ledger_verification.economic_pnl_usd, null); assert.equal(result.economic_evidence_complete, false);
  assert(result.missing_for_level4.includes("ACCOUNT_COST_COVERAGE_INCOMPLETE"));
  assert.equal(result.economic_score, null); assert.equal(result.level4_assessed, false);
  assert.equal(result.execution_allowed, false); assert.equal(result.financial_acceptance_allowed, false);
  assert.equal(fs.statSync(f.outputDir).mode & 0o777, 0o700);
  for (const ref of result.artifacts) {
    const filename = path.join(f.outputDir, ref.path), bytes = fs.readFileSync(filename);
    assert.equal(fs.statSync(filename).mode & 0o777, 0o600);
    assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), ref.sha256);
    if (ref.kind === "ORIGINAL_HTTP_RESPONSE_BODY") assert([...f.originalBodies.values()].some(b => b.equals(bytes)));
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(f.outputDir, "observation_manifest.json"), "utf8"));
  assert.equal(verifyManifest(manifest, f.outputDir).total_frames, 3);
  const bundle = JSON.parse(fs.readFileSync(path.join(f.outputDir, "ledger_bundle.json"), "utf8"));
  assert.equal(verifyNetLedgerHistoryBundle(bundle.pages, bundle.expected_integrity).verified, true);
  assert.equal(f.brokerCalls.length, f.callsBeforeCollection);
  assert(f.calls.every(c => c.method === "GET")); assert(f.calls.filter(c => c.path === "/healthz").every(c => !c.authenticated));
  assert(f.calls.filter(c => c.path !== "/healthz").every(c => c.authenticated));
  noSecretFiles(f.outputDir);
  if (process.env.HARPOON_QA_OUTPUT_DIR) {
    fs.mkdirSync(process.env.HARPOON_QA_OUTPUT_DIR, {recursive: true});
    const benchmark = {nature: "SYNTHETIC_ENGINEERING_ONLY", samples: 1, transport: "LOCAL_LOOPBACK_HTTP",
      duration_ms: result.duration_ms, requests: result.requests.length, network_bytes_seen: result.network_bytes_seen,
      artifact_bytes: result.persisted_artifact_bytes, observation_frames: 3, ledger_observations: 3,
      node_version: process.version, platform: process.platform, node_process_rss_bytes: process.memoryUsage().rss,
      source_account: ACCOUNT, broker_calls_during_collection: f.brokerCalls.length-f.callsBeforeCollection,
      limitations: ["One local synthetic sample; no latency percentile or production improvement is inferred.",
        "RSS includes test/runtime modules; it is not isolated collector memory.", "No financial performance conclusion."]};
    fs.writeFileSync(path.join(process.env.HARPOON_QA_OUTPUT_DIR, "collector_transport_benchmark.json"), JSON.stringify(benchmark, null, 2)+"\n", {mode: 0o600});
  }
});
test("no supplied selection verifies transport without creating a calibration manifest or training request", async t => {
  const f = await fixture(t), result = await collectRuntimeEvidence(f.options, f.environment);
  assert.equal(result.selection, null); assert.equal(result.observation_verification.calibration_manifest, null);
  assert.equal(fs.existsSync(path.join(f.outputDir, "observation_manifest.json")), false);
  assert(result.missing_for_level4.includes("CAUSAL_SELECTION_NOT_PROVIDED"));
  assert.equal(result.collection_complete, true); assert.equal(result.economic_evidence_complete, false);
  assert.equal(result.include_coordinator_export, false); assert.equal(result.coordinator_export, null);
  assert.equal(result.coordinator_export_verification, null);
  assert(!f.calls.some(c => c.path === "/v1/export"));
});
test("coordinator export opt-in retains original bytes and explicit identity without certifying history", async t => {
  const f = await fixture(t), result = await collectRuntimeEvidence({...f.options, includeCoordinatorExport: true}, f.environment);
  const ref = result.coordinator_export, checked = result.coordinator_export_verification;
  assert.equal(result.include_coordinator_export, true); assert.equal(ref.path, "coordinator_export.json");
  const bytes = fs.readFileSync(path.join(f.outputDir, ref.path));
  assert([...f.originalBodies.values()].some(b => b.equals(bytes)));
  assert.equal(crypto.createHash("sha256").update(bytes).digest("hex"), ref.sha256);
  assert.equal(bytes.length, ref.bytes); assert(result.artifacts.some(r => r.path === ref.path && r.sha256 === ref.sha256));
  assert.equal(checked.observed_account_id, ACCOUNT); assert.equal(checked.account_binding_verified, true);
  assert.equal(checked.version_verified, true); assert.equal(checked.forward_contract_present, true);
  assert.equal(checked.history_coverage_verified, false); assert.equal(checked.attribution_verification_executed, false);
  assert.equal(checked.atomic_snapshot_with_other_sources, false); assert.equal(checked.account_suffix_used, false);
  assert.equal(f.calls.filter(c => c.path === "/v1/export").length, 1);
  assert(f.calls.filter(c => c.path === "/v1/export").every(c => c.method === "GET" && c.authenticated));
  assert.equal(f.brokerCalls.length, f.callsBeforeCollection); noSecretFiles(f.outputDir);
});
for (const [fault, code] of [
  ["coordinator_wrong_version", "COORDINATOR_EXPORT_VERSION_MISMATCH"],
  ["coordinator_wrong_account", "COORDINATOR_EXPORT_ACCOUNT_MISMATCH"],
  ["coordinator_forward_wrong_account", "COORDINATOR_EXPORT_ACCOUNT_MISMATCH"],
]) test("coordinator export rejects explicit inconsistent identity: " + fault, async t => {
  const f = await fixture(t, fault);
  await assert.rejects(collectRuntimeEvidence({...f.options, includeCoordinatorExport: true}, f.environment), error => error.code === code);
  const report = failed(f); assert.equal(report.stage, "COORDINATOR_EXPORT");
  assert.equal(report.coordinator_export.path, "coordinator_export.json");
  assert.equal(report.coordinator_export_verification, null);
  assert.equal(f.brokerCalls.length, f.callsBeforeCollection);
});
test("coordinator export preserves missing full identity as unknown despite matching suffix and health", async t => {
  const f = await fixture(t, "coordinator_missing_identity");
  const result = await collectRuntimeEvidence({...f.options, includeCoordinatorExport: true}, f.environment);
  assert.equal(result.collection_complete, true);
  assert.equal(result.coordinator_export_verification.observed_account_id, null);
  assert.equal(result.coordinator_export_verification.account_binding_verified, false);
  assert.equal(result.coordinator_export_verification.atomic_snapshot_with_other_sources, false);
  assert.equal(result.coordinator_export_verification.history_coverage_verified, false);
});
test("coordinator export reuses secret checks before persisting its body", async t => {
  const f = await fixture(t, "coordinator_password_echo");
  await assert.rejects(collectRuntimeEvidence({...f.options, includeCoordinatorExport: true}, f.environment), /CREDENTIAL_ECHO_REJECTED/);
  const report = failed(f); assert.equal(report.stage, "COORDINATOR_EXPORT");
  assert.equal(report.coordinator_export, null);
  assert.equal(fs.existsSync(path.join(f.outputDir, "coordinator_export.json")), false); noSecretFiles(f.outputDir);
});
test("coordinator export is subject to the existing response byte cap", async t => {
  const f = await fixture(t, "coordinator_oversized");
  await assert.rejects(collectRuntimeEvidence({...f.options, includeCoordinatorExport: true, pageBytes: 20000}, f.environment), /RESPONSE_BYTES_BOUND/);
  const report = failed(f); assert.equal(report.stage, "COORDINATOR_EXPORT");
  assert.equal(fs.existsSync(path.join(f.outputDir, "coordinator_export.json")), false);
});
test("pure coordinator identity inspection never upgrades unknown identity or incomplete history", () => {
  const legacy = coordinatorExportIdentity({accountSuffix: ACCOUNT.slice(-4)}, ACCOUNT, ULTIMATE_VERSION);
  assert.equal(legacy.observed_version, null); assert.equal(legacy.version_verified, false);
  assert.equal(legacy.observed_account_id, null); assert.equal(legacy.account_binding_verified, false);
  assert.equal(legacy.history_coverage_verified, false); assert.equal(legacy.atomic_snapshot_with_other_sources, false);
  assert.equal(legacy.account_suffix_used, false);
  const valid = coordinatorExportIdentity({version: ULTIMATE_VERSION,
    forward_attribution: {schema: "HARPOON_FORWARD_COORDINATOR_EXPORT_1", account_id: ACCOUNT}}, ACCOUNT, ULTIMATE_VERSION);
  assert.equal(valid.forward_contract_present, true); assert.equal(valid.account_binding_verified, true);
  assert.equal(valid.history_coverage_verified, false);
});
test("pure coordinator identity inspection rejects conflicting claims and versions", () => {
  for (const body of [{version: "0.0.0"}, {account_id: "OTHER"},
    {netAccountLedger: {accountId: ACCOUNT}, forward_attribution: {account_id: "OTHER"}}, {account: {id: 123}}])
    assert.throws(() => coordinatorExportIdentity(body, ACCOUNT, ULTIMATE_VERSION), /COORDINATOR_EXPORT_(?:VERSION|ACCOUNT)_MISMATCH/);
  assert.throws(() => coordinatorExportIdentity([], ACCOUNT, ULTIMATE_VERSION), /COORDINATOR_EXPORT_OBJECT_REQUIRED/);
});
test("pure coordinator export option accepts only explicit booleans", async () => {
  assert.equal(parseArgs(["--include-coordinator-export", "true"]).includeCoordinatorExport, true);
  assert.equal(parseArgs(["--include-coordinator-export", "false"]).includeCoordinatorExport, false);
  for (const text of ["1", "yes", "TRUE", "null"])
    assert.throws(() => parseArgs(["--include-coordinator-export", text]), /INCLUDE_COORDINATOR_EXPORT_BOOLEAN_REQUIRED/);
  for (const value of [null, 1, "true", "false", {}])
    await assert.rejects(collectRuntimeEvidence({includeCoordinatorExport: value}, {}), /INCLUDE_COORDINATOR_EXPORT_BOOLEAN_REQUIRED/);
});
test("wrong version is rejected on the public health check before sending credentials", async t => {
  const f = await fixture(t);
  await assert.rejects(collectRuntimeEvidence({...f.options, expectedVersion: "0.0.0"}, f.environment), /EXPECTED_VERSION_MISMATCH/);
  assert.equal(f.calls.length, 1); assert.equal(f.calls[0].authenticated, false); failed(f);
});
test("wrong expected account rejects the snapshot before requesting market or ledger pages", async t => {
  const f = await fixture(t);
  await assert.rejects(collectRuntimeEvidence({...f.options, expectedAccount: "OTHER_ACCOUNT"}, f.environment), /EXPECTED_ACCOUNT_MISMATCH/);
  assert(!f.calls.some(c => c.path.includes("snapshot_id=") || c.path.includes("accounting/history"))); failed(f);
});
test("invalid authentication preserves only the completed public response", async t => {
  const f = await fixture(t);
  await assert.rejects(collectRuntimeEvidence(f.options, {HARPOON_PANEL_PASSWORD: "wrong-synthetic-password-of-at-least-32-characters"}), /HTTP_STATUS_401/);
  const report = failed(f); assert.equal(report.artifacts.length, 1); assert.equal(report.artifacts[0].path, "health_initial.json");
});
for (const [fault, code] of [
  ["bad_frame", "SOURCE_VERIFIER_OR_LOCAL_IO_REJECTED"],
  ["reordered_observation_page", "OBSERVATION_PAGE_IDENTITY_OR_CONTINUITY"],
  ["observation_wrong_account", "OBSERVATION_PAGE_IDENTITY_OR_CONTINUITY"],
  ["ledger_revision", "LEDGER_REVISION_CHANGED_NO_AUTOMATIC_RESTART"],
  ["reordered_ledger_page", "LEDGER_PAGE_CONTINUITY"],
  ["ledger_wrong_account", "LEDGER_ACCOUNT_OR_SCHEMA_MISMATCH"],
  ["rehashed_fake_pnl", "SOURCE_VERIFIER_OR_LOCAL_IO_REJECTED"],
  ["restart", "RUNTIME_IDENTITY_CHANGED_DURING_COLLECTION"],
]) test("rejects " + fault + " and preserves a clearly rejected partial collection", async t => {
  const f = await fixture(t, fault);
  await assert.rejects(collectRuntimeEvidence(f.options, f.environment), error => error.code === code);
  const report = failed(f); assert.equal(report.error_code, code); assert(report.artifacts.length > 0);
  if (fault === "rehashed_fake_pnl") assert.equal(report.stage, "LEDGER_SEMANTIC_VERIFICATION");
  assert.equal(f.brokerCalls.length, f.callsBeforeCollection);
});
test("redirects are not followed with credentials", async t => {
  const f = await fixture(t, "redirect");
  await assert.rejects(collectRuntimeEvidence(f.options, f.environment), /REDIRECT_REJECTED/);
  assert.equal(f.calls.length, 2); failed(f);
});
for (const fault of ["password_echo", "authorization_echo", "escaped_password_echo"])
  test("rejects credential reflection before persisting " + fault, async t => {
    const f = await fixture(t, fault);
    await assert.rejects(collectRuntimeEvidence(f.options, f.environment), /CREDENTIAL_ECHO_REJECTED/);
    const report = failed(f); assert.equal(report.artifacts.length, 1); noSecretFiles(f.outputDir);
  });
test("request timeout is bounded and does not retry", async t => {
  const f = await fixture(t, "timeout");
  await assert.rejects(collectRuntimeEvidence({...f.options, requestTimeoutMs: 50}, f.environment), /REQUEST_TIMEOUT/);
  assert.equal(f.calls.length, 2); const report = failed(f); assert(report.duration_ms < 2000);
});
test("total deadline expires independently of a longer request timeout", async t => {
  const f = await fixture(t, "deadline");
  await assert.rejects(collectRuntimeEvidence({...f.options, timeoutMs: 50, requestTimeoutMs: 1000}, f.environment), /COLLECTION_DEADLINE_EXCEEDED/);
  assert.equal(f.calls.length, 1); failed(f);
});
for (const fault of ["oversized", "chunk_oversized"])
  test("response byte cap rejects " + fault + " without saving an incomplete body", async t => {
    const f = await fixture(t, fault);
    await assert.rejects(collectRuntimeEvidence({...f.options, pageBytes: 4096}, f.environment), /RESPONSE_BYTES_BOUND/);
    const report = failed(f); assert.equal(report.incomplete_response_body_persisted, false); assert.equal(report.artifacts.length, 1);
  });
test("aggregate source and serialized-ledger budgets cannot be enlarged beyond the gate", async t => {
  const f = await fixture(t);
  await assert.rejects(collectRuntimeEvidence({...f.options, observationBytes: 1024}, f.environment), /RESPONSE_BYTES_BOUND|SOURCE_CATEGORY_BYTES_EXHAUSTED/);
  const report = failed(f);
  const observationBytes = report.artifacts.filter(r => r.path.startsWith("observation_")).reduce((n, r) => n+r.bytes, 0);
  assert(observationBytes <= 1024);
  await assert.rejects(collectRuntimeEvidence({...f.options, ledgerBundleBytes: HARD.ledgerBundleBytes+1}, f.environment), /INVALID_LIMIT_LEDGER_BUNDLE_BYTES/);
  await assert.rejects(collectRuntimeEvidence({...f.options, totalBytes: HARD.totalBytes+1}, f.environment), /INVALID_LIMIT_TOTAL_BYTES/);
});
test("ledger bundle limit is enforced before a complete receipt", async t => {
  const f = await fixture(t);
  await assert.rejects(collectRuntimeEvidence({...f.options, ledgerBundleBytes: 1024}, f.environment), /RESPONSE_BYTES_BOUND|LEDGER_BUNDLE_BYTES_BOUND/);
  const report = failed(f); assert.equal(fs.existsSync(path.join(f.outputDir, "ledger_bundle.json")), false);
  assert(report.artifacts.filter(r => r.path.startsWith("ledger_page_")).reduce((n,r)=>n+r.bytes,0) <= 1024);
});
test("page and request count limits prevent unbounded collection", async t => {
  const f = await fixture(t);
  await assert.rejects(collectRuntimeEvidence({...f.options, maxPages: 2}, f.environment), /OBSERVATION_PAGE_COUNT_BOUND/);
  failed(f); assert(!f.calls.some(c => c.path.includes("snapshot_id=")));
  const outputDir = path.join(f.root, "request-limit"), before = f.calls.length;
  await assert.rejects(collectRuntimeEvidence({...f.options, outputDir, maxRequests: 1}, f.environment), /COLLECTION_REQUEST_COUNT_BOUND/);
  failed({...f, outputDir}); assert.equal(f.calls.length-before, 1);
});
test("duplicate JSON keys are rejected without saving ambiguous source bytes", async t => {
  const f = await fixture(t, "duplicate_json");
  await assert.rejects(collectRuntimeEvidence(f.options, f.environment), /SOURCE_JSON_INVALID/);
  assert.equal(failed(f).artifacts.length, 1);
});
test("an existing output is never overwritten and is rejected before network access", async t => {
  const f = await fixture(t); fs.mkdirSync(f.outputDir); const file = path.join(f.outputDir, "existing.txt"); fs.writeFileSync(file, "preserve");
  await assert.rejects(collectRuntimeEvidence(f.options, f.environment), /OUTPUT_ALREADY_EXISTS/);
  assert.equal(fs.readFileSync(file, "utf8"), "preserve"); assert.equal(f.calls.length, 0);
});
test("unsafe endpoint forms and missing environment credentials fail before creating output", async t => {
  const f = await fixture(t);
  for (const url of ["http://example.invalid", "http://localhost:1234", "https://user:secret@example.invalid", "https://example.invalid/path", "https://example.invalid/?password=x", "file:///tmp/x"])
    assert.throws(() => endpoint(url), /REQUIRED|INVALID|BASE_URL/);
  assert.equal(endpoint("https://example.invalid").origin, "https://example.invalid");
  assert.equal(endpoint("http://[::1]:1234").hostname, "[::1]");
  await assert.rejects(collectRuntimeEvidence(f.options, {}), /PANEL_PASSWORD_ENV_REQUIRED/);
  assert.equal(f.calls.length, 0); assert.equal(fs.existsSync(f.outputDir), false);
  assert.throws(() => parseArgs(["--password", PASSWORD]), /CLI_ARGUMENTS_INVALID/);
});
test("invalid causal selection is rejected without generating a training input", async t => {
  const f = await fixture(t), selectionFile = path.join(f.root, "selection.json");
  fs.writeFileSync(selectionFile, JSON.stringify({...SELECTION, local_time: "25:00"}));
  await assert.rejects(collectRuntimeEvidence({...f.options, selectionFile}, f.environment), /SELECTION_CONTRACT_INVALID/);
  assert.equal(f.calls.length, 0); assert.equal(fs.existsSync(f.outputDir), false);
});
test("help runs without credentials or network and documents the restricted scope", () => {
  const env = {...process.env}; delete env.HARPOON_PANEL_PASSWORD; delete env.NODE_TEST_CONTEXT;
  const result = spawnSync(process.execPath, [path.join(__dirname, "collect_runtime_evidence.cjs"), "--help"], {env, encoding: "utf8", timeout: 5000});
  assert.equal(result.status, 0); assert.match(result.stdout, /fixed GET routes/); assert.match(result.stdout, /never financial approval or a score/);
  assert.equal(result.stderr, ""); assert(!result.stdout.includes(PASSWORD));
});
