import type { Json, Store, Config } from "./types";
import { Validators } from "./validators";
import { PriorityMutex } from "./scheduler";
import { digest, FUTURES_SPECS, need } from "./ultimate_contracts";
import type { FutureRoot } from "./ultimate_contracts";

export interface FutureContract {
  root: FutureRoot;
  symbol: string;
  lastTradeAt: number;
  firstNoticeAt?: number;
}
export function assertContract(
  c: FutureContract,
  now = Date.now(),
): FutureContract {
  need(
    c &&
      Object.hasOwn(FUTURES_SPECS, c.root) &&
      typeof c.symbol === "string" &&
      /^[A-Z]+:[A-Z0-9]+\.[FGHJKMNQUVXZ]\d{2,4}$/.test(c.symbol),
    "dated exchange contract required",
  );
  need(c.symbol.split(":")[1].split(".")[0] === c.root, "symbol/root mismatch");
  need(
    Number.isSafeInteger(c.lastTradeAt) && c.lastTradeAt > now + 86400000,
    "last trade is missing or within safety deadline",
  );
  if (FUTURES_SPECS[c.root].settlement !== "CASH")
    need(
      Number.isSafeInteger(c.firstNoticeAt) &&
        c.firstNoticeAt! > now + 86400000,
      "physical first notice deadline",
    );
  return c;
}
export function futuresSize(input: {
  equity: number;
  available: number;
  entry: number;
  stop: number;
  root: FutureRoot;
  margin: number;
  commission: number;
  slippage: number;
  cfg: Config;
}) {
  const i = input,
    spec = FUTURES_SPECS[i.root];
  need(
    spec &&
      [
        i.equity,
        i.available,
        i.entry,
        i.stop,
        i.margin,
        i.commission,
        i.slippage,
      ].every(Number.isFinite) &&
      i.equity > 0 &&
      i.available >= 0 &&
      i.entry > 0 &&
      i.stop > 0 &&
      i.margin > 0 &&
      i.commission >= 1.5 &&
      i.slippage >= 0 &&
      i.entry !== i.stop,
    "sizing inputs",
  );
  const riskPerContract =
    Math.abs(i.entry - i.stop) * spec.pointValue +
    2 * i.commission +
    i.slippage * spec.pointValue;
  const riskBudget =
    Math.min(i.equity, i.cfg.capitalLimit) * i.cfg.riskFraction;
  const quantity = Math.max(
    0,
    Math.floor(
      Math.min(
        riskBudget / riskPerContract,
        (i.available * 0.7) / i.margin,
        (i.equity * i.cfg.totalExposure) / (i.entry * spec.pointValue),
        (i.equity * i.cfg.assetExposure) / (i.entry * spec.pointValue),
      ),
    ),
  );
  return {
    quantity,
    riskBudget,
    riskPerContract,
    initialMarginPerContract: i.margin,
    notionalPerContract: i.entry * spec.pointValue,
    reason: quantity ? "SIZED" : "INTEGER_RISK_MARGIN_OR_EXPOSURE",
  };
}

/** Actual HTTP transport. Fixed broker simulation host; never falls back to fabricated responses. */
export class IronbeamPaperApi {
  readonly base = "https://demo.ironbeamapi.com/v2";
  private token = "";
  private authJob?: Promise<void>;
  metrics = {
    attempts: 0,
    successes: 0,
    failures: 0,
    lastSuccess: 0,
    lastError: "",
    latencyMs: 0,
  };
  constructor(
    private username: string,
    private password: string,
    private apikey: string,
    private transport: typeof fetch = fetch,
  ) {
    need(
      username.length > 0 && (password.length > 0 || apikey.length > 0),
      "Ironbeam credentials required",
    );
  }
  private async call(
    route: string,
    method: string,
    body?: Json,
    auth = true,
  ): Promise<Json> {
    need(
      route.startsWith("/") &&
        !route.startsWith("//") &&
        !/[\r\n\\]/.test(route),
      "broker route",
    );
    const start = Date.now();
    this.metrics.attempts++;
    try {
      const response = await this.transport(this.base + route, {
        method,
        redirect: "error",
        signal: AbortSignal.timeout(8000),
        headers: {
          "Content-Type": "application/json",
          ...(auth ? { Authorization: "Bearer " + this.token } : {}),
        },
        ...(body ? { body: JSON.stringify(body) } : {}),
      });
      need(response.ok, "Ironbeam HTTP " + response.status);
      const value = (await response.json()) as Json;
      need(value && value.status === "OK", "Ironbeam response not OK");
      this.metrics.successes++;
      this.metrics.lastSuccess = Date.now();
      this.metrics.lastError = "";
      return value;
    } catch (e) {
      this.metrics.failures++;
      this.metrics.lastError = e instanceof Error ? e.message : String(e);
      throw e;
    } finally {
      this.metrics.latencyMs = Date.now() - start;
    }
  }
  async request(route: string, method = "GET", body?: Json) {
    if (!this.token) {
      this.authJob ||= this.call(
        "/auth",
        "POST",
        {
          username: this.username,
          password: this.password,
          apikey: this.apikey,
        },
        false,
      )
        .then((r) => {
          need(
            typeof r.token === "string" && r.token.length > 10,
            "auth token missing",
          );
          this.token = r.token;
        })
        .finally(() => {
          this.authJob = undefined;
        });
      await this.authJob;
    }
    try {
      return await this.call(route, method, body);
    } catch (e) {
      if (this.metrics.lastError.includes("HTTP 401")) this.token = "";
      throw e;
    }
  }
}
export type FuturesApi = Pick<IronbeamPaperApi, "request">;
interface FuturesIntent {
  id: string;
  payload: Json;
  hash: string;
  at: number;
  state: string;
  strategyId?: number;
  orderId?: string;
  error?: string;
}
export class FuturesGateway {
  private mutex = new PriorityMutex();
  private intents: FuturesIntent[] = [];
  private snapshot: {
    at: number;
    balance: Json;
    risk: Json;
    positions: Json[];
    orders: Json[];
  } | null = null;
  private quotes: Record<string, Json> = {};
  private margins: Record<string, Json> = {};
  private accountError = "";
  private marketError = "";
  private accountAttempt = 0;
  private marketAttempt = 0;
  private marketSuccess = 0;
  private key: string;
  constructor(
    private store: Store,
    private cfg: Config,
    private validators: Validators,
    private api: FuturesApi | null = null,
    private accountId = "",
    private contracts: FutureContract[] = [],
    private allowPaperOrders = false,
    private commissionPerSideUsd: number | null = null,
  ) {
    need(
      !api || /^[A-Za-z0-9_-]{1,10}$/.test(accountId),
      "futures account ID required",
    );
    need(
      contracts.length <= 10 &&
        new Set(contracts.map((c) => c.symbol)).size === contracts.length,
      "futures contract universe",
    );
    contracts.forEach((c) => assertContract(c));
    need(
      commissionPerSideUsd === null ||
        (Number.isFinite(commissionPerSideUsd) && commissionPerSideUsd >= 1.5),
      "complete commission per side required",
    );
    this.key = "ultimate-futures-" + cfg.expected_account_id;
  }
  async load() {
    const old = await this.store.get(this.key);
    if (old) {
      need(
        old.accountId === this.accountId &&
          old.contractHash === digest(this.contracts) &&
          Array.isArray(old.intents),
        "futures journal binding; reconcile before changing account/contracts",
      );
      for (const i of old.intents)
        need(
          i.hash === digest(i.payload) && typeof i.id === "string",
          "futures intent integrity",
        );
      this.intents = old.intents;
      for (const i of this.intents)
        if (i.state === "SENDING") i.state = "UNKNOWN";
      await this.save();
    }
  }
  private async save() {
    await this.store.put(this.key, {
      accountId: this.accountId,
      contractHash: digest(this.contracts),
      intents: structuredClone(this.intents),
    });
  }
  async refreshAccount() {
    if (!this.api) return;
    return this.mutex.run(0, async () => {
      this.accountAttempt = Date.now();
      try {
        const id = encodeURIComponent(this.accountId);
        const [balance, risk, positions, orders] = await Promise.all([
          this.api!.request(`/account/${id}/balance?balanceType=CURRENT_OPEN`),
          this.api!.request(`/account/${id}/risk`),
          this.api!.request(`/account/${id}/positions`),
          this.api!.request(`/order/${id}/ANY`),
        ]);
        const result = this.validators.run("futures-account", () => {
          need(
            Array.isArray(balance.balances) &&
              Array.isArray(risk.risks) &&
              Array.isArray(positions.positions) &&
              Array.isArray(orders.orders),
            "broker snapshot shape",
          );
          const b = balance.balances.find(
              (x: Json) =>
                x.accountId === this.accountId &&
                x.currencyCode === "USD" &&
                x.balanceType === "CURRENT_OPEN",
            ),
            r = risk.risks.find(
              (x: Json) =>
                x.accountId === this.accountId && x.currencyCode === "USD",
            );
          need(
            b &&
              r &&
              [
                b.totalEquity,
                b.netLiquidityAvailable,
                r.startNetLiquidationValue,
                r.maxNetLiquidationValueMultiDay,
              ].every((x) => typeof x === "number" && Number.isFinite(x)) &&
              b.totalEquity > 0,
            "USD balance/risk or account binding unavailable",
          );
          need(
            positions.positions.every(
              (x: Json) =>
                x.accountId === this.accountId &&
                typeof x.quantity === "number" &&
                Number.isInteger(x.quantity) &&
                x.quantity >= 0 &&
                ["LONG", "SHORT"].includes(x.side),
            ),
            "futures positions",
          );
          need(
            orders.orders.every(
              (x: Json) =>
                x.accountId === this.accountId &&
                typeof x.orderId === "string" &&
                Number.isInteger(x.quantity) &&
                Number.isFinite(x.fillQuantity) &&
                x.fillQuantity >= 0 &&
                x.fillQuantity <= x.quantity,
            ),
            "futures orders/partial fills",
          );
          return {
            at: Date.now(),
            balance: b,
            risk: r,
            positions: positions.positions,
            orders: orders.orders,
          };
        });
        this.snapshot = result;
        this.accountError = "";
        for (const i of this.intents) {
          if (i.strategyId && !i.orderId) {
            const resolved = await this.api!.request(
              `/order/${id}/toorderid/${i.strategyId}`,
            );
            if (typeof resolved.orderId === "string" && resolved.orderId)
              i.orderId = resolved.orderId;
          }
          const order = result.orders.find((o) => o.orderId === i.orderId);
          if (order) i.state = order.status;
        }
        await this.save();
      } catch (e) {
        this.accountError = e instanceof Error ? e.message : String(e);
        throw e;
      }
    });
  }
  async refreshMarket() {
    if (!this.api || !this.contracts.length) return;
    this.marketAttempt = Date.now();
    try {
      const symbols = encodeURIComponent(
        this.contracts.map((c) => c.symbol).join(","),
      );
      const [raw, margin] = await Promise.all([
        this.api.request("/market/quotes?symbols=" + symbols),
        this.api.request("/info/security/margin?symbols=" + symbols),
      ]);
      this.validators.run("futures-market", () => {
        need(
          Array.isArray(raw.Quotes) &&
            Array.isArray(margin.securityMarginAndValues),
          "quote/margin shape",
        );
        const quotes: Record<string, Json> = {},
          margins: Record<string, Json> = {},
          now = Date.now();
        for (const c of this.contracts) {
          assertContract(c, now);
          const q = raw.Quotes.find((q: Json) => q.s === c.symbol),
            m = margin.securityMarginAndValues.find(
              (x: Json) => x.exchSym === c.symbol,
            );
          if (
            q &&
            [q.b, q.a, q.bt, q.at].every(
              (x) => typeof x === "number" && Number.isFinite(x),
            ) &&
            q.b > 0 &&
            q.a >= q.b &&
            Math.min(q.bt, q.at) <= now + 2000 &&
            now - Math.min(q.bt, q.at) <= this.cfg.quoteAgeMs
          )
            quotes[c.symbol] = {
              bid: q.b,
              ask: q.a,
              at: Math.min(q.bt, q.at),
              received: now,
            };
          if (
            m &&
            typeof m.currentTime === "number" &&
            m.currentTime <= now + 2000 &&
            now - m.currentTime <= 60000
          )
            margins[c.symbol] = m;
        }
        this.quotes = quotes;
        this.margins = margins;
        need(
          this.contracts.every((c) => quotes[c.symbol] && margins[c.symbol]),
          "fresh quotes or entitled margin missing",
        );
      });
      this.marketSuccess = Date.now();
      this.marketError = "";
    } catch (e) {
      this.marketError = e instanceof Error ? e.message : String(e);
      throw e;
    }
  }
  plan(raw: Json, now = Date.now()) {
    return this.validators.run("futures-plan", () => {
      need(
        raw &&
          typeof raw.symbol === "string" &&
          ["BUY", "SELL"].includes(raw.side),
        "symbol and side required",
      );
      const c = this.contracts.find((c) => c.symbol === raw.symbol);
      need(c, "contract not configured");
      assertContract(c, now);
      need(
        this.snapshot && !this.accountError && now - this.snapshot.at <= 15000,
        "fresh account reconciliation required",
      );
      need(
        !this.intents.some((i) =>
          ["SENDING", "UNKNOWN", "PENDING_ACK"].includes(i.state),
        ),
        "uncertain order prevents duplicate exposure",
      );
      need(
        !this.snapshot.positions.length &&
          !this.snapshot.orders.some(
            (o) =>
              ![
                "FILLED",
                "CANCELLED",
                "REJECTED",
                "EXPIRED",
                "REPLACED",
                "COMPLETE",
                "DONE_FOR_DAY",
              ].includes(o.status),
          ),
        "dedicated empty futures account required for new bracket",
      );
      const q = this.quotes[c.symbol],
        m = this.margins[c.symbol],
        s = this.snapshot;
      need(
        q &&
          m &&
          !this.marketError &&
          now - q.at <= this.cfg.quoteAgeMs &&
          now - m.currentTime <= 60000,
        "fresh quote/margin required",
      );
      const spec = FUTURES_SPECS[c.root],
        stop = raw.stop,
        target = raw.target,
        entry = raw.side === "BUY" ? q.ask : q.bid;
      need(
        [stop, target].every(
          (x) =>
            typeof x === "number" &&
            Number.isFinite(x) &&
            x > 0 &&
            Math.abs(x / spec.tick - Math.round(x / spec.tick)) < 1e-6,
        ),
        "target/stop tick precision",
      );
      need(
        raw.side === "BUY"
          ? stop < entry && target > entry
          : stop > entry && target < entry,
        "bracket direction",
      );
      need(
        ((q.ask - q.bid) / q.bid) * 10000 <= this.cfg.maxSpreadBps,
        "spread limit",
      );
      const equity = s.balance.totalEquity;
      need(
        equity > s.risk.startNetLiquidationValue * (1 - this.cfg.dailyLoss) &&
          equity >
            s.risk.maxNetLiquidationValueMultiDay * (1 - this.cfg.maxDrawdown),
        "futures loss limit",
      );
      const margin =
        raw.side === "BUY" ? m.initialMarginLong : m.initialMaginShort;
      const size = futuresSize({
        equity,
        available: s.balance.netLiquidityAvailable,
        entry,
        stop,
        root: c.root,
        margin,
        commission: this.commissionPerSideUsd ?? 1.5,
        slippage: Math.max(
          spec.tick * 2,
          (entry * this.cfg.slippageBps) / 10000,
        ),
        cfg: this.cfg,
      });
      return {
        ...size,
        symbol: c.symbol,
        entry,
        stop,
        target,
        side: raw.side,
        at: now,
        expires: now + 5000,
        execution: "IRONBEAM_PAPER_BRACKET",
        nativeTrailing: false,
        protection: "BROKER_BRACKET_CONFIRMATION_PENDING",
        fees:
          this.commissionPerSideUsd === null
            ? "FLOOR_ONLY_EXECUTION_BLOCKED"
            : "OPERATOR_CONFIGURED_COMPLETE_RATE",
      };
    });
  }
  async place(raw: Json) {
    return this.mutex.run(1, async () => {
      need(
        this.api &&
          this.allowPaperOrders &&
          raw.confirmation === "SEND_IRONBEAM_PAPER_BRACKET",
        "PAPER orders require explicit server switch and action confirmation",
      );
      need(
        this.commissionPerSideUsd !== null,
        "complete futures commission/fee rate must be configured before submission",
      );
      need(
        typeof raw.id === "string" && /^[a-zA-Z0-9_-]{12,80}$/.test(raw.id),
        "idempotency ID required",
      );
      const existing = this.intents.find((i) => i.id === raw.id);
      if (existing) {
        need(existing.hash === digest(existing.payload), "intent changed");
        return structuredClone(existing);
      }
      const plan = this.plan(raw);
      need(plan.quantity > 0, "risk/margin/exposure allows zero contracts");
      const payload = {
        accountId: this.accountId,
        exchSym: plan.symbol,
        side: plan.side,
        quantity: plan.quantity,
        orderType: "1",
        duration: "1",
        stopLoss: plan.stop,
        takeProfit: plan.target,
      };
      const intent: FuturesIntent = {
        id: raw.id,
        payload,
        hash: digest(payload),
        at: Date.now(),
        state: "SENDING",
      };
      this.intents.push(intent);
      await this.save();
      try {
        const response = await this.api.request(
          `/order/${encodeURIComponent(this.accountId)}/place`,
          "POST",
          payload,
        );
        intent.orderId =
          typeof response.orderId === "string" && response.orderId
            ? response.orderId
            : undefined;
        intent.strategyId =
          Number.isSafeInteger(response.strategyId) && response.strategyId > 0
            ? response.strategyId
            : undefined;
        intent.state =
          intent.orderId || intent.strategyId ? "PENDING_ACK" : "UNKNOWN";
      } catch (e) {
        intent.state = "UNKNOWN";
        intent.error = e instanceof Error ? e.message : String(e);
      }
      await this.save();
      return structuredClone(intent);
    });
  }
  view(now = Date.now()) {
    const snapshot = this.snapshot,
      quoteRows = Object.entries(this.quotes).map(([symbol, q]) => ({
        symbol,
        ...q,
        ageMs: now - q.at,
      }));
    return {
      mode: "paper",
      configured: !!this.api,
      accountSuffix: this.accountId.slice(-4),
      executionEnabled: this.allowPaperOrders,
      nativeTrailing: false,
      automatedStrategyPromotion: false,
      account: {
        state: !this.api
          ? "NOT_CONFIGURED"
          : this.accountError
            ? "ERROR"
            : !snapshot
              ? "WAITING"
              : now - snapshot.at > 15000
                ? "STALE"
                : "ALIVE",
        lastAttempt: this.accountAttempt,
        lastSuccess: snapshot?.at || 0,
        error: this.accountError,
        equity: snapshot?.balance.totalEquity ?? null,
      },
      market: {
        state: !this.api
          ? "NOT_CONFIGURED"
          : !this.contracts.length
            ? "WAIT_CONTRACTS"
            : this.marketError
              ? "ERROR"
              : !this.marketSuccess
                ? "WAITING"
                : quoteRows.some((q) => q.ageMs > this.cfg.quoteAgeMs)
                  ? "STALE"
                  : "ALIVE",
        lastAttempt: this.marketAttempt,
        lastSuccess: this.marketSuccess,
        error: this.marketError,
        quotes: quoteRows,
      },
      contracts: this.contracts.map((c) => ({
        ...c,
        spec: FUTURES_SPECS[c.root],
        margin: this.margins[c.symbol] || null,
      })),
      positions: snapshot?.positions || [],
      orders: snapshot?.orders || [],
      intents: structuredClone(this.intents),
      catalog: FUTURES_SPECS,
      limitations: [
        "Broker PAPER uses simulated funds/fills.",
        "External authenticated validation pending; API schema contract tests do not certify broker behavior.",
        "Trailing is not native on this API; only fixed broker brackets are exposed.",
        "Unknown submission remains blocked until a broker order ID is reconciled; no automatic resubmission.",
        "The existing 12 percent per-asset notional cap may legitimately allow zero micro contracts.",
        "Futures and Alpaca accounts are separately margined; this gateway permits only one dedicated bracket campaign at a time.",
      ],
    };
  }
}
