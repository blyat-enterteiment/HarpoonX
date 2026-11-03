"use strict";
// Explicit offline research transport. This module has no broker or LLM adapter.
const path = require("node:path");
const { spawn } = require("node:child_process");
const { createHash } = require("node:crypto");
const { performance } = require("node:perf_hooks");

const ROOT = path.resolve(__dirname, "..");
const ORIGIN = "SYNTHETIC_ENGINEERING_ONLY";
const RESPONSE_SCHEMA = "HARPOON_ROADMAP_OFFLINE_RESPONSE_1";
const STORED_SCHEMA = "HARPOON_ROADMAP_OFFLINE_STORED_1";
const WORKER_TIMEOUT_MS = 8000;
const MAX_BYTES = 8 * 1024 * 1024;
const KINDS = new Set(["INIT", "MARKET", "RECONCILE", "PREDICTOR", "PLAN", "EVENT", "FEE", "REDUCE", "CONTRACT_CHANGE"]);
const AUTHORITY_FIELDS = new Set(["execution_allowed", "orders_allowed", "liveApproved", "financial_acceptance_allowed"]);

function fault(code, status = 503) {
  return Object.assign(new Error(code), { status, code });
}
function plain(value) {
  return value !== null && typeof value === "object" && !Array.isArray(value);
}
function canonical(value, depth = 0) {
  if (depth > 64) throw fault("ROADMAP9_JSON_DEPTH", 422);
  if (value === null || typeof value === "boolean" || typeof value === "string") return value;
  if (typeof value === "number" && Number.isFinite(value)) return value;
  if (Array.isArray(value)) return value.map(item => canonical(item, depth + 1));
  if (!plain(value)) throw fault("ROADMAP9_JSON_VALUE", 422);
  return Object.fromEntries(Object.keys(value).sort().map(key => [key, canonical(value[key], depth + 1)]));
}
const digest = value => createHash("sha256").update(JSON.stringify(canonical(value))).digest("hex");
const rawDigest = value => createHash("sha256").update(value).digest("hex");
function noAuthority(value, depth = 0) {
  if (depth > 64) throw fault("ROADMAP9_JSON_DEPTH", 422);
  if (Array.isArray(value)) return value.forEach(item => noAuthority(item, depth + 1));
  if (!plain(value)) return;
  for (const [key, item] of Object.entries(value)) {
    if (AUTHORITY_FIELDS.has(key) && item !== false) throw fault("ROADMAP9_AUTHORITY_FORBIDDEN", 422);
    noAuthority(item, depth + 1);
  }
}
function storedRecord(value) {
  if (value === null || value === undefined) return null;
  if (!plain(value) || value.schema !== STORED_SCHEMA || !Number.isSafeInteger(value.revision) || value.revision < 1 ||
      !plain(value.session) || typeof value.sha256 !== "string" ||
      Object.keys(value).sort().join(",") !== "revision,schema,session,sha256") {
    throw fault("ROADMAP9_STORED_CONTRACT");
  }
  const { sha256, ...body } = value;
  if (digest(body) !== sha256) throw fault("ROADMAP9_STORED_INTEGRITY");
  return value;
}
function sealRecord(revision, session) {
  const body = { schema: STORED_SCHEMA, revision, session };
  return { ...body, sha256: digest(body) };
}
function commandFrom(body) {
  if (!plain(body) || Object.keys(body).sort().join(",") !== "command,origin" || body.origin !== ORIGIN ||
      !plain(body.command) || !KINDS.has(body.command.kind) ||
      typeof body.command.command_id !== "string" || !/^[A-Za-z0-9:_-]{1,128}$/.test(body.command.command_id) ||
      Object.hasOwn(body.command, "received_at_ms")) throw fault("ROADMAP9_REQUEST_CONTRACT", 422);
  noAuthority(body);
  return canonical(body.command);
}

class OfflineRoadmap {
  constructor(store, key, options = {}) {
    if (!store || typeof store.get !== "function" || typeof store.rpc !== "function") {
      throw fault("ROADMAP9_COMPARE_AND_SWAP_STORE_REQUIRED");
    }
    if (typeof key !== "string" || !key || key.length > 256) throw fault("ROADMAP9_STORE_KEY");
    this.store = store;
    this.key = "ROADMAP9_OFFLINE:" + key;
    this.python = options.python || process.env.HARPOON_QUANT_PYTHON || "python3";
    if (typeof this.python !== "string" || !this.python || this.python.includes("\0")) throw fault("ROADMAP9_PYTHON_CONFIG");
    this.busy = false;
    this.closed = false;
    this.child = null;
    this.lastRevision = null;
    this.recoveryRequired = false;
    this.lastFailure = null;
  }

  hold(code) {
    this.recoveryRequired = true;
    this.lastFailure = { code, observed_at_ms: Date.now() };
  }

  async runWorker(packet) {
    const raw = JSON.stringify(canonical(packet));
    if (Buffer.byteLength(raw) > MAX_BYTES) throw fault("ROADMAP9_JOURNAL_CAPACITY", 422);
    const binding = rawDigest(raw);
    return new Promise((resolve, reject) => {
      let output = "", errorBytes = 0, settled = false, terminalError = null;
      const deadline = performance.now() + WORKER_TIMEOUT_MS;
      const child = spawn(this.python, ["-B", "-m", "harpoon_quant.roadmap9.integration"], {
        cwd: ROOT, shell: false, stdio: ["pipe", "pipe", "pipe"],
        env: {
          PATH: process.env.PATH || "/usr/local/bin:/usr/bin:/bin",
          PYTHONPATH: path.join(ROOT, "quant"), PYTHONNOUSERSITE: "1",
          PYTHONDONTWRITEBYTECODE: "1", OPENBLAS_NUM_THREADS: "1", OMP_NUM_THREADS: "1",
          LC_ALL: "C.UTF-8",
        },
      });
      this.child = child;
      const finish = (error, value) => {
        if (settled) return;
        settled = true;
        clearTimeout(timer);
        if (this.child === child) this.child = null;
        if (error) reject(error); else resolve(value);
      };
      const terminate = code => {
        if (!terminalError) terminalError = fault(code);
        child.kill("SIGKILL");
      };
      const timer = setTimeout(() => terminate("ROADMAP9_WORKER_TIMEOUT"), WORKER_TIMEOUT_MS);
      child.on("error", () => finish(fault("ROADMAP9_WORKER_SPAWN")));
      child.stdin.on("error", () => terminate("ROADMAP9_WORKER_INPUT"));
      child.stdout.setEncoding("utf8");
      child.stdout.on("data", chunk => {
        output += chunk;
        if (Buffer.byteLength(output) > MAX_BYTES) terminate("ROADMAP9_WORKER_OUTPUT_BOUND");
      });
      child.stderr.on("data", chunk => {
        errorBytes += chunk.length;
        if (errorBytes > 65536) terminate("ROADMAP9_WORKER_STDERR_BOUND");
      });
      child.on("close", code => {
        if (terminalError) return finish(terminalError);
        if (this.closed) return finish(fault("ROADMAP9_CONTROLLER_CLOSED"));
        if (performance.now() >= deadline) return finish(fault("ROADMAP9_WORKER_TIMEOUT"));
        if (code !== 0) return finish(fault("ROADMAP9_WORKER_EXIT"));
        try {
          const result = JSON.parse(output);
          if (!plain(result) || result.schema !== RESPONSE_SCHEMA || result.request_sha256 !== binding || result.execution_allowed !== false) {
            throw fault("ROADMAP9_WORKER_BINDING");
          }
          noAuthority(result);
          if (result.error !== undefined) {
            if (!plain(result.error) || typeof result.error.code !== "string" || result.error.code.length > 512 ||
                Object.keys(result).sort().join(",") !== "error,execution_allowed,request_sha256,schema") {
              throw fault("ROADMAP9_WORKER_ERROR_CONTRACT");
            }
            return finish(fault(result.error.code, 422));
          }
          if (Object.keys(result).sort().join(",") !== "execution_allowed,request_sha256,schema,session,view" ||
              (result.session !== null && !plain(result.session)) || !plain(result.view) || result.view.origin !== ORIGIN ||
              !Number.isSafeInteger(result.view.evaluated_at_ms) || result.view.evaluated_at_ms !== packet.now_ms ||
              typeof result.view.alive !== "boolean" || typeof result.view.simulated_entries_ready !== "boolean" ||
              !Array.isArray(result.view.simulation_blockers) || !plain(result.view.health) ||
              typeof result.view.health.alive !== "boolean" || typeof result.view.health.entries_ready !== "boolean" ||
              !Array.isArray(result.view.health.blocking_reasons) ||
              !(result.view.valid_until_ms === null || Number.isSafeInteger(result.view.valid_until_ms)) ||
              !(result.view.entry_valid_until_ms === null || Number.isSafeInteger(result.view.entry_valid_until_ms)) ||
              !Array.isArray(result.view.campaign_exposures) || !result.view.campaign_exposures.every(row =>
                plain(row) && typeof row.symbol === "string" && typeof row.campaign_id === "string" &&
                Number.isSafeInteger(row.original_deadline) && typeof row.net_inventory === "string" &&
                Array.isArray(row.pending_order_ids) && row.pending_order_ids.every(id => typeof id === "string")) ||
              !Array.isArray(result.view.expired_campaigns)) {
            throw fault("ROADMAP9_WORKER_RESULT_CONTRACT");
          }
          return finish(null, result);
        } catch (error) { return finish(error.status ? error : fault("ROADMAP9_WORKER_JSON")); }
      });
      child.stdin.end(raw);
    });
  }

  publicView(view, revision, confirmed) {
    const result = structuredClone(view);
    const completed = Date.now();
    const expired = result.valid_until_ms === null || completed > result.valid_until_ms;
    const entryExpired = result.entry_valid_until_ms === null || completed > result.entry_valid_until_ms;
    result.expired_campaigns = result.campaign_exposures.filter(row => completed >= row.original_deadline);
    const deadlineExpired = result.expired_campaigns.length > 0;
    if (this.recoveryRequired || expired || deadlineExpired) {
      result.alive = false;
      result.simulated_entries_ready = false;
      const transportBlockers = [
        ...(this.recoveryRequired ? ["TRANSPORT_RECONCILIATION_REQUIRED"] : []),
        ...(expired ? ["INPUT_EXPIRED_BEFORE_RESPONSE"] : []),
        ...(deadlineExpired ? ["CAMPAIGN_DEADLINE_EXPIRED_WITH_EXPOSURE"] : []),
      ];
      result.simulation_blockers = [...new Set([...result.simulation_blockers, ...transportBlockers])];
      if (plain(result.health)) {
        result.health.alive = false;
        result.health.entries_ready = false;
        result.health.owned_inventory_management = "RECONCILE_ONLY";
        result.health.blocking_reasons = [...new Set([...result.health.blocking_reasons, ...transportBlockers])];
      }
    }
    if (entryExpired) {
      result.simulated_entries_ready = false;
      result.simulation_blockers = [...new Set([...result.simulation_blockers, "ENTRY_INPUT_EXPIRED_BEFORE_RESPONSE"])];
      result.health.entries_ready = false;
      result.health.blocking_reasons = [...new Set([...result.health.blocking_reasons, "ENTRY_INPUT_EXPIRED_BEFORE_RESPONSE"])];
    }
    result.execution_allowed = false;
    result.orders_allowed = false;
    result.financial_acceptance_allowed = false;
    result.completed_at_ms = completed;
    result.storage = { revision, confirmed, persisted: revision > 0, recovery_required: this.recoveryRequired,
      last_failure: this.lastFailure, namespace: "ISOLATED_SYNTHETIC_SESSION" };
    result.transport = { origin: ORIGIN, broker_transport_present: false, llm_transport_present: false,
      worker_timeout_ms: WORKER_TIMEOUT_MS, credentials_forwarded: false };
    return result;
  }

  async request(body = null) {
    if (this.closed) throw fault("ROADMAP9_CONTROLLER_CLOSED");
    if (this.busy) throw fault("ROADMAP9_REQUEST_IN_PROGRESS", 429);
    const command = body === null ? null : commandFrom(body);
    this.busy = true;
    try {
      let current;
      try { current = storedRecord(await this.store.get(this.key)); }
      catch (error) { this.hold(error.code || "ROADMAP9_STORAGE_READ"); throw fault(error.code || "ROADMAP9_STORAGE_READ"); }
      const revision = current?.revision || 0;
      if ((this.lastRevision === null && current !== null) || (this.lastRevision !== null && revision !== this.lastRevision)) {
        this.hold("ROADMAP9_RESTART_OR_EXTERNAL_COMMIT");
      }
      this.lastRevision = revision;
      if (command?.kind === "INIT" && current !== null) throw fault("ROADMAP9_SESSION_ALREADY_INITIALIZED", 409);
      if (this.recoveryRequired && ["PLAN", "REDUCE"].includes(command?.kind)) {
        throw fault("ROADMAP9_RECONCILIATION_REQUIRED", 409);
      }
      const now = Date.now();
      const packet = { session: current?.session || null,
        command: command === null ? null : { ...command, received_at_ms: now },
        now_ms: now, recovery_required: this.recoveryRequired };
      let result;
      try { result = await this.runWorker(packet); }
      catch (error) {
        if (error.status !== 422) this.hold(error.code || "ROADMAP9_WORKER_FAILURE");
        throw error;
      }
      if (command === null) return this.publicView(result.view, revision, true);
      if (!plain(result.session)) { this.hold("ROADMAP9_SESSION_RESULT_MISSING"); throw fault("ROADMAP9_SESSION_RESULT_MISSING"); }
      // Replayed command receipts never acquire a fresh reconciliation clock.
      // An exact retry does not create another journal revision or clear a hold.
      if (current !== null && digest(result.session) === digest(current.session)) {
        return this.publicView(result.view, revision, true);
      }
      if (["PLAN", "REDUCE"].includes(command.kind) &&
          (result.view.valid_until_ms === null || Date.now() > result.view.valid_until_ms)) {
        this.hold("ROADMAP9_INPUT_EXPIRED_BEFORE_COMMIT");
        throw fault("ROADMAP9_INPUT_EXPIRED_BEFORE_COMMIT");
      }
      if (command.kind === "PLAN" &&
          (result.view.entry_valid_until_ms === null || Date.now() > result.view.entry_valid_until_ms)) {
        // Predictor freshness blocks new risk without disabling deterministic
        // reductions supported by current market and reconciliation receipts.
        throw fault("ROADMAP9_ENTRY_INPUT_EXPIRED_BEFORE_COMMIT");
      }
      const next = sealRecord(revision + 1, result.session);
      try {
        const won = await this.store.rpc({ op: "cas", key: this.key, expected: current, value: next });
        if (won !== true) { this.hold("ROADMAP9_COMPARE_AND_SWAP_CONFLICT"); throw fault("ROADMAP9_COMPARE_AND_SWAP_CONFLICT", 409); }
      } catch (error) {
        this.hold(error.code || "ROADMAP9_STORAGE_WRITE_UNCERTAIN");
        throw error.status ? error : fault("ROADMAP9_STORAGE_WRITE_UNCERTAIN");
      }
      this.lastRevision = next.revision;
      if (command.kind === "RECONCILE") {
        this.recoveryRequired = false;
        this.lastFailure = null;
      }
      return this.publicView(result.view, next.revision, true);
    } finally { this.busy = false; }
  }

  close() {
    this.closed = true;
    this.hold("ROADMAP9_CONTROLLER_CLOSED");
    if (this.child) this.child.kill("SIGKILL");
  }
}

module.exports = { OfflineRoadmap, ORIGIN, WORKER_TIMEOUT_MS, MAX_BYTES };
