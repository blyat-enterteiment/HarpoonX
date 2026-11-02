"use strict";
// One bounded collection, fixed GET routes only. No broker transport or model fitting.
const fs = require("node:fs"), path = require("node:path"), http = require("node:http"), https = require("node:https");
const crypto = require("node:crypto"), {performance} = require("node:perf_hooks");
const {TextDecoder} = require("node:util");
const MIB = 1024 * 1024, REPORT_RESERVE = MIB;
const SCHEMA = "HARPOON_RUNTIME_EVIDENCE_COLLECTION_1";
const HARD = Object.freeze({pageBytes: 32*MIB, observationBytes: 128*MIB,
  ledgerBundleBytes: 32*MIB, totalBytes: 192*MIB, pages: 512, requests: 1030,
  timeoutMs: 600000, requestTimeoutMs: 30000});
const AUTHORITY = Object.freeze({execution_allowed: false, liveApproved: false,
  financial_acceptance_allowed: false, level4_assessed: false, economic_score: null});
class CollectionError extends Error {
  /** @param {string} code */
  constructor(code) { super(code); this.name = "CollectionError"; this.code = code; }
}
/** @param {any} ok @param {string} code */
function need(ok, code) { if (!ok) throw new CollectionError(code); }
/** @param {Buffer|string} value */
function sha(value) { return crypto.createHash("sha256").update(value).digest("hex"); }
/** @param {unknown} value @param {number} fallback @param {number} lo @param {number} hi @param {string} name */
function integer(value, fallback, lo, hi, name) {
  const n = value === undefined ? fallback : value;
  need(typeof n === "number" && Number.isSafeInteger(n) && n >= lo && n <= hi, "INVALID_LIMIT_" + name);
  return /** @type {number} */ (n);
}
/** @param {unknown} value */
function endpoint(value) {
  need(typeof value === "string" && value.length <= 2048, "BASE_URL_REQUIRED");
  let url;
  try { url = new URL(/** @type {string} */ (value)); } catch { throw new CollectionError("BASE_URL_INVALID"); }
  need(!url.username && !url.password && !url.search && !url.hash && url.pathname === "/", "BASE_URL_MUST_BE_ORIGIN_WITHOUT_CREDENTIALS");
  // HTTP is permitted only for literal loopback addresses; no hostname/DNS exception.
  const loopback = /^127(?:\.\d{1,3}){3}$/.test(url.hostname) || url.hostname === "[::1]";
  need(url.protocol === "https:" || url.protocol === "http:" && loopback, "HTTPS_REQUIRED_OUTSIDE_LITERAL_LOOPBACK");
  return url;
}
function helpers() {
  // Fixed application modules. Dynamic paths prevent checkJs from rechecking generated runtime JS.
  const root = path.resolve(__dirname, "..");
  return {
    strict: require(path.join(__dirname, "level4_readiness.cjs")).parseStrictJSON,
    snapshots: require(path.join(__dirname, "export_observation_snapshot.cjs")),
    digest: require(path.join(root, "runtime30/ultimate_contracts.js")).digest,
    verifyLedger: require(path.join(root, "runtime30/net_accounting.js")).verifyNetLedgerHistoryBundle,
  };
}
/** @param {any} value */
function validateSelection(value) {
  need(value && typeof value === "object" && !Array.isArray(value), "SELECTION_OBJECT_REQUIRED");
  const allowed = ["kind", "timezone", "local_time", "max_selection_delay_ms", "label_quote_max_age_ms", "label_maturity_max_delay_ms"];
  need(Object.keys(value).every(k => allowed.includes(k)) && Object.keys(value).length === allowed.length, "SELECTION_FIELDS_INVALID");
  need(value.kind === "FIRST_CAUSAL_FRAME_AT_OR_AFTER_LOCAL_GRID" && value.timezone === "America/New_York" &&
    typeof value.local_time === "string" && /^(?:[01]\d|2[0-3]):[0-5]\d$/.test(value.local_time), "SELECTION_CONTRACT_INVALID");
  integer(value.max_selection_delay_ms, 0, 0, 90000, "SELECTION_DELAY");
  integer(value.label_quote_max_age_ms, 0, 0, 900000, "LABEL_QUOTE_AGE");
  integer(value.label_maturity_max_delay_ms, 0, 0, 300000, "LABEL_MATURITY_DELAY");
  return value;
}
/** @param {any} input @param {string[]} secrets */
function containsSecret(input, secrets) {
  if (typeof input === "string") return secrets.some(s => input.includes(s));
  if (!input || typeof input !== "object") return false;
  return Object.entries(input).some(([key, value]) => secrets.some(s => key.includes(s)) || containsSecret(value, secrets));
}
/** Inspect explicit identity claims only. A suffix and a stable health process
 * never establish account identity, atomicity or complete campaign history.
 * @param {any} body @param {string} expectedAccount @param {string} expectedVersion */
function coordinatorExportIdentity(body, expectedAccount, expectedVersion) {
  need(body && typeof body === "object" && !Array.isArray(body), "COORDINATOR_EXPORT_OBJECT_REQUIRED");
  const version = body.version ?? null;
  if (version !== null) need(typeof version === "string" && version === expectedVersion, "COORDINATOR_EXPORT_VERSION_MISMATCH");
  const claims = [
    {field: "account_id", value: body.account_id},
    {field: "accountId", value: body.accountId},
    {field: "account.id", value: body.account?.id},
    {field: "netAccountLedger.accountId", value: body.netAccountLedger?.accountId},
    {field: "prospectiveQuantObservations.account_id", value: body.prospectiveQuantObservations?.account_id},
    {field: "forward_attribution.account_id", value: body.forward_attribution?.account_id},
  ].filter(c => c.value !== undefined && c.value !== null);
  for (const claim of claims)
    need(typeof claim.value === "string" && claim.value === expectedAccount, "COORDINATOR_EXPORT_ACCOUNT_MISMATCH");
  return {observed_version: version, version_verified: version !== null,
    observed_account_id: claims.length ? claims[0].value : null, account_binding_verified: claims.length > 0,
    explicit_identity_claims: claims, account_suffix_used: false,
    forward_contract_present: body.forward_attribution?.schema === "HARPOON_FORWARD_COORDINATOR_EXPORT_1",
    history_coverage_verified: false, attribution_verification_executed: false,
    atomic_snapshot_with_other_sources: false, source_authenticity_independently_verified: false,
    scope: "EXPLICIT_IDENTITY_CLAIMS_ONLY_REQUIRES_SEPARATE_FORWARD_ATTRIBUTION_VERIFICATION"};
}
/** @param {any} options @param {Record<string,string|undefined>} [environment] */
async function collectRuntimeEvidence(options, environment = process.env) {
  const started = performance.now(), startedAt = new Date().toISOString();
  const allowed = ["baseUrl", "expectedAccount", "expectedVersion", "outputDir", "selectionFile", "timeoutMs", "requestTimeoutMs",
    "pageBytes", "observationBytes", "ledgerBundleBytes", "totalBytes", "maxPages", "maxRequests", "observationPageSize", "ledgerPageSize",
    "includeCoordinatorExport"];
  need(options && typeof options === "object" && Object.keys(options).every(k => allowed.includes(k)), "COLLECTION_OPTIONS_INVALID");
  const includeCoordinatorExport = options.includeCoordinatorExport === undefined ? false : options.includeCoordinatorExport;
  need(typeof includeCoordinatorExport === "boolean", "INCLUDE_COORDINATOR_EXPORT_BOOLEAN_REQUIRED");
  const base = endpoint(options.baseUrl);
  need(typeof options.expectedAccount === "string" && /^[A-Za-z0-9_-]{1,128}$/.test(options.expectedAccount), "EXPECTED_ACCOUNT_REQUIRED");
  need(typeof options.expectedVersion === "string" && /^\d+\.\d+\.\d+(?:[-+][A-Za-z0-9.-]+)?$/.test(options.expectedVersion) && options.expectedVersion.length <= 64, "EXPECTED_VERSION_REQUIRED");
  need(typeof options.outputDir === "string" && options.outputDir.length > 0, "NEW_OUTPUT_DIRECTORY_REQUIRED");
  const output = path.resolve(options.outputDir);
  const password = environment.HARPOON_PANEL_PASSWORD;
  need(typeof password === "string" && password.length >= 32 && password.length <= 4096 && !/[\x00-\x1f\x7f]/.test(password), "PANEL_PASSWORD_ENV_REQUIRED");
  const authorization = "Basic " + Buffer.from("trader:" + password).toString("base64");
  const secretValues = [password, authorization, authorization.slice(6)];
  const limits = {
    timeoutMs: integer(options.timeoutMs, 300000, 50, HARD.timeoutMs, "TOTAL_TIME"),
    requestTimeoutMs: integer(options.requestTimeoutMs, 10000, 20, HARD.requestTimeoutMs, "REQUEST_TIME"),
    pageBytes: integer(options.pageBytes, HARD.pageBytes, 128, HARD.pageBytes, "PAGE_BYTES"),
    observationBytes: integer(options.observationBytes, HARD.observationBytes, 128, HARD.observationBytes, "OBSERVATION_BYTES"),
    ledgerBundleBytes: integer(options.ledgerBundleBytes, HARD.ledgerBundleBytes, 128, HARD.ledgerBundleBytes, "LEDGER_BUNDLE_BYTES"),
    totalBytes: integer(options.totalBytes, HARD.totalBytes, REPORT_RESERVE + 128, HARD.totalBytes, "TOTAL_BYTES"),
    maxPages: integer(options.maxPages, HARD.pages, 1, HARD.pages, "PAGES"),
    maxRequests: integer(options.maxRequests, HARD.requests, 1, HARD.requests, "REQUESTS"),
    observationPageSize: integer(options.observationPageSize, 100, 1, 100, "OBSERVATION_PAGE_SIZE"),
    ledgerPageSize: integer(options.ledgerPageSize, 1000, 1, 5000, "LEDGER_PAGE_SIZE"),
  };
  const api = helpers();
  /** @type {any|null} */ let selection = null;
  /** @type {Buffer|null} */ let selectionBytes = null;
  if (options.selectionFile !== undefined) {
    need(typeof options.selectionFile === "string", "SELECTION_FILE_INVALID");
    let handle;
    try {
      handle = fs.openSync(options.selectionFile, fs.constants.O_RDONLY | fs.constants.O_NOFOLLOW);
      const stat = fs.fstatSync(handle); need(stat.isFile() && stat.size <= 16384, "SELECTION_FILE_BOUND");
      const bounded = Buffer.alloc(stat.size + 1), length = fs.readSync(handle, bounded, 0, bounded.length, 0);
      need(length === stat.size, "SELECTION_FILE_CHANGED_DURING_READ");
      selectionBytes = bounded.subarray(0, length);
      selection = validateSelection(api.strict(new TextDecoder("utf-8", {fatal: true}).decode(selectionBytes)));
      need(!containsSecret(selection, secretValues), "CREDENTIAL_ECHO_REJECTED");
    } catch (error) { if (error instanceof CollectionError) throw error; throw new CollectionError("SELECTION_FILE_UNREADABLE_OR_INVALID"); }
    finally { if (handle !== undefined) fs.closeSync(handle); }
  }
  // Exclusive directory acquisition precedes every HTTP request. Existing outputs are never modified.
  try { fs.mkdirSync(output, {mode: 0o700}); }
  catch (error) { throw new CollectionError(/** @type {NodeJS.ErrnoException} */ (error).code === "EEXIST" ? "OUTPUT_ALREADY_EXISTS" : "OUTPUT_DIRECTORY_UNAVAILABLE"); }
  /** @type {any[]} */ const artifacts = [];
  /** @type {any[]} */ const requests = [];
  let artifactBytes = 0, networkBytes = 0, observationBytes = 0, stage = "START";
  /** @type {any|null} */ let observationVerification = null, ledgerVerification = null;
  /** @type {any|null} */ let coordinatorExportRef = null, coordinatorExportVerification = null;
  const remaining = () => limits.timeoutMs - (performance.now() - started);
  const deadline = () => need(remaining() > 0, "COLLECTION_DEADLINE_EXCEEDED");
  /** @param {string} name @param {Buffer} bytes @param {string} kind */
  const write = (name, bytes, kind) => {
    need(artifactBytes + bytes.length <= limits.totalBytes - REPORT_RESERVE, "COLLECTION_OUTPUT_BYTES_BOUND");
    const filename = path.join(output, name), handle = fs.openSync(filename, "wx", 0o600);
    try { fs.writeFileSync(handle, bytes); fs.fsyncSync(handle); } finally { fs.closeSync(handle); }
    const ref = {path: name, sha256: sha(bytes), bytes: bytes.length, kind};
    artifactBytes += bytes.length; artifacts.push(ref); return ref;
  };
  /** @param {string} name @param {any} value @param {string} kind */
  const writeJSON = (name, value, kind) => write(name, Buffer.from(JSON.stringify(value, null, 2) + "\n"), kind);
  /** @param {any} receipt @param {boolean} complete */
  const writeReceipt = (receipt, complete) => {
    const bytes = Buffer.from(JSON.stringify(receipt, null, 2) + "\n");
    need(bytes.length <= REPORT_RESERVE && artifactBytes + bytes.length <= limits.totalBytes, "COLLECTION_RECEIPT_BYTES_BOUND");
    const name = complete ? "collection_receipt.json" : "collection_failed.json", temporary = path.join(output, name + ".partial");
    const handle = fs.openSync(temporary, "wx", 0o600);
    try { fs.writeFileSync(handle, bytes); fs.fsyncSync(handle); } finally { fs.closeSync(handle); }
    fs.renameSync(temporary, path.join(output, name));
  };
  /** @param {string} route @param {boolean} authenticated @param {number} maxSourceBytes @returns {Promise<Buffer>} */
  const requestBytes = (route, authenticated, maxSourceBytes) => new Promise((resolve, reject) => {
    try { deadline(); need(requests.length < limits.maxRequests, "COLLECTION_REQUEST_COUNT_BOUND"); }
    catch (error) { reject(error); return; }
    const fixed = route === "/healthz" || route === "/v1/operational" || route === "/v1/quant/observations/snapshot" ||
      route === "/v1/export" ||
      /^\/v1\/quant\/observations\?snapshot_id=[0-9a-f]{64}&offset=\d+&limit=\d+$/.test(route) ||
      /^\/v1\/accounting\/history\?offset=\d+&limit=\d+$/.test(route);
    if (!fixed) { reject(new CollectionError("FIXED_GET_ROUTE_REQUIRED")); return; }
    const receipt = {method: "GET", route, authenticated, received_bytes: 0, status: null, completed: false};
    requests.push(receipt);
    const transport = base.protocol === "https:" ? https : http;
    const headers = {accept: "application/json", "accept-encoding": "identity", ...(authenticated ? {authorization} : {})};
    let settled = false, size = 0;
    /** @type {Buffer[]} */ const chunks = [];
    /** @type {NodeJS.Timeout|undefined} */ let timer;
    /** @param {Error|null} error @param {Buffer} [body] */
    const finish = (error, body) => {
      if (settled) return; settled = true; if (timer) clearTimeout(timer);
      error ? reject(error) : resolve(/** @type {Buffer} */ (body));
    };
    const req = transport.request(new URL(route, base), {method: "GET", headers, agent: false,
      rejectUnauthorized: true}, res => {
      receipt.status = /** @type {any} */ (res.statusCode ?? null);
      const stop = (code) => { finish(new CollectionError(code)); res.destroy(); req.destroy(); };
      if (res.statusCode >= 300 && res.statusCode < 400) { stop("REDIRECT_REJECTED"); return; }
      if (res.statusCode !== 200) { stop("HTTP_STATUS_" + String(res.statusCode ?? "UNKNOWN")); return; }
      if (!/^application\/json(?:\s*;|$)/i.test(String(res.headers["content-type"] || ""))) { stop("JSON_CONTENT_TYPE_REQUIRED"); return; }
      if (res.headers["content-encoding"] && String(res.headers["content-encoding"]).toLowerCase() !== "identity") { stop("CONTENT_ENCODING_REJECTED"); return; }
      const declared = res.headers["content-length"];
      if (declared !== undefined && (!/^\d+$/.test(String(declared)) || !Number.isSafeInteger(Number(declared)) || Number(declared) > Math.min(limits.pageBytes, maxSourceBytes))) { stop("RESPONSE_BYTES_BOUND"); return; }
      res.on("data", (chunk) => {
        if (settled) return;
        size += chunk.length; networkBytes += chunk.length; receipt.received_bytes = size;
        if (size > Math.min(limits.pageBytes, maxSourceBytes) || networkBytes > limits.totalBytes - REPORT_RESERVE) { stop("RESPONSE_BYTES_BOUND"); return; }
        chunks.push(chunk);
      });
      res.on("error", () => stop("RESPONSE_INCOMPLETE"));
      res.on("end", () => {
        if (settled) return;
        if (!res.complete) { stop("RESPONSE_INCOMPLETE"); return; }
        if (remaining() <= 0) { stop("COLLECTION_DEADLINE_EXCEEDED"); return; }
        receipt.completed = true; finish(null, Buffer.concat(chunks, size));
      });
    });
    req.on("error", () => finish(new CollectionError("NETWORK_REQUEST_FAILED")));
    const globalBudget = remaining(), collectionLimited = globalBudget <= limits.requestTimeoutMs;
    timer = setTimeout(() => { finish(new CollectionError(collectionLimited ? "COLLECTION_DEADLINE_EXCEEDED" : "REQUEST_TIMEOUT")); req.destroy(); },
      Math.max(1, Math.ceil(Math.min(limits.requestTimeoutMs, globalBudget))));
    req.end();
  });
  /** @param {string} route @param {string} filename @param {boolean} [authenticated] @param {number} [maxSourceBytes] */
  const fetchSource = async (route, filename, authenticated = true, maxSourceBytes = limits.pageBytes) => {
    need(maxSourceBytes > 0, "SOURCE_CATEGORY_BYTES_EXHAUSTED");
    const bytes = await requestBytes(route, authenticated, maxSourceBytes);
    need(!secretValues.some(value => bytes.includes(Buffer.from(value))), "CREDENTIAL_ECHO_REJECTED");
    let body;
    try { body = api.strict(new TextDecoder("utf-8", {fatal: true}).decode(bytes)); } catch { throw new CollectionError("SOURCE_JSON_INVALID"); }
    need(!containsSecret(body, secretValues), "CREDENTIAL_ECHO_REJECTED");
    const ref = write(filename, bytes, "ORIGINAL_HTTP_RESPONSE_BODY");
    return {body, ref};
  };
  const baseReceipt = () => ({schema: SCHEMA, started_at: startedAt, completed_at: new Date().toISOString(),
    duration_ms: performance.now() - started, source_origin: base.origin,
    expected_account_id: options.expectedAccount, expected_version: options.expectedVersion,
    include_coordinator_export: includeCoordinatorExport,
    limits, requests, artifacts, persisted_artifact_bytes: artifactBytes, network_bytes_seen: networkBytes,
    source_authenticity_independently_verified: false, ...AUTHORITY});
  try {
    if (selectionBytes) write("selection.json", selectionBytes, "USER_SUPPLIED_SELECTION_UNMODIFIED");
    stage = "HEALTH_VERSION";
    const firstHealth = await fetchSource("/healthz", "health_initial.json", false);
    need(firstHealth.body.version === options.expectedVersion, "EXPECTED_VERSION_MISMATCH");
    need(firstHealth.body.status === "HTTP_ALIVE" && Number.isSafeInteger(firstHealth.body.startedAt), "HEALTH_IDENTITY_INVALID");
    stage = "OPERATIONAL_STATUS";
    const operational = await fetchSource("/v1/operational", "operational.json");
    need(operational.body.schema === "HARPOON_OPERATIONAL_CAPABILITIES_1", "OPERATIONAL_SCHEMA_INVALID");
    stage = "OBSERVATION_SNAPSHOT";
    const snapshot = await fetchSource("/v1/quant/observations/snapshot", "observation_snapshot.json", true, limits.observationBytes);
    observationBytes = snapshot.ref.bytes;
    need(snapshot.body.account_id === options.expectedAccount, "EXPECTED_ACCOUNT_MISMATCH");
    const {snapshot_id: snapshotId, ...descriptor} = snapshot.body;
    need(descriptor.schema === "HARPOON_OBSERVATION_SNAPSHOT_1" && /^[a-f0-9]{64}$/.test(snapshotId || "") &&
      api.digest(descriptor) === snapshotId && descriptor.execution_allowed === false && descriptor.liveApproved === false &&
      Number.isSafeInteger(descriptor.total_frames) && descriptor.total_frames >= 0, "OBSERVATION_SNAPSHOT_INVALID");
    need(descriptor.total_frames <= limits.maxPages * limits.observationPageSize, "OBSERVATION_PAGE_COUNT_BOUND");
    /** @type {any[]} */ const observationRefs = [];
    let offset = 0;
    while (offset < descriptor.total_frames) {
      deadline(); stage = "OBSERVATION_PAGE"; need(observationRefs.length < limits.maxPages, "OBSERVATION_PAGE_COUNT_BOUND");
      const route = "/v1/quant/observations?snapshot_id=" + snapshotId + "&offset=" + offset + "&limit=" + limits.observationPageSize;
      const fetched = await fetchSource(route, "observation_page_" + String(observationRefs.length).padStart(4, "0") + ".json", true,
        limits.observationBytes - observationBytes);
      observationBytes += fetched.ref.bytes; need(observationBytes <= limits.observationBytes, "OBSERVATION_BYTES_BOUND");
      const page = fetched.body;
      need(page.account_id === options.expectedAccount && page.snapshot_id === snapshotId && page.head === descriptor.head &&
        page.total_frames === descriptor.total_frames && page.offset === offset && Array.isArray(page.frames) && page.frames.length > 0 &&
        page.frames.length <= limits.observationPageSize && page.next_offset === offset + page.frames.length && page.next_offset <= descriptor.total_frames,
        "OBSERVATION_PAGE_IDENTITY_OR_CONTINUITY");
      observationRefs.push({path: fetched.ref.path, sha256: fetched.ref.sha256}); offset = page.next_offset;
    }
    stage = "OBSERVATION_SEMANTIC_VERIFICATION"; deadline();
    // The empty context is used only in memory to call the existing integrity verifier.
    // Without a supplied causal selection, no calibration manifest/request is written.
    const verifiedManifest = api.snapshots.assemble(snapshot.body, observationRefs, selection ?? {}, output);
    observationVerification = {verified: true, frames: verifiedManifest.total_frames, snapshot_id: snapshotId,
      head: descriptor.head, account_id: descriptor.account_id, selection_provided: selection !== null,
      calibration_manifest: null, observation_nature: "RUNTIME_RECEIPTS_WITHOUT_INDEPENDENT_AUTHENTICATION"};
    if (selection !== null) {
      const ref = writeJSON("observation_manifest.json", verifiedManifest, "DERIVED_VERIFIED_SOURCE_MANIFEST");
      observationVerification.calibration_manifest = ref;
    }
    deadline(); stage = "LEDGER_PAGES";
    /** @type {any[]} */ const ledgerPages = [];
    let ledgerOffset = 0, integrity = null, totalRecords = null, ledgerRawBytes = 0;
    do {
      deadline(); need(ledgerPages.length < limits.maxPages, "LEDGER_PAGE_COUNT_BOUND");
      const route = "/v1/accounting/history?offset=" + ledgerOffset + "&limit=" + limits.ledgerPageSize;
      const fetched = await fetchSource(route, "ledger_page_" + String(ledgerPages.length).padStart(4, "0") + ".json", true,
        limits.ledgerBundleBytes - ledgerRawBytes);
      const page = fetched.body; ledgerRawBytes += fetched.ref.bytes;
      need(ledgerRawBytes <= limits.ledgerBundleBytes, "LEDGER_BUNDLE_BYTES_BOUND");
      need(page.schema === "HARPOON_NET_HISTORY_PAGE_1" && page.account_id === options.expectedAccount, "LEDGER_ACCOUNT_OR_SCHEMA_MISMATCH");
      if (integrity === null) { integrity = page.ledger_integrity; totalRecords = page.total_records; }
      need(page.ledger_integrity === integrity && page.total_records === totalRecords, "LEDGER_REVISION_CHANGED_NO_AUTOMATIC_RESTART");
      need(/^[a-f0-9]{64}$/.test(integrity || "") && Number.isSafeInteger(totalRecords) && totalRecords > 0 &&
        totalRecords <= 1000000 && page.offset === ledgerOffset && Array.isArray(page.records) && page.records.length > 0 &&
        page.records.length <= limits.ledgerPageSize, "LEDGER_PAGE_CONTINUITY");
      const next = ledgerOffset + page.records.length;
      need(next <= totalRecords && page.next_offset === (next < totalRecords ? next : null), "LEDGER_PAGE_CONTINUITY");
      ledgerPages.push(page); ledgerOffset = page.next_offset;
    } while (ledgerOffset !== null);
    stage = "LEDGER_SEMANTIC_VERIFICATION"; deadline();
    const ledgerBundle = {pages: ledgerPages, expected_integrity: integrity};
    const ledgerBytes = Buffer.from(JSON.stringify(ledgerBundle) + "\n");
    need(ledgerBytes.length <= limits.ledgerBundleBytes, "LEDGER_BUNDLE_BYTES_BOUND");
    const ledger = api.verifyLedger(ledgerPages, integrity);
    need(ledger.verified === true && ledger.accountId === options.expectedAccount, "LEDGER_VERIFICATION_FAILED");
    const ledgerRef = write("ledger_bundle.json", ledgerBytes, "DERIVED_COMPLETE_LEDGER_BUNDLE");
    ledgerVerification = {verified: true, account_id: ledger.accountId, from: ledger.from, through: ledger.through,
      observations: ledger.observations.length, expected_integrity: integrity, bundle: ledgerRef,
      execution_nature: ledger.state.evidence?.executionNature ?? null,
      economic_coverage_complete: ledger.derived?.economicCoverageComplete ?? false,
      broker_accruals_verified: ledger.brokerAccrualsVerified ?? false,
      economic_pnl_usd: ledger.derived?.economicNetPnlUsd ?? null,
      source_authenticity_independently_verified: false};
    if (includeCoordinatorExport) {
      stage = "COORDINATOR_EXPORT"; deadline();
      const exported = await fetchSource("/v1/export", "coordinator_export.json");
      coordinatorExportRef = exported.ref;
      coordinatorExportVerification = coordinatorExportIdentity(exported.body, options.expectedAccount, options.expectedVersion);
    }
    stage = "FINAL_IDENTITY"; deadline();
    const lastHealth = await fetchSource("/healthz", "health_final.json", false);
    need(lastHealth.body.version === options.expectedVersion && lastHealth.body.status === "HTTP_ALIVE" &&
      lastHealth.body.startedAt === firstHealth.body.startedAt, "RUNTIME_IDENTITY_CHANGED_DURING_COLLECTION");
    deadline(); stage = "COMPLETE";
    const receipt = {...baseReceipt(), status: "COMPLETE_SOURCE_COLLECTION", collection_complete: true,
      observation_verification: observationVerification, ledger_verification: ledgerVerification,
      coordinator_export: coordinatorExportRef, coordinator_export_verification: coordinatorExportVerification,
      selection: selection, economic_evidence_complete: false,
      missing_for_level4: [...(selection === null ? ["CAUSAL_SELECTION_NOT_PROVIDED"] : []),
        "CAUSAL_PANEL_NOT_BUILT_OR_ASSESSED", "OBSERVED_FIXED_MODELS_NOT_COLLECTED", "REGISTERED_COMPARISON_NOT_EXECUTED",
        ...(!ledgerVerification.economic_coverage_complete ? ["ACCOUNT_COST_COVERAGE_INCOMPLETE"] : []),
        ...(!ledgerVerification.broker_accruals_verified ? ["BROKER_ACCRUAL_COVERAGE_NOT_VERIFIED"] : [])],
      limitations: ["GET snapshot pins bounded metadata in the runtime; no order or configuration endpoint is called.",
        "Complete collection concerns source transport and local integrity, not profitability or level 4 approval.",
        "Model availability, training provenance, causal sample adequacy and execution assumptions require their existing validators.",
        "No operating expense, label, original receipt time, executable depth or model is inferred.",
        "Account and observation snapshots are separately fixed; equal account identity is not a claim of simultaneous sampling.",
        "Optional coordinator export is retained state, not certified complete history; stable health does not establish an atomic multi-source snapshot.",
        "Deadlines are checked on event-loop resumption; the collector is not a hard real-time scheduler."]};
    writeReceipt(receipt, true); return receipt;
  } catch (error) {
    const code = error instanceof CollectionError ? error.code : "SOURCE_VERIFIER_OR_LOCAL_IO_REJECTED";
    const receipt = {...baseReceipt(), status: "PARTIAL_COLLECTION_REJECTED", collection_complete: false,
      economic_evidence_complete: false, stage, error_code: code,
      observation_verification: observationVerification, ledger_verification: ledgerVerification,
      coordinator_export: coordinatorExportRef, coordinator_export_verification: coordinatorExportVerification,
      incomplete_response_body_persisted: false, automatic_restarts: 0};
    try { writeReceipt(receipt, false); } catch { /* A write failure cannot be turned into a completion receipt. */ }
    throw new CollectionError(code);
  }
}
const HELP = `HARPOON runtime evidence collector (fixed GET routes; no orders or model fitting)
Usage:
  node tools/collect_runtime_evidence.cjs --base-url URL --expected-account ID \\\n    --expected-version VERSION --output NEW_DIRECTORY [--selection FILE] \\\n    [--timeout-ms MS] [--request-timeout-ms MS]

HARPOON_PANEL_PASSWORD must already be supplied through the environment.
Do not put credentials in command arguments or in the URL. Username is trader.
HTTPS is required except for literal 127.0.0.0/8 or ::1 loopback addresses.
An existing output is rejected. Completed original responses remain after errors.
Without a selection file, no calibration manifest or training request is created.
Optional --include-coordinator-export true|false defaults to false. It calls
GET /v1/export only; history and cross-source atomicity remain unverified.
This command verifies transport/integrity, never financial approval or a score.
`;
/** @param {string[]} argv */
function parseArgs(argv) {
  if (argv.length === 1 && argv[0] === "--help") return null;
  const names = {"--base-url": "baseUrl", "--expected-account": "expectedAccount", "--expected-version": "expectedVersion",
    "--output": "outputDir", "--selection": "selectionFile", "--timeout-ms": "timeoutMs", "--request-timeout-ms": "requestTimeoutMs",
    "--include-coordinator-export": "includeCoordinatorExport"};
  const options = {};
  need(argv.length > 0 && argv.length % 2 === 0, "CLI_ARGUMENTS_INVALID_USE_HELP");
  for (let i = 0; i < argv.length; i += 2) {
    const name = names[argv[i]];
    need(name && !Object.hasOwn(options, name) && typeof argv[i+1] === "string" && !argv[i+1].startsWith("--"), "CLI_ARGUMENTS_INVALID_USE_HELP");
    if (name === "includeCoordinatorExport") {
      need(argv[i+1] === "true" || argv[i+1] === "false", "INCLUDE_COORDINATOR_EXPORT_BOOLEAN_REQUIRED");
      options[name] = argv[i+1] === "true";
    } else options[name] = ["timeoutMs", "requestTimeoutMs"].includes(name) ? Number(argv[i+1]) : argv[i+1];
  }
  return options;
}
async function main(argv) {
  const options = parseArgs(argv);
  if (options === null) { process.stdout.write(HELP); return; }
  const receipt = await collectRuntimeEvidence(options);
  process.stdout.write(JSON.stringify({status: receipt.status, collection_complete: true,
    receipt: path.join(path.resolve(options.outputDir), "collection_receipt.json"), ...AUTHORITY}) + "\n");
}
module.exports = {collectRuntimeEvidence, parseArgs, endpoint, validateSelection, coordinatorExportIdentity, CollectionError, SCHEMA, HARD};
if (require.main === module) main(process.argv.slice(2)).catch(error => {
  process.stderr.write(JSON.stringify({status: "COLLECTION_REJECTED",
    error_code: error instanceof CollectionError ? error.code : "COLLECTION_FAILED", ...AUTHORITY}) + "\n");
  process.exitCode = 1;
});
