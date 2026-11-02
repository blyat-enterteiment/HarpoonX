import fs from "node:fs";
import path from "node:path";
import { randomUUID } from "node:crypto";
import { Worker } from "node:worker_threads";
import type { Json, Store } from "./types";
import { Validators } from "./validators";
import { PriorityMutex } from "./scheduler";
import {
  assertDataset,
  assertProtocol,
  defaultProtocol,
  digest,
  need,
} from "./ultimate_contracts";
import type { ResearchDataset, ResearchProtocol } from "./ultimate_contracts";
import type { ReplayLimits } from "./ultimate_replay";

export interface LabTrial {
  id: string;
  registeredAt: number;
  protocol: ResearchProtocol;
  protocolHash: string;
  codeHash: string;
  datasetHash: string | null;
  status:
    | "REGISTERED"
    | "READY"
    | "QUEUED"
    | "RUNNING"
    | "COMPLETE"
    | "FAILED"
    | "INTERRUPTED";
  attempts: number;
  slots: number;
  result?: Json;
  error?: string;
  startedAt?: number;
  completedAt?: number;
}
export interface LabState {
  schema: "HARPOON-ULTIMATE-LEDGER-1";
  trials: LabTrial[];
  budget: number;
  spent: number;
  chain: {
    at: number;
    action: string;
    trialId: string;
    valueHash: string;
    previous: string;
    hash: string;
  }[];
}
export class ResearchLab {
  state: LabState = {
    schema: "HARPOON-ULTIMATE-LEDGER-1",
    trials: [],
    budget: 72,
    spent: 0,
    chain: [],
  };
  lastSuccess = 0;
  lastError = "";
  private committed?: LabState;
  private mutex = new PriorityMutex();
  private worker?: Worker;
  private job?: Promise<void>;
  private stopped = false;
  private codeHash = digest(
    [
      "ultimate_contracts.js",
      "ultimate_replay.js",
      "ultimate_stats.js",
      "ultimate_frequency.js",
      "policy.js", // Calendar-aware holding deadlines are a replay dependency.
    ].map((f) => fs.readFileSync(path.join(__dirname, f), "utf8")),
  );
  private key: string;
  constructor(
    private store: Store,
    account: string,
    private validators: Validators,
    private limits: ReplayLimits,
  ) {
    this.key = "ultimate-lab-" + account;
  }
  private audit(action: string, trialId: string, value: unknown) {
    const entry = {
      at: Date.now(),
      action,
      trialId,
      valueHash: digest(value),
      previous: this.state.chain.at(-1)?.hash || "GENESIS",
    };
    this.state.chain.push({ ...entry, hash: digest(entry) });
  }
  private async save() {
    const snapshot = structuredClone(this.state);
    try {
      await this.validators.check("ultimate-journal", () =>
        this.store.put(this.key, snapshot),
      );
      this.committed = snapshot;
    } catch (e) {
      if (this.committed) this.state = structuredClone(this.committed);
      this.lastError = e instanceof Error ? e.message : String(e);
      throw e;
    }
  }
  async load() {
    const old = (await this.store.get(this.key)) as LabState | null;
    if (old) {
      this.validators.run("ultimate-ledger", () => {
        need(
          old.schema === "HARPOON-ULTIMATE-LEDGER-1" &&
            Array.isArray(old.trials) &&
            old.trials.length <= 32 &&
            Array.isArray(old.chain) &&
            old.chain.length <= 1000,
          "ledger schema",
        );
        need(
          old.budget === 72 &&
            Number.isInteger(old.spent) &&
            old.spent >= 0 &&
            old.spent <= old.budget,
          "ledger budget",
        );
        need(
          new Set(old.trials.map((t) => t.id)).size === old.trials.length &&
            old.trials.reduce((n, t) => n + t.slots, 0) === old.spent,
          "trial IDs or slot accounting",
        );
        let previous = "GENESIS";
        for (const { hash, ...entry } of old.chain) {
          need(
            entry.previous === previous && hash === digest(entry),
            "ledger chain integrity",
          );
          previous = hash;
        }
        for (const trial of old.trials) {
          assertProtocol(trial.protocol);
          need(
            trial.protocolHash === digest(trial.protocol) &&
              trial.slots === 9 * trial.protocol.universe.length,
            "protocol seal/budget",
          );
          need(
            old.chain.some(
              (e) =>
                e.action === "REGISTER" &&
                e.trialId === trial.id &&
                e.valueHash ===
                  digest({
                    protocolHash: trial.protocolHash,
                    codeHash: trial.codeHash,
                    registeredAt: trial.registeredAt,
                  }),
            ),
            "missing registration seal",
          );
          if (trial.result)
            need(
              old.chain.some(
                (e) =>
                  e.action === "COMPLETE" &&
                  e.trialId === trial.id &&
                  e.valueHash === digest(trial.result),
              ),
              "report seal",
            );
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
  async register(raw: unknown) {
    return this.mutex.run(1, async () => {
      const protocol = this.validators.run("ultimate-protocol", () =>
        assertProtocol(raw),
      );
      const slots = 9 * protocol.universe.length;
      need(
        protocol.familyTrials >= this.state.budget,
        "multiplicity must cover the full cumulative search budget",
      );
      need(
        this.state.trials.length < 32 &&
          this.state.spent + slots <= this.state.budget,
        "cumulative experiment budget exhausted",
      );
      const trial: LabTrial = {
        id: randomUUID(),
        registeredAt: Date.now(),
        protocol,
        protocolHash: digest(protocol),
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
      } catch (e) {
        this.state = prior;
        throw e;
      }
      this.lastSuccess = Date.now();
      return structuredClone(trial);
    });
  }
  private trial(id: string) {
    const t = this.state.trials.find((t) => t.id === id);
    need(t, "unknown ultimate trial");
    need(
      t.protocolHash === digest(t.protocol) && t.codeHash === this.codeHash,
      "protocol/code binding changed; register a new experiment",
    );
    return t;
  }
  async importData(id: string, raw: unknown) {
    return this.mutex.run(1, async () => {
      const t = this.trial(id);
      need(
        t.status === "REGISTERED" && !t.datasetHash,
        "dataset is already locked",
      );
      const data = this.validators.run("ultimate-dataset", () =>
          assertDataset(raw, t.protocol),
        ),
        hash = digest(data);
      await this.validators.check("ultimate-dataset-write", () =>
        this.store.put(this.key + ":dataset:" + id, data),
      );
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
  async queue(id: string) {
    return this.mutex.run(1, async () => {
      const t = this.trial(id);
      need(
        t.status === "READY" && t.attempts === 0,
        "one frozen attempt per experiment",
      );
      need(
        !this.state.trials.some((x) =>
          ["QUEUED", "RUNNING"].includes(x.status),
        ),
        "worker already queued/running",
      );
      t.status = "QUEUED";
      this.audit("QUEUED", id, t.datasetHash);
      await this.save();
      return { id, status: t.status };
    });
  }
  async tick() {
    if (this.stopped || this.worker) return;
    const trial = this.state.trials.find((t) => t.status === "QUEUED");
    if (!trial) return;
    this.job = this.execute(trial);
    await this.job;
  }
  private async execute(trial: LabTrial) {
    try {
      const t = this.trial(trial.id),
        data = (await this.store.get(
          this.key + ":dataset:" + t.id,
        )) as ResearchDataset;
      this.validators.run("ultimate-dataset", () => {
        assertDataset(data, t.protocol);
        need(digest(data) === t.datasetHash, "stored dataset hash mismatch");
      });
      t.status = "RUNNING";
      t.attempts++;
      t.startedAt = Date.now();
      this.audit("START", t.id, t.attempts);
      await this.save();
      const result = await new Promise<Json>((resolve, reject) => {
        const worker = new Worker(path.join(__dirname, "ultimate_worker.js"), {
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
        need(
          result.schema === "HARPOON-ULTIMATE-REPORT-1" &&
            result.protocolHash === t.protocolHash &&
            result.datasetHash === t.datasetHash &&
            result.promotion === "NONE" &&
            Array.isArray(result.rows) &&
            result.rows.length === 9,
          "report binding",
        );
      });
      t.result = result;
      t.status = "COMPLETE";
      t.completedAt = Date.now();
      this.audit("COMPLETE", t.id, result);
      await this.save();
      this.lastSuccess = Date.now();
      this.lastError = "";
    } catch (e) {
      trial.status = "FAILED";
      trial.error = e instanceof Error ? e.message : String(e);
      this.lastError = trial.error;
      this.audit("FAILED", trial.id, trial.error);
      await this.save();
    } finally {
      this.worker = undefined;
    }
  }
  async stop() {
    this.stopped = true;
    if (this.worker) await this.worker.terminate();
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
        FUTURES: defaultProtocol(),
        ALPACA_PROXY: defaultProtocol("ALPACA_PROXY"),
      },
      trials: this.state.trials.map((t) => ({
        ...t,
        result: t.result
          ? { ...t.result, dailyUnitReturns: undefined }
          : undefined,
      })),
    };
  }
  export(id: string) {
    const t = this.state.trials.find((t) => t.id === id);
    need(t, "unknown trial");
    return {
      trial: structuredClone(t),
      chain: structuredClone(this.state.chain),
      limitations:
        "Hashes identify bytes; they do not attest market data authenticity.",
    };
  }
  verifyBundled(report: Json, registration: Json) {
    const t = registration.trial;
    need(
      t &&
        t.codeHash === this.codeHash &&
        t.protocolHash === digest(t.protocol) &&
        t.protocolHash === report.protocolHash &&
        t.datasetHash === report.datasetHash &&
        digest(t.result) === digest(report),
      "bundled report code/data/protocol binding",
    );
    let previous = "GENESIS";
    need(Array.isArray(registration.chain), "bundled chain");
    for (const { hash, ...entry } of registration.chain) {
      need(
        entry.previous === previous && hash === digest(entry),
        "bundled hash chain",
      );
      previous = hash;
    }
    need(
      registration.chain.some(
        (entry: Json) =>
          entry.action === "COMPLETE" &&
          entry.trialId === t.id &&
          entry.valueHash === digest(report),
      ),
      "bundled report seal",
    );
    return true;
  }
}
