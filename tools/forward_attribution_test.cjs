"use strict";
// Hermetic accounting/identity fixtures. No market experiment, network or order authority.
// PAPER below is a schema test label, not evidence of a paper or real account.
const test = require("node:test"), assert = require("node:assert/strict");
const fs = require("node:fs"), os = require("node:os"), path = require("node:path"), crypto = require("node:crypto");
const { NetAccountLedger, verifyNetLedgerHistoryBundle } = require("../runtime30/net_accounting.js");
const { digest } = require("../runtime30/ultimate_contracts.js");
const { verifyForwardAttribution } = require("./verify_forward_attribution.cjs");
const T0 = Date.UTC(2026, 9, 15, 13, 30), MIN = 60000, ACCOUNT = "SYNTHETIC-ATTRIBUTION-ACCOUNT";
const ASSETS = [{ symbol: "AAPL", book: "equity", multiplier: 1, currency: "USD" }];
const hash = b => crypto.createHash("sha256").update(b).digest("hex");
function seal(value) { const copy = { ...value }; delete copy.integrity; return { ...copy, integrity: digest(copy) }; }
class Store {
  data = new Map();
  async get(k) { return structuredClone(this.data.get(k) ?? null); }
  async put(k, v) { this.data.set(k, structuredClone(v)); return true; }
  async lease() { return true; }
  async close() {}
}
class Broker {
  account = { id: ACCOUNT, currency: "USD", cash: "20000", equity: "20000" };
  positions = []; activities = []; calls = [];
  fill(order, side, qty, price, at) {
    const signed = side === "buy" ? qty : -qty, old = this.positions[0]?.qty || "0";
    const quantity = Number(old) + signed; assert(quantity >= 0);
    this.account.cash = String(Number(this.account.cash) - signed * price);
    this.positions = quantity ? [{ symbol: "AAPL", qty: String(quantity), market_value: String(quantity * price), asset_class: "us_equity" }] : [];
    this.account.equity = String(Number(this.account.cash) + quantity * price);
    this.activities.push({ id: "fill-" + (this.activities.length + 1), activity_type: "FILL", order_id: order,
      transaction_time: new Date(at).toISOString(), symbol: "AAPL", side, qty: String(qty), price: String(price), type: "partial_fill" });
  }
  async request(url, method = "GET") {
    assert.equal(method, "GET"); this.calls.push(url);
    if (url === "/v2/account") return structuredClone(this.account);
    if (url === "/v2/positions") return structuredClone(this.positions);
    if (url.startsWith("/v2/account/activities?")) {
      const q = new URL(url, "https://synthetic.invalid").searchParams, token = q.get("page_token");
      const offset = token ? this.activities.findIndex(a => a.id === token) + 1 : 0;
      return structuredClone(this.activities.slice(offset, offset + Number(q.get("page_size"))));
    }
    throw Error("UNEXPECTED_SYNTHETIC_READ " + url);
  }
}
function costReceipt(through) {
  return { schema: "HARPOON_COST_RECEIPT_1", account_id: ACCOUNT, currency: "USD", receipt_id: "synthetic-" + through,
    coverage_complete: true, from: T0, through, known_at: through, reference: "SYNTHETIC_NO_COST_FIXTURE",
    categories: ["DATA", "INFRASTRUCTURE", "INFERENCE", "OTHER"], entries: [] };
}
function intent(id, order, kind, qty, at) {
  const side = kind === "entry" ? "buy" : "sell";
  return { id, campaign: "campaign-1", symbol: "AAPL", kind, at, status: "filled",
    payload: { symbol: "AAPL", side, qty: String(qty), client_order_id: id },
    order: { id: order, client_order_id: id, symbol: "AAPL", side, qty: String(qty), filled_qty: String(qty), status: "filled" } };
}
async function fixture(t, { tolerance = 0, open = false, partial = false, partialExit = 0 } = {}) {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-forward-test-"));
  t.after(() => fs.rmSync(dir, { recursive: true, force: true }));
  const store = new Store(), api = new Broker(), ledger = new NetAccountLedger(store, api, "synthetic-ledger", ACCOUNT,
    { executionNature: "PAPER", performanceIntervalMs: MIN });
  const refresh = now => ledger.refresh({ now, instruments: ASSETS, externalCosts: costReceipt(now) });
  await refresh(T0);
  api.fill("broker-entry", "buy", partial ? 1 : 2, 100, T0 + 10000);
  if (partial) api.fill("broker-entry", "buy", 1, 100, T0 + 20000);
  await refresh(T0 + MIN);
  if (!open || partialExit) api.fill("broker-exit", "sell", partialExit || 2, 101, T0 + MIN + 20000);
  await refresh(T0 + 2 * MIN);
  if (tolerance) await refresh(T0 + 2 * MIN + tolerance);
  const through = T0 + 2 * MIN + tolerance;
  const page = await ledger.exportHistory(0, 5000);
  const config = { expected_account_id: ACCOUNT, mode: "paper", quant: { enabled: false } };
  const expected = { account_id: ACCOUNT, execution_nature: "PAPER", candidate_role: "NATIVE", runtime_version: "SYNTHETIC-VERSION",
    runtime_config_hash: digest(config), model_hash: null, quant_config_hash: null, model_available_at: null,
    registered_at: T0 - MIN, period: { start_at: T0, end_at: T0 + 2 * MIN }, boundary_tolerance_ms: tolerance,
    initial_snapshot_max_age_ms: MIN };
  const entry = intent("intent-entry", "broker-entry", "entry", 2, T0 + 2000);
  const exit = intent("intent-exit", "broker-exit", "time", partialExit || 2, T0 + MIN + 10000);
  const campaignIntents = !open || partialExit ? [entry, exit] : [entry];
  const campaign = { id: "campaign-1", symbol: "AAPL", book: "equity", plugin: "fixture-native", created: T0 + 1000,
    closed: !open, intents: campaignIntents.map(i => i.id), forwardProvenance: seal({
      schema: "HARPOON_FORWARD_CAMPAIGN_PROVENANCE_1", campaign_id: "campaign-1", quant_receipt: null,
      decision: { decision_id: "actual-fixture-decision-id", decision_at: T0, known_at: T0 + 1000,
        account_id: ACCOUNT, execution_nature: "PAPER", candidate_role: "NATIVE", runtime_version: expected.runtime_version,
        runtime_config_hash: expected.runtime_config_hash, model_hash: null, quant_config_hash: null, model_available_at: null,
        signal_id: "fixture-native|AAPL", signal_at: T0 + 500, signal_expires: T0 + MIN,
        symbol: "AAPL", book: "equity", plugin: "fixture-native", planned_quantity: 2, quant_receipt_hash: null }
    }) };
  const makeExport = (at, campaigns, intents, positions) => ({ version: expected.runtime_version, risk: config,
    autopilot: { mode: "PAPER" }, forward_attribution: seal({ schema: "HARPOON_FORWARD_COORDINATOR_EXPORT_1", account_id: ACCOUNT,
      execution_nature: "PAPER", exported_at: at, reconciled_at: at, runtime_version: expected.runtime_version,
      runtime_config_hash: expected.runtime_config_hash, reconciliation_error: null, storage_error: null,
      broker_positions: structuredClone(positions), broker_open_orders: [], state_sequence: intents.length,
      history_scope: "CURRENT_RETAINED_STATE_NOT_COMPLETE_JOURNAL", source_authenticity_independently_verified: false,
      execution_allowed: false, liveApproved: false }), history: { campaigns, intents } });
  const initial = makeExport(T0, [], [], []), terminal = makeExport(through, [campaign], campaignIntents, api.positions);
  const bundle = { pages: [page], expected_integrity: page.ledger_integrity };
  const write = (name, value) => { const bytes = JSON.stringify(value); fs.writeFileSync(path.join(dir, name), bytes); return { path: name, sha256: hash(bytes) }; };
  const request = { schema: "HARPOON_FORWARD_ATTRIBUTION_REQUEST_1", expected,
    ledger_bundle: write("ledger.json", bundle), coordinator_export: write("terminal.json", terminal),
    initial_coordinator_export: write("initial.json", initial) };
  const verify = () => verifyForwardAttribution(request, dir);
  const saveTerminal = () => { request.coordinator_export = write("terminal.json", terminal); };
  const saveInitial = () => { request.initial_coordinator_export = write("initial.json", initial); };
  return { dir, api, ledger, bundle, config, initial, terminal, request, expected, campaign, entry, exit, verify, write, saveTerminal, saveInitial, refresh };
}
function blocked(result, pattern) {
  assert.equal(result.verified, false); assert.match(result.blockers.join("\n"), pattern);
  assert.equal(result.risk.maximum_observed_holding_hours, null);
  assert.equal(result.execution_allowed, false); assert.equal(result.financial_acceptance_allowed, false);
}
test("exact fill links reconstruct accounting and holding, without financial authority", async t => {
  const f = await fixture(t), r = f.verify(); assert.deepEqual(r.blockers, []); assert.equal(r.verified, true);
  assert.equal(r.ledger.verified, true); assert.equal(r.ledger.derived.accountNetPnlUsd, 2);
  assert.equal(r.required_fill_count, 2); assert.equal(r.attributed_fill_count, 2);
  assert(Math.abs(r.risk.maximum_observed_holding_hours - 70000 / 3600000) < 1e-12);
  assert.equal(r.preregistrationVerified, false); assert.equal(r.source_authenticity_independently_verified, false);
  assert.equal(r.execution_allowed, false); assert.equal(r.financial_acceptance_allowed, false);
});
test("partial fills and open inventory remain attributed and valued", async t => {
  const f = await fixture(t, { partial: true, open: true }), r = f.verify(); assert.deepEqual(r.blockers, []);
  assert.equal(r.attributed_fill_count, 2); assert.equal(r.ledger.observations.at(-1).positions[0].quantity, 2);
  assert.equal(r.risk.campaigns[0].remaining_quantity, 2);
  assert(Math.abs(r.risk.maximum_observed_holding_hours - 110000 / 3600000) < 1e-12);
});
test("a partial exit does not reset continuous holding age", async t => {
  const f = await fixture(t, { partial: true, open: true, partialExit: 1 }), r = f.verify(); assert.deepEqual(r.blockers, []);
  assert.equal(r.attributed_fill_count, 3); assert.equal(r.risk.campaigns[0].remaining_quantity, 1);
  assert(Math.abs(r.risk.maximum_observed_holding_hours - 110000 / 3600000) < 1e-12);
});
test("file tampering and rehashed provenance tampering are different explicit failures", async t => {
  const f = await fixture(t); fs.appendFileSync(path.join(f.dir, "terminal.json"), " ");
  blocked(f.verify(), /SOURCE_FILE_HASH_MISMATCH/);
  f.campaign.forwardProvenance.decision.model_hash = "a".repeat(64); f.saveTerminal();
  blocked(f.verify(), /PROVENANCE_MISSING_OR_TAMPERED/);
  f.campaign.forwardProvenance = seal(f.campaign.forwardProvenance); f.saveTerminal();
  blocked(f.verify(), /DECISION_BINDING_MISMATCH:model_hash/);
});
test("missing legacy provenance cannot be repaired by timestamp proximity", async t => {
  const f = await fixture(t); f.campaign.forwardProvenance = null; f.saveTerminal();
  blocked(f.verify(), /PROVENANCE_MISSING_OR_TAMPERED/);
});
test("unknown broker order ID and duplicate ownership both block attribution", async t => {
  const f = await fixture(t); f.entry.order.id = "other-order-near-in-time"; f.saveTerminal();
  blocked(f.verify(), /FILL_ORDER_ID_NOT_RETAINED/);
  f.entry.order.id = "broker-entry";
  f.terminal.history.intents.push({ ...structuredClone(f.entry), id: "duplicate-intent" }); f.saveTerminal();
  blocked(f.verify(), /BROKER_ORDER_ID_MISSING_OR_AMBIGUOUS/);
});
test("future decision knowledge is rejected even after valid resealing", async t => {
  const f = await fixture(t); f.campaign.forwardProvenance.decision.known_at = f.entry.at + 1;
  f.campaign.forwardProvenance = seal(f.campaign.forwardProvenance); f.saveTerminal();
  blocked(f.verify(), /DECISION_NOT_CAUSALLY_PRIOR_TO_ORDER/);
});
test("rehashing normalized fill timestamps cannot move real raw fills outside the period", async t => {
  const f = await fixture(t), b = structuredClone(f.bundle), page = b.pages[0];
  const records = page.records, header = records.find(r => r.kind === "HEADER");
  const observations = records.filter(r => r.kind === "OBSERVATION").map(r => r.value);
  const activities = records.filter(r => r.kind === "ACTIVITY").map(r => r.value);
  const externalCosts = records.filter(r => r.kind === "COST").map(r => r.value);
  for (const a of activities) a.at = T0 - 1;
  const state = { ...header.value, observations, activities, externalCosts };
  state.evidence.activitiesHash = digest(activities); state.integrity = seal(state).integrity;
  header.value = { ...state }; delete header.value.observations; delete header.value.activities; delete header.value.externalCosts;
  b.expected_integrity = page.ledger_integrity = state.integrity;
  assert.equal(verifyNetLedgerHistoryBundle(b.pages, b.expected_integrity).verified, true,
    "bookkeeping verification alone does not establish the normalized attribution clock");
  f.request.ledger_bundle = f.write("ledger.json", b);
  blocked(f.verify(), /FILL_RAW_TIME_OR_TYPE_MISMATCH/);
});
test("initial inventory, pending intent and missing initial export never become zero", async t => {
  const f = await fixture(t); f.initial.forward_attribution.broker_positions = [{ symbol: "AAPL", qty: "1" }];
  f.initial.forward_attribution = seal(f.initial.forward_attribution); f.saveInitial();
  blocked(f.verify(), /INITIAL_INVENTORY_OR_PENDING_NOT_FLAT/);
  f.initial.forward_attribution.broker_positions = []; f.initial.forward_attribution = seal(f.initial.forward_attribution);
  f.initial.history.intents = [{ id: "maybe-accepted", status: "UNKNOWN" }]; f.saveInitial();
  blocked(f.verify(), /INITIAL_LOCAL_PENDING_OR_UNKNOWN_INTENT/);
  delete f.request.initial_coordinator_export;
  blocked(f.verify(), /BOUND_SOURCE_REFERENCE_REQUIRED/);
});
test("account and PAPER/REAL contradictions cannot certify real execution", async t => {
  const f = await fixture(t); f.request.expected.execution_nature = "REAL";
  blocked(f.verify(), /EXECUTION_NATURE_MISMATCH/);
  f.request.expected.execution_nature = "PAPER"; f.request.expected.account_id = "different-account";
  blocked(f.verify(), /ACCOUNT_MISMATCH/);
});
test("missing tolerance is unknown, and an uncovered late-fill window is not certified", async t => {
  const f = await fixture(t); delete f.expected.boundary_tolerance_ms;
  blocked(f.verify(), /BOUNDARY_TOLERANCE_REQUIRED/);
  f.expected.boundary_tolerance_ms = 30000;
  blocked(f.verify(), /BOUNDARY_COVERAGE_MISSING/);
});
test("late fills inside the preregistered boundary tolerance cannot be dropped", async t => {
  const f = await fixture(t, { open: true, tolerance: 30000 });
  f.api.fill("broker-late-exit", "sell", 2, 101, T0 + 2 * MIN + 20000);
  await f.refresh(T0 + 3 * MIN);
  const page = await f.ledger.exportHistory(0, 5000);
  f.request.ledger_bundle = f.write("ledger.json", { pages: [page], expected_integrity: page.ledger_integrity });
  f.terminal.forward_attribution.reconciled_at = T0 + 3 * MIN;
  f.terminal.forward_attribution.exported_at = T0 + 3 * MIN;
  f.terminal.forward_attribution.broker_positions = [];
  f.terminal.forward_attribution = seal(f.terminal.forward_attribution); f.saveTerminal();
  const r = f.verify(); blocked(r, /FILL_ORDER_ID_NOT_RETAINED/); assert.equal(r.required_fill_count, 2);
});
test("numerical model receipt must match the frozen model and actual selected decision", async t => {
  const f = await fixture(t), d = f.campaign.forwardProvenance.decision;
  f.config.quant.enabled = true; f.expected.runtime_config_hash = digest(f.config);
  Object.assign(f.expected, { candidate_role: "SVR", model_hash: "a".repeat(64), quant_config_hash: "b".repeat(64), model_available_at: T0 - 2 * MIN });
  Object.assign(d, { candidate_role: "SVR", model_hash: f.expected.model_hash, quant_config_hash: f.expected.quant_config_hash,
    runtime_config_hash: f.expected.runtime_config_hash, model_available_at: f.expected.model_available_at });
  const q = { engine: "HARPOON_QUANT_1", forecast_model_kind: "SVR_RBF", research_only: false, execution_allowed: true,
    decision_id: d.decision_id, decision_at: d.decision_at, completed_at: d.known_at, account_id: ACCOUNT,
    model_hash: d.model_hash, config_hash: d.quant_config_hash, selected: [{ id: d.signal_id }],
    decision_inputs: { calibration_available_at: new Date(d.model_available_at).toISOString() } };
  f.campaign.forwardProvenance.quant_receipt = q; d.quant_receipt_hash = digest(q);
  f.campaign.forwardProvenance = seal(f.campaign.forwardProvenance);
  for (const exp of [f.initial, f.terminal]) {
    exp.forward_attribution.runtime_config_hash = f.expected.runtime_config_hash;
    exp.forward_attribution = seal(exp.forward_attribution);
  }
  f.saveInitial(); f.saveTerminal(); assert.deepEqual(f.verify().blockers, []);
  q.research_only = true; f.campaign.forwardProvenance.decision.quant_receipt_hash = digest(q);
  f.campaign.forwardProvenance = seal(f.campaign.forwardProvenance); f.saveTerminal();
  blocked(f.verify(), /QUANT_RECEIPT_DID_NOT_SELECT_EXECUTABLE_SIGNAL/);
});
test("coordinator persists native provenance with the intent before the synthetic POST", async () => {
  const { ready, signal, prepare } = require("./xxx_fixtures.cjs");
  const { e, api, store } = await ready(); const s = signal("equity"); prepare(e, s);
  const original = api.request.bind(api); let observed = false;
  api.request = async (url, method = "GET", body, market) => {
    if (url === "/v2/orders" && method === "POST" && body.side === "buy") {
      const saved = [...store.data.values()].find(v => Array.isArray(v?.campaigns) && v.campaigns.length);
      assert(saved, "campaign must be in durable fixture store before POST");
      const campaign = saved.campaigns[0], p = campaign.forwardProvenance;
      assert.equal(p.decision.candidate_role, "NATIVE"); assert.equal(p.decision.model_hash, null);
      assert.equal(p.quant_receipt, null); assert.equal(p.integrity, seal(p).integrity);
      const i = saved.intents.find(x => x.id === body.client_order_id);
      assert.equal(i.campaign, campaign.id); assert(p.decision.known_at <= i.at);
      observed = true;
    }
    return original(url, method, body, market);
  };
  await e.entries("equity"); assert.equal(observed, true);
  const ex = e.evidence(); assert.equal(ex.forward_attribution.account_id, e.cfg.expected_account_id);
  assert.equal(ex.forward_attribution.integrity, seal(ex.forward_attribution).integrity);
  assert.equal(ex.history.campaigns[0].forwardProvenance.decision.candidate_role, "NATIVE");
});
test("CLI cannot overwrite its input or an existing report", async t => {
  const { spawnSync } = require("node:child_process"), f = await fixture(t);
  const source = path.join(f.dir, "request.json"), output = path.join(f.dir, "report.json");
  fs.writeFileSync(source, JSON.stringify(f.request)); fs.writeFileSync(output, "PRESERVE_EXISTING_REPORT");
  const before = fs.readFileSync(source, "utf8"), tool = path.join(__dirname, "verify_forward_attribution.cjs");
  const run = target => spawnSync(process.execPath, ["--no-use-env-proxy", tool, "--input", source, "--output", target],
    { encoding: "utf8", timeout: 10000 });
  assert.equal(run(source).status, 2); assert.equal(fs.readFileSync(source, "utf8"), before);
  assert.equal(run(output).status, 2); assert.equal(fs.readFileSync(output, "utf8"), "PRESERVE_EXISTING_REPORT");
  const fresh = path.join(f.dir, "fresh-report.json"), result = run(fresh);
  assert.equal(result.status, 0, result.stderr); assert.equal(JSON.parse(fs.readFileSync(fresh, "utf8")).verified, true);
});
