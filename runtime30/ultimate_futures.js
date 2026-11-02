"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FuturesGateway = exports.IronbeamPaperApi = void 0;
exports.assertContract = assertContract;
exports.futuresSize = futuresSize;
const scheduler_1 = require("./scheduler");
const ultimate_contracts_1 = require("./ultimate_contracts");
function assertContract(c, now = Date.now()) {
    (0, ultimate_contracts_1.need)(c &&
        Object.hasOwn(ultimate_contracts_1.FUTURES_SPECS, c.root) &&
        typeof c.symbol === "string" &&
        /^[A-Z]+:[A-Z0-9]+\.[FGHJKMNQUVXZ]\d{2,4}$/.test(c.symbol), "dated exchange contract required");
    (0, ultimate_contracts_1.need)(c.symbol.split(":")[1].split(".")[0] === c.root, "symbol/root mismatch");
    (0, ultimate_contracts_1.need)(Number.isSafeInteger(c.lastTradeAt) && c.lastTradeAt > now + 86400000, "last trade is missing or within safety deadline");
    if (ultimate_contracts_1.FUTURES_SPECS[c.root].settlement !== "CASH")
        (0, ultimate_contracts_1.need)(Number.isSafeInteger(c.firstNoticeAt) &&
            c.firstNoticeAt > now + 86400000, "physical first notice deadline");
    return c;
}
function futuresSize(input) {
    const i = input, spec = ultimate_contracts_1.FUTURES_SPECS[i.root];
    (0, ultimate_contracts_1.need)(spec &&
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
        i.entry !== i.stop, "sizing inputs");
    const riskPerContract = Math.abs(i.entry - i.stop) * spec.pointValue +
        2 * i.commission +
        i.slippage * spec.pointValue;
    const riskBudget = Math.min(i.equity, i.cfg.capitalLimit) * i.cfg.riskFraction;
    const quantity = Math.max(0, Math.floor(Math.min(riskBudget / riskPerContract, (i.available * 0.7) / i.margin, (i.equity * i.cfg.totalExposure) / (i.entry * spec.pointValue), (i.equity * i.cfg.assetExposure) / (i.entry * spec.pointValue))));
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
class IronbeamPaperApi {
    username;
    password;
    apikey;
    transport;
    base = "https://demo.ironbeamapi.com/v2";
    token = "";
    authJob;
    metrics = {
        attempts: 0,
        successes: 0,
        failures: 0,
        lastSuccess: 0,
        lastError: "",
        latencyMs: 0,
    };
    constructor(username, password, apikey, transport = fetch) {
        this.username = username;
        this.password = password;
        this.apikey = apikey;
        this.transport = transport;
        (0, ultimate_contracts_1.need)(username.length > 0 && (password.length > 0 || apikey.length > 0), "Ironbeam credentials required");
    }
    async call(route, method, body, auth = true) {
        (0, ultimate_contracts_1.need)(route.startsWith("/") &&
            !route.startsWith("//") &&
            !/[\r\n\\]/.test(route), "broker route");
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
            (0, ultimate_contracts_1.need)(response.ok, "Ironbeam HTTP " + response.status);
            const value = (await response.json());
            (0, ultimate_contracts_1.need)(value && value.status === "OK", "Ironbeam response not OK");
            this.metrics.successes++;
            this.metrics.lastSuccess = Date.now();
            this.metrics.lastError = "";
            return value;
        }
        catch (e) {
            this.metrics.failures++;
            this.metrics.lastError = e instanceof Error ? e.message : String(e);
            throw e;
        }
        finally {
            this.metrics.latencyMs = Date.now() - start;
        }
    }
    async request(route, method = "GET", body) {
        if (!this.token) {
            this.authJob ||= this.call("/auth", "POST", {
                username: this.username,
                password: this.password,
                apikey: this.apikey,
            }, false)
                .then((r) => {
                (0, ultimate_contracts_1.need)(typeof r.token === "string" && r.token.length > 10, "auth token missing");
                this.token = r.token;
            })
                .finally(() => {
                this.authJob = undefined;
            });
            await this.authJob;
        }
        try {
            return await this.call(route, method, body);
        }
        catch (e) {
            if (this.metrics.lastError.includes("HTTP 401"))
                this.token = "";
            throw e;
        }
    }
}
exports.IronbeamPaperApi = IronbeamPaperApi;
class FuturesGateway {
    store;
    cfg;
    validators;
    api;
    accountId;
    contracts;
    allowPaperOrders;
    commissionPerSideUsd;
    mutex = new scheduler_1.PriorityMutex();
    intents = [];
    snapshot = null;
    quotes = {};
    margins = {};
    accountError = "";
    marketError = "";
    accountAttempt = 0;
    marketAttempt = 0;
    marketSuccess = 0;
    key;
    constructor(store, cfg, validators, api = null, accountId = "", contracts = [], allowPaperOrders = false, commissionPerSideUsd = null) {
        this.store = store;
        this.cfg = cfg;
        this.validators = validators;
        this.api = api;
        this.accountId = accountId;
        this.contracts = contracts;
        this.allowPaperOrders = allowPaperOrders;
        this.commissionPerSideUsd = commissionPerSideUsd;
        (0, ultimate_contracts_1.need)(!api || /^[A-Za-z0-9_-]{1,10}$/.test(accountId), "futures account ID required");
        (0, ultimate_contracts_1.need)(contracts.length <= 10 &&
            new Set(contracts.map((c) => c.symbol)).size === contracts.length, "futures contract universe");
        contracts.forEach((c) => assertContract(c));
        (0, ultimate_contracts_1.need)(commissionPerSideUsd === null ||
            (Number.isFinite(commissionPerSideUsd) && commissionPerSideUsd >= 1.5), "complete commission per side required");
        this.key = "ultimate-futures-" + cfg.expected_account_id;
    }
    async load() {
        const old = await this.store.get(this.key);
        if (old) {
            (0, ultimate_contracts_1.need)(old.accountId === this.accountId &&
                old.contractHash === (0, ultimate_contracts_1.digest)(this.contracts) &&
                Array.isArray(old.intents), "futures journal binding; reconcile before changing account/contracts");
            for (const i of old.intents)
                (0, ultimate_contracts_1.need)(i.hash === (0, ultimate_contracts_1.digest)(i.payload) && typeof i.id === "string", "futures intent integrity");
            this.intents = old.intents;
            for (const i of this.intents)
                if (i.state === "SENDING")
                    i.state = "UNKNOWN";
            await this.save();
        }
    }
    async save() {
        await this.store.put(this.key, {
            accountId: this.accountId,
            contractHash: (0, ultimate_contracts_1.digest)(this.contracts),
            intents: structuredClone(this.intents),
        });
    }
    async refreshAccount() {
        if (!this.api)
            return;
        return this.mutex.run(0, async () => {
            this.accountAttempt = Date.now();
            try {
                const id = encodeURIComponent(this.accountId);
                const [balance, risk, positions, orders] = await Promise.all([
                    this.api.request(`/account/${id}/balance?balanceType=CURRENT_OPEN`),
                    this.api.request(`/account/${id}/risk`),
                    this.api.request(`/account/${id}/positions`),
                    this.api.request(`/order/${id}/ANY`),
                ]);
                const result = this.validators.run("futures-account", () => {
                    (0, ultimate_contracts_1.need)(Array.isArray(balance.balances) &&
                        Array.isArray(risk.risks) &&
                        Array.isArray(positions.positions) &&
                        Array.isArray(orders.orders), "broker snapshot shape");
                    const b = balance.balances.find((x) => x.accountId === this.accountId &&
                        x.currencyCode === "USD" &&
                        x.balanceType === "CURRENT_OPEN"), r = risk.risks.find((x) => x.accountId === this.accountId && x.currencyCode === "USD");
                    (0, ultimate_contracts_1.need)(b &&
                        r &&
                        [
                            b.totalEquity,
                            b.netLiquidityAvailable,
                            r.startNetLiquidationValue,
                            r.maxNetLiquidationValueMultiDay,
                        ].every((x) => typeof x === "number" && Number.isFinite(x)) &&
                        b.totalEquity > 0, "USD balance/risk or account binding unavailable");
                    (0, ultimate_contracts_1.need)(positions.positions.every((x) => x.accountId === this.accountId &&
                        typeof x.quantity === "number" &&
                        Number.isInteger(x.quantity) &&
                        x.quantity >= 0 &&
                        ["LONG", "SHORT"].includes(x.side)), "futures positions");
                    (0, ultimate_contracts_1.need)(orders.orders.every((x) => x.accountId === this.accountId &&
                        typeof x.orderId === "string" &&
                        Number.isInteger(x.quantity) &&
                        Number.isFinite(x.fillQuantity) &&
                        x.fillQuantity >= 0 &&
                        x.fillQuantity <= x.quantity), "futures orders/partial fills");
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
                        const resolved = await this.api.request(`/order/${id}/toorderid/${i.strategyId}`);
                        if (typeof resolved.orderId === "string" && resolved.orderId)
                            i.orderId = resolved.orderId;
                    }
                    const order = result.orders.find((o) => o.orderId === i.orderId);
                    if (order)
                        i.state = order.status;
                }
                await this.save();
            }
            catch (e) {
                this.accountError = e instanceof Error ? e.message : String(e);
                throw e;
            }
        });
    }
    async refreshMarket() {
        if (!this.api || !this.contracts.length)
            return;
        this.marketAttempt = Date.now();
        try {
            const symbols = encodeURIComponent(this.contracts.map((c) => c.symbol).join(","));
            const [raw, margin] = await Promise.all([
                this.api.request("/market/quotes?symbols=" + symbols),
                this.api.request("/info/security/margin?symbols=" + symbols),
            ]);
            this.validators.run("futures-market", () => {
                (0, ultimate_contracts_1.need)(Array.isArray(raw.Quotes) &&
                    Array.isArray(margin.securityMarginAndValues), "quote/margin shape");
                const quotes = {}, margins = {}, now = Date.now();
                for (const c of this.contracts) {
                    assertContract(c, now);
                    const q = raw.Quotes.find((q) => q.s === c.symbol), m = margin.securityMarginAndValues.find((x) => x.exchSym === c.symbol);
                    if (q &&
                        [q.b, q.a, q.bt, q.at].every((x) => typeof x === "number" && Number.isFinite(x)) &&
                        q.b > 0 &&
                        q.a >= q.b &&
                        Math.min(q.bt, q.at) <= now + 2000 &&
                        now - Math.min(q.bt, q.at) <= this.cfg.quoteAgeMs)
                        quotes[c.symbol] = {
                            bid: q.b,
                            ask: q.a,
                            at: Math.min(q.bt, q.at),
                            received: now,
                        };
                    if (m &&
                        typeof m.currentTime === "number" &&
                        m.currentTime <= now + 2000 &&
                        now - m.currentTime <= 60000)
                        margins[c.symbol] = m;
                }
                this.quotes = quotes;
                this.margins = margins;
                (0, ultimate_contracts_1.need)(this.contracts.every((c) => quotes[c.symbol] && margins[c.symbol]), "fresh quotes or entitled margin missing");
            });
            this.marketSuccess = Date.now();
            this.marketError = "";
        }
        catch (e) {
            this.marketError = e instanceof Error ? e.message : String(e);
            throw e;
        }
    }
    plan(raw, now = Date.now()) {
        return this.validators.run("futures-plan", () => {
            (0, ultimate_contracts_1.need)(raw &&
                typeof raw.symbol === "string" &&
                ["BUY", "SELL"].includes(raw.side), "symbol and side required");
            const c = this.contracts.find((c) => c.symbol === raw.symbol);
            (0, ultimate_contracts_1.need)(c, "contract not configured");
            assertContract(c, now);
            (0, ultimate_contracts_1.need)(this.snapshot && !this.accountError && now - this.snapshot.at <= 15000, "fresh account reconciliation required");
            (0, ultimate_contracts_1.need)(!this.intents.some((i) => ["SENDING", "UNKNOWN", "PENDING_ACK"].includes(i.state)), "uncertain order prevents duplicate exposure");
            (0, ultimate_contracts_1.need)(!this.snapshot.positions.length &&
                !this.snapshot.orders.some((o) => ![
                    "FILLED",
                    "CANCELLED",
                    "REJECTED",
                    "EXPIRED",
                    "REPLACED",
                    "COMPLETE",
                    "DONE_FOR_DAY",
                ].includes(o.status)), "dedicated empty futures account required for new bracket");
            const q = this.quotes[c.symbol], m = this.margins[c.symbol], s = this.snapshot;
            (0, ultimate_contracts_1.need)(q &&
                m &&
                !this.marketError &&
                now - q.at <= this.cfg.quoteAgeMs &&
                now - m.currentTime <= 60000, "fresh quote/margin required");
            const spec = ultimate_contracts_1.FUTURES_SPECS[c.root], stop = raw.stop, target = raw.target, entry = raw.side === "BUY" ? q.ask : q.bid;
            (0, ultimate_contracts_1.need)([stop, target].every((x) => typeof x === "number" &&
                Number.isFinite(x) &&
                x > 0 &&
                Math.abs(x / spec.tick - Math.round(x / spec.tick)) < 1e-6), "target/stop tick precision");
            (0, ultimate_contracts_1.need)(raw.side === "BUY"
                ? stop < entry && target > entry
                : stop > entry && target < entry, "bracket direction");
            (0, ultimate_contracts_1.need)(((q.ask - q.bid) / q.bid) * 10000 <= this.cfg.maxSpreadBps, "spread limit");
            const equity = s.balance.totalEquity;
            (0, ultimate_contracts_1.need)(equity > s.risk.startNetLiquidationValue * (1 - this.cfg.dailyLoss) &&
                equity >
                    s.risk.maxNetLiquidationValueMultiDay * (1 - this.cfg.maxDrawdown), "futures loss limit");
            const margin = raw.side === "BUY" ? m.initialMarginLong : m.initialMaginShort;
            const size = futuresSize({
                equity,
                available: s.balance.netLiquidityAvailable,
                entry,
                stop,
                root: c.root,
                margin,
                commission: this.commissionPerSideUsd ?? 1.5,
                slippage: Math.max(spec.tick * 2, (entry * this.cfg.slippageBps) / 10000),
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
                fees: this.commissionPerSideUsd === null
                    ? "FLOOR_ONLY_EXECUTION_BLOCKED"
                    : "OPERATOR_CONFIGURED_COMPLETE_RATE",
            };
        });
    }
    async place(raw) {
        return this.mutex.run(1, async () => {
            (0, ultimate_contracts_1.need)(this.api &&
                this.allowPaperOrders &&
                raw.confirmation === "SEND_IRONBEAM_PAPER_BRACKET", "PAPER orders require explicit server switch and action confirmation");
            (0, ultimate_contracts_1.need)(this.commissionPerSideUsd !== null, "complete futures commission/fee rate must be configured before submission");
            (0, ultimate_contracts_1.need)(typeof raw.id === "string" && /^[a-zA-Z0-9_-]{12,80}$/.test(raw.id), "idempotency ID required");
            const existing = this.intents.find((i) => i.id === raw.id);
            if (existing) {
                (0, ultimate_contracts_1.need)(existing.hash === (0, ultimate_contracts_1.digest)(existing.payload), "intent changed");
                return structuredClone(existing);
            }
            const plan = this.plan(raw);
            (0, ultimate_contracts_1.need)(plan.quantity > 0, "risk/margin/exposure allows zero contracts");
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
            const intent = {
                id: raw.id,
                payload,
                hash: (0, ultimate_contracts_1.digest)(payload),
                at: Date.now(),
                state: "SENDING",
            };
            this.intents.push(intent);
            await this.save();
            try {
                const response = await this.api.request(`/order/${encodeURIComponent(this.accountId)}/place`, "POST", payload);
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
            }
            catch (e) {
                intent.state = "UNKNOWN";
                intent.error = e instanceof Error ? e.message : String(e);
            }
            await this.save();
            return structuredClone(intent);
        });
    }
    view(now = Date.now()) {
        const snapshot = this.snapshot, quoteRows = Object.entries(this.quotes).map(([symbol, q]) => ({
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
                spec: ultimate_contracts_1.FUTURES_SPECS[c.root],
                margin: this.margins[c.symbol] || null,
            })),
            positions: snapshot?.positions || [],
            orders: snapshot?.orders || [],
            intents: structuredClone(this.intents),
            catalog: ultimate_contracts_1.FUTURES_SPECS,
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
exports.FuturesGateway = FuturesGateway;
