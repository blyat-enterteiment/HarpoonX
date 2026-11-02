import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import type { Config, Json, Store } from "./types";
import { assertSelectorModel, ContractError, Validators } from "./validators";
import { fresh } from "./types";
const hash = (v: unknown) =>
  createHash("sha256").update(JSON.stringify(v)).digest("hex");
const need = (ok: unknown, msg: string) => {
  if (!ok) throw new ContractError("selector", msg);
};
export const SELECTOR_PIPELINE = "HARPOON-SELECTOR-30-1";
export const RIDGE_PLUGINS = {
  equity: "equity-strategy-14",
  etf: "etf-strategy-14",
} as const;
type SelectorBook = keyof typeof RIDGE_PLUGINS;
export class Selectors {
  state: Json = {
    schema: SELECTOR_PIPELINE,
    trials: [],
    models: {},
    sessions: {},
    samples: {},
    events: 0,
    lastCapture: 0,
    lastError: "",
    status: "WAIT_DATA",
  };
  private key: string;
  private codeHash = hash(
    [
      "../runtime/selector30.cjs",
      "./selectors.js",
      "./plugins.js",
      "./policy.js",
    ].map((f) => fs.readFileSync(path.join(__dirname, f), "utf8")),
  );
  constructor(
    private store: Store,
    private cfg: Config,
    private legacy: Json,
    private catalog: Json[],
    private validators = new Validators(),
  ) {
    this.key = "selector30-" + cfg.expected_account_id;
  }
  binding() {
    return hash({
      cfg: this.cfg,
      recipes: this.catalog.filter(
        (p) => p.params.selection_filter === "ridge_lcb",
      ),
      pipeline: SELECTOR_PIPELINE,
      code: this.codeHash,
    });
  }
  async load() {
    const old = await this.store.get(this.key);
    if (old) {
      need(
        old.schema === SELECTOR_PIPELINE &&
          old.accountId === this.cfg.expected_account_id,
        "journal/account mismatch",
      );
      this.state = old;
      for (const [book, m] of Object.entries(this.state.models)) {
        try {
          this.validators.run("selector-model", () =>
            assertSelectorModel((m as Json).model),
          );
          need(
            (m as Json).binding === this.binding() &&
              ["equity", "etf"].includes(book) &&
              Number.isFinite((m as Json).validUntil) &&
              (m as Json).validUntil > Date.now(),
            "stored model binding or validity mismatch",
          );
        } catch (error) {
          delete this.state.models[book];
          this.state.lastError = book + ": " + String(error);
          this.state.status = "MODEL_INVALIDATED";
          this.state.invalidations = [
            ...(this.state.invalidations || []),
            { book, at: Date.now(), reason: String(error) },
          ].slice(-20);
          await this.save();
        }
      }
    } else {
      this.state.accountId = this.cfg.expected_account_id;
      await this.save();
    }
    let recovered = false;
    for (const t of this.state.trials)
      if (t.status === "RUNNING" || t.status === "QUEUED") {
        t.status = "INTERRUPTED";
        recovered = true;
      }
    if (recovered) await this.save();
  }
  async save() {
    await this.store.put(this.key, structuredClone(this.state));
  }
  async register(book: string, costs: Json = {}) {
    need(["equity", "etf"].includes(book), "book must be equity or etf");
    need(
      this.state.trials.filter(
        (t: Json) =>
          t.book === book &&
          !["REJECTED", "INSTALLED", "RETIRED"].includes(t.status),
      ).length === 0,
      "active trial already exists",
    );
    need(this.state.trials.length < 32, "trial limit reached");
    const plugin = this.catalog.find(
      (p) => p.id === RIDGE_PLUGINS[book as SelectorBook],
    )!;
    const recipe = this.legacy.HXX.recipe(plugin.params),
      reference = {
        ...recipe,
        selection_filter: "none",
        name: "Referencia sin selector",
      };
    const c = {
      ...this.legacy.settings,
      mode: "paper",
      feed: this.cfg.stockFeed,
      starting_budget: this.cfg.capitalLimit,
      capital_limit: this.cfg.capitalLimit,
      risk_pct: this.cfg.riskFraction,
      daily_loss_pct: this.cfg.dailyLoss,
      max_drawdown_pct: this.cfg.maxDrawdown,
      open_risk_pct: this.cfg.openRiskFraction,
      gross_pct: this.cfg.totalExposure,
      symbol_pct: this.cfg.assetExposure,
      factor_pct: this.cfg.factorExposure,
      equity_book_pct: this.cfg.totalExposure,
      etf_book_pct: this.cfg.totalExposure,
      max_symbols: this.cfg.maxPositions,
      min_plan_qty: 4,
      close_minutes: 10,
      slippage_bps: this.cfg.slippageBps,
      max_spread_bps: this.cfg.maxSpreadBps,
      reserve_pct: 0,
      growth_cap: 1,
      x: { ...this.legacy.settings.x, hold_hours: recipe.hold_hours },
      replay_policy: this.legacy.HXI.POLICY,
      xii: {
        cluster_exposure_pct: this.cfg.factorExposure,
        cluster_risk_pct: this.cfg.openRiskFraction,
      },
      xi: {
        external_costs_confirmed: costs.confirmed === true,
        data_cost_total: Number(costs.dataUsd || 0),
        infra_cost_total: Number(costs.infraUsd || 0),
      },
    };
    need(
      [c.xi.data_cost_total, c.xi.infra_cost_total].every(
        (n) => Number.isFinite(n) && n >= 0 && n <= 1e6,
      ),
      "invalid operator-declared costs",
    );
    const trial = {
      id: randomUUID(),
      book,
      plugin: plugin.id,
      registered_at: new Date().toISOString(),
      recipe,
      reference,
      cost_usd: 0,
      cfg: c,
      binding: this.binding(),
      status: "REGISTERED",
      source: "SERVER_REGISTERED",
      datasetHash: null,
      report: null,
    };
    this.state.trials.push(trial);
    this.state.status = "COLLECTING";
    await this.save();
    return trial.id;
  }
  trial(id: string) {
    const t = this.state.trials.find((t: Json) => t.id === id);
    need(t, "unknown trial");
    need(t.binding === this.binding(), "policy binding changed");
    return t as Json;
  }
  normalize(raw: Json, book: string, now = Date.now()) {
    need(
      raw &&
        Array.isArray(raw.samples) &&
        Array.isArray(raw.events) &&
        raw.sessions &&
        typeof raw.sessions === "object",
      "samples/events/sessions required",
    );
    need(
      raw.samples.length <= 50000 &&
        raw.events.length <= 600000 &&
        Object.keys(raw.sessions).length <= 1200,
      "dataset limits exceeded",
    );
    const ids = new Set<string>(),
      features = this.legacy.HXII.FEATURES;
    for (const s of raw.samples) {
      need(
        typeof s.id === "string" && s.id.length <= 180 && !ids.has(s.id),
        "duplicate/invalid sample",
      );
      ids.add(s.id);
      const at = Date.parse(s.at);
      need(
        Number.isFinite(at) &&
          at <= now &&
          s.feature?.book === book &&
          features.every((k: string) => Number.isFinite(s.feature[k])),
        "invalid sample features/time/book",
      );
      need(
        Date.parse(s.feature.bar_end) <= at &&
          s.feature.ask >= s.feature.bid &&
          s.feature.bid > 0 &&
          s.feature.atr > 0,
        "future bars or invalid observed prices",
      );
    }
    const eventIds = new Set<string>();
    for (const e of raw.events) {
      need(
        typeof e.id === "string" && e.id.length <= 180 && !eventIds.has(e.id),
        "duplicate/invalid event id",
      );
      eventIds.add(e.id);
      const received = Date.parse(e.at);
      need(
        e.kind === "COTIZACIONES" &&
          Number.isFinite(received) &&
          received <= now &&
          Array.isArray(e.data?.quotes),
        "invalid quote event",
      );
      for (const q of e.data.quotes)
        need(
          Array.isArray(q) &&
            q.length === 4 &&
            typeof q[0] === "string" &&
            q.slice(1).every(Number.isFinite) &&
            q[2] > 0 &&
            q[3] >= q[2] &&
            received - q[1] >= -2000 &&
            received - q[1] <= 15000,
          "invalid/stale quote tuple",
        );
    }
    for (const [day, s] of Object.entries(raw.sessions) as [string, Json][]) {
      need(
        /^\d{4}-\d{2}-\d{2}$/.test(day) &&
          [s.open, s.close, s.first, s.last, s.gap, s.market_return].every(
            Number.isFinite,
          ) &&
          s.open < s.close &&
          s.close <= now &&
          s.first <= s.last &&
          s.gap >= 0,
        "invalid completed session",
      );
    }
    return {
      schema: "HARPOON-SELECTOR-DATA-30-1",
      source:
        raw.source === "SYNTHETIC_TEST"
          ? "SYNTHETIC_TEST"
          : "USER_IMPORTED_OBSERVATIONS",
      samples: raw.samples,
      events: raw.events,
      sessions: raw.sessions,
    };
  }
  async importData(id: string, raw: Json) {
    const t = this.trial(id);
    need(
      !["RUNNING", "QUEUED", "INSTALLED", "RETIRED"].includes(t.status),
      "trial unavailable for import",
    );
    const data = this.validators.run("selector-dataset", () =>
        this.normalize(raw, t.book),
      ),
      fingerprint = hash(data);
    need(
      !t.datasetHash || t.datasetHash === fingerprint,
      "dataset immutable after first import; register another trial for new historical data",
    );
    await this.store.put(this.key + "-import-" + id, data);
    t.datasetHash = fingerprint;
    t.status = "DATA_IMPORTED";
    await this.save();
    return {
      samples: data.samples.length,
      events: data.events.length,
      sessions: Object.keys(data.sessions).length,
      source: data.source,
      hash: fingerprint,
    };
  }
  async capture(m: Json, features: Json[], clock: Json, now = Date.now()) {
    if (
      !this.state.trials.length ||
      clock.is_open !== true ||
      now - this.state.lastCapture < 20000
    )
      return;
    const day = this.legacy.ny(now).day,
      session = m.calendar.find((s: Json) => s.date === day),
      spot = m.quotes.SPY;
    if (!session || !fresh(spot, now, this.cfg.quoteAgeMs)) return;
    const qs = this.cfg.universe
      .filter((i) => i.book !== "crypto")
      .map((i) => [i.symbol, m.quotes[i.symbol]])
      .filter(([, q]) => fresh(q as any, now, this.cfg.quoteAgeMs));
    if (!qs.length) return;
    const event = {
      id: "observed-" + now,
      kind: "COTIZACIONES",
      at: new Date(now).toISOString(),
      source: "ALPACA_OBSERVED",
      data: {
        quotes: qs.map(([symbol, q]) => [
          symbol,
          (q as Json).at,
          (q as Json).bid,
          (q as Json).ask,
        ]),
      },
    };
    await this.store.put(this.key + "-event-" + now, event);
    this.state.events++;
    this.state.lastCapture = now;
    const s = (this.state.sessions[day] ??= {
      open: session.open,
      close: session.close,
      first: now,
      last: now,
      gap: 0,
      openingAsk: spot.ask,
      market_return: 0,
    });
    s.gap = Math.max(s.gap, now - s.last);
    s.last = now;
    s.market_return = spot.bid / s.openingAsk - 1;
    for (const f of features) {
      if (
        !["equity", "etf"].includes(f.book) ||
        !this.legacy.HXII.FEATURES.every((k: string) => Number.isFinite(f[k]))
      )
        continue;
      const key = day + ":" + f.symbol,
        prior = this.state.samples[key] || { n: 0, at: 0 };
      if (prior.n >= 2 || now - prior.at < 1800000) continue;
      const sample = {
        id: "observed-" + randomUUID(),
        at: new Date(now).toISOString(),
        day,
        source: "ALPACA_OBSERVED",
        feature: structuredClone(f),
        selection_cohort: structuredClone(features),
        selected_at_observation: true,
      };
      await this.store.put(this.key + "-sample-" + sample.id, sample);
      this.state.samples[key] = { n: prior.n + 1, at: now };
    }
    this.state.status = "COLLECTING";
    this.state.lastError = "";
    await this.save();
  }
  private async scan(prefix: string) {
    need(
      typeof this.store.scan === "function",
      "persistent store must implement ordered scan",
    );
    return this.store.scan!(prefix, 700000);
  }
  async dataset(id: string) {
    const t = this.trial(id),
      imported = (await this.store.get(this.key + "-import-" + id)) || {
        samples: [],
        events: [],
        sessions: {},
        source: "ALPACA_OBSERVED",
      },
      cutoff = Date.parse(t.registered_at),
      symbols = new Set(
        this.cfg.universe.filter((i) => i.book === t.book).map((i) => i.symbol),
      );
    const observedSamples = (await this.scan(this.key + "-sample-")).filter(
        (s: Json) => s.feature.book === t.book,
      ),
      observedEvents = (await this.scan(this.key + "-event-"))
        .map((e: Json) => ({
          ...e,
          data: {
            quotes: e.data.quotes.filter((q: Json[]) =>
              symbols.has(String(q[0])),
            ),
          },
        }))
        .filter((e: Json) => e.data.quotes.length);
    const samples = [
        ...imported.samples.filter((s: Json) => Date.parse(s.at) < cutoff),
        ...observedSamples,
      ],
      events = [
        ...imported.events.filter((e: Json) => Date.parse(e.at) < cutoff),
        ...observedEvents,
      ],
      sessions = {
        ...Object.fromEntries(
          Object.entries(imported.sessions).filter(
            ([, s]) => (s as Json).close < cutoff,
          ),
        ),
        ...Object.fromEntries(
          Object.entries(this.state.sessions).filter(
            ([, s]) => (s as Json).close < Date.now(),
          ),
        ),
      };
    const complete = Object.keys(sessions)
        .filter((d) => {
          const s = (sessions as Json)[d];
          return (
            s.first <= s.open + 600000 &&
            s.last >= s.close - 30000 &&
            s.gap <= 60000
          );
        })
        .sort(),
      hold = complete.slice(-63);
    const prospectiveVerified =
      hold.length === 63 &&
      hold.every((d) => {
        const s = this.state.sessions[d];
        return (
          s &&
          s.open > cutoff &&
          s.first <= s.open + 600000 &&
          s.last >= s.close - 30000 &&
          s.gap <= 60000
        );
      });
    return {
      samples,
      events,
      sessions,
      source:
        imported.source === "SYNTHETIC_TEST"
          ? "SYNTHETIC_TEST"
          : "ALPACA_OBSERVED_WITH_OPERATOR_HISTORICAL_IMPORT",
      prospectiveVerified,
    };
  }
  async prepare(id: string, diagnostic = false) {
    const t = this.trial(id);
    need(
      !["RUNNING", "QUEUED", "INSTALLED"].includes(t.status),
      "trial unavailable",
    );
    const data = await this.dataset(id),
      days = Object.keys(data.sessions)
        .filter((d) => {
          const s = data.sessions[d] as Json;
          return (
            s.first <= s.open + 600000 &&
            s.last >= s.close - 30000 &&
            s.gap <= 60000
          );
        })
        .sort(),
      last = days.at(-1) || "";
    const holdStart = days.length >= 384 ? days.at(-63)! : "";
    if (
      data.prospectiveVerified &&
      holdStart &&
      data.samples.length >= 1000 &&
      data.events.length > 0
    ) {
      need(
        holdStart > (this.state.sealedThrough?.[t.book] || ""),
        "holdout already consumed",
      );
      this.state.sealedThrough ??= {};
      this.state.sealedThrough[t.book] = last;
    }
    t.status = "QUEUED";
    await this.save();
    return {
      operation: "selector",
      trialId: id,
      selectorInput: {
        ...data,
        trial: {
          recipe: t.recipe,
          reference: t.reference,
          registered_at: t.registered_at,
          cost_usd: t.cost_usd,
        },
        cfg: t.cfg,
        attempts:
          this.state.trials.filter((x: Json) => x.book === t.book).length - 1,
        diagnostic: diagnostic || !data.prospectiveVerified,
        sealedThrough: "",
        source: data.source,
        prospectiveVerified: data.prospectiveVerified,
      },
    };
  }
  async started(id: string) {
    this.trial(id).status = "RUNNING";
    await this.save();
  }
  async completed(id: string, result: Json) {
    need(
      result?.schema === SELECTOR_PIPELINE &&
        result.report &&
        typeof result.report.status === "string",
      "worker result contract",
    );
    const t = this.trial(id);
    await this.store.put(this.key + "-report-" + id, result);
    t.report = {
      status: result.report.status,
      reason: result.report.reason || "",
      gates: result.report.gates || {},
      trainingLabels: result.trainingLabels,
      prospectiveVerified: result.prospectiveVerified,
      diagnostic: result.report.diagnostic_only !== false,
    };
    t.status =
      result.report.status === "ACEPTADA" &&
      result.prospectiveVerified &&
      result.source !== "SYNTHETIC_TEST"
        ? "READY_TO_INSTALL"
        : result.report.status === "RECHAZADA"
          ? "REJECTED"
          : "WAIT_DATA";
    t.completedAt = Date.now();
    this.state.status = t.status;
    await this.save();
  }
  async failed(id: string, error: string) {
    const t = this.trial(id);
    t.status = "ERROR";
    t.error = error;
    this.state.lastError = error;
    this.state.status = "ERROR";
    await this.save();
  }
  async install(id: string, confirmation: string) {
    need(
      confirmation === "INSTALAR SELECTOR PAPER",
      "explicit PAPER installation confirmation required",
    );
    const t = this.trial(id),
      result = await this.store.get(this.key + "-report-" + id),
      report = result?.report;
    need(
      t.status === "READY_TO_INSTALL" &&
        report?.status === "ACEPTADA" &&
        result.prospectiveVerified === true &&
        result.source !== "SYNTHETIC_TEST" &&
        report.diagnostic_only === false &&
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
        ].every((k) => report.gates?.[k] === true) &&
        report.folds?.length === 12 &&
        report.candidate?.sessions === 252 &&
        report.holdout?.sessions === 63,
      "internally accepted prospective report required",
    );
    const model = this.validators.run("selector-model", () =>
        assertSelectorModel(report.frozen_selector),
      ),
      through = this.state.sessions[report.holdout_end]?.close;
    need(
      Number.isFinite(through) && through + 30 * 86400000 > Date.now(),
      "validation expired",
    );
    this.state.models[t.book] = {
      model,
      validUntil: through + 30 * 86400000,
      binding: this.binding(),
      trialId: id,
      reportHash: hash(result),
      scope:
        "PAPER_ONLY_NEW_XXX_POLICY_REQUIRES_PROSPECTIVE_EXECUTION_VALIDATION",
    };
    t.status = "INSTALLED";
    await this.save();
    return this.state.models[t.book];
  }
  async revoke(book: string) {
    need(["equity", "etf"].includes(book), "invalid book");
    delete this.state.models[book];
    await this.save();
  }
  async retire(id: string) {
    const t = this.trial(id);
    need(!["RUNNING", "QUEUED"].includes(t.status), "research busy");
    t.status = "RETIRED";
    if (this.state.models[t.book]?.trialId === id)
      delete this.state.models[t.book];
    await this.save();
  }
  view() {
    return {
      pipeline: SELECTOR_PIPELINE,
      status: this.state.status,
      lastCapture: this.state.lastCapture,
      observedQuoteBatches: this.state.events,
      capturedSamples: Object.values(this.state.samples).reduce(
        (n: number, x) => n + Number((x as Json).n),
        0,
      ),
      capturedSessions: Object.keys(this.state.sessions).length,
      lastError: this.state.lastError,
      trials: this.state.trials.map((t: Json) => ({
        id: t.id,
        book: t.book,
        plugin: t.plugin,
        registeredAt: t.registered_at,
        status: t.status,
        datasetHash: t.datasetHash,
        report: t.report,
        error: t.error,
      })),
      models: Object.entries(this.state.models).map(([book, x]) => ({
        book,
        trialId: (x as Json).trialId,
        validUntil: (x as Json).validUntil,
        n: (x as Json).model.n,
        trainedThrough: (x as Json).model.through,
      })),
      requirements: {
        completeSessions: 384,
        observedPaths: 1000,
        prospectiveSessions: 63,
        source:
          "Server-captured prospective quotes; imported history is not broker-attested",
      },
      implementation:
        "REGISTER_IMPORT_CAPTURE_TRAIN_VALIDATE_INSTALL_PERSIST_EVALUATE_CONNECTED",
    };
  }
}
