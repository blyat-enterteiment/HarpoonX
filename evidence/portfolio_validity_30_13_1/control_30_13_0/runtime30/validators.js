"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Validators = exports.CORE_CONTRACTS = exports.ContractError = void 0;
exports.numeric = numeric;
exports.assertAccount = assertAccount;
exports.assertClock = assertClock;
exports.assertPositions = assertPositions;
exports.assertOrder = assertOrder;
exports.assertIntent = assertIntent;
exports.assertSignal = assertSignal;
exports.assertJournal = assertJournal;
exports.assertExitPlan = assertExitPlan;
exports.assertCampaignInventory = assertCampaignInventory;
exports.assertFreshQuote = assertFreshQuote;
exports.assertSelectorModel = assertSelectorModel;
exports.assertBars = assertBars;
exports.assertPositionEvaluation = assertPositionEvaluation;
exports.assertOperationalCoverage = assertOperationalCoverage;
exports.assertRetryState = assertRetryState;
exports.assertPartialEntryRisk = assertPartialEntryRisk;
exports.assertSellReservation = assertSellReservation;
const node_perf_hooks_1 = require("node:perf_hooks");
const types_1 = require("./types");
class ContractError extends Error {
    contract;
    constructor(contract, detail) {
        super(contract + ": " + detail);
        this.contract = contract;
        this.name = "ContractError";
    }
}
exports.ContractError = ContractError;
const demand = (ok, contract, detail) => {
    if (!ok)
        throw new ContractError(contract, detail);
};
function numeric(v, contract) {
    demand(v !== null &&
        v !== undefined &&
        v !== "" &&
        (typeof v !== "string" || v.trim().length > 0) &&
        (typeof v === "number" || typeof v === "string"), contract, "numeric value required");
    const n = Number(v);
    demand(Number.isFinite(n), contract, "finite value required");
    return n;
}
exports.CORE_CONTRACTS = [
    "config",
    "journal",
    "account",
    "clock",
    "positions",
    "journal-write",
    "quote-equity",
    "quote-etf",
    "quote-crypto",
    "quote-options",
    "bars-securities",
    "bars-crypto",
    "signal",
    "inventory",
    "intent",
    "order-response",
    "selector-dataset",
    "selector-model",
    "exit-plan",
    "native-order-tree",
    "stream-event",
    "position-evaluation",
    "position-coverage",
    "guardian-coverage",
    "protection-retry",
    "sell-reservation",
    "partial-entry-risk",
];
class Validators {
    checks = {};
    constructor(contracts = []) {
        for (const name of contracts)
            this.checks[name] = {
                attempts: 0,
                passed: 0,
                failed: 0,
                lastAttempt: 0,
                lastSuccess: 0,
                lastError: "",
                durationMs: null,
            };
    }
    run(contract, fn) {
        const s = (this.checks[contract] ??= {
            attempts: 0,
            passed: 0,
            failed: 0,
            lastAttempt: 0,
            lastSuccess: 0,
            lastError: "",
            durationMs: null,
        });
        const begin = node_perf_hooks_1.performance.now();
        s.attempts++;
        s.lastAttempt = Date.now();
        try {
            const value = fn();
            s.passed++;
            s.lastSuccess = Date.now();
            s.lastError = "";
            return value;
        }
        catch (e) {
            s.failed++;
            s.lastError = e instanceof Error ? e.message : String(e);
            throw e;
        }
        finally {
            s.durationMs = node_perf_hooks_1.performance.now() - begin;
        }
    }
    view() {
        return Object.entries(this.checks).map(([name, x]) => ({
            name,
            ...x,
            status: x.lastError ? "ERROR" : x.passed ? "VALIDATED" : "NOT_RUN",
        }));
    }
    async check(contract, fn) {
        const s = (this.checks[contract] ??= {
            attempts: 0,
            passed: 0,
            failed: 0,
            lastAttempt: 0,
            lastSuccess: 0,
            lastError: "",
            durationMs: null,
        });
        const start = node_perf_hooks_1.performance.now();
        s.attempts++;
        s.lastAttempt = Date.now();
        try {
            const v = await fn();
            s.passed++;
            s.lastSuccess = Date.now();
            s.lastError = "";
            return v;
        }
        catch (e) {
            s.failed++;
            s.lastError = e instanceof Error ? e.message : String(e);
            throw e;
        }
        finally {
            s.durationMs = node_perf_hooks_1.performance.now() - start;
        }
    }
}
exports.Validators = Validators;
function assertAccount(a, expected) {
    demand(a && typeof a.id === "string" && a.id.length > 0, "account", "identity missing");
    if (expected)
        demand(a.id === expected, "account", "binding mismatch");
    demand(typeof a.status === "string" && (0, types_1.positive)(numeric(a.equity, "account")), "account", "invalid equity/status");
    for (const k of ["cash", "buying_power"])
        numeric(a[k], "account." + k);
    return a;
}
function assertClock(c, now = Date.now()) {
    demand(c && typeof c.is_open === "boolean", "clock", "is_open missing");
    demand(Number.isFinite(Date.parse(c.timestamp)) &&
        Math.abs(now - Date.parse(c.timestamp)) <= 15000, "clock", "stale timestamp");
    demand(Number.isFinite(Date.parse(c.next_close)), "clock", "next_close missing");
    return c;
}
function assertPositions(rows) {
    demand(Array.isArray(rows) && rows.length <= 1000, "positions", "incomplete or oversized snapshot");
    const seen = new Set();
    for (const p of rows) {
        demand(p && /^[A-Z0-9./-]{1,40}$/.test(p.symbol), "positions", "invalid symbol");
        const symbol = p.symbol.replace("/", "");
        demand(!seen.has(symbol), "positions", "duplicate symbol");
        seen.add(symbol);
        numeric(p.qty, "positions.qty");
        numeric(p.market_value, "positions.market_value");
    }
    return rows;
}
function assertOrder(o, clientId) {
    demand(o &&
        typeof o.id === "string" &&
        typeof o.client_order_id === "string" &&
        (!clientId || o.client_order_id === clientId), "order", "identity mismatch");
    demand(typeof o.status === "string" &&
        o.status.length > 0 &&
        ["buy", "sell"].includes(o.side), "order", "status/side missing");
    demand(typeof o.symbol === "string" && o.symbol.length > 0, "order", "symbol missing");
    const qty = numeric(o.qty, "order.qty"), filled = numeric(o.filled_qty, "order.filled_qty");
    demand(qty > 0 && filled >= 0 && filled <= qty, "order", "filled quantity out of bounds");
    if (filled > 0)
        demand((0, types_1.positive)(numeric(o.filled_avg_price, "order.filled_avg_price")), "order", "invalid fill price");
    return o;
}
function assertIntent(p, i) {
    demand(p && p.symbol === i.symbol && ["buy", "sell"].includes(p.side), "intent", "identity or side mismatch");
    const q = numeric(p.qty, "intent.qty");
    demand(q >= i.minQty &&
        (0, types_1.positive)(i.step) &&
        Math.abs(q / i.step - Math.round(q / i.step)) < 1e-5, "intent", "quantity/precision");
    demand(["market", "limit", "stop", "stop_limit", "trailing_stop"].includes(p.type), "intent", "unsupported order type");
    demand((i.book === "crypto" ? ["gtc", "ioc"] : ["day", "gtc"]).includes(p.time_in_force), "intent", "unsupported time in force");
    for (const field of p.type === "limit"
        ? ["limit_price"]
        : p.type === "stop"
            ? ["stop_price"]
            : p.type === "stop_limit"
                ? ["limit_price", "stop_price"]
                : []) {
        const n = numeric(p[field], "intent." + field);
        demand(n > 0 && Math.abs(n / i.tick - Math.round(n / i.tick)) < 1e-5, "intent", "invalid price tick");
    }
    if (i.book === "options")
        demand(Number.isInteger(q) &&
            p.position_intent ===
                (p.side === "buy" ? "buy_to_open" : "sell_to_close"), "intent", "option position intent/whole contracts");
    if (p.type === "stop_limit" && p.side === "sell")
        demand(Number(p.limit_price) <= Number(p.stop_price), "intent", "sell limit exceeds stop");
    if (p.type === "trailing_stop")
        demand(["equity", "etf"].includes(i.book) &&
            p.side === "sell" &&
            (0, types_1.positive)(numeric(p.trail_price, "intent.trail_price")) &&
            p.trail_percent === undefined &&
            !p.order_class, "intent", "invalid standalone trailing order");
    if (p.order_class !== undefined && p.order_class !== "simple") {
        demand(p.order_class === "oco" &&
            ["equity", "etf"].includes(i.book) &&
            p.side === "sell" &&
            p.type === "limit" &&
            Number.isInteger(q), "intent", "unsupported native exit group");
        const stop = numeric(p.stop_loss?.stop_price, "intent.oco.stop"), target = numeric(p.take_profit?.limit_price, "intent.oco.target");
        demand(stop > 0 &&
            target > stop &&
            target === Number(p.limit_price) &&
            Math.abs(stop / i.tick - Math.round(stop / i.tick)) < 1e-5 &&
            Math.abs(target / i.tick - Math.round(target / i.tick)) < 1e-5, "intent", "invalid native OCO prices");
    }
    return p;
}
function assertSignal(s, i, now = Date.now()) {
    demand(s && s.symbol === i.symbol && s.book === i.book, "signal", "asset binding mismatch");
    demand([s.entry, s.stop, s.score, s.at, s.expires].every(Number.isFinite) &&
        s.entry > s.stop &&
        s.stop > 0, "signal", "invalid values");
    demand(s.at <= now + 2000 &&
        s.expires >= now &&
        s.expires > s.at &&
        s.expires - s.at <= 120000, "signal", "invalid signal window");
    const p = s.exit;
    demand(p &&
        [
            p.tp1R,
            p.tp2R,
            p.tp1Fraction,
            p.tp2Fraction,
            p.lockFraction,
            p.trailR,
            p.maxHoldHours,
        ].every(Number.isFinite), "signal.exit", "non-finite policy");
    demand(p.tp1R > 0 &&
        p.tp2R > p.tp1R &&
        p.tp1Fraction >= 0 &&
        p.tp2Fraction >= 0 &&
        p.tp1Fraction + p.tp2Fraction <= 1 &&
        p.lockFraction >= 0.1 &&
        p.lockFraction <= 0.9 &&
        p.trailR > 0 &&
        p.maxHoldHours > 0 &&
        p.maxHoldHours <= 72, "signal.exit", "out of bounds");
    return s;
}
function assertJournal(s, account) {
    demand(s && s.schema === "HARPOON-XXX-1" && s.accountId === account, "journal", "schema/account mismatch");
    demand(Array.isArray(s.campaigns) &&
        Array.isArray(s.intents) &&
        Array.isArray(s.plugins) &&
        Array.isArray(s.events), "journal", "collections missing");
    demand(Number.isInteger(s.sequence) &&
        s.sequence >= 0 &&
        typeof s.paused === "boolean" &&
        s.research, "journal", "state fields missing");
    demand(new Set(s.intents.map((i) => i.id)).size === s.intents.length &&
        new Set(s.campaigns.map((c) => c.id)).size === s.campaigns.length, "journal", "duplicate identity");
    for (const c of s.campaigns)
        demand(c &&
            c.instrument &&
            c.policy &&
            (0, types_1.positive)(c.risk) &&
            (0, types_1.positive)(c.stop) &&
            typeof c.closed === "boolean", "journal", "invalid campaign");
    for (const c of s.campaigns) {
        if (c.exitPlan)
            assertExitPlan(c);
        if (c.evaluation)
            assertPositionEvaluation(c.evaluation, Date.now());
        if (c.orderRetry) {
            demand(Object.keys(c.orderRetry).every((k) => ["protect", "urgent", "profit"].includes(k)), "journal", "invalid retry class");
            for (const retry of Object.values(c.orderRetry))
                assertRetryState(retry);
        }
        if (c.partialEntryRisk)
            assertPartialEntryRisk(c, s.intents);
    }
    return s;
}
function assertExitPlan(c) {
    const p = c.exitPlan;
    demand(p &&
        typeof p.id === "string" &&
        [
            "tp1",
            "tp2",
            "stop",
            "flatten",
            "expiry",
            "time",
            "signal",
            "stagnation",
        ].includes(p.kind) &&
        (0, types_1.positive)(p.detectedAt) &&
        (0, types_1.positive)(p.targetSold) &&
        ["CANCELING", "READY", "WORKING", "COMPLETE"].includes(p.status), "exit-plan", "invalid durable exit plan");
    if (p.minimumPrice !== undefined)
        demand((0, types_1.positive)(p.minimumPrice), "exit-plan", "invalid limit floor");
    return p;
}
function assertCampaignInventory(c, qty) {
    demand(Number.isFinite(qty) && qty >= 0 && (0, types_1.positive)(c.instrument.multiplier), "inventory", "invalid owned quantity/multiplier");
}
function assertFreshQuote(q, now = Date.now(), maxAge = 15000) {
    demand((0, types_1.fresh)(q, now, maxAge), "quote", "missing/stale/crossed quote");
    return q;
}
function assertSelectorModel(m, through = Date.now()) {
    demand(m &&
        m.version === "12.0.0" &&
        m.weights?.length === 9 &&
        m.means?.length === 8 &&
        m.scales?.length === 8, "selector.model", "shape");
    demand([
        ...m.weights,
        ...m.means,
        ...m.scales,
        m.bias,
        m.margin,
        m.through,
        m.cutoff,
    ].every(Number.isFinite) &&
        m.scales.every((n) => n > 0) &&
        m.through < m.cutoff &&
        m.through < through &&
        m.n >= 240 &&
        m.days >= 40, "selector.model", "invalid fit or time boundary");
    demand(m.features?.join() ===
        "rvol,momentum_bps,spread_bps,volume_acceleration,atr_pct,vwap_distance,sector_relative_bps,session_minutes", "selector.model", "feature contract mismatch");
    return m;
}
function assertBars(rows) {
    demand(Array.isArray(rows), "bars", "array required");
    for (const b of rows)
        demand(b &&
            [b.o, b.h, b.l, b.c].every(types_1.positive) &&
            Number.isFinite(b.v) &&
            b.v >= 0 &&
            Number.isFinite(Date.parse(b.t)) &&
            b.h >= Math.max(b.o, b.c, b.l) &&
            b.l <= Math.min(b.o, b.c), "bars", "Invalid OHLCV");
    demand(new Set(rows.map((b) => b.t)).size === rows.length, "bars", "duplicate timestamps");
    return rows;
}
/** Structural telemetry validation does not imply operational coverage or broker protection. */
function assertPositionEvaluation(r, now) {
    demand(r && typeof r.campaign === "string" && typeof r.symbol === "string" &&
        ["equity", "etf", "crypto", "options"].includes(r.book) &&
        ["lastAttempt", "lastCompleted", "quoteAt", "syncAt"].every((k) => Number.isFinite(r[k]) && r[k] >= 0) &&
        r.lastAttempt > 0 && r.lastAttempt <= now + 2000 && r.lastCompleted <= now + 2000 &&
        ["STARTING", "EVALUATED", "STALE_RECONCILIATION", "OWNERSHIP_UNCERTAIN", "PENDING_ENTRY", "NO_INVENTORY", "STALE_SESSION", "MARKET_CLOSED", "STALE_DATA", "ERROR"].includes(r.outcome), "position-evaluation", "invalid per-position evaluation telemetry");
    return r;
}
function assertOperationalCoverage(coverage) {
    demand(coverage.entrySafe === true && coverage.fresh + coverage.sessionGated === coverage.total &&
        coverage.completed + coverage.sessionGated >= coverage.total, "position-coverage", coverage.state + ": " + coverage.detail);
    return coverage;
}
function assertRetryState(r) {
    demand(r && Number.isInteger(r.failures) && r.failures >= 1 && r.failures <= 30 &&
        (0, types_1.positive)(r.lastAt) && Number.isFinite(r.nextAt) && r.nextAt > r.lastAt && r.nextAt - r.lastAt <= 60000 &&
        typeof r.lastError === "string" && typeof r.lastIntent === "string" && typeof r.requestKey === "string", "protection-retry", "invalid persisted retry budget");
    return r;
}
function assertPartialEntryRisk(c, intents) {
    const r = c.partialEntryRisk;
    demand(r && r.source === "BROKER_RECONCILIATION" &&
        typeof r.entryId === "string" && intents.some((i) => i.id === r.entryId && i.campaign === c.id && i.kind === "entry") &&
        [r.firstObservedAt, r.lastObservedAt, r.deadlineAt].every(types_1.positive) &&
        r.lastObservedAt >= r.firstObservedAt && r.deadlineAt > r.firstObservedAt &&
        [r.heldQty, r.coveredQty].every((n) => Number.isFinite(n) && n >= 0) &&
        r.coveredQty <= r.heldQty + c.instrument.step * 1e-6 &&
        (r.cancelRequestedAt === null || (0, types_1.positive)(r.cancelRequestedAt)) &&
        ["WAIT_CANCEL", "WAIT_PROTECTION", "UNVERIFIED", "RESOLVED"].includes(r.status) &&
        typeof r.overdue === "boolean" &&
        (r.overdueAt === undefined || ((0, types_1.positive)(r.overdueAt) && r.overdueAt >= r.deadlineAt)), "partial-entry-risk", "invalid durable observation or entry identity");
    demand(r.status === "RESOLVED"
        ? (0, types_1.positive)(r.resolvedAt) && r.resolvedAt >= r.firstObservedAt && !r.overdue &&
            ["CONFIRMED_FLAT", "CONFIRMED_PROTECTION"].includes(r.resolution || "")
        : r.resolvedAt === undefined && r.resolution === undefined, "partial-entry-risk", "invalid resolution evidence");
    return r;
}
/** Count OCO siblings once, while reserving unresolved and cancel-pending quantities. */
function assertSellReservation(c, intents, held, requested) {
    const reservations = new Map();
    const terminal = new Set(["filled", "canceled", "expired", "rejected", "replaced"]);
    for (const i of intents.filter((x) => x.campaign === c.id && x.payload.side === "sell" && !terminal.has(x.status))) {
        demand(!["UNKNOWN", "SUBMITTING"].includes(i.status), "sell-reservation", "uncertain order must reconcile before another sale");
        const n = Number(i.order?.qty || i.payload.qty) - Number(i.order?.filled_qty || 0);
        demand(Number.isFinite(n) && n >= 0, "sell-reservation", "invalid pending sale quantity");
        const group = i.parentId || i.id;
        reservations.set(group, Math.max(reservations.get(group) || 0, n));
    }
    const reserved = [...reservations.values()].reduce((a, b) => a + b, 0);
    demand(Number.isFinite(held) && (0, types_1.positive)(requested) && requested + reserved <= held + c.instrument.step * 1e-6, "sell-reservation", "sell quantity plus pending reservations exceeds reconciled inventory");
    return { held, requested, reserved };
}
