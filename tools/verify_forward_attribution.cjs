"use strict";
/** Offline identity/causality verification, never a profitability or order gate.
 * Local hashes detect inconsistent evidence; they do not authenticate a broker.
 * Every fill is linked by its broker order ID, never by temporal proximity.
 */
const fs = require("node:fs"), path = require("node:path"), crypto = require("node:crypto");
const { parseStrictJSON } = require("./level4_readiness.cjs");
const { verifyNetLedgerHistoryBundle } = require("../runtime30/net_accounting.js");
const { digest } = require("../runtime30/ultimate_contracts.js");
const REQUEST = "HARPOON_FORWARD_ATTRIBUTION_REQUEST_1";
const TERMINAL = new Set(["filled", "canceled", "expired", "rejected", "replaced"]);
const SHA = /^[a-f0-9]{64}$/;
const authority = { execution_allowed: false, liveApproved: false, financial_acceptance_allowed: false };
const need = (v, code) => { if (!v) throw Error(code); };
const object = v => !!v && typeof v === "object" && !Array.isArray(v);
const finite = v => typeof v === "number" && Number.isFinite(v);
const nonempty = v => typeof v === "string" && v.trim().length > 0 && v.length <= 500;
const near = (a, b) => finite(a) && finite(b) && Math.abs(a - b) <= 1e-8 * Math.max(1, Math.abs(a), Math.abs(b));
const sha = bytes => crypto.createHash("sha256").update(bytes).digest("hex");
function instant(v, code) {
  const n = typeof v === "number" ? v : typeof v === "string" && /T.*(?:Z|[+-]\d\d:\d\d)$/.test(v) ? Date.parse(v) : NaN;
  need(Number.isSafeInteger(n) && n > 0, code); return n;
}
function sealValid(value, code) {
  need(object(value) && SHA.test(value.integrity || ""), code);
  const copy = { ...value }; delete copy.integrity;
  need(digest(copy) === value.integrity, code); return value;
}
function readRef(ref, base, sources) {
  need(object(ref) && nonempty(ref.path) && SHA.test(ref.sha256 || ""), "BOUND_SOURCE_REFERENCE_REQUIRED");
  const file = path.resolve(base, ref.path), stat = fs.statSync(file);
  need(stat.isFile() && stat.size <= 192 * 1024 * 1024, "SOURCE_FILE_SIZE_BOUND");
  const bytes = fs.readFileSync(file);
  need(sha(bytes) === ref.sha256, "SOURCE_FILE_HASH_MISMATCH:" + path.basename(file));
  if (ref.bytes !== undefined) need(ref.bytes === bytes.length, "SOURCE_BYTE_COUNT_MISMATCH");
  sources.push({ path: file, sha256: ref.sha256, bytes: bytes.length });
  need(sources.reduce((n, r) => n + r.bytes, 0) <= 384 * 1024 * 1024, "TOTAL_SOURCE_BYTES_BOUND");
  return parseStrictJSON(bytes.toString("utf8"));
}
function expectedBindings(input) {
  const e = input.expected;
  need(object(e) && nonempty(e.account_id), "EXPECTED_ACCOUNT_ID_REQUIRED");
  need(["PAPER", "REAL", "LIVE"].includes(e.execution_nature), "EXPECTED_EXECUTION_NATURE_REQUIRED");
  need(["NATIVE", "RIDGE", "SVR"].includes(e.candidate_role), "EXPECTED_CANDIDATE_ROLE_REQUIRED");
  need(nonempty(e.runtime_version) && SHA.test(e.runtime_config_hash || ""), "EXPECTED_RUNTIME_BINDING_REQUIRED");
  need(object(e.period), "EXPECTED_PERIOD_REQUIRED");
  const start = instant(e.period.start_at, "EXPECTED_PERIOD_START"), end = instant(e.period.end_at, "EXPECTED_PERIOD_END");
  const registered = instant(e.registered_at, "EXPECTED_REGISTRATION_TIME_REQUIRED");
  need(registered < start && start < end && end <= Date.now(), "EXPECTED_PERIOD_OR_REGISTRATION_ORDER");
  const tolerance = e.boundary_tolerance_ms, age = e.initial_snapshot_max_age_ms;
  need(Number.isSafeInteger(tolerance) && tolerance >= 0 && tolerance <= 90000, "BOUNDARY_TOLERANCE_REQUIRED");
  need(Number.isSafeInteger(age) && age > 0 && age <= 90000, "INITIAL_SNAPSHOT_AGE_LIMIT_REQUIRED");
  need(end + tolerance <= Date.now(), "ATTRIBUTION_WINDOW_NOT_YET_CLOSED");
  if (e.candidate_role === "NATIVE") {
    need(e.model_hash === null && e.quant_config_hash === null && e.model_available_at === null,
      "NATIVE_MODEL_BINDINGS_MUST_BE_EXPLICIT_NULL");
  } else {
    need(SHA.test(e.model_hash || "") && SHA.test(e.quant_config_hash || ""), "EXPECTED_NUMERICAL_MODEL_BINDING_REQUIRED");
    need(instant(e.model_available_at, "EXPECTED_MODEL_AVAILABILITY_REQUIRED") < registered, "MODEL_NOT_FROZEN_BEFORE_REGISTRATION");
  }
  return { ...e, start, end, registered, tolerance, maxInitialAge: age,
    model_available_at: e.model_available_at === null ? null : instant(e.model_available_at, "EXPECTED_MODEL_AVAILABILITY_REQUIRED") };
}
function exportHeader(value, e, kind) {
  need(object(value), kind + "_EXPORT_REQUIRED");
  const h = sealValid(value.forward_attribution, kind + "_EXPORT_INTEGRITY");
  need(h.schema === "HARPOON_FORWARD_COORDINATOR_EXPORT_1", kind + "_EXPORT_SCHEMA");
  need(h.account_id === e.account_id, kind + "_ACCOUNT_MISMATCH");
  need(h.execution_nature === e.execution_nature, kind + "_EXECUTION_NATURE_MISMATCH");
  need(h.runtime_version === e.runtime_version && value.version === h.runtime_version, kind + "_RUNTIME_VERSION_MISMATCH");
  need(h.runtime_config_hash === e.runtime_config_hash && object(value.risk) && digest(value.risk) === h.runtime_config_hash,
    kind + "_RUNTIME_CONFIG_MISMATCH");
  need(value.risk.expected_account_id === e.account_id && typeof value.risk.mode === "string" &&
    value.risk.mode.toUpperCase() === e.execution_nature, kind + "_CONFIG_IDENTITY_MISMATCH");
  if (object(value.autopilot) && value.autopilot.mode !== undefined)
    need(value.autopilot.mode === e.execution_nature, kind + "_AUTOPILOT_EXECUTION_NATURE_MISMATCH");
  need(!h.reconciliation_error && !h.storage_error, kind + "_RECONCILIATION_OR_STORAGE_ERROR");
  const exported = instant(h.exported_at, kind + "_EXPORT_TIME_REQUIRED"), reconciled = instant(h.reconciled_at, kind + "_RECONCILIATION_TIME_REQUIRED");
  need(reconciled <= exported && exported <= Date.now(), kind + "_SNAPSHOT_TIME_ORDER");
  need(Array.isArray(h.broker_positions) && Array.isArray(h.broker_open_orders), kind + "_BROKER_STATE_UNKNOWN");
  need(object(value.history) && Array.isArray(value.history.campaigns) && Array.isArray(value.history.intents), kind + "_HISTORY_MISSING");
  need(h.history_scope === "CURRENT_RETAINED_STATE_NOT_COMPLETE_JOURNAL", kind + "_HISTORY_SCOPE_UNKNOWN");
  return { ...h, exported_at: exported, reconciled_at: reconciled };
}
function quantities(positions, normalized = false) {
  need(Array.isArray(positions), "POSITION_STATE_UNKNOWN"); const out = new Map();
  for (const p of positions) {
    need(object(p) && nonempty(p.symbol) && !out.has(p.symbol), "POSITION_IDENTITY_AMBIGUOUS");
    const n = normalized ? p.quantity : Number(p.qty);
    need(finite(n) && (normalized || typeof p.qty === "string" || typeof p.qty === "number"), "POSITION_QUANTITY_UNKNOWN");
    out.set(p.symbol, n);
  }
  return out;
}
function sameQuantities(a, b, code) {
  for (const symbol of new Set([...a.keys(), ...b.keys()])) need(near(a.get(symbol) ?? 0, b.get(symbol) ?? 0), code + ":" + symbol);
}

function verifyForwardAttribution(input, baseDir = process.cwd()) {
  const out = { schema: "HARPOON_FORWARD_ATTRIBUTION_REPORT_1", verified: false, blockers: [],
    generated_at: new Date().toISOString(), period: null, accountId: null, executionNature: null,
    candidateBindings: null, expectedBindingsHash: null, preregistrationVerified: false,
    ledger_verified: false, ledger: null, attributions: [], sources: [],
    risk: { maximum_observed_holding_hours: null, method: "CONTINUOUS_CAMPAIGN_AGE_FROM_FIRST_FILL_PARTIAL_EXITS_DO_NOT_RESET", campaigns: null },
    snapshot_coherence: { initial_flat_verified: false, terminal_quantities_reconciled: false,
      atomic_snapshot_with_ledger: false, complete_historical_journal_claimed: false },
    source_authenticity_independently_verified: false,
    limitations: ["Hashes and local timestamps do not independently authenticate the broker or clock.",
      "Retained coordinator state is not a complete historical journal; every required exact link must still be present.",
      "Attribution does not establish costs, net profitability, statistical significance or trading authority.",
      "Snapshot reconciliation is by quantities and explicit order identities, not an atomic broker snapshot."], ...authority };
  const record = (error, prefix = "") => { const code = prefix + String(error?.message || error); if (!out.blockers.includes(code)) out.blockers.push(code); };
  let e, terminal, initial, th, ih;
  try {
    need(object(input) && input.schema === REQUEST, "ATTRIBUTION_REQUEST_SCHEMA");
    e = expectedBindings(input); out.expectedBindingsHash = digest(input.expected);
    out.accountId = e.account_id; out.executionNature = e.execution_nature;
    out.candidateBindings = { candidate_role: e.candidate_role, runtime_version: e.runtime_version,
      runtime_config_hash: e.runtime_config_hash, model_hash: e.model_hash,
      quant_config_hash: e.quant_config_hash, model_available_at: e.model_available_at };
    out.period = { start_at: e.start, end_at: e.end, attribution_through: e.end + e.tolerance,
      effective_start_at: null, effective_end_at: null, boundary_tolerance_ms: e.tolerance };
  } catch (err) { record(err); return out; }
  try {
    const bundle = readRef(input.ledger_bundle, baseDir, out.sources);
    need(object(bundle) && Array.isArray(bundle.pages) && SHA.test(bundle.expected_integrity || ""), "LEDGER_BUNDLE_REQUIRED");
    out.ledger = verifyNetLedgerHistoryBundle(bundle.pages, bundle.expected_integrity);
    need(out.ledger.verified === true, "LEDGER_RECONSTRUCTION_FAILED"); out.ledger_verified = true;
    need(out.ledger.accountId === e.account_id, "LEDGER_ACCOUNT_MISMATCH");
    need(out.ledger.state?.evidence?.executionNature === e.execution_nature, "LEDGER_EXECUTION_NATURE_MISMATCH");
    need(out.ledger.state.reconciled === true, "LEDGER_NOT_RECONCILED");
  } catch (err) { record(err, "LEDGER:"); }
  try { terminal = readRef(input.coordinator_export, baseDir, out.sources); th = exportHeader(terminal, e, "TERMINAL"); }
  catch (err) { record(err); }
  try { initial = readRef(input.initial_coordinator_export, baseDir, out.sources); ih = exportHeader(initial, e, "INITIAL"); }
  catch (err) { record(err); }
  if (!out.ledger_verified || !th || !ih) return out;
  const ledger = out.ledger, scopeEnd = e.end + e.tolerance;
  // Validate raw clocks before selecting a period. Otherwise rehashed normalized
  // timestamps could move a round trip outside the scope and erase its attribution.
  const allFills = ledger.activities.filter(a => a.raw?.activity_type === "FILL" || a.activityType === "FILL" || a.classification === "FILL");
  for (const a of allFills) {
    try {
      need(object(a.raw) && a.raw.activity_type === "FILL" && a.activityType === "FILL" &&
        a.at === instant(a.raw.transaction_time, "FILL_RAW_TIME_UNKNOWN"), "FILL_RAW_TIME_OR_TYPE_MISMATCH");
      need(a.id === a.raw.id && a.orderId === a.raw.order_id && nonempty(a.orderId) && a.symbol === a.raw.symbol,
        "FILL_RAW_IDENTITY_MISMATCH");
      need(a.knownAt >= a.at && a.knownAt <= ledger.through, "FILL_KNOWLEDGE_TIME_NOT_CAUSAL");
    } catch (err) { record(err, "FILL:" + a.id + ":"); }
  }
  let first, last;
  try {
    need(ledger.from <= e.start + e.tolerance && ledger.through >= scopeEnd, "LEDGER_BOUNDARY_COVERAGE_MISSING");
    first = ledger.observations.find(r => r.at >= e.start); last = ledger.observations.find(r => r.at >= e.end);
    need(first && last && first.at - e.start <= e.tolerance && last.at - e.end <= e.tolerance && first.at < last.at,
      "LEDGER_BOUNDARY_MARK_MISSING_OR_LATE");
    out.period.effective_start_at = first.at; out.period.effective_end_at = last.at;
    need(ih.exported_at <= e.start && e.start - ih.reconciled_at <= e.maxInitialAge,
      "INITIAL_SNAPSHOT_NOT_BEFORE_START_OR_TOO_OLD");
    need(th.reconciled_at >= scopeEnd && th.exported_at >= ledger.through, "TERMINAL_SNAPSHOT_NOT_THROUGH_ATTRIBUTION_WINDOW");
    need(ih.broker_positions.length === 0 && ih.broker_open_orders.length === 0, "INITIAL_INVENTORY_OR_PENDING_NOT_FLAT");
    need(initial.history.intents.every(i => object(i) && TERMINAL.has(i.status)), "INITIAL_LOCAL_PENDING_OR_UNKNOWN_INTENT");
    need(initial.history.campaigns.every(c => object(c) && c.closed === true), "INITIAL_LOCAL_CAMPAIGN_OPEN_OR_UNKNOWN");
    need(first.positions.length === 0, "INITIAL_LEDGER_INVENTORY_NOT_FLAT");
    for (const a of ledger.activities) if (a.activityType === "FILL" || a.classification === "FILL") {
      need(finite(a.at), "FILL_TIME_UNKNOWN:" + a.id);
      need(!(a.at > ih.reconciled_at && a.at <= first.at), "FILL_BETWEEN_INITIAL_SNAPSHOT_AND_BASELINE:" + a.id);
    }
    out.snapshot_coherence.initial_flat_verified = true;
  } catch (err) { record(err); }

  const campaigns = new Map(), intents = new Map(), orders = new Map();
  try {
    for (const c of terminal.history.campaigns) {
      need(object(c) && nonempty(c.id) && !campaigns.has(c.id), "CAMPAIGN_ID_MISSING_OR_DUPLICATED"); campaigns.set(c.id, c);
    }
    for (const i of terminal.history.intents) {
      need(object(i) && nonempty(i.id) && !intents.has(i.id), "INTENT_ID_MISSING_OR_DUPLICATED"); intents.set(i.id, i);
      if (i.order) {
        need(object(i.order) && nonempty(i.order.id) && !orders.has(i.order.id), "BROKER_ORDER_ID_MISSING_OR_AMBIGUOUS");
        orders.set(i.order.id, i);
      }
    }
  } catch (err) { record(err); return out; }
  const validCampaigns = new Map();
  function validateCampaign(c, i) {
    need(c && Array.isArray(c.intents) && c.intents.includes(i.id), "CAMPAIGN_INTENT_LINK_MISSING");
    need(c.symbol === i.symbol && i.payload?.symbol === c.symbol, "CAMPAIGN_INTENT_SYMBOL_MISMATCH");
    const p = sealValid(c.forwardProvenance, "CAMPAIGN_PROVENANCE_MISSING_OR_TAMPERED");
    need(p.schema === "HARPOON_FORWARD_CAMPAIGN_PROVENANCE_1" && p.campaign_id === c.id && object(p.decision), "CAMPAIGN_PROVENANCE_SCHEMA");
    const d = p.decision;
    need(nonempty(d.decision_id), "DECISION_ID_REQUIRED");
    for (const key of ["account_id", "execution_nature", "candidate_role", "runtime_version", "runtime_config_hash", "model_hash", "quant_config_hash"])
      need(d[key] === e[key], "DECISION_BINDING_MISMATCH:" + key);
    need(d.symbol === c.symbol && d.plugin === c.plugin && d.book === c.book &&
      d.signal_id === c.plugin + "|" + c.symbol, "DECISION_CAMPAIGN_IDENTITY_MISMATCH");
    const decisionAt = instant(d.decision_at, "DECISION_TIME_REQUIRED"), knownAt = instant(d.known_at, "DECISION_KNOWLEDGE_TIME_REQUIRED");
    const created = instant(c.created, "CAMPAIGN_CREATED_TIME_REQUIRED"), intentAt = instant(i.at, "INTENT_TIME_REQUIRED");
    need(e.registered < decisionAt && e.start <= decisionAt && decisionAt <= created && created <= knownAt &&
      knownAt <= intentAt && intentAt <= th.exported_at, "DECISION_NOT_CAUSALLY_PRIOR_TO_ORDER");
    need(instant(d.signal_at, "SIGNAL_TIME_REQUIRED") <= knownAt &&
      instant(d.signal_expires, "SIGNAL_EXPIRY_REQUIRED") >= knownAt, "SIGNAL_UNKNOWN_OR_EXPIRED_AT_DECISION");
    need(finite(d.planned_quantity) && d.planned_quantity > 0, "PLANNED_QUANTITY_UNKNOWN");
    if (e.candidate_role === "NATIVE") {
      need(d.model_available_at === null && d.quant_receipt_hash === null && p.quant_receipt === null, "NATIVE_RECEIPT_MUST_BE_NULL");
    } else {
      need(instant(d.model_available_at, "MODEL_AVAILABILITY_REQUIRED") === e.model_available_at &&
        e.model_available_at <= decisionAt && SHA.test(d.quant_receipt_hash || ""), "MODEL_RECEIPT_NOT_AVAILABLE_AT_DECISION");
      const q = p.quant_receipt;
      need(object(q) && digest(q) === d.quant_receipt_hash && q.decision_id === d.decision_id && q.decision_at === d.decision_at &&
        q.account_id === d.account_id && q.model_hash === d.model_hash && q.config_hash === d.quant_config_hash,
        "QUANT_RECEIPT_BINDING_MISSING_OR_TAMPERED");
      need(q.engine === "HARPOON_QUANT_1" && q.execution_allowed === true && q.research_only === false &&
        Array.isArray(q.selected) && q.selected.some(s => s.id === d.signal_id), "QUANT_RECEIPT_DID_NOT_SELECT_EXECUTABLE_SIGNAL");
      const observedRole = q.forecast_model_kind === "SVR_RBF" ? "SVR" : q.forecast_model_kind === null ? "RIDGE" : null;
      need(observedRole === e.candidate_role, "QUANT_RECEIPT_MODEL_ROLE_MISMATCH");
      need(instant(q.completed_at, "QUANT_COMPLETION_TIME_REQUIRED") <= knownAt &&
        instant(q.decision_inputs?.calibration_available_at, "QUANT_MODEL_TIME_REQUIRED") === e.model_available_at,
        "QUANT_RECEIPT_KNOWLEDGE_NOT_CAUSAL");
    }
    if (i.parentId) {
      const parent = intents.get(i.parentId);
      need(parent && parent.campaign === c.id && parent.at === i.at && parent.symbol === c.symbol, "NATIVE_CHILD_PARENT_LINK_MISSING");
    }
    validCampaigns.set(c.id, c); return d;
  }
  const orderFillTotals = new Map();
  for (const a of allFills) orderFillTotals.set(a.orderId, (orderFillTotals.get(a.orderId) ?? 0) + Math.abs(a.quantityDelta));
  const scoped = allFills.filter(a => finite(a.at) && e.start <= a.at && a.at <= scopeEnd).sort((a, b) => a.at - b.at || a.id.localeCompare(b.id));
  for (const a of scoped) {
    try {
      need(a.classification === "FILL" && a.baselineIncluded === false, "FILL_NOT_POST_BASELINE_RECONSTRUCTED");
      need(object(a.raw) && nonempty(a.raw.order_id) && a.orderId === a.raw.order_id && a.symbol === a.raw.symbol &&
        a.id === a.raw.id && a.activityType === a.raw.activity_type, "FILL_RAW_IDENTITY_MISMATCH");
      need(a.at === instant(a.raw.transaction_time, "FILL_RAW_TIME_UNKNOWN"), "FILL_RAW_TIME_MISMATCH");
      const signed = Number(a.raw.qty) * (a.raw.side === "buy" ? 1 : a.raw.side === "sell" ? -1 : NaN);
      need(finite(signed) && signed !== 0 && Number(a.raw.qty) > 0 && near(a.quantityDelta, signed), "FILL_RAW_QUANTITY_MISMATCH");
      const i = orders.get(a.orderId);
      need(i, "FILL_ORDER_ID_NOT_RETAINED");
      const c = campaigns.get(i.campaign), d = validateCampaign(c, i);
      need(i.order.client_order_id === i.id && (i.payload.client_order_id === undefined || i.payload.client_order_id === i.id), "INTENT_CLIENT_ORDER_ID_MISMATCH");
      need(i.order.symbol === c.symbol && a.symbol === c.symbol && i.order.side === a.raw.side && i.payload.side === a.raw.side,
        "FILL_INTENT_ORDER_CONTRACT_MISMATCH");
      need(Number(i.order.qty) > 0 && Number(i.payload.qty) > 0 && near(Number(i.order.qty), Number(i.payload.qty)), "ORDER_QUANTITY_MISMATCH");
      need(a.at >= i.at && a.knownAt >= a.at && a.knownAt <= ledger.through && a.at <= th.reconciled_at, "FILL_CLOCK_NOT_CAUSAL");
      const cum = orderFillTotals.get(a.orderId);
      need(finite(cum) && near(cum, Number(i.order.filled_qty)) && cum <= Number(i.order.qty) + 1e-8, "ORDER_FILL_TOTAL_NOT_RECONCILED");
      out.attributions.push({ activity_id: a.id, order_id: a.orderId, intent_id: i.id, campaign_id: c.id,
        decision_id: d.decision_id, candidate_role: d.candidate_role, symbol: a.symbol, side: a.raw.side,
        quantity_delta: a.quantityDelta, at: a.at, known_at: a.knownAt, kind: i.kind,
        provenance_hash: c.forwardProvenance.integrity, runtime_config_hash: d.runtime_config_hash, model_hash: d.model_hash });
    } catch (err) { record(err, "FILL:" + a.id + ":"); }
  }
  // Pending exposure also needs provenance. A submitted cancel is not terminal.
  for (const o of th.broker_open_orders) {
    try {
      need(object(o) && nonempty(o.id) && orders.has(o.id), "OPEN_ORDER_NOT_ATTRIBUTED");
      const i = orders.get(o.id); validateCampaign(campaigns.get(i.campaign), i);
      need(!TERMINAL.has(i.status) && o.client_order_id === i.id && o.symbol === i.symbol &&
        near(Number(o.filled_qty), Number(i.order.filled_qty)), "OPEN_ORDER_SNAPSHOT_MISMATCH");
    } catch (err) { record(err, "PENDING:"); }
  }
  for (const i of terminal.history.intents.filter(i => !TERMINAL.has(i.status))) {
    if (!th.broker_open_orders.some(o => o.id === i.order?.id)) record(Error("LOCAL_PENDING_WITHOUT_CONFIRMED_BROKER_ORDER:" + i.id));
  }
  try {
    sameQuantities(quantities(th.broker_positions), quantities(ledger.observations.at(-1).positions, true), "TERMINAL_POSITION_QUANTITY_MISMATCH");
    out.snapshot_coherence.terminal_quantities_reconciled = true;
  } catch (err) { record(err); }
  // Reconstruct inventory at every retained mark; a scalar final NAV alone is insufficient.
  if (first && last && out.attributions.length === scoped.length && out.snapshot_coherence.initial_flat_verified) {
    try {
      const inventory = new Map(); let cursor = 0;
      for (const row of ledger.observations.filter(r => first.at <= r.at && r.at <= scopeEnd)) {
        while (cursor < out.attributions.length && out.attributions[cursor].at <= row.at) {
          const a = out.attributions[cursor++]; inventory.set(a.symbol, (inventory.get(a.symbol) ?? 0) + a.quantity_delta);
        }
        sameQuantities(inventory, quantities(row.positions, true), "CAMPAIGN_LEDGER_INVENTORY_MISMATCH_AT_" + row.at);
      }
    } catch (err) { record(err); }
    try {
      const lots = new Map(), riskCampaigns = new Map(); let maximum = 0;
      for (const a of out.attributions) {
        const c = validCampaigns.get(a.campaign_id), l = lots.get(a.campaign_id) || [];
        const stats = riskCampaigns.get(a.campaign_id) || { campaign_id: a.campaign_id, symbol: a.symbol,
          entry_quantity: 0, remaining_quantity: 0, maximum_observed_holding_hours: 0, open_since: null };
        need(a.quantity_delta > 0 ? a.kind === "entry" : a.kind !== "entry", "FILL_DIRECTION_OR_ENTRY_CLASSIFICATION_UNKNOWN");
        if (stats.open_since !== null) {
          const age = (a.at - stats.open_since) / 3600000; need(age >= 0, "CAMPAIGN_TIME_REGRESSION");
          maximum = Math.max(maximum, age); stats.maximum_observed_holding_hours = Math.max(stats.maximum_observed_holding_hours, age);
        }
        if (a.quantity_delta > 0) {
          if (stats.open_since === null) stats.open_since = a.at;
          stats.entry_quantity += a.quantity_delta;
          need(stats.entry_quantity <= c.forwardProvenance.decision.planned_quantity + 1e-8, "CAMPAIGN_ENTRY_EXCEEDS_PRERECORDED_QUANTITY");
          l.push({ at: a.at, quantity: a.quantity_delta });
        } else {
          let remaining = -a.quantity_delta;
          while (remaining > 1e-8) {
            need(l.length > 0, "EXIT_WITHOUT_ATTRIBUTED_ENTRY_INVENTORY");
            const lot = l[0], taken = Math.min(remaining, lot.quantity);
            const hours = (a.at - lot.at) / 3600000;
            need(hours >= 0, "EXIT_PRECEDES_ENTRY"); maximum = Math.max(maximum, hours);
            stats.maximum_observed_holding_hours = Math.max(stats.maximum_observed_holding_hours, hours);
            lot.quantity -= taken; remaining -= taken; if (lot.quantity <= 1e-8) l.shift();
          }
        }
        if (!l.length) stats.open_since = null;
        lots.set(a.campaign_id, l); riskCampaigns.set(a.campaign_id, stats);
      }
      for (const [id, l] of lots) {
        const stats = riskCampaigns.get(id); stats.remaining_quantity = l.reduce((n, x) => n + x.quantity, 0);
        if (stats.open_since !== null) {
          const age = (scopeEnd - stats.open_since) / 3600000; need(age >= 0, "CAMPAIGN_AFTER_WINDOW");
          maximum = Math.max(maximum, age); stats.maximum_observed_holding_hours = Math.max(stats.maximum_observed_holding_hours, age);
        }
        for (const lot of l) {
          const hours = (scopeEnd - lot.at) / 3600000; need(hours >= 0, "OPEN_LOT_AFTER_WINDOW");
          maximum = Math.max(maximum, hours); stats.maximum_observed_holding_hours = Math.max(stats.maximum_observed_holding_hours, hours);
        }
      }
      // Zero has a meaning only with a verified flat start and no missing links.
      out.risk.maximum_observed_holding_hours = maximum;
      out.risk.campaigns = [...riskCampaigns.values()];
    } catch (err) { record(err, "HOLDING:"); }
  }
  out.verified = out.blockers.length === 0;
  if (!out.verified) { out.risk.maximum_observed_holding_hours = null; out.risk.campaigns = null; }
  out.attributed_fill_count = out.attributions.length; out.required_fill_count = scoped.length;
  return out;
}

module.exports = { verifyForwardAttribution, REQUEST_SCHEMA: REQUEST };
if (require.main === module) {
  let output, inputFile;
  try {
    const args = process.argv.slice(2); need(args.length === 4, "USAGE: --input request.json --output result.json");
    const flags = new Map();
    for (let i = 0; i < args.length; i += 2) {
      need(["--input", "--output"].includes(args[i]) && !flags.has(args[i]), "CLI_FLAGS_INVALID"); flags.set(args[i], args[i + 1]);
    }
    need(flags.has("--input") && flags.has("--output"), "CLI_FILES_REQUIRED");
    inputFile = path.resolve(flags.get("--input")); output = path.resolve(flags.get("--output"));
    need(inputFile !== output, "CLI_OUTPUT_OVERWRITES_INPUT");
    need(!fs.existsSync(output), "CLI_OUTPUT_ALREADY_EXISTS");
    need(fs.statSync(inputFile).size <= 1024 * 1024, "CLI_REQUEST_SIZE_BOUND");
    const result = verifyForwardAttribution(parseStrictJSON(fs.readFileSync(inputFile, "utf8")), path.dirname(inputFile));
    fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n", { flag: "wx" });
    process.stdout.write(JSON.stringify({ verified: result.verified, blockers: result.blockers, output }) + "\n");
    process.exitCode = result.verified ? 0 : 2;
  } catch (err) {
    const result = { schema: "HARPOON_FORWARD_ATTRIBUTION_REPORT_1", verified: false, blockers: [String(err.message || err)],
      ledger: null, risk: { maximum_observed_holding_hours: null }, ...authority };
    if (output && output !== inputFile && !fs.existsSync(output)) {
      try { fs.writeFileSync(output, JSON.stringify(result, null, 2) + "\n", { flag: "wx" }); } catch { /* Preserve any concurrently created file. */ }
    }
    process.stderr.write(JSON.stringify(result) + "\n"); process.exitCode = 2;
  }
}
