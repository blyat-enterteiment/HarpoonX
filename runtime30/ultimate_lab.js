"use strict";
var __importDefault = (this && this.__importDefault) || function (mod) {
    return (mod && mod.__esModule) ? mod : { "default": mod };
};
Object.defineProperty(exports, "__esModule", { value: true });
exports.ResearchLab = void 0;
const node_fs_1 = __importDefault(require("node:fs"));
const node_path_1 = __importDefault(require("node:path"));
const node_crypto_1 = require("node:crypto");
const node_worker_threads_1 = require("node:worker_threads");
const scheduler_1 = require("./scheduler");
const ultimate_contracts_1 = require("./ultimate_contracts");
class ResearchLab {
    store;
    validators;
    limits;
    state = {
        schema: "HARPOON-ULTIMATE-LEDGER-1",
        trials: [],
        budget: 72,
        spent: 0,
        chain: [],
    };
    lastSuccess = 0;
    lastError = "";
    committed;
    mutex = new scheduler_1.PriorityMutex();
    worker;
    job;
    stopped = false;
    codeHash = (0, ultimate_contracts_1.digest)([
        "ultimate_contracts.js",
        "ultimate_replay.js",
        "ultimate_reservations.js", // Shared pending-risk/capital reservations are part of the evaluated code.
        "ultimate_stats.js",
        "ultimate_frequency.js",
        "policy.js", // Calendar-aware holding deadlines are a replay dependency.
    ].map((f) => node_fs_1.default.readFileSync(node_path_1.default.join(__dirname, f), "utf8")));
    key;
    constructor(store, account, validators, limits) {
        this.store = store;
        this.validators = validators;
        this.limits = limits;
        this.key = "ultimate-lab-" + account;
    }
    audit(action, trialId, value) {
        const entry = {
            at: Date.now(),
            action,
            trialId,
            valueHash: (0, ultimate_contracts_1.digest)(value),
            previous: this.state.chain.at(-1)?.hash || "GENESIS",
        };
        this.state.chain.push({ ...entry, hash: (0, ultimate_contracts_1.digest)(entry) });
    }
    async save() {
        const snapshot = structuredClone(this.state);
        try {
            await this.validators.check("ultimate-journal", () => this.store.put(this.key, snapshot));
            this.committed = snapshot;
        }
        catch (e) {
            if (this.committed)
                this.state = structuredClone(this.committed);
            this.lastError = e instanceof Error ? e.message : String(e);
            throw e;
        }
    }
    async load() {
        const old = (await this.store.get(this.key));
        if (old) {
            this.validators.run("ultimate-ledger", () => {
                (0, ultimate_contracts_1.need)(old.schema === "HARPOON-ULTIMATE-LEDGER-1" &&
                    Array.isArray(old.trials) &&
                    old.trials.length <= 32 &&
                    Array.isArray(old.chain) &&
                    old.chain.length <= 1000, "ledger schema");
                (0, ultimate_contracts_1.need)(old.budget === 72 &&
                    Number.isInteger(old.spent) &&
                    old.spent >= 0 &&
                    old.spent <= old.budget, "ledger budget");
                (0, ultimate_contracts_1.need)(new Set(old.trials.map((t) => t.id)).size === old.trials.length &&
                    old.trials.reduce((n, t) => n + t.slots, 0) === old.spent, "trial IDs or slot accounting");
                let previous = "GENESIS";
                for (const { hash, ...entry } of old.chain) {
                    (0, ultimate_contracts_1.need)(entry.previous === previous && hash === (0, ultimate_contracts_1.digest)(entry), "ledger chain integrity");
                    previous = hash;
                }
                for (const trial of old.trials) {
                    (0, ultimate_contracts_1.assertProtocol)(trial.protocol);
                    (0, ultimate_contracts_1.need)(trial.protocolHash === (0, ultimate_contracts_1.digest)(trial.protocol) &&
                        trial.slots === 9 * trial.protocol.universe.length, "protocol seal/budget");
                    (0, ultimate_contracts_1.need)(old.chain.some((e) => e.action === "REGISTER" &&
                        e.trialId === trial.id &&
                        e.valueHash ===
                            (0, ultimate_contracts_1.digest)({
                                protocolHash: trial.protocolHash,
                                codeHash: trial.codeHash,
                                registeredAt: trial.registeredAt,
                            })), "missing registration seal");
                    if (trial.result)
                        (0, ultimate_contracts_1.need)(old.chain.some((e) => e.action === "COMPLETE" &&
                            e.trialId === trial.id &&
                            e.valueHash === (0, ultimate_contracts_1.digest)(trial.result)), "report seal");
                }
            });
            this.state = old;
            this.committed = structuredClone(old);
            for (const trial of old.trials)
                if (["QUEUED", "RUNNING"].includes(trial.status)) {
                    trial.status = "INTERRUPTED";
                    trial.error = "Process restarted; attempt consumed";
                    this.audit("INTERRUPTED", trial.id, trial.attempts);
                }
            await this.save();
        }
        this.lastSuccess = Date.now();
        this.committed = structuredClone(this.state);
    }
    async register(raw) {
        return this.mutex.run(1, async () => {
            const protocol = this.validators.run("ultimate-protocol", () => (0, ultimate_contracts_1.assertProtocol)(raw));
            const slots = 9 * protocol.universe.length;
            (0, ultimate_contracts_1.need)(protocol.familyTrials >= this.state.budget, "multiplicity must cover the full cumulative search budget");
            (0, ultimate_contracts_1.need)(this.state.trials.length < 32 &&
                this.state.spent + slots <= this.state.budget, "cumulative experiment budget exhausted");
            const trial = {
                id: (0, node_crypto_1.randomUUID)(),
                registeredAt: Date.now(),
                protocol,
                protocolHash: (0, ultimate_contracts_1.digest)(protocol),
                codeHash: this.codeHash,
                datasetHash: null,
                status: "REGISTERED",
                attempts: 0,
                slots,
            };
            const prior = structuredClone(this.state);
            this.state.trials.push(trial);
            this.state.spent += slots;
            this.audit("REGISTER", trial.id, {
                protocolHash: trial.protocolHash,
                codeHash: trial.codeHash,
                registeredAt: trial.registeredAt,
            });
            try {
                await this.save();
            }
            catch (e) {
                this.state = prior;
                throw e;
            }
            this.lastSuccess = Date.now();
            return structuredClone(trial);
        });
    }
    trial(id) {
        const t = this.state.trials.find((t) => t.id === id);
        (0, ultimate_contracts_1.need)(t, "unknown ultimate trial");
        (0, ultimate_contracts_1.need)(t.protocolHash === (0, ultimate_contracts_1.digest)(t.protocol) && t.codeHash === this.codeHash, "protocol/code binding changed; register a new experiment");
        return t;
    }
    async importData(id, raw) {
        return this.mutex.run(1, async () => {
            const t = this.trial(id);
            (0, ultimate_contracts_1.need)(t.status === "REGISTERED" && !t.datasetHash, "dataset is already locked");
            const data = this.validators.run("ultimate-dataset", () => (0, ultimate_contracts_1.assertDataset)(raw, t.protocol)), hash = (0, ultimate_contracts_1.digest)(data);
            await this.validators.check("ultimate-dataset-write", () => this.store.put(this.key + ":dataset:" + id, data));
            t.datasetHash = hash;
            t.status = "READY";
            this.audit("DATASET_LOCKED", id, {
                hash,
                sourceTrust: "SUPPLIED_FILE_HASHES_NOT_PROVIDER_ATTESTATION",
            });
            await this.save();
            this.lastSuccess = Date.now();
            return {
                id,
                datasetHash: hash,
                status: t.status,
                sourceTrust: "SUPPLIED_FILE_HASHES_NOT_PROVIDER_ATTESTATION",
            };
        });
    }
    async queue(id) {
        return this.mutex.run(1, async () => {
            const t = this.trial(id);
            (0, ultimate_contracts_1.need)(t.status === "READY" && t.attempts === 0, "one frozen attempt per experiment");
            (0, ultimate_contracts_1.need)(!this.state.trials.some((x) => ["QUEUED", "RUNNING"].includes(x.status)), "worker already queued/running");
            t.status = "QUEUED";
            this.audit("QUEUED", id, t.datasetHash);
            await this.save();
            return { id, status: t.status };
        });
    }
    async tick() {
        if (this.stopped || this.worker)
            return;
        const trial = this.state.trials.find((t) => t.status === "QUEUED");
        if (!trial)
            return;
        this.job = this.execute(trial);
        await this.job;
    }
    async execute(trial) {
        try {
            const t = this.trial(trial.id), data = (await this.store.get(this.key + ":dataset:" + t.id));
            this.validators.run("ultimate-dataset", () => {
                (0, ultimate_contracts_1.assertDataset)(data, t.protocol);
                (0, ultimate_contracts_1.need)((0, ultimate_contracts_1.digest)(data) === t.datasetHash, "stored dataset hash mismatch");
            });
            t.status = "RUNNING";
            t.attempts++;
            t.startedAt = Date.now();
            this.audit("START", t.id, t.attempts);
            await this.save();
            const result = await new Promise((resolve, reject) => {
                const worker = new node_worker_threads_1.Worker(node_path_1.default.join(__dirname, "ultimate_worker.js"), {
                    workerData: {
                        protocol: t.protocol,
                        data,
                        registeredAt: t.registeredAt,
                        limits: this.limits,
                    },
                    resourceLimits: { maxOldGenerationSizeMb: 768 },
                });
                this.worker = worker;
                const timeout = setTimeout(() => {
                    void worker.terminate();
                    reject(Error("Research CPU budget exceeded"));
                }, 180000);
                const finish = () => {
                    clearTimeout(timeout);
                };
                worker.once("message", (message) => {
                    finish();
                    message.error
                        ? reject(Error(message.error))
                        : resolve(message.report);
                });
                worker.once("error", (e) => {
                    finish();
                    reject(e);
                });
                worker.once("exit", (code) => {
                    finish();
                    reject(Error("Research worker exited before result, code " + code));
                });
            });
            this.validators.run("ultimate-report", () => {
                (0, ultimate_contracts_1.need)(result.schema === "HARPOON-ULTIMATE-REPORT-1" &&
                    result.protocolHash === t.protocolHash &&
                    result.datasetHash === t.datasetHash &&
                    result.promotion === "NONE" &&
                    Array.isArray(result.rows) &&
                    result.rows.length === 9, "report binding");
            });
            t.result = result;
            t.status = "COMPLETE";
            t.completedAt = Date.now();
            this.audit("COMPLETE", t.id, result);
            await this.save();
            this.lastSuccess = Date.now();
            this.lastError = "";
        }
        catch (e) {
            trial.status = "FAILED";
            trial.error = e instanceof Error ? e.message : String(e);
            this.lastError = trial.error;
            this.audit("FAILED", trial.id, trial.error);
            await this.save();
        }
        finally {
            this.worker = undefined;
        }
    }
    async stop() {
        this.stopped = true;
        if (this.worker)
            await this.worker.terminate();
        await this.job;
    }
    view() {
        return {
            schema: this.state.schema,
            budget: this.state.budget,
            spent: this.state.spent,
            sourceTrust: "FILE_IMPORTS_REQUIRE_EXTERNAL_PROVENANCE_REVIEW",
            promotion: "NONE",
            status: this.lastError
                ? "ERROR"
                : this.worker
                    ? "RUNNING"
                    : this.state.trials.some((t) => t.status === "QUEUED")
                        ? "QUEUED"
                        : this.lastSuccess
                            ? "READY"
                            : "STARTING",
            lastSuccess: this.lastSuccess,
            lastError: this.lastError,
            ledgerHead: this.state.chain.at(-1)?.hash || null,
            defaults: {
                FUTURES: (0, ultimate_contracts_1.defaultProtocol)(),
                ALPACA_PROXY: (0, ultimate_contracts_1.defaultProtocol)("ALPACA_PROXY"),
            },
            trials: this.state.trials.map((t) => ({
                ...t,
                result: t.result
                    ? { ...t.result, dailyUnitReturns: undefined }
                    : undefined,
            })),
        };
    }
    export(id) {
        const t = this.state.trials.find((t) => t.id === id);
        (0, ultimate_contracts_1.need)(t, "unknown trial");
        return {
            trial: structuredClone(t),
            chain: structuredClone(this.state.chain),
            limitations: "Hashes identify bytes; they do not attest market data authenticity.",
        };
    }
    verifyBundled(report, registration) {
        const t = registration.trial;
        (0, ultimate_contracts_1.need)(t &&
            t.codeHash === this.codeHash &&
            t.protocolHash === (0, ultimate_contracts_1.digest)(t.protocol) &&
            t.protocolHash === report.protocolHash &&
            t.datasetHash === report.datasetHash &&
            (0, ultimate_contracts_1.digest)(t.result) === (0, ultimate_contracts_1.digest)(report), "bundled report code/data/protocol binding");
        let previous = "GENESIS";
        (0, ultimate_contracts_1.need)(Array.isArray(registration.chain), "bundled chain");
        for (const { hash, ...entry } of registration.chain) {
            (0, ultimate_contracts_1.need)(entry.previous === previous && hash === (0, ultimate_contracts_1.digest)(entry), "bundled hash chain");
            previous = hash;
        }
        (0, ultimate_contracts_1.need)(registration.chain.some((entry) => entry.action === "COMPLETE" &&
            entry.trialId === t.id &&
            entry.valueHash === (0, ultimate_contracts_1.digest)(report)), "bundled report seal");
        return true;
    }
}
exports.ResearchLab = ResearchLab;
