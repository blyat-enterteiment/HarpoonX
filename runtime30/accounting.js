"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FeeLedger = void 0;
exports.executionMetrics = executionMetrics;
const policy_1 = require("./policy");
/** Reported account activities, independently fetched. Never infer missing fees as a zero all-in cost. */
class FeeLedger {
    api;
    store;
    key;
    state = {
        status: "NOT_RUN",
        lastSuccess: 0,
        rows: [],
        reportedUsdFees: null,
        complete: false,
    };
    constructor(api, store, key) {
        this.api = api;
        this.store = store;
        this.key = key;
    }
    async load() {
        const saved = await this.store.get(this.key);
        if (saved?.source === "ALPACA_ACCOUNT_ACTIVITIES" &&
            Array.isArray(saved.rows))
            this.state = saved;
    }
    async refresh(from) {
        if (!Number.isFinite(from) || from <= 0)
            throw Error("Fee ledger requires actual journal inception");
        const before = Date.now(), rows = [], seen = new Set();
        let token = "", complete = false;
        this.state.status = "FETCHING";
        try {
            for (let page = 0; page < 100; page++) {
                const query = new URLSearchParams({
                    after: new Date(from).toISOString(),
                    until: new Date(before).toISOString(),
                    direction: "asc",
                    page_size: "100",
                    ...(token ? { page_token: token } : {}),
                });
                const response = await this.api.request("/v2/account/activities?" + query);
                if (!Array.isArray(response) || response.length > 100)
                    throw Error("Invalid activity page");
                for (const row of response) {
                    if (!row ||
                        typeof row.id !== "string" ||
                        !row.id ||
                        typeof row.activity_type !== "string" ||
                        seen.has(row.id))
                        throw Error("Invalid or repeated activity identity");
                    seen.add(row.id);
                    rows.push(row);
                }
                if (response.length < 100) {
                    complete = true;
                    break;
                }
                const next = response.at(-1).id;
                if (next === token)
                    throw Error("Activity pagination stalled");
                token = next;
            }
            if (!complete)
                throw Error("Activity coverage exceeds 10,000-row bound; report incomplete");
            const feeRows = rows.filter((r) => ["FEE", "PTC", "PTR", "CFEE"].includes(r.activity_type));
            const usd = feeRows.filter((r) => r.activity_type !== "CFEE" || r.currency === "USD");
            if (usd.some((r) => r.net_amount === null ||
                r.net_amount === undefined ||
                r.net_amount === "" ||
                !Number.isFinite(Number(r.net_amount))))
                throw Error("USD fee has no validated amount");
            const state = {
                source: "ALPACA_ACCOUNT_ACTIVITIES",
                status: "OBSERVED",
                from,
                through: before,
                lastSuccess: Date.now(),
                activityRows: rows.length,
                rows: feeRows,
                reportedUsdFees: usd.reduce((n, r) => n - Number(r.net_amount), 0),
                unpricedFees: feeRows.filter((r) => !usd.includes(r)),
                coverageComplete: true,
                complete: false,
                basis: "Reported USD charges/rebates only. CFEE without explicit USD currency is unpriced; all-in net is not certified.",
            };
            await this.store.put(this.key, state);
            this.state = state;
        }
        catch (e) {
            this.state = {
                ...this.state,
                status: "ERROR",
                error: String(e),
                complete: false,
            };
            throw e;
        }
    }
    view() {
        return structuredClone(this.state);
    }
}
exports.FeeLedger = FeeLedger;
const distribution = (values) => {
    const a = values
        .filter((x) => Number.isFinite(x) && x >= 0)
        .sort((x, y) => x - y);
    return {
        samples: a.length,
        medianMs: a.length ? a[Math.floor((a.length - 1) * 0.5)] : null,
        p95Ms: a.length ? a[Math.floor((a.length - 1) * 0.95)] : null,
    };
};
function executionMetrics(campaigns, intents, cfg) {
    let gross = 0, estimatedFees = 0, giveback = 0, closed = 0, wins = 0, uncoveredObservedMs = 0;
    for (const c of campaigns) {
        const f = (0, policy_1.fills)(c, intents);
        gross += f.gross;
        estimatedFees +=
            c.book === "crypto"
                ? ((f.paid + f.received) * cfg.cryptoFeeBps) / 10000
                : c.book === "options"
                    ? (f.bought + f.sold) * cfg.optionsFeePerContract
                    : 0;
        uncoveredObservedMs += c.protectionTelemetry?.uncoveredTotalMs || 0;
        if (c.closed && f.bought > 0) {
            closed++;
            if (f.gross > 0)
                wins++;
            giveback += Math.max(0, (c.protectionTelemetry?.observedPeakPnl || 0) - f.gross);
        }
    }
    const exits = intents.filter((i) => i.kind !== "entry" && i.kind !== "protect");
    return {
        source: "BROKER_FILLS_AND_OBSERVED_QUOTES",
        realizedGrossUsd: gross,
        estimatedFeesUsd: estimatedFees,
        estimatedNetUsd: gross - estimatedFees,
        closedCampaigns: closed,
        grossWinRate: closed ? wins / closed : null,
        closedGrossGivebackUsd: closed ? giveback : null,
        uncoveredObservedMs,
        latency: {
            quoteToDecision: distribution(exits
                .filter((i) => i.decisionAt && i.quoteAt)
                .map((i) => i.decisionAt - i.quoteAt)),
            decisionToAck: distribution(exits
                .filter((i) => i.ackAt && i.decisionAt)
                .map((i) => i.ackAt - i.decisionAt)),
            submitToAck: distribution(exits.filter((i) => i.ackAt).map((i) => i.ackAt - i.at)),
            ackToFillObservation: distribution(exits
                .filter((i) => i.ackAt && i.fillObservedAt)
                .map((i) => i.fillObservedAt - i.ackAt)),
        },
        basis: "Actual fill prices already include realized price impact/spread; no second slippage deduction. Fees are separate estimates. Giveback uses observed gross peaks on closed campaigns; coverage duration is sampled, not an exact venue guarantee.",
    };
}
