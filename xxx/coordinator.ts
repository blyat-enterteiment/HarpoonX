import { createHash, randomUUID } from "node:crypto";
import fs from "node:fs";
import path from "node:path";
import { fresh, floorStep, price, TERMINAL, validateConfig } from "./types";
import type {
  Api,
  Book,
  Campaign,
  Config,
  Intent,
  Json,
  State,
  Store,
  PositionEvaluation,
} from "./types";
import {
  availableSize,
  exitDecision,
  fills,
  deadlineFor,
  observeExit,
} from "./policy";
import { Scheduler, PriorityMutex } from "./scheduler";
import { Market } from "./market";
import { Plugins } from "./plugins";
import { normalizeOrder } from "./broker";
import { Selectors } from "./selectors";
import { RuntimeProbe, ObservedApi, systemHealth } from "./health";
import { AlpacaStreams } from "./streams";
import {
  urgentExit,
  rememberExit,
  remainingExit,
  nativeGroups,
  orderTree,
  protectionSnapshot,
  sampleProtection,
} from "./exits";
import { FeeLedger, executionMetrics } from "./accounting";
import { NetAccountLedger } from "./net_accounting";
import { QuantObservationJournal } from "./quant_observations";
import { entryOperationalFailures, operationalCapabilities } from "./operational_status";
import { ResearchLab } from "./ultimate_lab";
import { FuturesGateway } from "./ultimate_futures";
import { ULTIMATE_VERSION } from "./version";
import { sessionContext } from "./sessions";
import { digest } from "./ultimate_contracts";
import {
  Validators,
  CORE_CONTRACTS,
  assertAccount,
  assertClock,
  assertPositions,
  assertJournal,
  assertIntent,
  assertSignal,
  assertCampaignInventory,
  assertExitPlan,
  assertFreshQuote,
  assertPositionEvaluation,
  assertOperationalCoverage,
  assertRetryState,
  assertSellReservation,
  assertPartialEntryRisk,
} from "./validators";
const same = (a: string, b: string) =>
  a.replace("/", "") === b.replace("/", "");
export class Coordinator {
  cfg: Config;
  validators = new Validators(CORE_CONTRACTS);
  probe = new RuntimeProbe();
  broker: ObservedApi;
  selectors: Selectors;
  streams: AlpacaStreams;
  fees: FeeLedger;
  netLedger: NetAccountLedger;
  quantObservations: QuantObservationJournal;
  netAccountingError = "";
  quantObservationError = "";
  quantLastPlan: Json = {status: "NOT_RUN"};
  quantEconomicGate: Json = {status: "NOT_EVALUATED", dictamen: "VENTAJA_NO_DEMOSTRADA", execution_allowed: false, liveApproved: false};
  exitResearchReport: Json;
  ultimateLab: ResearchLab;
  futures: FuturesGateway;
  bundledUltimateReport: Json = {
    status: "NO_BUNDLED_REPORT",
    promotion: "NONE",
  };
  streamWork = false;
  streamWakeAt = 0;
  private pulseJob?: Promise<void>;
  healthSequence = 0;
  exitErrors: Record<string, Json> = {};
  exitCheckAt = 0;
  readonly evaluationDeadlineMs = 5000;
  positionEvaluations: Record<string, PositionEvaluation> = {};
  private lastActionCampaign = "";
  metricHistory: Json[] = [];
  quantResearch: Json = {status: "NOT_RUN"};
  quantPerformance: Json = {status: "WAIT_RECONCILED_PERFORMANCE"};
  quantDiscovery: Json = {status: "NOT_RUN", health: "WAITING", reason: "Aún no observado"};
  discoveryHold = false;
  private decisionSequence = 0;
  private readonly decisionRunId = randomUUID();
  state!: State;
  market: Market;
  plugins: Plugins;
  scheduler = new Scheduler();
  mutex = new PriorityMutex();
  account: Json = {};
  positions: Json[] = [];
  openOrders: Json[] = [];
  clock: Json = {};
  clockAt = 0;
  syncAt = 0;
  reconcileError = "STARTING";
  storageError = "";
  key: string;
  leaseName: string;
  stopping = false;
  autopilotStartedAt = 0;
  pendingResearch: Json | null = null;
  preparingResearch = false;
  saveQueue: Promise<unknown> = Promise.resolve();
  constructor(
    public store: Store,
    public api: Api,
    cfg: Config,
  ) {
    this.cfg = this.validators.run("config", () => validateConfig(cfg));
    this.key = "xxx-" + cfg.expected_account_id;
    this.leaseName = "account-paper-" + cfg.expected_account_id;
    this.broker = new ObservedApi(api);
    this.api = this.broker;
    this.fees = new FeeLedger(this.api, store, this.key + "-reported-fees");
    this.netLedger = new NetAccountLedger(store, this.api, this.key + "-net-account", cfg.expected_account_id,
      {...cfg.quant?.accounting, executionNature: cfg.mode.toUpperCase()});
    this.quantObservations = new QuantObservationJournal(store, this.key + "-quant-observations", cfg.expected_account_id, cfg.quant?.observations || {});
    this.ultimateLab = new ResearchLab(
      store,
      cfg.expected_account_id,
      this.validators,
      {
        capitalUsd: cfg.capitalLimit,
        riskFraction: cfg.riskFraction,
        openRiskFraction: cfg.openRiskFraction,
        grossFraction: cfg.totalExposure,
        assetFraction: cfg.assetExposure,
        dailyLoss: cfg.dailyLoss,
        maxDrawdown: cfg.maxDrawdown,
      },
    );
    this.futures = new FuturesGateway(store, cfg, this.validators);
    const ultimateReportFile = path.join(
      __dirname,
      "../evidence/ultimate/report.json",
    );
    if (fs.existsSync(ultimateReportFile)) {
      try {
        const report = JSON.parse(fs.readFileSync(ultimateReportFile, "utf8"));
        this.validators.run("ultimate-bundled-report", () => {
          if (
            report.schema !== "HARPOON-ULTIMATE-REPORT-1" ||
            report.promotion !== "NONE"
          )
            throw Error("Bundled report contract");
          this.ultimateLab.verifyBundled(
            report,
            JSON.parse(
              fs.readFileSync(
                path.join(__dirname, "../evidence/ultimate/registry.json"),
                "utf8",
              ),
            ),
          );
        });
        this.bundledUltimateReport = report;
      } catch (e) {
        this.bundledUltimateReport = {
          status: "INVALID",
          error: String(e),
          promotion: "NONE",
        };
      }
    }
    try {
      const file = path.join(__dirname, "../evidence/tp32/report.json"),
        report = JSON.parse(fs.readFileSync(file, "utf8")),
        protocol = fs.readFileSync(
          path.join(__dirname, "../research/tp32/protocol.json"),
        );
      if (
        report.schema !== "HARPOON-WF-REPORT-32-1" ||
        createHash("sha256").update(protocol).digest("hex") !==
          report.protocolSha256
      )
        throw Error("Research report contract/hash mismatch");
      this.exitResearchReport = report;
    } catch (e) {
      this.exitResearchReport = {
        status: "UNAVAILABLE",
        error: String(e),
        promotion: "NONE",
      };
    }
    this.market = new Market(this.api, this.cfg, this.validators);
    this.streams = new AlpacaStreams(
      this.api,
      cfg,
      (symbol, raw) => this.onQuote(symbol, raw),
      async (raw) => this.onTradeUpdate(raw),
      (raw) => {
        this.plugins.sharedFlow(raw);
        if (raw.T === "t") this.market.recordMicro(raw.S, raw, "trade");
      },
      (name) => {
        this.plugins.sharedReset(name);
        this.market.resetMicro(name);
        if (name === "orders") this.syncAt = 0;
      },
      undefined,
      (name) => name === "crypto" || this.session("equity"),
    );
    this.plugins = new Plugins(store, cfg);
    this.selectors = new Selectors(
      store,
      cfg,
      this.plugins.legacy,
      this.plugins.catalog,
      this.validators,
    );
  }
  async save() {
    const snapshot = structuredClone(this.state);
    const work = this.saveQueue.then(() =>
      this.validators.check("journal-write", () =>
        this.store.put(this.key, snapshot),
      ),
    );
    this.saveQueue = work.catch((e) => {
      this.storageError = String(e);
    });
    return work;
  }
  event(kind: string, data: Json = {}) {
    const detail = { ...data };
    if (detail.kind !== undefined) {
      detail.intentKind = detail.kind;
      delete detail.kind;
    }
    this.state.events.push({ ...detail, at: Date.now(), kind });
    this.state.events = this.state.events.slice(-300);
  }
  async initialize(startPaper = false) {
    if (!(await this.store.lease(this.leaseName)))
      throw Error("Account lease held by another runtime");
    const rawAccount = await this.api.request("/v2/account");
    const account = this.validators.run("account", () =>
      assertAccount(rawAccount, this.cfg.expected_account_id),
    );
    if (
      account.id !== this.cfg.expected_account_id ||
      account.status !== "ACTIVE"
    )
      throw Error("PAPER account binding mismatch");
    const fingerprint = createHash("sha256")
        .update(JSON.stringify(this.cfg))
        .digest("hex"),
      priorConfig = await this.store.get(this.key + "-config");
    if (priorConfig && priorConfig !== fingerprint)
      throw Error(
        "Configuration differs from journal; reconcile before changing account limits",
      );
    const old = await this.store.get(this.key);
    if (old) {
      if (old.schema !== "HARPOON-XXX-1" || old.accountId !== account.id)
        throw Error("Journal schema/account mismatch");
      this.state = this.validators.run("journal", () =>
        assertJournal(old, account.id),
      );
      if (this.state.research.status === "RUNNING")
        this.state.research.status = "INTERRUPTED_BUDGET_CONSUMED";
      if (this.state.research.status === "QUEUED")
        this.state.research.status = "INTERRUPTED_NOT_RUN";
    } else {
      const [positions, orders] = await Promise.all([
        this.api.request("/v2/positions"),
        this.api.request("/v2/orders?status=open&limit=500"),
      ]);
      if (
        !Array.isArray(positions) ||
        !Array.isArray(orders) ||
        positions.length ||
        orders.length
      )
        throw Error(
          "New XXX journal requires an empty dedicated PAPER account; existing positions are not silently adopted",
        );
      this.state = {
        schema: "HARPOON-XXX-1",
        accountId: account.id,
        paused: !startPaper,
        researchPaused: false,
        plugins: this.cfg.enabledPlugins,
        campaigns: [],
        intents: [],
        peakEquity: Number(account.equity),
        day: "",
        dayEquity: Number(account.equity),
        halt: "",
        events: [],
        research: { status: "WAIT_DATA", runs: 0, paidModelCalls: 0 },
        sequence: 0,
      };
    }
    this.plugins.models =
      (await this.store.get(this.key + "-economic-models")) || {};
    await this.selectors.load();
    await this.ultimateLab.load();
    await this.futures.load();
    await this.fees.load();
    try { await this.netLedger.load(); } catch (error) { this.netAccountingError = String(error); }
    try { await this.quantObservations.load(); } catch (error) { this.quantObservationError = String(error); }
    this.plugins.selectors = this.selectors.state.models;
    this.plugins.validateSelection(this.state.plugins);
    await this.store.put(this.key + "-config", fingerprint);
    if (this.cfg.quant?.enabled && this.cfg.quant.discovery) {
      this.discoveryHold = true;
      try {
        const saved = await this.store.get(this.key + "-discovery-registry");
        if (saved) {
          if (saved.accountId !== account.id || saved.baseConfigHash !== fingerprint)
            throw Error("DISCOVERY_REGISTRY_ACCOUNT_OR_CONFIG_MISMATCH");
          const restored = require("../runtime/discovery.cjs").restore(this, saved.registry);
          if (restored.status === "BLOCKED") throw Error(restored.reason);
          this.quantDiscovery = {status: "RESTORED_WAITING", health: "WAITING",
            reason: "Vigilancia restaurada; requiere datos actuales", restored,
            at: saved.registry.at || null};
        }
      } catch (error) {
        this.quantDiscovery = {status: "BLOCKED", health: "BLOCKED", reason: String(error)};
        this.event("QUANT_DISCOVERY_RESTORE_BLOCKED", this.quantDiscovery);
      }
    }
    await this.save();
    for (const c of this.state.campaigns.filter((c) => !c.closed))
      this.market.assets[c.symbol] = c.instrument;
    await this.reconcile();
    await this.sessions();
    this.configureLanes();
  }
  configureLanes() {
    this.scheduler.add("ultimate-research-worker", 3000, async () => {
      if (!this.state.researchPaused) await this.ultimateLab.tick();
    });
    this.scheduler.add("futures-account-reconciliation", 5000, () =>
      this.futures.refreshAccount(),
    );
    this.scheduler.add("futures-quotes-and-margin", 3000, () =>
      this.futures.refreshMarket(),
    );
    this.scheduler.add("account-reconciliation", 5000, () => this.reconcile());
    if (this.cfg.quant?.enabled) {
      this.scheduler.add("net-account-ledger", 60000, () => this.refreshNetAccounting());
      this.scheduler.add("quant-prospective-observations", this.quantObservations.intervalMs, () => this.captureQuantObservations());
      this.scheduler.add("quant-economic-evidence", 900000, async () => {
        this.quantEconomicGate = await require("../runtime/quant_bridge.cjs").verifyEconomicGate(this);
      });
    }
    this.scheduler.add("positions-and-take-profit", 1000, async () => {
      await this.pulse();
      this.validators.run("guardian-coverage", () => assertOperationalCoverage(this.exitCoverage()));
    });
    this.scheduler.add("sessions", 15000, () => this.sessions());
    this.scheduler.add("catalog", 3600000, () => this.market.catalog());
    for (const book of ["equity", "etf", "crypto", "options"] as Book[]) {
      this.scheduler.add("quotes-" + book, 3000, async () => {
        if (book !== "crypto" && !this.session(book)) return;
        await this.market.quotesFor(
          book,
          this.active()
            .filter((c) => c.book === book)
            .map((c) => c.symbol),
        );
      });
      if (book !== "options")
        this.scheduler.add("history-" + book, 60000, () =>
          this.market.history(book),
        );
      this.scheduler.add("entries-" + book, 15000, () => this.entries(book));
    }
    if (this.cfg.quant?.enabled && this.cfg.quant.discovery) {
      this.scheduler.add("quant-stock-discovery", 900000, () => this.discoverStocks());
    }
    if (this.cfg.quant?.microstructure?.enabled) {
      this.scheduler.add("quant-calibration-context", 900000, async () => {
        const result = await require("../runtime/quant_bridge.cjs").context(this);
        this.event("QUANT_CALIBRATION_CONTEXT", {
          status: result.status, curve: result.curve,
          microstructure: Object.fromEntries(Object.entries(result.microstructure || {}).map(([s, value]) =>
            [s, {status: (value as Json).status, reason: (value as Json).reason, quote_events: (value as Json).quote_events}])),
        });
        if (result.status !== "CALIBRATION_CONTEXT") throw Error("Quant context worker unavailable");
      });
    }
    if (this.cfg.quant?.enabled) {
      this.scheduler.add("quant-performance", 60000, async () => {
        if (Date.now() - this.syncAt > 15000) {
          this.quantPerformance = {status: "STALE_ACCOUNT"};
          return;
        }
        this.quantPerformance = await require("../runtime/quant_bridge.cjs").performance(this);
      });
    }
    if (this.cfg.quant?.optimizer?.enabled) {
      this.scheduler.add("quant-recursive-calibration", 900000, async () => {
        if (this.state.researchPaused) {this.quantResearch = {status:"PAUSED"};return;}
        this.quantResearch = await require("../runtime/quant_bridge.cjs").optimize(this);
        this.event("QUANT_RECURSIVE_CALIBRATION", {status: this.quantResearch.status, campaign: this.quantResearch.campaign?.id, budget: this.quantResearch.budget});
      });
    }
    this.scheduler.add("options-context", 60000, async () => {
      if (this.session("options")) await this.market.optionChains();
    });
    this.scheduler.add("plugin-flow-history", 60000, async () => {
      this.plugins.updateStreams(
        this.api,
        this.state.plugins,
        this.cfg.streaming !== false && !!this.broker.keys?.key,
      );
      await this.market.benchmarkHistory(this.plugins.benchmarkSymbols());
      const targets = this.plugins.astraSymbols(this.state.plugins);
      if (targets.length)
        await this.market.detailedHistory([
          ...new Set([
            ...targets,
            "SPY",
            ...this.cfg.universe
              .filter((i) => targets.includes(i.symbol))
              .map((i) => this.plugins.sector(i.factor)),
          ]),
        ]);
      if (this.state.plugins.some((id) => id.startsWith("crypto-warroom")))
        await this.market.fourHour();
    });
    this.scheduler.add("selector-observations", 20000, async () => {
      if (!this.selectors.state.trials.length || !this.session("equity"))
        return;
      const now = Date.now(),
        features = this.plugins.features(this.market, now);
      await this.selectors.capture(this.market, features, this.clock, now);
    });
    this.scheduler.add("research", 5000, () => this.research());
    this.scheduler.add("execution-streams", 15000, async () => {
      this.updateStreams();
    });
    this.scheduler.add("reported-fees", 60000, () =>
      this.fees.refresh(
        Math.min(Date.now(), ...this.state.campaigns.map((c) => c.created)),
      ),
    );
  }
  active() {
    return this.state.campaigns.filter((c) => !c.closed);
  }
  updateStreams() {
    this.streams.start({
      stocks: [
        ...new Set([
          ...this.cfg.universe
            .filter((i) => ["equity", "etf"].includes(i.book))
            .map((i) => i.symbol),
          ...this.cfg.optionUnderlyings,
        ]),
      ],
      crypto: this.cfg.universe
        .filter((i) => i.book === "crypto")
        .map((i) => i.symbol),
      options: [
        ...new Set([
          ...this.active()
            .filter((c) => c.book === "options")
            .map((c) => c.symbol),
          ...(this.market.watched.options || []),
        ]),
      ],
    });
  }
  onQuote(symbol: string, raw: Json) {
    if (this.stopping) return;
    const now = Date.now(),
      q = this.plugins.legacy.quote
        ? this.plugins.legacy.quote(raw, now)
        : {
            bid: Number(raw.bp),
            ask: Number(raw.ap),
            at: Date.parse(raw.t),
            received: now,
          };
    const book =
      this.market.assets[symbol]?.book ||
      this.cfg.universe.find((i) => i.symbol === symbol)?.book ||
      "equity";
    this.validators.run("quote-" + book, () =>
      assertFreshQuote(q, now, this.cfg.quoteAgeMs),
    );
    const prior = this.market.quotes[symbol];
    if (prior && q.at < prior.at) return;
    this.market.quotes[symbol] = q;
    this.market.recordMicro(symbol, raw, "quote");
    if (
      this.streamWork ||
      now - this.streamWakeAt < 100 ||
      !this.active().some((c) => c.symbol === symbol)
    )
      return;
    this.streamWork = true;
    this.streamWakeAt = now;
    void this.pulse()
      .catch((e) => {
        for (const c of this.active().filter((c) => c.symbol === symbol))
          this.exitErrors[c.id] = { at: Date.now(), symbol, error: String(e) };
        this.event("STREAM_GUARDIAN_ERROR", { symbol, error: String(e) });
      })
      .finally(() => {
        this.streamWork = false;
      });
  }
  async onTradeUpdate(raw: Json) {
    if (this.stopping) return;
    await this.mutex.run(0, async () => {
      const o = this.validators.run("stream-event", () =>
        normalizeOrder(raw.order, raw.order?.client_order_id),
      );
      const i = this.state.intents.find(
        (x) => x.id === o.client_order_id || x.order?.id === o.id,
      );
      if (!i) {
        this.syncAt = 0;
        this.event("EXTERNAL_ORDER_STREAM", { symbol: o.symbol });
        return;
      }
      if (
        !same(o.symbol, i.symbol) ||
        o.side !== i.payload.side ||
        (!i.parentId && Number(o.qty) !== Number(i.payload.qty))
      )
        throw Error("Stream order contract mismatch");
      const oldFilled = Number(i.order?.filled_qty || 0),
        newFilled = Number(o.filled_qty);
      if (newFilled < oldFilled) return;
      if (
        TERMINAL.has(i.status) &&
        !TERMINAL.has(o.status) &&
        newFilled === oldFilled
      )
        return;
      if (newFilled === oldFilled && i.status === o.status) return;
      i.order = o;
      i.status = o.status;
      if (newFilled > oldFilled) i.fillObservedAt = Date.now();
      this.adoptLegs(i, o);
      this.syncAt = 0;
      this.event("TRADE_UPDATE_OBSERVED", {
        symbol: i.symbol,
        kind: i.kind,
        event: raw.event,
        qtyDelta: newFilled - oldFilled,
      });
      await this.save();
    });
    await this.reconcile();
    await this.pulse();
  }
  adoptLegs(parent: Intent, order: Json) {
    if (parent.payload.order_class !== "oco") return;
    const rows = this.validators.run("native-order-tree", () =>
      orderTree([order]),
    );
    for (const child of rows.filter((o) => o.id !== order.id)) {
      const o = normalizeOrder(child, child.client_order_id);
      if (
        !same(o.symbol, parent.symbol) ||
        o.side !== "sell" ||
        !["stop", "stop_limit"].includes(o.type) ||
        Number(o.qty) > Number(parent.payload.qty)
      )
        throw Error("Native OCO child contract mismatch");
      const existing = this.state.intents.find(
        (i) => i.id === o.client_order_id || i.order?.id === o.id,
      );
      if (existing) {
        if (existing.parentId !== parent.id)
          throw Error("Native child ownership conflict");
        const priorFilled = Number(existing.order?.filled_qty || 0),
          observedFilled = Number(o.filled_qty);
        // Nested parent responses can arrive after a terminal child update.
        // Apply the same monotonicity rule as the direct trade-update path;
        // a genuinely larger cumulative fill must still reach reconciliation.
        if (TERMINAL.has(existing.status) && !TERMINAL.has(o.status) &&
            observedFilled === priorFilled) continue;
        if (observedFilled >= priorFilled) {
          existing.order = o;
          existing.status = o.status;
        }
        continue;
      }
      const i: Intent = {
        id: o.client_order_id,
        symbol: parent.symbol,
        campaign: parent.campaign,
        kind: "protect",
        parentId: parent.id,
        nativeRole: "stop_leg",
        payload: {
          symbol: o.symbol,
          qty: o.qty,
          side: o.side,
          type: o.type,
          stop_price: o.stop_price,
          time_in_force: o.time_in_force,
        },
        at: parent.at,
        status: o.status,
        order: o,
        ackAt: Date.now(),
      };
      this.state.intents.push(i);
      this.state.campaigns
        .find((c) => c.id === parent.campaign)!
        .intents.push(i.id);
    }
  }
  pending(c?: Campaign) {
    return this.state.intents.filter(
      (i) => (!c || i.campaign === c.id) && !TERMINAL.has(i.status),
    );
  }
  confirmedProtection(c: Campaign) {
    return protectionSnapshot(
      c,
      this.state.intents,
      Number(this.position(c.symbol)?.qty || 0),
      Date.now(),
    ).quantityCovered;
  }
  position(s: string) {
    return this.positions.find((p) => same(p.symbol, s));
  }
  async authority() {
    if (
      this.stopping ||
      this.storageError ||
      !(await this.store.lease(this.leaseName))
    )
      throw Error("No durable exclusive broker authority");
  }
  async sessions() {
    const r = await this.api.request("/v2/clock"),
      now = Date.now();
    if (
      typeof r.is_open !== "boolean" ||
      Math.abs(now - Date.parse(r.timestamp)) > 15000 ||
      !Number.isFinite(Date.parse(r.next_close))
    )
      throw Error("Invalid broker clock");
    this.validators.run("clock", () => assertClock(r, now));
    this.clock = r;
    this.clockAt = now;
    if (
      !this.market.updated.calendar ||
      now - this.market.updated.calendar > 3600000
    ) {
      const rows = await this.api.request(
        "/v2/calendar?" +
          new URLSearchParams({
            start: new Date(now - 55 * 86400000).toISOString().slice(0, 10),
            end: new Date(now + 60 * 86400000).toISOString().slice(0, 10),
          }),
      );
      if (!Array.isArray(rows)) throw Error("Invalid calendar");
      this.market.calendar = this.plugins.legacy.HX.sessions(rows);
      this.market.updated.calendar = now;
    }
  }
  session(book: Book, entry = false) {
    const now = Date.now();
    return (
      book === "crypto" ||
      (now - this.clockAt <= 45000 &&
        this.clock.is_open === true &&
        now < Date.parse(this.clock.next_close) - (entry ? 600000 : 0))
    );
  }
  async reconcile() {
    return this.mutex.run(1, async () => {
      await this.authority();
      this.syncAt = 0;
      const rawOrders = await this.api.request(
        "/v2/orders?status=open&limit=500&nested=true",
      );
      if (!Array.isArray(rawOrders) || rawOrders.length >= 500)
        throw Error("Open-order snapshot incomplete");
      const orders = this.validators.run("native-order-tree", () =>
        orderTree(rawOrders),
      );
      for (const i of this.pending()) {
        try {
          const found = orders.find((o: Json) => o.client_order_id === i.id),
            raw =
              found ||
              (await this.api.request(
                "/v2/orders:by_client_order_id?client_order_id=" +
                  encodeURIComponent(i.id),
              )),
            o = this.validators.run("order-response", () =>
              normalizeOrder(raw, i.id),
            );
          if (
            !same(String(o.symbol), i.symbol) ||
            o.side !== i.payload.side ||
            (!i.parentId && Number(o.qty) !== Number(i.payload.qty)) ||
            (i.parentId && Number(o.qty) > Number(i.payload.qty)) ||
            Number(o.filled_qty) > Number(o.qty)
          )
            throw Error("Order contract mismatch");
          const prior = Number(i.order?.filled_qty || 0);
          if (Number(o.filled_qty) < prior)
            throw Error("Fill quantity regressed");
          i.order = o;
          i.status = o.status;
          this.adoptLegs(i, o);
          this.observeSubmission(this.state.campaigns.find((c) => c.id === i.campaign)!, i);
          delete i.error;
          if (Number(o.filled_qty) > prior) {
            i.fillObservedAt = Date.now();
            this.event("FILL_OBSERVED", {
              symbol: i.symbol,
              clientOrderId: i.id,
              qtyDelta: Number(o.filled_qty) - prior,
              average: Number(o.filled_avg_price),
              kind: i.kind,
            });
          }
        } catch (e) {
          i.status = "UNKNOWN";
          i.error = String(e);
        }
      }
      const [account, positions] = await Promise.all([
        this.api.request("/v2/account"),
        this.api.request("/v2/positions"),
      ]);
      this.validators.run("account", () =>
        assertAccount(account, this.cfg.expected_account_id),
      );
      this.validators.run("positions", () => assertPositions(positions));
      this.account = account;
      this.positions = positions;
      this.openOrders = orders;
      const issues: string[] = [];
      if (
        this.pending().some(
          (i) => i.status === "UNKNOWN" || i.status === "SUBMITTING",
        )
      )
        issues.push("UNCERTAIN_ORDER");
      if (
        orders.some(
          (o: Json) =>
            !this.state.intents.some((i) => i.id === o.client_order_id),
        )
      )
        issues.push("EXTERNAL_ORDER");
      if (
        positions.some(
          (p: Json) => !this.active().some((c) => same(c.symbol, p.symbol)),
        )
      )
        issues.push("EXTERNAL_POSITION");
      for (const c of this.active()) {
        const f = fills(c, this.state.intents),
          p = this.position(c.symbol),
          qty = Number(p?.qty || 0),
          tolerance =
            c.book === "crypto"
              ? Math.max(
                  c.instrument.step,
                  (f.bought * this.cfg.cryptoFeeBps) / 10000,
                )
              : 1e-8;
        if (qty < 0 || qty > f.qty + tolerance || qty < f.qty - tolerance)
          issues.push("INVENTORY_MISMATCH:" + c.symbol);
        if (
          qty === 0 &&
          !this.pending(c).length &&
          (f.qty <= tolerance || f.bought === 0)
        ) {
          c.closed = true;
          c.closedAt = Date.now();
        }
      }
      this.reconcileError = issues.join("; ");
      const day = this.plugins.legacy.ny(Date.now()).day;
      if (this.state.day !== day) {
        this.state.day = day;
        this.state.dayEquity = Number(account.equity);
      }
      this.state.peakEquity = Math.max(
        this.state.peakEquity,
        Number(account.equity),
      );
      if (
        Number(account.equity) <=
        this.state.dayEquity * (1 - this.cfg.dailyLoss)
      )
        this.state.halt = "DAILY_LOSS";
      if (
        Number(account.equity) <=
        this.state.peakEquity * (1 - this.cfg.maxDrawdown)
      )
        this.state.halt = "DRAWDOWN";
      if (this.state.halt) for (const c of this.active()) c.flatten = true;
      this.syncAt = Date.now();
      // Include just-closed campaigns: only reconciled terminal inventory may
      // resolve a persisted partial-entry exposure, never a missing local row.
      for (const c of this.state.campaigns)
        if (!c.closed || (c.partialEntryRisk && c.partialEntryRisk.status !== "RESOLVED"))
          this.observePartialEntryRisk(c, this.syncAt);
      this.metricHistory.push({
        at: this.syncAt,
        equity: Number(account.equity),
        cash: Number(account.cash),
        positions: positions.length,
        pending: this.pending().length,
      });
      this.metricHistory = this.metricHistory.slice(-240);
      await this.save();
    });
  }
  own(c: Campaign) {
    const qty = Number(this.position(c.symbol)?.qty || 0),
      f = fills(c, this.state.intents),
      tol =
        c.book === "crypto"
          ? Math.max(
              c.instrument.step,
              (f.bought * this.cfg.cryptoFeeBps) / 10000,
            )
          : 1e-8;
    return (
      qty >= 0 &&
      Math.abs(qty - f.qty) <= tol &&
      !this.openOrders.some(
        (o) =>
          same(o.symbol, c.symbol) &&
          !this.state.intents.some((i) => i.id === o.client_order_id),
      ) &&
      !this.pending(c).some((i) => ["UNKNOWN", "SUBMITTING"].includes(i.status))
    );
  }
  private partialEntryObservationFresh(c: Campaign, now: number) {
    return !!this.syncAt && now >= this.syncAt && now - this.syncAt <= 10000 &&
      !this.reconcileError && this.own(c) &&
      (!c.partialEntryRisk || this.syncAt >= c.partialEntryRisk.lastObservedAt);
  }
  private partialEntryRiskSnapshot(c: Campaign, now: number) {
    const r = c.partialEntryRisk;
    if (!r) return null;
    const observationFresh = this.partialEntryObservationFresh(c, now);
    const status = r.status !== "RESOLVED" && !observationFresh ? "UNVERIFIED" : r.status;
    return { ...r, status, observationFresh, quantityBasis: "LAST_RECONCILED",
      overdue: status !== "RESOLVED" && (r.overdue || now >= r.deadlineAt),
      elapsedMs: now < r.firstObservedAt ? null : (r.resolvedAt || now) - r.firstObservedAt };
  }
  private observePartialEntryRisk(c: Campaign, now: number) {
    let r = c.partialEntryRisk;
    if (r?.status === "RESOLVED") return;
    const verified = this.partialEntryObservationFresh(c, now);
    const entry = this.pending(c).find((i) => i.kind === "entry");
    // Telemetry uses broker inventory, not executable rounded-down order size.
    const qty = verified ? Number(this.position(c.symbol)?.qty || 0) : null;
    const coverage = qty !== null ? protectionSnapshot(c, this.state.intents, qty, now) : null;
    if (!r) {
      if (!verified || !entry || !(Number(entry.order?.filled_qty) > 0) ||
        qty === null || qty <= 0 || !coverage || coverage.aligned) return;
      r = c.partialEntryRisk = { source: "BROKER_RECONCILIATION", entryId: entry.id,
        firstObservedAt: this.syncAt, lastObservedAt: this.syncAt, deadlineAt: this.syncAt + this.cfg.orderTtlMs,
        heldQty: qty, coveredQty: Math.min(qty, coverage.covered),
        cancelRequestedAt: entry.cancelAt || null, status: "WAIT_CANCEL", overdue: false };
      this.event("PARTIAL_ENTRY_UNPROTECTED", { symbol: c.symbol, entryId: entry.id,
        heldQty: qty, coveredQty: r.coveredQty, deadlineAt: r.deadlineAt });
    }
    if (!verified || qty === null || !coverage) {
      r.status = "UNVERIFIED"; // Retain last-known quantities; absence is not flatness.
    } else {
      r.lastObservedAt = this.syncAt;
      r.heldQty = qty;
      r.coveredQty = Math.min(qty, coverage.covered);
      if (entry?.cancelAt)
        r.cancelRequestedAt = r.cancelRequestedAt === null ? entry.cancelAt : Math.min(r.cancelRequestedAt, entry.cancelAt);
      if (!entry && (qty === 0 || coverage.aligned)) {
        r.status = "RESOLVED";
        r.overdue = false;
        r.resolvedAt = now;
        r.resolution = qty === 0 ? "CONFIRMED_FLAT" : "CONFIRMED_PROTECTION";
        this.event("PARTIAL_ENTRY_PROTECTION_RESOLVED", { symbol: c.symbol, entryId: r.entryId,
          resolution: r.resolution, heldQty: qty, coveredQty: r.coveredQty,
          elapsedMs: now - r.firstObservedAt });
      } else r.status = entry ? "WAIT_CANCEL" : "WAIT_PROTECTION";
    }
    if (r.status !== "RESOLVED" && now >= r.deadlineAt) {
      r.overdue = true;
      if (r.overdueAt === undefined) {
        r.overdueAt = now;
        this.event("PARTIAL_ENTRY_PROTECTION_OVERDUE", { symbol: c.symbol, entryId: r.entryId,
          status: r.status, heldQty: r.heldQty, coveredQty: r.coveredQty,
          firstObservedAt: r.firstObservedAt, lastObservedAt: r.lastObservedAt,
          deadlineAt: r.deadlineAt });
      }
    }
    this.validators.run("partial-entry-risk", () => assertPartialEntryRisk(c, this.state.intents));
  }
  private retryClass(kind: Intent["kind"]): "protect" | "urgent" | "profit" {
    return kind === "protect" ? "protect" : urgentExit(kind) ? "urgent" : "profit";
  }
  private observeSubmission(c: Campaign, i: Intent) {
    if (i.kind === "entry" || i.parentId) return;
    const key = this.retryClass(i.kind), requestKey = [i.kind, i.nativeRole || "", i.payload.type, i.payload.order_class || ""].join(":");
    if (i.status === "rejected") {
      if (c.orderRetry?.[key]?.lastIntent === i.id) return;
      const failures = Math.min(30, (c.orderRetry?.[key]?.failures || 0) + 1), now = Date.now();
      const retry = { failures, lastAt: now, nextAt: now + Math.min(60000, 2000 * 2 ** Math.min(5, failures - 1)),
        lastError: i.error || "Definitive broker rejection", lastIntent: i.id, requestKey };
      this.validators.run("protection-retry", () => assertRetryState(retry));
      (c.orderRetry ??= {})[key] = retry;
      this.event("ORDER_RETRY_BACKOFF", { symbol: c.symbol, kind: i.kind, failures, nextAt: retry.nextAt });
    } else if (!["UNKNOWN", "SUBMITTING"].includes(i.status) && c.orderRetry?.[key]) {
      const retry = c.orderRetry[key]!;
      // Reconciliation of an older accepted sibling must not reset a rejected leg's budget.
      if (retry.requestKey === requestKey && this.state.intents.indexOf(i) > this.state.intents.findIndex((x) => x.id === retry.lastIntent))
        delete c.orderRetry[key];
    }
  }
  async submit(
    c: Campaign,
    kind: Intent["kind"],
    payload: Json,
    meta: { nativeRole?: Intent["nativeRole"] } = {},
  ) {
    await this.authority();
    if (kind !== "entry" && (c.orderRetry?.[this.retryClass(kind)]?.nextAt || 0) > Date.now()) return;
    this.validators.run("intent", () => assertIntent(payload, c.instrument));
    if (payload.side === "sell") {
      if (!this.syncAt || Date.now() - this.syncAt > 10000 || !this.own(c))
        throw Error("Fresh owned inventory required before sale");
      this.validators.run("sell-reservation", () => assertSellReservation(c, this.state.intents,
        Number(this.position(c.symbol)?.qty || 0), Number(payload.qty)));
    }
    const id =
      "h30-" +
      createHash("sha256").update(this.key).digest("hex").slice(0, 8) +
      "-" +
      ++this.state.sequence;
    const i: Intent = {
      id,
      symbol: c.symbol,
      campaign: c.id,
      kind,
      payload: { ...payload, client_order_id: id },
      at: Date.now(),
      status: "SUBMITTING",
      ...meta,
      ...(kind !== "entry" && kind !== "protect" && c.exitPlan
        ? { decisionAt: c.exitPlan.detectedAt, quoteAt: c.exitPlan.quoteAt }
        : {}),
    };
    this.state.intents.push(i);
    c.intents.push(id);
    if (kind === "protect") c.protectionChangedAt = Date.now();
    if (kind !== "entry" && kind !== "protect" && c.exitPlan) {
      c.exitPlan.orderId = id;
      c.exitPlan.status = "WORKING";
    }
    await this.save();
    try {
      const response = await this.api.request("/v2/orders", "POST", i.payload);
      const o = this.validators.run("order-response", () =>
        normalizeOrder(response, id),
      );
      if (
        !same(o.symbol, c.symbol) ||
        o.side !== payload.side ||
        Number(o.qty) !== Number(payload.qty)
      )
        throw Error("Order response contract mismatch");
      i.order = o;
      i.status = o.status;
      i.ackAt = Date.now();
      if (Number(o.filled_qty) > 0) i.fillObservedAt = Date.now();
      this.adoptLegs(i, o);
      this.event("ORDER_ACK", {
        symbol: c.symbol,
        kind,
        clientOrderId: id,
        status: i.status,
      });
    } catch (e) {
      const err = e as Json;
      i.status =
        err.not_sent || [400, 401, 403, 422].includes(err.status)
          ? "rejected"
          : "UNKNOWN";
      i.error = String(e);
      this.event("ORDER_UNCONFIRMED", {
        symbol: c.symbol,
        kind,
        status: i.status,
      });
    } finally {
      this.observeSubmission(c, i);
      this.syncAt = 0;
      await this.save();
    }
    return i;
  }
  async cancel(i: Intent) {
    if (
      !i.order?.id ||
      TERMINAL.has(i.status) ||
      (i.cancelAt && Date.now() - i.cancelAt < 5000)
    )
      return;
    await this.authority();
    i.cancelAt = Date.now();
    await this.save();
    try {
      await this.api.request(
        "/v2/orders/" + encodeURIComponent(i.order.id),
        "DELETE",
      );
      this.event("CANCEL_REQUESTED", { clientOrderId: i.id });
    } catch (e) {
      i.error = String(e);
    }
    this.syncAt = 0;
    await this.save();
  }
  payload(
    c: Campaign,
    kind: Intent["kind"],
    qty: number,
    q?: import("./types").Quote,
  ): Json {
    const i = c.instrument,
      option = c.book === "options",
      crypto = c.book === "crypto",
      tif = crypto ? "gtc" : "day";
    const base: Json = {
      symbol: c.symbol,
      qty: String(floorStep(qty, i.step)),
      side: "sell",
      time_in_force: tif,
      ...(option ? { position_intent: "sell_to_close" } : {}),
    };
    if (kind === "protect") {
      const stop = price(c.stop, i.tick);
      return {
        ...base,
        type: crypto ? "stop_limit" : "stop",
        stop_price: stop,
        ...(crypto
          ? {
              limit_price: price(
                c.stop * (1 - this.cfg.slippageBps / 10000),
                i.tick,
              ),
            }
          : { time_in_force: option ? "day" : "gtc" }),
      };
    }
    if (!q || !fresh(q, Date.now(), this.cfg.quoteAgeMs)) {
      if (!urgentExit(kind)) throw Error("Fresh quote required for profit exit");
      if (option) throw Error("Fresh OPRA bid required for option close");
      return { ...base, type: "market" };
    }
    if (
      kind === "stop" ||
      kind === "time" ||
      kind === "expiry" ||
      kind === "stagnation" ||
      kind === "signal" ||
      kind === "flatten"
    ) {
      if (!option) return { ...base, type: "market" };
    }
    return {
      ...base,
      type: "limit",
      limit_price: price(
        Math.max(
          q.bid * (1 - this.cfg.slippageBps / 10000),
          kind === c.exitPlan?.kind ? c.exitPlan.minimumPrice || 0 : 0,
        ),
        i.tick,
        !!c.exitPlan?.minimumPrice,
      ),
    };
  }
  nativeEnabled(c: Campaign) {
    const rejected = this.state.intents.find(
      (i) =>
        i.campaign === c.id &&
        i.status === "rejected" &&
        (i.payload.order_class === "oco" || i.payload.type === "trailing_stop"),
    );
    if (rejected && !c.nativeDisabledReason) {
      c.nativeDisabledReason =
        rejected.error || "Native group rejected by broker";
      // One deterministic fallback to a simpler stop is a different order form.
      // Its own definitive rejection re-enters the persisted cooldown.
      if (c.orderRetry?.protect) delete c.orderRetry.protect;
      this.event("NATIVE_FALLBACK", {
        symbol: c.symbol,
        reason: c.nativeDisabledReason,
      });
    }
    return (
      ["equity", "etf"].includes(c.book) &&
      !!this.cfg.nativeProtection &&
      this.cfg.nativeProtection !== "stop" &&
      !c.nativeDisabledReason
    );
  }
  async cancelProtections(c: Campaign) {
    const pending = this.pending(c).filter((i) => i.kind === "protect");
    const roots = pending.filter((i) => !i.parentId),
      rootIds = new Set(roots.map((i) => i.id));
    for (const i of [
      ...roots,
      ...pending.filter((i) => i.parentId && !rootIds.has(i.parentId)),
    ]) {
      await this.cancel(i);
      if (!this.syncAt) break;
    }
    if (c.exitPlan) c.exitPlan.status = "CANCELING";
  }
  pulse(): Promise<void> {
    if (this.pulseJob) return this.pulseJob;
    const work = (async () => {
      for (let step = 0; step < 8 && !this.stopping; step++) {
        if (!this.syncAt || Date.now() - this.syncAt > 10000)
          await this.reconcile();
        await this.manage();
        if (this.syncAt) break;
      }
    })();
    this.pulseJob = work.finally(() => {
      this.pulseJob = undefined;
    });
    return this.pulseJob;
  }
  /** Complete the observation pass for every campaign before issuing any broker mutation. */
  private evaluatePosition(c: Campaign, now: number) {
    const prior = this.positionEvaluations[c.id];
    const r: PositionEvaluation = {
      campaign: c.id, symbol: c.symbol, book: c.book,
      lastAttempt: now, lastCompleted: prior?.lastCompleted || 0,
      outcome: "STARTING", detail: "Evaluation started", quoteAt: this.market.quotes[c.symbol]?.at || 0,
      syncAt: this.syncAt,
    };
    this.positionEvaluations[c.id] = r;
    c.evaluation = r; // Durable diagnostics only; never restored as current-runtime coverage.
    delete this.exitErrors[c.id];
    try {
      this.observePartialEntryRisk(c, now);
      if (!this.syncAt || now - this.syncAt < 0 || now - this.syncAt > 10000) {
        r.outcome = "STALE_RECONCILIATION";
        r.detail = "Fresh reconciliation required";
        return;
      }
      if (!this.own(c)) {
        r.outcome = "OWNERSHIP_UNCERTAIN";
        r.detail = "Inventory, order identity or submission is unresolved";
        return;
      }
      const qty = floorStep(Number(this.position(c.symbol)?.qty || 0), c.instrument.step);
      this.validators.run("inventory", () => assertCampaignInventory(c, qty));
      if (qty <= 0) {
        r.outcome = this.pending(c).length ? "PENDING_ENTRY" : "NO_INVENTORY";
        r.lastCompleted = Date.now();
        r.detail = "Inventory and pending orders evaluated";
        return;
      }
      if (!this.session(c.book)) {
        r.outcome = now - this.clockAt > 45000 || now < this.clockAt ? "STALE_SESSION" : "MARKET_CLOSED";
        r.detail = r.outcome === "MARKET_CLOSED" ? "Session closed; quote-based exits not evaluated" : "Broker session clock is stale";
        return;
      }
      const q = this.market.quotes[c.symbol], quoteFresh = fresh(q, now, this.cfg.quoteAgeMs);
      sampleProtection(c, this.state.intents, qty, quoteFresh ? q : undefined, now);
      if (quoteFresh) {
        observeExit(c, q, now, this.market.calendar, this.plugins.legacy);
        this.plugins.manageSignal(c, this.market, now, fills(c, this.state.intents).entry);
      }
      const observed = exitDecision(c, this.state.intents, q, qty, now, this.cfg);
      if (!this.nativeEnabled(c) || (observed && urgentExit(observed.kind)))
        rememberExit(c, this.state.intents, observed, q, this.cfg, now);
      if (c.exitPlan) this.validators.run("exit-plan", () => assertExitPlan(c));
      r.outcome = quoteFresh ? "EVALUATED" : "STALE_DATA";
      r.detail = quoteFresh ? "Exit rules evaluated with owned inventory and fresh data" : "Quote-based exits incomplete; non-price urgent exits remain eligible";
      if (quoteFresh) r.lastCompleted = Date.now();
    } catch (e) {
      r.outcome = "ERROR";
      r.detail = String(e);
      this.exitErrors[c.id] = { at: Date.now(), symbol: c.symbol, error: String(e) };
      this.event("EXIT_ERROR", { symbol: c.symbol, error: String(e) });
    } finally {
      this.validators.run("position-evaluation", () => assertPositionEvaluation(r, Date.now()));
    }
  }
  exitCoverage(now = Date.now()) {
    const positions = this.active().map((c) => {
      const r = this.positionEvaluations[c.id];
      const partialEntryRisk = this.partialEntryRiskSnapshot(c, now);
      const ageMs = r?.lastCompleted ? now - r.lastCompleted : null;
      const qty = Number(this.position(c.symbol)?.qty || 0);
      const retry = Object.values(c.orderRetry || {}).find((x) => x.nextAt > now);
      const sessionGated = r?.outcome === "MARKET_CLOSED" && now >= r.lastAttempt && now - r.lastAttempt <= this.evaluationDeadlineMs &&
        this.clock.is_open === false && now >= this.clockAt && now - this.clockAt <= 45000 &&
        qty > 0 && protectionSnapshot(c, this.state.intents, qty, now).aligned &&
        !this.pending(c).some((i) => i.kind !== "protect") && !retry;
      let state = "ALIVE", detail = r?.detail || "No completed evaluation in this runtime";
      if (this.exitErrors[c.id] || r?.outcome === "ERROR") {
        state = "ERROR"; detail = this.exitErrors[c.id]?.error || detail;
      } else if (!r) state = "WAITING";
      else if (!this.syncAt || now - this.syncAt > 10000 || now < this.syncAt) {
        state = "WAITING"; detail = "Fresh broker reconciliation required";
      } else if (!this.own(c)) {
        state = "DEGRADED"; detail = "Inventory or uncertain order unresolved";
      } else if (["STALE_DATA", "STALE_SESSION", "STALE_RECONCILIATION"].includes(r.outcome)) state = "STALE";
      else if (r.outcome === "MARKET_CLOSED") {
        state = sessionGated ? "MARKET_CLOSED" : "WAITING";
        detail = sessionGated ? "Closed session verified; aligned native protection confirmed; price exits await reopening" : "Closed-session safety requires a fresh clock and aligned protection";
      }
      else if (ageMs === null || r.lastCompleted < r.lastAttempt) state = "WAITING";
      else if (ageMs < 0 || ageMs > this.evaluationDeadlineMs) state = "STALE";
      else if (qty > 0 && this.session(c.book) && !fresh(this.market.quotes[c.symbol], now, this.cfg.quoteAgeMs)) {
        state = "STALE"; detail = "Position quote is now stale";
      } else if (qty > 0 && c.book !== "crypto" && (now - this.clockAt > 45000 || now < this.clockAt)) {
        state = "STALE"; detail = "Broker session clock is now stale";
      } else if (retry) {
        state = "DEGRADED"; detail = "Definitive rejection retry cooldown until " + new Date(retry.nextAt).toISOString();
      } else if (qty > 0 && !protectionSnapshot(c, this.state.intents, qty, now).aligned) {
        state = "DEGRADED"; detail = "Native protection does not cover and align with all inventory";
      } else if (this.pending(c).some((i) => i.kind !== "protect")) {
        state = "DEGRADED"; detail = "Entry or exit order still pending confirmation";
      }
      if (partialEntryRisk && partialEntryRisk.status !== "RESOLVED") {
        if (state === "ALIVE" || state === "MARKET_CLOSED") state = "DEGRADED";
        detail += "; PARTIAL_ENTRY_UNPROTECTED " + partialEntryRisk.status +
          (partialEntryRisk.overdue ? " OVERDUE" : "") + "; deadline=" + partialEntryRisk.deadlineAt;
      }
      return { campaign: c.id, symbol: c.symbol, book: c.book,
        lastAttempt: r?.lastAttempt || 0, lastCompleted: r?.lastCompleted || 0,
        ageMs, outcome: r?.outcome || "NOT_EVALUATED", detail, state,
        entrySafe: state === "ALIVE" || state === "MARKET_CLOSED",
        quoteAt: r?.quoteAt || 0, syncAt: r?.syncAt || 0, partialEntryRisk };
    });
    const completed = positions.filter((p) => ["EVALUATED", "NO_INVENTORY", "PENDING_ENTRY"].includes(p.outcome) && p.lastCompleted >= p.lastAttempt && p.lastCompleted > 0).length;
    const freshCount = positions.filter((p) => p.state === "ALIVE").length;
    const state = positions.some((p) => p.state === "ERROR") ? "ERROR"
      : positions.some((p) => p.state === "STALE") ? "STALE"
      : positions.some((p) => p.state === "DEGRADED") ? "DEGRADED"
      : positions.some((p) => ["WAITING", "MARKET_CLOSED"].includes(p.state)) ? "WAITING"
      : !this.syncAt || now - this.syncAt > 10000 || now < this.syncAt ? "WAITING" : "ALIVE";
    const entrySafe = !!this.syncAt && now >= this.syncAt && now - this.syncAt <= 10000 && positions.every((p) => p.entrySafe);
    return { state, entrySafe, sessionGated: positions.filter((p) => p.state === "MARKET_CLOSED").length,
      total: positions.length, completed, fresh: freshCount,
      deadlineMs: this.evaluationDeadlineMs,
      lastCompletedAt: completed === positions.length && positions.length ? Math.min(...positions.map((p) => p.lastCompleted)) : 0,
      positions, detail: positions.length ? freshCount + "/" + positions.length + " positions evaluated, current and fully protected" +
        (positions.some((p) => p.state !== "ALIVE") ? "; " + positions.filter((p) => p.state !== "ALIVE").map((p) => p.symbol + ": " + p.detail).join("; ") : "") : "No active campaigns; broker reconciliation still required" };
  }
  private validateCoverage() {
    try {
      this.validators.run("position-coverage", () => assertOperationalCoverage(this.exitCoverage()));
    } catch (e) {
      // Expected fail-closed gate; individual blocked campaigns must not stop other exits.
      if (!(e instanceof Error)) throw e;
    }
  }
  async manage() {
    return this.mutex.run(0, async () => {
      await this.authority();
      const scanAt = Date.now(), active = this.active();
      for (const c of active) this.evaluatePosition(c, Date.now());
      await this.save();
      if (active.every((c) => ["EVALUATED", "NO_INVENTORY", "PENDING_ENTRY"].includes(this.positionEvaluations[c.id]?.outcome) && this.positionEvaluations[c.id]?.lastCompleted >= scanAt))
        this.exitCheckAt = Date.now();
      this.validateCoverage();
      if (!this.syncAt || Date.now() - this.syncAt > 10000) return;
      // Round-robin within priority classes; urgent exits are observed globally first.
      const last = active.findIndex((c) => c.id === this.lastActionCampaign);
      const rotated = last < 0 ? active : [...active.slice(last + 1), ...active.slice(0, last + 1)];
      const priority = (c: Campaign) => c.exitPlan && c.exitPlan.status !== "COMPLETE" && urgentExit(c.exitPlan.kind) ? 0 : c.exitPlan && c.exitPlan.status !== "COMPLETE" ? 1 : 2;
      const candidates = rotated.sort((a, b) => priority(a) - priority(b));
      for (const c of candidates) {
        const outcome = this.positionEvaluations[c.id].outcome;
        if (["ERROR", "STALE_RECONCILIATION", "OWNERSHIP_UNCERTAIN", "STALE_SESSION"].includes(outcome)) continue;
        // Session closure gates new sale/protection orders, not cancellation
        // of a known remaining entry. evaluatePosition has already verified
        // fresh ownership; managePosition's entry branch can only cancel and
        // returns before every sale or protection path. Cancellation remains
        // pending until the next broker reconciliation confirms the result.
        if (outcome === "MARKET_CLOSED" && !this.pending(c).some(i => i.kind === "entry")) continue;
        try { await this.managePosition(c); }
        catch (e) {
          this.exitErrors[c.id] = { at: Date.now(), symbol: c.symbol, error: String(e) };
          this.positionEvaluations[c.id].outcome = "ERROR";
          this.positionEvaluations[c.id].detail = String(e);
          this.event("EXIT_ERROR", { symbol: c.symbol, error: String(e) });
        }
        if (!this.syncAt) { this.lastActionCampaign = c.id; break; }
      }
      await this.save();
      this.validateCoverage();
    });
  }
  private async managePosition(c: Campaign) {
    const pending = this.pending(c),
      entry = pending.find((i) => i.kind === "entry");
    if (entry) {
      if (
        this.state.paused ||
        this.state.halt ||
        Date.now() - entry.at >= this.cfg.orderTtlMs ||
        Number(entry.order?.filled_qty) > 0
      )
        await this.cancel(entry);
      if (!this.syncAt) return;
      return;
    }
    if (!this.own(c)) {
      this.event("POSITION_WAIT", {
        symbol: c.symbol,
        reason: "OWNERSHIP_OR_RECONCILIATION",
      });
      return;
    }
    const qty = floorStep(
      Number(this.position(c.symbol)?.qty || 0),
      c.instrument.step,
    );
    this.validators.run("inventory", () =>
      assertCampaignInventory(c, qty),
    );
    if (qty <= 0) {
      for (const i of pending) await this.cancel(i);
      return;
    }
    if (!this.session(c.book)) return;
    const q = this.market.quotes[c.symbol];
    const native = this.nativeEnabled(c);
    const decision = remainingExit(c, this.state.intents, qty),
      sell = pending.find((i) => i.kind !== "protect");
    if (sell) {
      if (
        (decision &&
          urgentExit(decision.kind) &&
          !urgentExit(sell.kind)) ||
        Date.now() - sell.at >= this.cfg.orderTtlMs
      )
        await this.cancel(sell);
      await this.save();
      if (!this.syncAt) return;
      const free = floorStep(
        Math.max(
          0,
          qty -
            (Number(sell.order?.qty || sell.payload.qty) -
              Number(sell.order?.filled_qty || 0)),
        ),
        c.instrument.step,
      );
      if (
        !pending.some((i) => i.kind === "protect") &&
        free >= c.instrument.minQty &&
        fresh(q, Date.now(), this.cfg.quoteAgeMs) &&
        c.stop < q.bid
      ) {
        await this.submit(
          c,
          "protect",
          this.payload(c, "protect", free, q),
        );
        return;
      }
      return;
    }
    const protections = pending.filter((i) => i.kind === "protect"),
      protect = protections.find((i) => !i.parentId) || protections[0];
    await this.save();
    if (decision) {
      if (protections.length) {
        await this.cancelProtections(c);
        return;
      }
      if (c.exitPlan) c.exitPlan.status = "READY";
      await this.submit(
        c,
        decision.kind,
        this.payload(c, decision.kind, Math.min(qty, decision.qty), q),
      );
      return;
    }
    if (
      native &&
      fresh(q, Date.now(), this.cfg.quoteAgeMs) &&
      c.stop < q.bid
    ) {
      const groups = nativeGroups(
          c,
          this.state.intents,
          qty,
          this.cfg,
          q,
        ),
        roots = protections.filter((i) => !i.parentId);
      const invalid = roots.some(
        (i) =>
          !groups.some(
            (g) =>
              g.role === i.nativeRole &&
              Math.abs(
                g.qty -
                  (Number(i.order?.qty || i.payload.qty) -
                    Number(i.order?.filled_qty || 0)),
              ) <
                c.instrument.step * 1e-6,
          ),
      );
      const coverage = protectionSnapshot(
        c,
        this.state.intents,
        qty,
        Date.now(),
      );
      const drift = protections.some(
        (i) =>
          ["stop", "stop_limit", "trailing_stop"].includes(
            i.order?.type || i.payload.type,
          ) &&
          Number(i.order?.stop_price || i.payload.stop_price) +
            c.instrument.tick * 1e-6 <
            Number(price(c.stop, c.instrument.tick)),
      );
      if (
        (invalid || drift) &&
        Date.now() - (c.protectionChangedAt || 0) >=
          (this.cfg.protectionRefreshMs || 5000)
      ) {
        await this.cancelProtections(c);
        c.protectionChangedAt = Date.now();
        return;
      }
      if (invalid || drift) return;
      const next = groups.find(
        (g) => !roots.some((i) => i.nativeRole === g.role),
      );
      if (next) {
        const base = {
          symbol: c.symbol,
          qty: String(next.qty),
          side: "sell",
          time_in_force: "gtc",
        };
        let payload: Json;
        if (next.type === "oco") {
          const target = price(next.target!, c.instrument.tick, true);
          payload = {
            ...base,
            type: "limit",
            order_class: "oco",
            limit_price: target,
            take_profit: { limit_price: target },
            stop_loss: { stop_price: price(c.stop, c.instrument.tick) },
          };
        } else if (next.type === "trailing_stop")
          payload = {
            ...base,
            type: "trailing_stop",
            trail_price: price(next.trail!, c.instrument.tick),
          };
        else
          payload = {
            ...base,
            type: "stop",
            stop_price: price(c.stop, c.instrument.tick),
          };
        await this.submit(c, "protect", payload, {
          nativeRole: next.role,
        });
        return;
      }
      if (!coverage.quantityCovered)
        this.exitErrors[c.id] = {
          at: Date.now(),
          symbol: c.symbol,
          error:
            "Native stop legs not yet confirmed for full inventory",
        };
      return;
    }
    if (protect) {
      const needsUpdate =
        protections.length !== 1 ||
        !!protect.parentId ||
        Number(protect.order?.qty || protect.payload.qty) -
          Number(protect.order?.filled_qty || 0) !==
          qty ||
        Number(price(c.stop, c.instrument.tick)) >
          Number(
            protect.order?.stop_price || protect.payload.stop_price,
          ) +
            c.instrument.tick * 1e-6;
      if (
        needsUpdate &&
        Date.now() - (c.protectionChangedAt || 0) >=
          (this.cfg.protectionRefreshMs || 5000)
      ) {
        await this.cancelProtections(c);
        c.protectionChangedAt = Date.now();
      }
      if (!this.syncAt) return;
      return;
    }
    if (
      fresh(q, Date.now(), this.cfg.quoteAgeMs) &&
      c.stop < q.bid &&
      qty >= c.instrument.minQty
    ) {
      await this.submit(
        c,
        "protect",
        this.payload(c, "protect", qty, q),
      );
      return;
    }
  }
  entryReady() {
    const heartbeat = this.scheduler.lanes.find(
      (l) => l.name === "positions-and-take-profit",
    );
    const guardianReady =
      !this.autopilotStartedAt ||
      (!!heartbeat &&
        !heartbeat.error &&
        heartbeat.lastSuccess > 0 &&
        Date.now() - heartbeat.lastSuccess < 4000);
    return (
      guardianReady &&
      this.exitCoverage().entrySafe &&
      !this.stopping &&
      !this.state.paused &&
      !this.state.halt &&
      !this.storageError &&
      !this.reconcileError &&
      Date.now() - this.syncAt < 10000 &&
      this.account.status === "ACTIVE" &&
      !this.account.trading_blocked &&
      !this.account.account_blocked &&
      !this.account.trade_suspended_by_user &&
      !this.pending().some((i) => i.kind !== "protect")
    );
  }
  async discoverStocks() {
    const at = Date.now(), context = sessionContext(at, this.market.calendar);
    if (!this.cfg.quant?.enabled || !this.cfg.quant.discovery) return;
    if (!this.session("equity", true)) {
      this.quantDiscovery = {...this.quantDiscovery, health: "WAITING",
        reason: "Fuera de la ventana autorizada de nuevas entradas",
        attempt_at: at, session_context: context};
      return;
    }
    this.discoveryHold = true;
    let result: Json;
    try {
      result = await require("../runtime/quant_bridge.cjs").discover(this);
      this.quantDiscovery = {...result, session_context: context, persisted: false};
      if (typeof result.snapshot_id !== "string" || !/^[a-f0-9]{64}$/.test(result.snapshot_id))
        throw Error("DISCOVERY_SNAPSHOT_ID_REQUIRED");
      if (digest(result.snapshot) !== result.snapshot_id)
        throw Error("DISCOVERY_SNAPSHOT_HASH_MISMATCH");
      const snapshotKey = this.key + "-discovery-snapshot-" + result.snapshot_id;
      const existing = await this.store.get(snapshotKey);
      const record: Json = {...result, session_context: context, accountId: this.cfg.expected_account_id};
      if (existing && (digest(existing.snapshot) !== digest(record.snapshot) || existing.accountId !== record.accountId))
        throw Error("DISCOVERY_SNAPSHOT_IMMUTABILITY");
      if (!existing) await this.store.put(snapshotKey, record);
      if (result.registry) {
        const baseConfigHash = await this.store.get(this.key + "-config");
        await this.store.put(this.key + "-discovery-registry", {
          accountId: this.cfg.expected_account_id, baseConfigHash, registry: result.registry,
        });
      }
      await this.store.put(this.key + "-discovery-latest", {
        snapshot_id: result.snapshot_id, at: result.at, health: result.health,
      });
      this.quantDiscovery.persisted = true;
      this.event("QUANT_STOCK_NET", this.quantDiscovery);
    } catch (error) {
      this.quantDiscovery = {...this.quantDiscovery, status: "BLOCKED", health: "BLOCKED",
        reason: String(error), attempt_at: at, persisted: false, session_context: context};
      this.event("QUANT_STOCK_NET", this.quantDiscovery);
      throw error;
    }
    // A completed, durably recorded discovery cannot freeze other asset engines.
    // Candidate-specific failures remain excluded by readiness and entry gates.
    this.discoveryHold = false;
    if (result.health === "BLOCKED" || result.health === "DEGRADED")
      throw Error("DISCOVERY_" + result.health + ": " + result.reason);
  }
  async refreshNetAccounting() {
    try {
      await this.netLedger.refresh({instruments: {...Object.fromEntries(this.cfg.universe.map(i => [i.symbol, i])), ...this.market.assets}});
      this.netAccountingError = "";
    } catch (error) { this.netAccountingError = String(error); throw error; }
  }
  async captureQuantObservations() {
    try {
      await require("../runtime/quant_bridge.cjs").observe(this);
      this.quantObservationError = "";
    } catch (error) { this.quantObservationError = String(error); throw error; }
  }
  async entries(book: Book) {
    const operationalFailures = entryOperationalFailures(this);
    if (operationalFailures.length) {
      this.event("ENTRY_GATE", {book, reason: "OPERATIONAL_VALIDATORS", failures: operationalFailures});
      return;
    }
    if (this.discoveryHold) {
      this.event("ENTRY_GATE", {book, reason: "DISCOVERY_OR_PERSISTENCE_UNRESOLVED"});
      return;
    }
    if (!this.session(book, true)) return;
    const decisionAt = Date.now();
    const decisionId = this.decisionRunId + ":" + (++this.decisionSequence);
    let signals = this.plugins.evaluate(
      book,
      this.market,
      this.state.plugins,
    );
    let quantPlan: Json | null = null;
    let quantDecisionRecord: Json | null = null;
    const quantState = () => JSON.stringify([
      this.account.equity, this.account.cash, this.account.buying_power,
      this.positions, this.pending(), this.active().map(c => [c.id, c.symbol, c.closed]),
      this.state.dayEquity, this.state.peakEquity, this.cfg.universe, this.discoveryHold,
    ]);
    const quantSnapshot = this.cfg.quant?.enabled ? quantState() : null;
    if (this.cfg.quant?.enabled) {
      // Run numerical work outside the order mutex: exits retain priority.
      // One joint snapshot includes every book's currently eligible signals.
      const all = ["equity", "etf", "crypto", "options"].flatMap((b) =>
        this.session(b as Book, true) ? this.plugins.evaluate(b as Book, this.market, this.state.plugins) : []);
      const opportunitySnapshot = all.map(s => ({id: s.plugin + "|" + s.symbol,
        symbol: s.symbol, book: s.book, at: s.at, expires: s.expires,
        quote: structuredClone(this.market.quotes[s.symbol] || null)}));
      quantPlan = await require("../runtime/quant_bridge.cjs").plan(this, all);
      this.quantLastPlan = {status: quantPlan?.status || "UNCLASSIFIED", reason: quantPlan?.reason || null,
        completed_at: Date.now(), model_hash: quantPlan?.model_hash || null,
        engine: quantPlan?.engine || null, origin: quantPlan?.decision_inputs?.origin || null,
        research_only: quantPlan?.research_only === true,
        execution_allowed: quantPlan?.execution_allowed === true};
      const decisionRecord: Json = { reason: quantPlan?.reason, execution_allowed: quantPlan?.execution_allowed === true,
        selected: quantPlan?.selected || [], rejected: quantPlan?.rejected || {},
        engine: quantPlan?.engine ?? null, forecast_model_kind: quantPlan?.forecast_model_kind ?? null,
        research_only: quantPlan?.research_only === true,
        model_hash: quantPlan?.model_hash, config_hash: quantPlan?.config_hash,
        decision_id: decisionId, decision_at: decisionAt, completed_at: Date.now(),
        session_context: sessionContext(decisionAt, this.market.calendar),
        discovery_snapshot_id: this.quantDiscovery.snapshot_id || null,
        account_id: this.cfg.expected_account_id, requested_book: book,
        decision_inputs: quantPlan?.decision_inputs || null,
        opportunities: opportunitySnapshot};
      quantDecisionRecord = decisionRecord;
      // Persist signal-bearing decisions before any external order; no full history duplication.
      if (all.length) {
        try { await this.store.put(this.key + "-quant-decision-" + decisionId, decisionRecord); }
        catch (error) {
          this.event("QUANT_TRACE_BLOCKED", {decision_id: decisionId, reason: String(error)});
          throw error;
        }
      }
      this.event("QUANT_PLAN", decisionRecord);
      const chosen = quantPlan?.execution_allowed === true ? quantPlan.selected as Json[] : [];
      signals = signals.filter((s) => chosen.some((x) => x.id === s.plugin + "|" + s.symbol))
        .sort((a,b) => Number(chosen.find((x) => x.id === b.plugin + "|" + b.symbol)?.robust_net_usd || 0) -
          Number(chosen.find((x) => x.id === a.plugin + "|" + a.symbol)?.robust_net_usd || 0));
    }
    return this.mutex.run(2, async () => {
      const failures = entryOperationalFailures(this);
      if (failures.length) {
        this.event("ENTRY_GATE", {book, decision_id: decisionId, reason: "OPERATIONAL_VALIDATORS", failures});
        return;
      }
      if (this.discoveryHold) {
        this.event("ENTRY_GATE", {book, decision_id: decisionId, reason: "DISCOVERY_OR_PERSISTENCE_UNRESOLVED"});
        return;
      }
      await this.authority();
      if (quantSnapshot !== null && quantSnapshot !== quantState()) {
        this.event("QUANT_PLAN_INVALIDATED", { reason: "ACCOUNT_OR_INVENTORY_CHANGED" });
        return;
      }
      if (!this.entryReady()) return;
      // Protect every filled position before allocating another dollar.
      if (
        this.active().some(
          (c) =>
            Number(this.position(c.symbol)?.qty) > 0 &&
            !protectionSnapshot(
              c,
              this.state.intents,
              Number(this.position(c.symbol)?.qty || 0),
              Date.now(),
            ).aligned,
        )
      )
        return;
      for (let signal of signals) {
        if (
          !this.entryReady() ||
          !this.session(book, true) ||
          signal.expires < Date.now() ||
          !this.state.plugins.includes(signal.plugin)
        )
          return;
        if (this.active().some((c) => c.symbol === signal.symbol)) continue;
        const q = this.market.quotes[signal.symbol],
          asset = this.market.assets[signal.symbol];
        if (
          !asset ||
          !fresh(q, Date.now(), this.cfg.quoteAgeMs) ||
          q.ask > signal.entry
        )
          continue;
        signal = {
          ...signal,
          entry: Number(price(signal.entry, asset.tick, true)),
          stop: Number(price(signal.stop, asset.tick)),
        };
        const profileId = this.state.exitProfile || "BASELINE_30_1";
        let exitRegime = "BASELINE";
        try {
          const selected = require("../runtime/exit_profiles32.cjs").profile(
            signal.exit,
            profileId,
            signal.exitObservation || signal.reentryFeature || {},
          );
          signal = { ...signal, exit: selected.policy };
          exitRegime = selected.regime;
        } catch (e) {
          this.event("EXIT_PROFILE_GATE", {
            symbol: signal.symbol,
            profile: profileId,
            error: String(e),
          });
          continue;
        }
        if (signal.stop <= 0 || signal.stop >= signal.entry) continue;
        this.validators.run("signal", () => assertSignal(signal, asset));
        if (
          book === "options" &&
          !(Number(this.account.options_trading_level) >= 2)
        )
          continue;
        const history = this.state.campaigns.filter(
          (c) =>
            c.symbol === signal.symbol &&
            this.plugins.legacy.ny(c.created).day === this.state.day &&
            fills(c, this.state.intents).bought > 0,
        );
        if (history.length) {
          const reason = signal.reentryFeature
            ? this.plugins.legacy.HX.reentry(
                signal.reentryFeature,
                history.map((c) => ({
                  ...c,
                  closed_at: c.closedAt
                    ? new Date(c.closedAt).toISOString()
                    : "",
                })),
                Date.now(),
                signal.exit.reentry === true,
              )
            : "REENTRY_NOT_AVAILABLE";
          if (reason) {
            this.event("ENTRY_GATE", { symbol: signal.symbol, reason });
            continue;
          }
        }
        let qty = availableSize(
          signal,
          asset,
          this.cfg,
          this.account,
          this.positions,
          this.state.campaigns,
          this.state.intents,
        );
        if (this.cfg.quant?.enabled) {
          const item = quantPlan?.selected?.find((x: Json) => x.id === signal.plugin + "|" + signal.symbol);
          qty = floorStep(Math.min(qty, Number(item?.quantity || 0)), asset.step);
        }
        if (!qty) continue;
        const c: Campaign = {
          id: "c" + (this.state.sequence + 1) + "-" + Date.now(),
          symbol: signal.symbol,
          book,
          plugin: signal.plugin,
          created: Date.now(),
          instrument: structuredClone(asset),
          policy: structuredClone(signal.exit),
          risk: signal.entry - signal.stop,
          peak: signal.entry,
          stop: signal.stop,
          closed: false,
          intents: [],
          entryCeiling: signal.entry,
          entryAtr: signal.entryAtr,
          exitProfile: profileId,
          exitRegime,
          deadline: deadlineFor(
            book,
            Date.now(),
            signal.exit.maxHoldHours,
            this.market.calendar,
            asset.expiry,
          ),
        };
        // Attribution is evidence only. Preserve the actual decision before
        // submit() persists its intent and performs the existing order call.
        // No permission, quantity, price or risk policy is changed here.
        const calibrationAt = typeof quantPlan?.decision_inputs?.calibration_available_at === "string"
          ? Date.parse(quantPlan.decision_inputs.calibration_available_at) : NaN;
        const decisionBinding: Json = {
          decision_id: decisionId, decision_at: decisionAt, known_at: Date.now(),
          account_id: this.cfg.expected_account_id, execution_nature: this.cfg.mode.toUpperCase(),
          candidate_role: !this.cfg.quant?.enabled ? "NATIVE"
            : quantPlan?.forecast_model_kind === "SVR_RBF" ? "SVR"
              : quantPlan?.engine === "HARPOON_QUANT_1" && quantPlan?.research_only !== true ? "RIDGE" : null,
          runtime_version: ULTIMATE_VERSION, runtime_config_hash: digest(this.cfg),
          quant_config_hash: typeof quantPlan?.config_hash === "string" ? quantPlan.config_hash : null,
          model_hash: typeof quantPlan?.model_hash === "string" ? quantPlan.model_hash : null,
          model_available_at: Number.isFinite(calibrationAt) ? calibrationAt : null,
          signal_id: signal.plugin + "|" + signal.symbol, signal_at: signal.at,
          signal_expires: signal.expires, symbol: signal.symbol, book, plugin: signal.plugin,
          planned_quantity: qty,
          quant_receipt_hash: quantDecisionRecord ? digest(quantDecisionRecord) : null,
        };
        const provenance: Json = { schema: "HARPOON_FORWARD_CAMPAIGN_PROVENANCE_1",
          campaign_id: c.id, decision: decisionBinding,
          quant_receipt: quantDecisionRecord ? structuredClone(quantDecisionRecord) : null };
        c.forwardProvenance = { ...provenance, integrity: digest(provenance) };
        this.state.campaigns.push(c);
        this.event("ENTRY_SIGNAL", {
          symbol: c.symbol,
          plugin: c.plugin,
          reason: signal.reason,
        });
        await this.submit(c, "entry", {
          symbol: c.symbol,
          qty: String(qty),
          side: "buy",
          type: "limit",
          limit_price: price(signal.entry, asset.tick, true),
          time_in_force: book === "crypto" ? "gtc" : "day",
          ...(book === "options" ? { position_intent: "buy_to_open" } : {}),
        });
        return;
      }
    });
  }
  async control(action: string, body: Json = {}) {
    return this.mutex.run(0, async () => {
      switch (action) {
        case "pause":
          this.state.paused = true;
          break;
        case "resume":
          if (
            this.reconcileError ||
            Date.now() - this.syncAt > 10000 ||
            this.storageError ||
            this.state.halt
          )
            throw Error("Reconciliation/risk gate prevents resume");
          this.state.paused = false;
          break;
        case "flatten":
          this.state.paused = true;
          for (const c of this.active()) c.flatten = true;
          break;
        case "plugins":
          this.plugins.validateSelection(body.enabled);
          this.state.plugins = [...body.enabled];
          break;
        case "exit-profile": {
          const ids = require("../runtime/exit_profiles32.cjs").IDS;
          if (!ids.includes(body.profile)) throw Error("Unknown exit profile");
          if (
            body.profile !== "BASELINE_30_1" &&
            body.confirmation !== "EXPERIMENTAL_PAPER_ONLY"
          )
            throw Error("Experimental policy acknowledgement required");
          this.state.exitProfile = body.profile;
          break;
        }
        case "selector-register":
          await this.selectors.register(body.book, body.costs);
          break;
        case "selector-install":
          await this.selectors.install(body.trialId, body.confirmation);
          this.plugins.selectors = this.selectors.state.models;
          break;
        case "selector-revoke":
          await this.selectors.revoke(body.book);
          this.plugins.selectors = this.selectors.state.models;
          break;
        case "selector-retire":
          await this.selectors.retire(body.trialId);
          this.plugins.selectors = this.selectors.state.models;
          break;
        case "research-pause":
          if (typeof body.paused !== "boolean") throw Error("Boolean required");
          this.state.researchPaused = body.paused;
          break;
        default:
          throw Error("Unknown action");
      }
      this.event("CONTROL", { action });
      await this.save();
      return this.view();
    });
  }
  async queueResearch(input: Json) {
    let prepared: Json | null = null;
    if (input.operation === "selector") {
      await this.mutex.run(2, async () => {
        if (
          this.preparingResearch ||
          this.pendingResearch ||
          this.state.research.status === "RUNNING"
        )
          throw Error("Research busy");
        if (this.state.research.runs >= this.cfg.researchMaxRuns)
          throw Error("Research budget exhausted");
        this.preparingResearch = true;
      });
      try {
        prepared = await this.selectors.prepare(
          input.trialId,
          input.diagnostic === true,
        );
      } catch (e) {
        this.preparingResearch = false;
        throw e;
      }
    }
    try {
      return await this.mutex.run(2, async () => {
        if (
          (this.preparingResearch && !prepared) ||
          this.pendingResearch ||
          this.state.research.status === "RUNNING"
        )
          throw Error("Research busy");
        if (this.state.research.runs >= this.cfg.researchMaxRuns)
          throw Error("Research budget exhausted");
        const request: Json = prepared || structuredClone(input);
        if (!["optimize", "selector"].includes(request.operation)) {
          const W = this.plugins.legacy.HWarRoom3,
            cp = W.protocol(request.protocol);
          if (
            cp.end > Date.now() ||
            (request.asof || Date.now()) > Date.now() + 2000
          )
            throw Error("Future research observations are forbidden");
          const seal = createHash("sha256")
            .update(JSON.stringify({ protocol: cp, data: request.data }))
            .digest("hex");
          request.protocol = cp;
          request.internalSeal = seal;
          const reserve = this.key + "-holdout-" + cp.start + "-" + cp.end;
          if (await this.store.get(reserve))
            throw Error(
              "Holdout already consumed; new untouched window required",
            );
          if (request.stage === "holdout") {
            const train = await this.store.get(this.key + "-training");
            if (
              !train ||
              train.seal !== seal ||
              train.result.status !== "READY_TO_LOCK"
            )
              throw Error(
                "Holdout requires matching internally computed training result",
              );
            request.lock = {
              selected: train.result.selected,
              source: train.result.source,
              protocolId: cp.id,
              states: train.result.states,
              stressStates: train.result.stressStates,
              trialSharpes: train.result.trialSharpes,
              models: train.result.models,
            };
            request.internalTraining = train.result;
            await this.store.put(reserve, { at: Date.now(), seal });
          }
        }
        this.pendingResearch = request;
        this.state.research.status = "QUEUED";
        await this.save();
      });
    } finally {
      if (prepared) this.preparingResearch = false;
    }
  }
  async research() {
    if (this.state.researchPaused || !this.pendingResearch) return;
    const input = this.pendingResearch;
    this.pendingResearch = null;
    if (this.state.research.runs >= this.cfg.researchMaxRuns) {
      this.state.research.status = "BUDGET_EXHAUSTED";
      await this.save();
      return;
    }
    this.state.research.runs++;
    this.state.research.status = "RUNNING";
    await this.save();
    try {
      if (input.operation === "selector")
        await this.selectors.started(input.trialId);
      const result = await require("../runtime/warroom3.cjs").worker(input);
      await this.store.put(
        this.key + "-research-" + this.state.research.runs,
        result,
      );
      if (input.operation === "selector")
        await this.selectors.completed(input.trialId, result);
      if (
        !["optimize", "selector"].includes(input.operation) &&
        result.stage === "train"
      )
        await this.store.put(this.key + "-training", {
          seal: input.internalSeal,
          result,
        });
      if (
        !["optimize", "selector"].includes(input.operation) &&
        result.stage === "holdout" &&
        input.internalTraining
      ) {
        const combined = this.plugins.legacy.HWarRoom3.combine(
          input.internalTraining,
          result,
          input.protocol,
        );
        await this.store.put(
          this.key + "-combined-" + this.state.research.runs,
          combined,
        );
        if (
          combined.status === "ACCEPTED_FOR_PAPER" &&
          combined.source !== "SYNTHETIC_TEST"
        ) {
          const id = result.selected,
            model = input.lock.models[id];
          if (
            model?.executionValidated === true &&
            model.fitThrough <= input.protocol.holdoutStart
          ) {
            this.plugins.models[id] = {
              model,
              config: input.protocol.strategy,
              minLabels: input.protocol.policy.minLabels,
              validUntil: input.protocol.end + 30 * 86400000,
              source: result.source,
              seal: input.internalSeal,
            };
            await this.store.put(
              this.key + "-economic-models",
              this.plugins.models,
            );
            this.event("ECONOMIC_MODEL_AVAILABLE", {
              recipe: id,
              scope: "PAPER_ONLY_NEW_XXX_EXITS_REQUIRE_PROSPECTIVE_VALIDATION",
            });
          }
        }
      }
      this.state.research.status = "COMPLETE";
      this.state.research.result = {
        status: result.report?.status || result.status,
        source: result.source,
        selected: result.selected,
      };
    } catch (e) {
      if (input.operation === "selector")
        await this.selectors.failed(input.trialId, String(e));
      this.state.research.status = "ERROR";
      this.state.research.error = String(e);
    }
    await this.save();
  }
  healthBooks(now = Date.now()) {
    return (["equity", "etf", "crypto", "options"] as Book[]).map((book) => {
      const held = this.active()
          .filter((c) => c.book === book)
          .map((c) => c.symbol),
        symbols =
          book === "options"
            ? [...new Set([...held, ...(this.market.watched.options || [])])]
            : this.cfg.universe
                .filter((i) => i.book === book)
                .map((i) => i.symbol),
        present = symbols.map((s) => this.market.quotes[s]).filter(Boolean),
        valid = symbols.filter((s) =>
          fresh(this.market.quotes[s], now, this.cfg.quoteAgeMs),
        ),
        oldest = present.length ? Math.min(...present.map((q) => q.at)) : 0,
        lastQuoteAt = present.length
          ? Math.max(...present.map((q) => q.at))
          : 0,
        heldStale = held.some(
          (s) => !fresh(this.market.quotes[s], now, this.cfg.quoteAgeMs),
        ),
        closed = !this.session(book),
        dataState = closed
          ? "MARKET_CLOSED"
          : heldStale
            ? "STALE"
            : !valid.length
              ? present.length
                ? "STALE"
                : "WAITING"
              : valid.length < symbols.length
                ? "DEGRADED"
                : "ALIVE";
      return {
        book,
        session: closed ? "CLOSED" : "OPEN",
        dataState,
        watched: symbols.length,
        fresh: valid.length,
        held: held.length,
        lastQuoteAt,
        quoteAgeMs: oldest ? Math.max(0, now - oldest) : null,
        feed:
          book === "options"
            ? "opra"
            : book === "crypto"
              ? "alpaca-us"
              : this.cfg.stockFeed,
        reason: closed
          ? "Fuera de sesión regular"
          : heldStale
            ? "Posición con cotización vencida"
            : !valid.length
              ? "Sin cotizaciones válidas observadas"
              : valid.length + " cotizaciones vigentes",
      };
    });
  }
  evidence() {
    const forward: Json = {
      schema: "HARPOON_FORWARD_COORDINATOR_EXPORT_1",
      account_id: this.cfg.expected_account_id, execution_nature: this.cfg.mode.toUpperCase(),
      exported_at: Date.now(), runtime_version: ULTIMATE_VERSION,
      runtime_config_hash: digest(this.cfg), reconciled_at: this.syncAt || null,
      reconciliation_error: this.reconcileError || null, storage_error: this.storageError || null,
      broker_positions: structuredClone(this.positions), broker_open_orders: structuredClone(this.openOrders),
      state_sequence: this.state.sequence,
      history_scope: "CURRENT_RETAINED_STATE_NOT_COMPLETE_JOURNAL",
      source_authenticity_independently_verified: false,
      execution_allowed: false, liveApproved: false,
    };
    return {
      ...this.view(),
      exportedAt: new Date().toISOString(),
      forward_attribution: { ...forward, integrity: digest(forward) },
      history: {
        campaigns: this.state.campaigns.map(c => ({ ...structuredClone(c), forwardProvenance: c.forwardProvenance ?? null })),
        intents: structuredClone(this.state.intents),
        recentEvents: structuredClone(this.state.events),
        accounting:
          "Broker fills; gross PnL. Fees are estimates, not an audited net return.",
      },
    };
  }
  view() {
    const heartbeat = this.scheduler
      .view()
      .find((l) => l.name === "positions-and-take-profit");
    const operationalCoverage = this.exitCoverage();
    return {
      operationalCoverage,
      operationalCapabilities: operationalCapabilities(this),
      netAccountLedger: this.netLedger.view(),
      prospectiveQuantObservations: this.quantObservations.view(),
      economicGate: this.quantEconomicGate,
      quantitativePerformance: this.quantPerformance,
      recursiveCalibration: this.quantResearch,
      stockEtfDiscovery: {...this.quantDiscovery, entryHold: this.discoveryHold},
      version: ULTIMATE_VERSION,
      edition: "XXXUltimate",
      autopilot: {
        mode: "PAPER",
        autoStartDefault: true,
        operatorOverridesPersistent: true,
        startedAt: this.autopilotStartedAt || null,
        state: this.stopping
          ? "STOPPING"
          : this.state.halt
            ? "RISK_BLOCKED"
            : this.state.paused
              ? "ENTRIES_PAUSED_GUARDIAN_ACTIVE"
              : !heartbeat?.lastSuccess
                ? "STARTING"
                : heartbeat.error || Date.now() - heartbeat.lastSuccess >= 4000 || !operationalCoverage.entrySafe
                  ? "GUARDIAN_DEGRADED"
                  : this.active().length
                    ? operationalCoverage.sessionGated ? "MANAGING_SESSION_GATED" : "MANAGING"
                    : this.entryReady()
                      ? "SCANNING"
                      : "WAIT_DATA_OR_RECONCILIATION",
        heartbeat: heartbeat || null,
        brokerReconciledAt: this.syncAt,
        protectionActiveWhenPaused: true,
        researchIndependent: true,
        policy: this.state.exitProfile || "BASELINE_30_1",
        nativeProtection: this.cfg.nativeProtection || "stop",
        capabilities: [
          "partial_take_profit",
          "runner",
          "monotonic_trailing",
          "durable_exit_plans",
          "urgent_stop_preemption",
          "broker_reconciliation",
          "risk_gates",
          "independent_async_lanes",
        ],
        policyEvidence:
          "BASELINE_RETAINED_NO_EXPERIMENTAL_POLICY_PASSED_LAST_VALIDATION",
      },
      ultimate: {
        lab: this.ultimateLab.view(),
        futures: this.futures.view(),
        bundledResearch: this.bundledUltimateReport,
      },
      mode: "paper",
      accountSuffix: this.state.accountId.slice(-4),
      paused: this.state.paused,
      halt: this.state.halt,
      reconciliation: this.reconcileError || "OK",
      syncAt: this.syncAt,
      storageError: this.storageError,
      account: {
        equity: this.account.equity,
        cash: this.account.cash,
        buyingPower: this.account.buying_power,
        optionsLevel: this.account.options_trading_level,
      },
      books: (["equity", "etf", "crypto", "options"] as Book[]).map((book) => ({
        book,
        session: this.session(book) ? "OPEN" : "CLOSED",
        executionAdapter: true,
        positions: this.active().filter((c) => c.book === book).length,
        plugins: this.state.plugins.filter((id) =>
          this.plugins.catalog.some((p) => p.id === id && p.book === book),
        ).length,
      })),
      lanes: this.scheduler.view(),
      validators: this.validators.view(),
      health: systemHealth(this),
      streams: this.streams.snapshot(),
      executionMetrics: executionMetrics(
        this.state.campaigns,
        this.state.intents,
        this.cfg,
      ),
      fees: this.fees.view(),
      exitResearch: this.exitResearchReport,
      exitProfile: this.state.exitProfile || "BASELINE_30_1",
      plugins: this.plugins.catalog.map((p) => ({
        ...p,
        enabled: this.state.plugins.includes(p.id),
        executionAvailable: true,
        modelReady:
          p.params.selection_filter !== "ridge_lcb" ||
          (this.plugins.selectors[p.book]?.validUntil || 0) > Date.now(),
        integration:
          p.params.selection_filter === "ridge_lcb"
            ? "Pipeline conectado · requiere modelo validado e instalado"
            : "PAPER adapter implemented; data, permission and evidence gates apply",
      })),
      positions: this.active().map((c) => ({
        ...c,
        partialEntryRisk: this.partialEntryRiskSnapshot(c, Date.now()),
        evaluation: operationalCoverage.positions.find((p) => p.campaign === c.id),
        quantity: Number(this.position(c.symbol)?.qty || 0),
        fills: fills(c, this.state.intents),
        quote: this.market.quotes[c.symbol],
        protectionState: protectionSnapshot(
          c,
          this.state.intents,
          Number(this.position(c.symbol)?.qty || 0),
          Date.now(),
        ),
        protection: this.pending(c)
          .filter((i) => i.kind === "protect")
          .map((i) => ({
            status: i.status,
            id: i.id,
            role: i.nativeRole,
            type: i.order?.type || i.payload.type,
            stop: i.order?.stop_price || i.payload.stop_price,
          })),
      })),
      orders: this.pending(),
      signals: this.plugins.diagnostics,
      marketErrors: this.market.errors,
      research: { ...this.state.research, paused: this.state.researchPaused },
      selectors: this.selectors.view(),
      events: this.state.events.slice(-100),
      limitations: [
        "PAPER execution; profitability not established",
        "Stops/slippage/fills are not guaranteed",
        "Option contracts: long call/put only; no spread/naked short executor",
      ],
      risk: this.cfg,
    };
  }
  start() {
    if (this.autopilotStartedAt || this.stopping) return;
    this.autopilotStartedAt = Date.now();
    this.probe.start();
    this.updateStreams();
    this.scheduler.start();
  }
  async stop() {
    this.stopping = true;
    this.probe.close();
    this.plugins.stop();
    this.streams.stop();
    await this.ultimateLab.stop();
    await this.scheduler.stop();
    await this.pulseJob;
    await this.save();
    await this.store.lease(this.leaseName, true);
    await this.store.close();
  }
}
