// Additive PROFIT8 offline research fork of ultimate_replay_roadmap9.js.
// Frozen predecessor is unchanged. New behavior requires options.profit8.
// Historical/synthetic simulation only; no broker or production coordinator route.
"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FundedPortfolioReplayError = exports.FundedEntryBudgetError = exports.DEFAULT_REPLAY_LIMITS = exports.UnresolvedHoldingExposureError = exports.UnobservedEntryError = void 0;
exports.planSignalEntryAt = planSignalEntryAt;
exports.planCalendarHolding = planCalendarHolding;
exports.causalReferencePrice = causalReferencePrice;
exports.planFundedEntry = planFundedEntry;
exports.verifyFundedEntryFill = verifyFundedEntryFill;
exports.planFundedIocLimit = planFundedIocLimit;
exports.opportunities = opportunities;
exports.nextTrailingStop = nextTrailingStop;
exports.replayCampaign = replayCampaign;
exports.runStudy = runStudy;
exports.replayFundedPortfolio = replayFundedPortfolio;
exports.PROFIT8_REPLAY_LIMITS = Object.freeze({ capitalUsd: 20000, riskFraction: 0.0025,
    openRiskFraction: 0.0025, grossFraction: 0.12, assetFraction: 0.12,
    dailyLoss: 0.02, maxDrawdown: 0.08 });
exports.planProfit8FundedEntry = planProfit8FundedEntry;
exports.planProfit8IocLimit = planProfit8IocLimit;
exports.selectProfit8Quantity = selectProfit8Quantity;
exports.replayProfit8Teacher = replayProfit8Teacher;
exports.profit8BasisWeights = profit8BasisWeights;
exports.profit8KnownAt = profit8KnownAt;
const ultimate_contracts_1 = require("./ultimate_contracts");
const ultimate_stats_1 = require("./ultimate_stats");
const ultimate_frequency_1 = require("./ultimate_frequency");
const policy_1 = require("./policy");
const ultimate_reservations_1 = require("./ultimate_reservations");
/** A missing execution observation does not prove that a planned order was unfilled. */
class UnobservedEntryError extends Error {
    details;
    code = "UNOBSERVED_ENTRY";
    constructor(details) {
        super("UNOBSERVED_ENTRY: " + JSON.stringify(details));
        this.details = details;
        this.name = "UnobservedEntryError";
    }
}
exports.UnobservedEntryError = UnobservedEntryError;
/** Earliest supported bar-open execution time, determined without future bars. */
function planSignalEntryAt(decisionAt, sessions) {
    (0, ultimate_contracts_1.need)(Number.isSafeInteger(decisionAt), "signal decision timestamp");
    const session = sessions.find((s) => s.open <= decisionAt && decisionAt < s.close);
    if (!session)
        return null;
    const planned = session.open + Math.ceil((decisionAt - session.open) / 300000) * 300000;
    // Preserve the existing one-bar-before-close admission boundary. This is a
    // scheduling constraint, not a check that the historical execution exists.
    return planned < session.close - 300000 ? planned : null;
}
/** An opened position without an executable exit cannot disappear from a curve. */
class UnresolvedHoldingExposureError extends Error {
    details;
    code = "UNRESOLVED_HOLDING_EXPOSURE";
    constructor(details) {
        // ResearchLab workers persist error.message. Keep the unresolved position
        // in that transport as well as typed details; a worker boundary must not
        // erase inventory merely because no complete portfolio can be returned.
        super("UNRESOLVED_HOLDING_EXPOSURE: " + JSON.stringify(details));
        this.details = details;
        this.name = "UnresolvedHoldingExposureError";
    }
}
exports.UnresolvedHoldingExposureError = UnresolvedHoldingExposureError;
/** Scheduling-only result: separates a refused entry from unresolved inventory. */
function planCalendarHolding(signal, firstOpen, data, p) {
    const base = { decisionAt: signal.at, plannedEntryAt: firstOpen, positionOpened: false };
    if (p.kind !== "ALPACA_PROXY" || signal.hypothesis !== "CLOSED_CHANNEL")
        return { ...base, status: "NOT_APPLICABLE", reason: null, deadlineAt: null };
    (0, ultimate_contracts_1.need)(Number.isSafeInteger(firstOpen) && firstOpen >= signal.at, "planned entry chronology");
    // An incomplete calendar is not evidence that its last listed session is the
    // last executable session before the limit. Establish coverage first.
    const roadmapHours = signal.metadata?.roadmapHorizonHours ?? 72;
    (0, ultimate_contracts_1.need)([24,48,72].includes(roadmapHours), "ROADMAP_HORIZON");
    const target72h = signal.at + roadmapHours * 3600000;
    if (!data.sessions.some((s) => Number.isSafeInteger(s.open) &&
        Number.isSafeInteger(s.close) && s.open < s.close && s.close >= target72h))
        return { ...base, status: "REFUSED_BEFORE_ENTRY", reason: "CALENDAR_HORIZON_NOT_COVERED", deadlineAt: null };
    let target;
    try {
        // Runtime anchors at decision/submission time, not a later pending fill.
        target = (0, policy_1.deadlineFor)("equity", signal.at, roadmapHours, data.sessions);
    }
    catch {
        return { ...base, status: "REFUSED_BEFORE_ENTRY", reason: "NO_CALENDAR_HOLDING_WINDOW", deadlineAt: null };
    }
    const session = data.sessions.find((s) => s.open <= target && target < s.close);
    if (!session)
        return { ...base, status: "REFUSED_BEFORE_ENTRY", reason: "NO_EXECUTABLE_EXIT_SESSION", deadlineAt: null };
    // The validated resolution is five minutes. Round earlier using only the
    // supplied session and grid, never a later price or future bar existence.
    const deadlineAt = session.open + Math.floor((target - session.open) / 300000) * 300000;
    return firstOpen >= deadlineAt
        ? { ...base, status: "REFUSED_BEFORE_ENTRY", reason: "ENTRY_AT_OR_AFTER_DEADLINE", deadlineAt }
        : { ...base, status: "SCHEDULED", reason: null, deadlineAt };
}
exports.DEFAULT_REPLAY_LIMITS = {
    capitalUsd: 20000,
    riskFraction: 0.0025,
    openRiskFraction: 0.015,
    grossFraction: 0.5,
    assetFraction: 0.12,
    dailyLoss: 0.02,
    maxDrawdown: 0.08,
};
/** Last completed close available at the decision; a future fill is not a quote. */
function causalReferencePrice(signal, series) {
    let latest;
    for (const bar of series.bars) {
        if (Number.isSafeInteger(bar.t) && Number.isSafeInteger(bar.end) &&
            Number.isSafeInteger(bar.availableAt) && bar.t < bar.end &&
            bar.end <= bar.availableAt && bar.availableAt <= signal.at &&
            (!latest || bar.end > latest.end))
            latest = bar;
    }
    const valid = latest !== undefined && Number.isFinite(latest.c) && latest.c > 0;
    return {
        status: valid ? "AVAILABLE" : "NO_CAUSAL_PRICE",
        price: valid ? latest.c : null,
        sourceBarAt: latest?.t ?? null,
        sourceAvailableAt: latest?.availableAt ?? null,
        decisionAt: signal.at,
        reason: valid ? null : latest ? "INVALID_LAST_AVAILABLE_CLOSE" : "NO_AVAILABLE_COMPLETED_BAR",
    };
}
/** Same four sizing coefficients; only the price source is causal. */
function planFundedEntry(signal, series, p, limits, state) {
    const reference = causalReferencePrice(signal, series);
    if (reference.status !== "AVAILABLE")
        return { status: "NO_CAUSAL_PRICE", reference };
    const px = reference.price, { equity, openRisk, notional } = state;
    (0, ultimate_contracts_1.need)([equity, openRisk, notional].every(Number.isFinite) && equity > 0 && openRisk >= 0 && notional >= 0, "funded sizing state");
    const riskUnit = signal.stopDistance * series.pointValue + 2 * p.costs.perSideUsd +
        (2 * px * series.pointValue * (p.costs.spreadBps / 2 + p.costs.slippageBps)) / 10000;
    (0, ultimate_contracts_1.need)(Number.isFinite(riskUnit) && riskUnit > 0, "funded risk unit");
    const quantity = Math.floor(Math.min((equity * limits.riskFraction) / riskUnit, Math.max(0, equity * limits.openRiskFraction - openRisk) / riskUnit, Math.max(0, equity * limits.grossFraction - notional) / px, (equity * limits.assetFraction) / px));
    return {
        status: "PLANNED", reference, quantity, riskUnit,
        riskBudgetUsd: Math.max(0, Math.min(equity * limits.riskFraction, equity * limits.openRiskFraction - openRisk)),
        notionalBudgetUsd: Math.max(0, Math.min(equity * limits.assetFraction, equity * limits.grossFraction - notional)),
    };
}
/** Check a fixed-size modeled fill; never resize it using its future price. */
function verifyFundedEntryFill(trade, signal, series, p, budgets) {
    const numericalToleranceUsd = 1e-8;
    const entry = Number.isFinite(trade.entry) && trade.entry > 0 ? trade.entry : null;
    const qty = Number.isSafeInteger(trade.quantity) && trade.quantity > 0 ? trade.quantity : null;
    const actualEntryNotionalUsd = entry !== null && qty !== null ? qty * entry * series.pointValue : null;
    const entryFeeUsd = qty !== null ? qty * p.costs.perSideUsd : null;
    const distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
    const friction = (p.costs.spreadBps / 2 + p.costs.slippageBps) / 10000;
    const modeledRiskUsd = entry !== null && qty !== null
        ? qty * (distance * series.pointValue + 2 * p.costs.perSideUsd + 2 * entry * series.pointValue * friction)
        : null;
    const breaches = [];
    if (trade.id !== signal.id || trade.symbol !== signal.symbol || series.symbol !== signal.symbol || trade.direction !== signal.direction)
        breaches.push("MODELED_FILL_NOT_BOUND_TO_SIGNAL");
    if (qty !== budgets.plannedQuantity || !Number.isSafeInteger(budgets.plannedQuantity) || budgets.plannedQuantity <= 0)
        breaches.push("FILLED_QUANTITY_DIFFERS_FROM_EX_ANTE_PLAN");
    if (!Number.isSafeInteger(trade.opened) || trade.opened < signal.at || entry === null)
        breaches.push("INVALID_MODELED_FILL");
    if (!Number.isFinite(budgets.riskBudgetUsd) || budgets.riskBudgetUsd < 0 || modeledRiskUsd === null || !Number.isFinite(modeledRiskUsd))
        breaches.push("RISK_BUDGET_OR_FILL_RISK_UNVERIFIABLE");
    else if (modeledRiskUsd > budgets.riskBudgetUsd + numericalToleranceUsd)
        breaches.push("MODELED_FILL_RISK_EXCEEDS_EX_ANTE_BUDGET");
    if (!Number.isFinite(budgets.notionalBudgetUsd) || budgets.notionalBudgetUsd < 0 || actualEntryNotionalUsd === null || !Number.isFinite(actualEntryNotionalUsd))
        breaches.push("NOTIONAL_BUDGET_OR_FILL_UNVERIFIABLE");
    else if (actualEntryNotionalUsd > budgets.notionalBudgetUsd + numericalToleranceUsd)
        breaches.push("MODELED_FILL_NOTIONAL_EXCEEDS_EX_ANTE_BUDGET");
    if (typeof budgets.cashBudgetUsd !== "number" || !Number.isFinite(budgets.cashBudgetUsd) || actualEntryNotionalUsd === null || entryFeeUsd === null)
        breaches.push("CONSERVATIVE_CASH_BUDGET_UNVERIFIABLE");
    else if (actualEntryNotionalUsd + entryFeeUsd > budgets.cashBudgetUsd + numericalToleranceUsd)
        breaches.push("MODELED_FILL_COST_EXCEEDS_CONSERVATIVE_CASH");
    return {
        status: breaches.length ? "NO_FACTIBLE" : "VERIFIED",
        actualEntryNotionalUsd, modeledRiskUsd, entryFeeUsd, numericalToleranceUsd,
        budgets: { ...budgets, cashBudgetUsd: budgets.cashBudgetUsd ?? null },
        breaches,
        exposure: { signalId: signal.id, symbol: signal.symbol, decisionAt: signal.at,
            openedAt: trade.opened, entryPrice: entry, remainingQuantityAtEntry: qty },
        economicPnlUsd: null,
    };
}
class FundedEntryBudgetError extends Error {
    details;
    code = "FUNDED_ENTRY_BUDGET_BREACH";
    constructor(details) {
        super("FUNDED_ENTRY_BUDGET_BREACH: " + JSON.stringify(details));
        this.details = details;
        this.name = "FundedEntryBudgetError";
    }
}
exports.FundedEntryBudgetError = FundedEntryBudgetError;
/** A buy limit fixed before reading the modeled next opening. */
function planFundedIocLimit(signal, series, p, budgets) {
    (0, ultimate_contracts_1.need)(signal.direction === 1 && series.pointValue === 1 &&
        Number.isSafeInteger(budgets.plannedQuantity) && budgets.plannedQuantity > 0 &&
        [budgets.riskBudgetUsd, budgets.notionalBudgetUsd, budgets.cashBudgetUsd]
            .every(v => typeof v === "number" && Number.isFinite(v) && v >= 0), "IOC ex-ante budget contract");
    const q = budgets.plannedQuantity;
    const distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
    const fee = p.costs.perSideUsd;
    const friction = (p.costs.spreadBps / 2 + p.costs.slippageBps) / 10000;
    const baseRisk = q * (distance * series.pointValue + 2 * fee);
    const riskPriceCeiling = friction > 0
        ? (budgets.riskBudgetUsd - baseRisk) / (2 * q * series.pointValue * friction)
        : baseRisk <= budgets.riskBudgetUsd + 1e-8 ? Infinity : -Infinity;
    const rawCeiling = Math.min(riskPriceCeiling, budgets.notionalBudgetUsd / (q * series.pointValue), (budgets.cashBudgetUsd - q * fee) / (q * series.pointValue));
    const priceCeiling = Number.isFinite(rawCeiling) ? round(rawCeiling, series.tick, false) : null;
    return {
        status: priceCeiling !== null && priceCeiling >= series.tick ? "PLANNED" : "REFUSED_BEFORE_ENTRY",
        reason: priceCeiling !== null && priceCeiling >= series.tick ? null : "NO_PRICE_WITHIN_APPROVED_BUDGET",
        priceCeiling: priceCeiling !== null && priceCeiling >= series.tick ? priceCeiling : null,
        decisionAt: signal.at, plannedEntryAt: signal.plannedEntryAt ?? null,
        quantity: q, roundedStopDistance: distance, baseRiskUsd: baseRisk,
        budgets: { ...budgets },
        model: "BUY_IOC_AT_PLANNED_OPEN_ONLY;FRICTION_AND_TICK_INCLUDED;NO_QUEUE_CLAIM",
    };
}
const efficiency = (a) => {
    const changes = a.slice(1).map((b, i) => Math.abs(b.c - a[i].c)), sum = changes.reduce((x, y) => x + y, 0);
    return sum > 0 ? Math.abs(a.at(-1).c - a[0].c) / sum : 0;
};
const atr = (a) => (0, ultimate_stats_1.mean)(a
    .slice(1)
    .map((b, i) => Math.max(b.h - b.l, Math.abs(b.h - a[i].c), Math.abs(b.l - a[i].c))));
const round = (n, tick, up) => (up ? Math.ceil(n / tick - 1e-8) : Math.floor(n / tick + 1e-8)) * tick;
function opportunities(data, p, options) {
    if (options?.windows !== undefined)
        (0, ultimate_contracts_1.need)(Array.isArray(options.windows) &&
            options.windows.length > 0 && new Set(options.windows).size === options.windows.length &&
            options.windows.every(w => w === "OPEN90" || w === "CLOSE90"), "opportunity windows");
    const out = [], funnel = {
        sessions: 0,
        incompleteSessions: 0,
        warmup: 0,
        evaluated: 0,
        accepted: 0,
        dataGap: 0,
    };
    for (const series of data.series) {
        const indexes = new Map(series.bars.map((b, i) => [b, i]));
        const groups = data.sessions.map((session) => series.bars.filter((b) => b.t >= session.open && b.end <= session.close));
        const previousDays = [];
        for (let day = 0; day < data.sessions.length; day++) {
            const session = data.sessions[day], bars = groups[day];
            const split = data.splitEvents.filter((e) => e.symbol === series.symbol &&
                e.at <= session.open &&
                (day === 0 || e.at > data.sessions[day - 1].open));
            if (split.length) {
                const ratio = split.reduce((n, e) => n * e.ratio, 1);
                for (const old of previousDays) {
                    const adjust = (b) => ({
                        ...b,
                        o: b.o / ratio,
                        h: b.h / ratio,
                        l: b.l / ratio,
                        c: b.c / ratio,
                        v: b.v * ratio,
                        ...(b.vw === undefined ? {} : { vw: b.vw / ratio }),
                    });
                    old.daily = adjust(old.daily);
                    old.bars = old.bars.map(adjust);
                }
            }
            if (!bars.length)
                continue;
            funnel.sessions++;
            const completeSession = !(bars.length !== (session.close - session.open) / 300000 ||
                bars[0].t !== session.open ||
                bars.at(-1).end !== session.close ||
                bars.some((b, i) => i && b.t !== bars[i - 1].end));
            // Full-session completeness is a retrospective diagnostic and determines
            // whether a completed daily observation can enter subsequent history. It
            // must never decide whether an earlier intraday signal existed.
            if (!completeSession)
                funnel.incompleteSessions++;
            const fired = new Set(), prior = previousDays.filter((x) => x.daily.availableAt <= session.open).slice(-50), daily = prior.map((x) => x.daily);
            const priorBars = prior.slice(-2).flatMap((x) => x.bars);
            let vol = 0, vwSum = 0, square = 0, prefixComplete = true, priorAvailableAt = -Infinity;
            for (let j = 0; j < bars.length; j++) {
                const b = bars[j], x = b.vw ?? (b.h + b.l + b.c) / 3;
                prefixComplete = prefixComplete &&
                    b.t === session.open + j * 300000 && b.end === b.t + 300000;
                if (!prefixComplete || b.end > b.availableAt || priorAvailableAt > b.availableAt) {
                    prefixComplete = false;
                    funnel.dataGap++;
                    continue;
                }
                priorAvailableAt = Math.max(priorAvailableAt, b.availableAt);
                vol += b.v;
                vwSum += x * b.v;
                square += x * x * b.v;
                if (j < 3 || prior.length < 20 || !b.v || !vol) {
                    funnel.warmup++;
                    continue;
                }
                // Do not consume a daily hypothesis/direction quota outside the chosen
                // windows. Prefix volume and VWAP above still use the entire causal day.
                if (options?.windows && !options.windows.some(window => window === "OPEN90"
                    ? b.availableAt >= session.open && b.availableAt < Math.min(session.close, session.open + 90 * 60000)
                    : b.availableAt >= Math.max(session.open, session.close - 90 * 60000) && b.availableAt < session.close))
                    continue;
                const plannedEntryAt = planSignalEntryAt(b.availableAt, data.sessions);
                if (plannedEntryAt === null) {
                    funnel.dataGap++;
                    continue;
                }
                // The hint is derived from the known prefix and grid. A later missing
                // bar may invalidate it; replay resolves the exact planned timestamp.
                const fillIndex = indexes.get(b) + (plannedEntryAt - b.t) / 300000;
                const observed = [...priorBars, ...bars.slice(0, j + 1)].slice(-15), risk = Math.max(series.tick * 2, atr(observed));
                const er = efficiency(bars.slice(Math.max(0, j - 11), j + 1));
                const rangeHigh = Math.max(...bars.slice(0, 3).map((z) => z.h)), rangeLow = Math.min(...bars.slice(0, 3).map((z) => z.l));
                const historicalVolume = (0, ultimate_stats_1.mean)(prior
                    .slice(-20)
                    .map((z) => z.bars.slice(0, j + 1).reduce((n, z) => n + z.v, 0))), rvol = historicalVolume > 0 ? vol / historicalVolume : 0;
                const vw = vwSum / vol, sigma = Math.sqrt(Math.max(0, square / vol - vw * vw));
                const add = (hypothesis, direction, stopDistance, target) => {
                    const key = hypothesis + ":" + direction;
                    if (fired.has(key) || (direction === -1 && p.kind === "ALPACA_PROXY"))
                        return;
                    fired.add(key);
                    out.push({
                        id: (0, ultimate_contracts_1.digest)([series.symbol, hypothesis, b.availableAt, direction]),
                        symbol: series.symbol,
                        hypothesis,
                        direction,
                        at: b.availableAt,
                        plannedEntryAt,
                        index: fillIndex,
                        stopDistance: Math.max(series.tick * 2, stopDistance),
                        regime: er,
                        target,
                    });
                    funnel.accepted++;
                };
                funnel.evaluated++;
                if (rvol >= 1.5) {
                    if (b.c > rangeHigh)
                        add("OPENING_BREAKOUT", 1, Math.max(risk, (rangeHigh - rangeLow) / 2));
                    if (b.c < rangeLow)
                        add("OPENING_BREAKOUT", -1, Math.max(risk, (rangeHigh - rangeLow) / 2));
                }
                if (prior.length >= 50) {
                    let ema = daily[0].c;
                    for (const z of daily.slice(1))
                        ema += (2 / 51) * (z.c - ema);
                    if (b.c > Math.max(...daily.slice(-20).map((z) => z.h)) &&
                        daily.at(-1).c > ema)
                        add("CLOSED_CHANNEL", 1, atr(daily.slice(-15)));
                    if (b.c < Math.min(...daily.slice(-20).map((z) => z.l)) &&
                        daily.at(-1).c < ema)
                        add("CLOSED_CHANNEL", -1, atr(daily.slice(-15)));
                }
                if (j >= 12 && er <= 0.3 && sigma > series.tick) {
                    if (b.c <= vw - 2 * sigma)
                        add("VWAP_REVERSION", 1, risk, vw);
                    if (b.c >= vw + 2 * sigma)
                        add("VWAP_REVERSION", -1, risk, vw);
                }
            }
            if (completeSession && prefixComplete)
                previousDays.push({
                    bars,
                    daily: {
                        t: session.open,
                        end: session.close,
                        availableAt: Math.max(...bars.map((b) => b.availableAt)),
                        o: bars[0].o,
                        h: Math.max(...bars.map((b) => b.h)),
                        l: Math.min(...bars.map((b) => b.l)),
                        c: bars.at(-1).c,
                        v: vol,
                    },
                });
        }
    }
    return {
        signals: out.sort((a, b) => a.at - b.at || a.symbol.localeCompare(b.symbol)),
        funnel,
    };
}
/** Shared long/short exit transition: only completed observations can tighten a stop. */
function nextTrailingStop(direction, old, entry, peak, distance, policy, regime) {
    const peakR = (direction * (peak - entry)) / distance;
    if (peakR < (policy === "RUNNER" ? 2 : 1.5))
        return old;
    const trail = policy === "RUNNER" ? 2 : policy === "REGIME" && regime >= 0.5 ? 2.5 : 1.5;
    const lock = entry + direction * peakR * distance * 0.6, candidate = direction === 1
        ? Math.max(lock, peak - trail * distance)
        : Math.min(lock, peak + trail * distance);
    return direction === 1 ? Math.max(old, candidate) : Math.min(old, candidate);
}
function replayCampaign(signal, series, data, p, policy, quantity = 4, costMultiplier = 1, options) {
    (0, ultimate_contracts_1.need)(Number.isInteger(quantity) && quantity > 0 && costMultiplier >= 1, "replay size/cost");
    const hasEntryPlan = signal.plannedEntryAt !== undefined;
    if (hasEntryPlan) {
        (0, ultimate_contracts_1.need)(Number.isSafeInteger(signal.plannedEntryAt) && signal.plannedEntryAt >= signal.at, "entry plan precedes signal decision");
        (0, ultimate_contracts_1.need)(signal.plannedEntryAt === planSignalEntryAt(signal.at, data.sessions), "entry plan differs from causal calendar grid");
    }
    else {
        (0, ultimate_contracts_1.need)(Number.isSafeInteger(signal.index) && signal.index >= 0, "legacy entry index");
    }
    const entryIndex = hasEntryPlan
        ? series.bars.findIndex((b) => b.t === signal.plannedEntryAt)
        : signal.index;
    const first = series.bars[entryIndex], plannedEntryAt = signal.plannedEntryAt ?? first?.t ?? null, dir = signal.direction, friction = ((p.costs.spreadBps / 2 + p.costs.slippageBps) * costMultiplier) / 10000;
    const unobservedEntry = (reason) => {
        throw new UnobservedEntryError({ reason, signalId: signal.id, symbol: signal.symbol,
            hypothesis: signal.hypothesis, policy, decisionAt: signal.at, plannedEntryAt,
            plannedQuantity: quantity, positionOpened: null, exposureUnknown: true, economicPnlUsd: null });
    };
    if (plannedEntryAt === null)
        unobservedEntry("MISSING_LEGACY_ENTRY_OBSERVATION");
    (0, ultimate_contracts_1.need)(plannedEntryAt >= signal.at, "entry precedes signal decision");
    // A calendar refusal is decided before asking whether an execution price is
    // present. In contrast, missing future prices do not imply a refused order.
    const holdingPlan = planCalendarHolding(signal, plannedEntryAt, data, p), calendarHolding = holdingPlan.status !== "NOT_APPLICABLE", strictPath = calendarHolding || hasEntryPlan;
    if (holdingPlan.status === "REFUSED_BEFORE_ENTRY")
        return null;
    if (!first)
        unobservedEntry("MISSING_PLANNED_ENTRY_BAR");
    (0, ultimate_contracts_1.need)(first.t >= signal.at && first.t === plannedEntryAt, "entry timestamp binding");
    const session = data.sessions.find((s) => first.t >= s.open && first.t < s.close);
    (0, ultimate_contracts_1.need)(session !== undefined, "entry outside declared calendar");
    const entry = round(first.o * (1 + dir * friction), series.tick, dir === 1), distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
    const inventoryEvents = options === undefined ? [] : [{
            at: first.t, knownAt: first.t, quantityDelta: quantity,
            feeUsd: quantity * p.costs.perSideUsd * costMultiplier, kind: "ENTRY",
            ...(options?.profit8Trace ? { filledPrice: entry, reason: "ENTRY" } : {})
        }];
    const cashDividends = options?.cashDividends ? (0, ultimate_contracts_1.assertCashDividends)(data) : [];
    if (options?.cashDividends)
        (0, ultimate_contracts_1.need)(p.kind === "ALPACA_PROXY" && dir === 1 && series.pointValue === 1, "cash dividends require long cash-share campaigns");
    let stop = entry - dir * distance, remaining = quantity, realized = -p.costs.perSideUsd * quantity * costMultiplier, fees = -realized, peak = entry, peakPnl = 0, ambiguous = 0, reason = "DATA_ENDED", closed = first.t, pendingStop;
    // Match the existing cash-equity runtime deadline. The supplied session
    // calendar is the scheduling input; no later price or future bar existence
    // chooses the deadline. Calendar publication-time provenance remains a data
    // requirement, not something reconstructed from a successful historical fill.
    let deadline;
    if (calendarHolding) {
        deadline = holdingPlan.deadlineAt;
    }
    else {
        deadline =
            signal.hypothesis === "CLOSED_CHANNEL"
                ? first.t + 72 * 3600000
                : Math.min(session.close - 300000, first.t +
                    (signal.hypothesis === "VWAP_REVERSION" ? 3600000 : 86400000));
    }
    const contractDeadline = Math.min(series.firstNoticeAt ?? Infinity, series.lastTradeAt ?? Infinity) -
        86400000;
    if (data.splitEvents.some((e) => e.symbol === series.symbol && e.at > first.t && e.at <= deadline)) {
        if (hasEntryPlan)
            unobservedEntry("CORPORATE_ACTION_PATH_UNMODELED");
        return null;
    }
    const marks = [], tpDone = [false, false];
    let roadmapReduced = false;
    const unresolved = (reason, encounteredAt) => {
        throw new UnresolvedHoldingExposureError({
            reason,
            signalId: signal.id,
            symbol: signal.symbol,
            hypothesis: signal.hypothesis,
            policy,
            openedAt: first.t,
            decisionAt: signal.at,
            deadlineAt: deadline,
            encounteredAt,
            entryPrice: entry,
            openedQuantity: quantity,
            remainingQuantity: remaining,
            lastKnownMark: marks.at(-1) ?? null,
            realizedPnlUsd: realized,
            economicPnlUsd: null,
        });
    };
    const close = (qty, px, at, why, knownAt = at) => {
        if (qty <= 0)
            return;
        const filled = round(px * (1 - dir * friction), series.tick, dir !== 1), charge = qty * p.costs.perSideUsd * costMultiplier;
        realized += dir * (filled - entry) * qty * series.pointValue - charge;
        fees += charge;
        remaining -= qty;
        if (options !== undefined)
            inventoryEvents.push({ at, knownAt, quantityDelta: -qty,
                feeUsd: charge, kind: "EXIT",
                ...(options?.profit8Trace ? { filledPrice: filled, reason: why } : {}) });
        closed = at;
        reason = why;
    };
    for (let i = entryIndex; i < series.bars.length && remaining; i++) {
        const b = series.bars[i], prior = series.bars[i - 1];
        // An overnight transition cannot jump over a declared session whose
        // entire tape is absent. Legacy no-option scope remains unchanged.
        if (options !== undefined && i > entryIndex && b.t !== prior.end) {
            const previousSession = data.sessions.findIndex(s => s.close === prior.end);
            if (previousSession < 0 || data.sessions[previousSession + 1]?.open !== b.t)
                unresolved("MISSING_SESSION_WITH_OPEN_EXPOSURE", b.t);
        }
        if (i > entryIndex &&
            b.t !== prior.end &&
            !data.sessions.some((s) => s.open === b.t &&
                s.close >= b.end &&
                prior.end === data.sessions.find((z) => z.close === prior.end)?.close)) {
            if (strictPath)
                unresolved("MISSING_BAR_WITH_OPEN_EXPOSURE", b.t);
            return null;
        }
        if (pendingStop && b.t >= pendingStop.at) {
            stop = pendingStop.price;
            pendingStop = undefined;
        }
        if (strictPath &&
            b.t > Math.min(deadline, contractDeadline))
            unresolved("NO_EXECUTABLE_BAR_AT_PLANNED_DEADLINE", b.t);
        if (b.t >= Math.min(deadline, contractDeadline)) {
            close(remaining, b.o, b.t, b.t >= contractDeadline ? "CONTRACT_DEADLINE" : "TIME");
            marks.push({ at: b.t, pnl: realized });
            break;
        }
        const roadmapAction = require("./roadmap9_exit.js").exitAction(
            signal, b.t, remaining, roadmapReduced, options?.forecastDecisions);
        if (roadmapAction) {
            close(roadmapAction.quantity, b.o, b.t, roadmapAction.reason);
            roadmapReduced = true;
            if (!remaining) { marks.push({at:b.t,pnl:realized}); break; }
        }
        const researchReason = signal.metadata?.researchExit
            ? require('./research_residual_exit.js').exitReason(signal, data, b.t)
            : null;
        if (researchReason) {
            close(remaining, b.o, b.t, researchReason);
            marks.push({ at: b.t, pnl: realized });
            break;
        }
        const stopHit = dir === 1 ? b.l <= stop : b.h >= stop;
        const targets = policy === "RUNNER"
            ? [2, Infinity]
            : policy === "REGIME" && signal.regime >= 0.5
                ? [2, 4]
                : [1.5, 3];
        const targetHit = targets.some((r) => dir === 1 ? b.h >= entry + r * distance : b.l <= entry - r * distance);
        if (stopHit && targetHit)
            ambiguous++;
        if (stopHit)
            close(remaining, dir === 1 ? Math.min(b.o, stop) : Math.max(b.o, stop), b.end, "STOP", b.availableAt);
        else {
            if (signal.hypothesis === "VWAP_REVERSION" &&
                signal.target &&
                (dir === 1
                    ? b.h >= signal.target && signal.target > entry
                    : b.l <= signal.target && signal.target < entry))
                close(remaining, signal.target, b.end, "VWAP", b.availableAt);
            for (let j = 0; j < 2 && remaining; j++) {
                const target = round(entry + dir * targets[j] * distance, series.tick, dir === 1), qty = Math.floor(quantity * 0.25);
                if (!tpDone[j] &&
                    Number.isFinite(target) &&
                    (dir === 1 ? b.h >= target : b.l <= target)) {
                    close(Math.min(qty, remaining), target, b.end, "TP" + (j + 1), b.availableAt);
                    tpDone[j] = true;
                }
            }
        }
        const pnl = realized +
            dir * (b.c - entry) * remaining * series.pointValue -
            remaining * p.costs.perSideUsd * costMultiplier;
        marks.push({ at: b.availableAt, pnl });
        peakPnl = Math.max(peakPnl, pnl);
        if (dir * (b.c - peak) > 0)
            peak = b.c;
        const candidate = round(nextTrailingStop(dir, stop, entry, peak, distance, policy, signal.regime), series.tick, dir !== 1);
        if (dir * (candidate - stop) > 0)
            pendingStop = { price: candidate, at: b.availableAt };
    }
    if (remaining) {
        if (strictPath)
            unresolved("DATA_ENDED_WITH_OPEN_EXPOSURE", null);
        return null; // Other legacy research scopes retain their explicit incomplete-path exclusion.
    }
    const riskUsd = quantity * distance * series.pointValue;
    const dividendEntitlements = cashDividends
        .filter(d => d.symbol === series.symbol && first.t < d.exAt && d.exAt <= closed)
        .flatMap(d => {
        const earlierEvents = inventoryEvents.filter(e => e.at < d.exAt);
        (0, ultimate_contracts_1.need)(earlierEvents.every(e => e.knownAt <= d.exAt), "dividend remaining inventory unobservable at ex date");
        const held = earlierEvents.reduce((n, e) => n + e.quantityDelta, 0);
        return held <= 0 ? [] : [{ dividendId: d.id, campaignId: signal.id,
                symbol: signal.symbol, exAt: d.exAt, payableAt: d.payableAt, quantity: held,
                amountPerShare: d.amountPerShare, amountUsd: held * d.amountPerShare }];
    });
    const dividendAccruedUsd = dividendEntitlements.reduce((n, d) => n + d.amountUsd, 0);
    const dividendPaidUsd = dividendEntitlements.reduce((n, d) => n + (d.payableAt !== null && d.payableAt <= closed ? d.amountUsd : 0), 0);
    // Keep the frozen legacy/no-option API unchanged. Traced PROFIT8 campaigns
    // use receipt time as the terminal boundary, including delayed intrabar fills.
    const chronology = options?.profit8Trace
        ? require("./replay_chronology.cjs").terminalTimeline(marks,
            Math.max(closed, ...inventoryEvents.map(e => e.knownAt)), realized)
        : null;
    if (chronology) {
        marks.splice(0, marks.length, ...chronology.marks);
        peakPnl = chronology.peak;
    }
    return {
        id: signal.id,
        symbol: signal.symbol,
        hypothesis: signal.hypothesis,
        policy,
        direction: dir,
        opened: first.t,
        closed,
        riskUsd,
        netUsd: realized,
        netR: realized / riskUsd,
        feesUsd: fees,
        peakClosePnl: peakPnl,
        givebackUsd: Math.max(0, peakPnl - realized),
        ambiguousBars: ambiguous,
        quantity,
        entry,
        marks,
        reason,
        ...(chronology ? { chronology: { terminalKnownAt: marks.at(-1).at,
            lateNonterminalMarksRemoved: chronology.lateNonterminalMarks,
            semantics: "TERMINAL_RECEIPT_SUPERSEDES_LATE_MARKS" } } : {}),
        ...(calendarHolding
            ? { holdingDeadlineAt: deadline, holdingClockStartedAt: signal.at }
            : {}),
        ...(options === undefined ? {} : { inventoryEvents, dividendEntitlements,
            dividendAccruedUsd, dividendPaidUsd,
            dividendReceivableUsd: dividendAccruedUsd - dividendPaidUsd,
            netEconomicUsd: realized + dividendAccruedUsd }),
    };
}
function windowTrades(trades, sessions, purgeMs) {
    if (!sessions.length)
        return [];
    const start = sessions[0].open, end = sessions.at(-1).close;
    return trades.filter((t) => t.opened >= start && t.opened <= end - purgeMs && t.closed <= end);
}
function normalizedDaily(trades, sessions, riskFraction = 0.0025) {
    return sessions.map((s, index) => {
        const previous = index ? sessions[index - 1].close : s.open - 1;
        const pnlAt = (t, at) => at < t.opened
            ? 0
            : at >= t.closed
                ? t.netUsd
                : (t.marks.findLast((m) => m.at <= at)?.pnl ?? -t.feesUsd / 2);
        return trades.reduce((value, t) => value +
            ((pnlAt(t, s.close) - pnlAt(t, previous)) / t.riskUsd) * riskFraction, 0);
    });
}
function evaluate(trades, sessions) {
    return {
        ...(0, ultimate_stats_1.metrics)(normalizedDaily(trades, sessions), trades.map((t) => t.netR)),
        netUnitPnlUsd: trades.reduce((n, t) => n + t.netUsd, 0),
        modeledFeesUsd: trades.reduce((n, t) => n + t.feesUsd, 0),
        ambiguousBars: trades.reduce((n, t) => n + t.ambiguousBars, 0),
    };
}
function runStudy(protocolInput, datasetInput, registeredAt, limits = exports.DEFAULT_REPLAY_LIMITS) {
    const p = (0, ultimate_contracts_1.assertProtocol)(protocolInput), data = (0, ultimate_contracts_1.assertDataset)(datasetInput, p), generated = opportunities(data, p);
    const bySymbol = Object.fromEntries(data.series.map((s) => [s.symbol, s]));
    const ids = ultimate_contracts_1.HYPOTHESES.flatMap((h) => ultimate_contracts_1.EXIT_VARIANTS.map((x) => h + ":" + x));
    const common = [], excluded = { incompletePath: 0 };
    const trades = Object.fromEntries(ids.map((id) => [id, []]));
    const stress = Object.fromEntries(ids.map((id) => [id, []]));
    for (const signal of generated.signals) {
        const base = ultimate_contracts_1.EXIT_VARIANTS.map((policy) => replayCampaign(signal, bySymbol[signal.symbol], data, p, policy));
        const cost = ultimate_contracts_1.EXIT_VARIANTS.map((policy) => replayCampaign(signal, bySymbol[signal.symbol], data, p, policy, 4, 2));
        if ([...base, ...cost].some((t) => t === null)) {
            excluded.incompletePath++;
            continue;
        }
        common.push(signal);
        ultimate_contracts_1.EXIT_VARIANTS.forEach((x, j) => {
            const id = signal.hypothesis + ":" + x;
            trades[id].push(base[j]);
            stress[id].push(cost[j]);
        });
    }
    const purge = p.purgeHours * 3600000, holdout = data.sessions.slice(-p.holdoutSessions), dev = data.sessions.slice(0, -p.holdoutSessions - p.gapSessions);
    const folds = [];
    for (let end = p.trainSessions; end + p.gapSessions + p.testSessions <= dev.length; end += p.testSessions) {
        const train = dev.slice(end - p.trainSessions, end), test = dev.slice(end + p.gapSessions, end + p.gapSessions + p.testSessions);
        const ranked = ids
            .map((id) => ({
            id,
            value: evaluate(windowTrades(trades[id], train, purge), train),
        }))
            .filter((x) => x.value.campaigns >= 30 && (x.value.growthLog ?? -Infinity) > 0);
        ranked.sort((a, b) => (b.value.growthLog ?? -Infinity) - (a.value.growthLog ?? -Infinity));
        folds.push({ train, test, selected: ranked[0]?.id || "CASH" });
    }
    (0, ultimate_contracts_1.need)(folds.length > 0, "no valid external folds");
    const oos = folds.flatMap((f) => f.test), oosTrades = (id, source = trades) => folds.flatMap((f) => windowTrades(source[id], f.test, purge));
    const matrix = ids.map((id) => normalizedDaily(oosTrades(id), oos));
    const rows = ids.map((id, index) => {
        const baseId = id.split(":")[0] + ":BASELINE", a = oosTrades(id), h = windowTrades(trades[id], holdout, purge), double = oosTrades(id, stress);
        const m = evaluate(a, oos), hm = evaluate(h, holdout), sm = evaluate(double, oos);
        const bootstrap = (v) => (0, ultimate_stats_1.bootstrapLower)(v, p.bootstrapRuns, p.blockSessions, Math.max(p.familyTrials, ids.length * p.universe.length));
        const lower = bootstrap(matrix[index]), heldLower = bootstrap(normalizedDaily(h, holdout));
        const baselineDaily = normalizedDaily(oosTrades(baseId), oos), pairedLower = id === baseId
            ? null
            : bootstrap(matrix[index].map((v, i) => v - baselineDaily[i]));
        const heldBase = normalizedDaily(windowTrades(trades[baseId], holdout, purge), holdout), heldDaily = normalizedDaily(h, holdout);
        const pairedHoldoutLower = id === baseId
            ? null
            : bootstrap(heldDaily.map((v, i) => v - heldBase[i]));
        const dsr = (0, ultimate_stats_1.deflatedSharpe)(matrix, index, p.familyTrials, a.length);
        const holdoutFresh = holdout[0].open > Math.max(registeredAt, p.knownHistoryThrough);
        const gates = {
            oosSample: a.length >= p.minOosCampaigns,
            holdoutSample: h.length >= p.minHoldoutCampaigns,
            oosLowerPositive: lower !== null && lower > 0,
            holdoutLowerPositive: heldLower !== null && heldLower > 0,
            doubleCostEvidence: double.length > 0 &&
                (sm.expectancyR ?? 0) > 0 &&
                windowTrades(stress[id], holdout, purge).reduce((n, t) => n + t.netR, 0) > 0,
            dsr: dsr.value !== null && dsr.value >= 0.95,
            maxDrawdown: m.maxDrawdown <= limits.maxDrawdown &&
                hm.maxDrawdown <= limits.maxDrawdown,
            tpImprovement: id === baseId ||
                (pairedLower !== null &&
                    pairedLower > 0 &&
                    pairedHoldoutLower !== null &&
                    pairedHoldoutLower > 0 &&
                    m.maxDrawdown <= evaluate(oosTrades(baseId), oos).maxDrawdown),
            untouchedHoldout: holdoutFresh,
            actualFutures: p.kind === "FUTURES",
            authenticatedExecution: false,
        };
        return {
            id,
            oos: m,
            holdout: hm,
            doubleCostOos: sm,
            lower,
            heldLower,
            pairedLower,
            pairedHoldoutLower,
            dsr,
            gates,
            status: Object.values(gates).every(Boolean)
                ? "ELIGIBLE_FOR_REVIEW"
                : "NOT_PROMOTED",
        };
    });
    const selected = folds.flatMap((f) => f.selected === "CASH"
        ? []
        : windowTrades(trades[f.selected], f.test, purge));
    // The unit cohort is an attribution estimand. Portfolio admission consumes
    // every raw causal signal; another policy's future path cannot remove it.
    const fundedResult = replayFundedPortfolio(generated.signals, data, p, folds, oos, limits);
    return {
        schema: "HARPOON-ULTIMATE-REPORT-1",
        generatedAt: Date.now(),
        registeredAt,
        protocolHash: (0, ultimate_contracts_1.digest)(p),
        datasetHash: (0, ultimate_contracts_1.digest)(data),
        kind: p.kind,
        source: data.provenance,
        scope: "OBSERVED_BARS_MODELED_EXECUTION",
        promotion: "NONE",
        unitCurveScope: "OVERLAPPING_OPPORTUNITIES_NORMALIZED_TO_025_PERCENT_RISK_NOT_ACCOUNT_RETURNS",
        hypotheses: ultimate_contracts_1.HYPOTHESES,
        policies: ultimate_contracts_1.EXIT_VARIANTS,
        trialCount: ids.length * p.universe.length,
        foldCount: folds.length,
        windows: {
            oosFrom: oos[0].date,
            oosThrough: oos.at(-1).date,
            holdoutFrom: holdout[0].date,
            holdoutThrough: holdout.at(-1).date,
        },
        funnel: generated.funnel,
        excluded,
        commonOpportunities: common.length,
        rows,
        selection: {
            rule: "TRAIN_ONLY_POSITIVE_LOG_GROWTH_MIN_30_ELSE_CASH",
            folds: folds.map((f) => ({
                trainFrom: f.train[0].date,
                trainThrough: f.train.at(-1).date,
                testFrom: f.test[0].date,
                testThrough: f.test.at(-1).date,
                selected: f.selected,
            })),
            oos: evaluate(selected, oos),
        },
        fundedPortfolio: fundedResult.portfolio,
        pbo: (0, ultimate_stats_1.probabilityBacktestOverfit)(matrix),
        dailyUnitReturns: Object.fromEntries(ids.map((id, i) => [id, matrix[i]])),
        frequencyDiagnostics: (0, ultimate_frequency_1.trainingFrequencies)(data, folds[0].train.at(-1).close),
        limitations: [
            "Historical fills, spreads and queue positions are modeled; no authenticated fills are inferred.",
            "Common-cohort exit attribution and funded portfolio are separate estimands.",
            "All nine variants per root count toward multiplicity; row intervals depend on block and stationarity assumptions.",
            "DSR uses HAC effective sample approximation; PBO is a diagnostic, not prospective proof.",
            "A reused or preregistration-preceding holdout cannot authorize promotion.",
            "Proxy data cannot validate futures execution, basis, shorts or contract rolls.",
            "Stops have adverse precedence; close-derived trailing activates only after availability.",
            "Portfolio marks are bar-based; intrabar margin calls, settlement and market impact require additional observations.",
            "Futures funded results require historical margin data; absence is not zero margin.",
            "Contract commissions are a floor; exchange, clearing and data fees must be added to supplied assumptions.",
        ],
    };
}
/** A failed funded replay preserves reservations and exposure instead of a PnL. */
class FundedPortfolioReplayError extends Error {
    code;
    details;
    economicPnlUsd = null;
    constructor(code, details) {
        super(code + ": " + JSON.stringify(details));
        this.code = code;
        this.details = details;
        this.name = "FundedPortfolioReplayError";
    }
}
exports.FundedPortfolioReplayError = FundedPortfolioReplayError;
/**
 * Execute a supplied policy selection with one continuous capital pool.
 * This function neither fits nor selects policies and never calls runStudy.
 * Model observations retain their availability clocks; they are not broker
 * receipts. All reservations are conservative approved ceilings, not estimates
 * of remaining buying power from a broker account.
 */
function replayFundedPortfolio(signals, data, p, folds, sessions, limits = exports.DEFAULT_REPLAY_LIMITS, options) {
    (0, ultimate_contracts_1.need)(options?.continuous === undefined || typeof options.continuous === "boolean", "continuous replay option");
    (0, ultimate_contracts_1.need)(options?.cashDividends === undefined || typeof options.cashDividends === "boolean", "cash-dividend replay option");
    (0, ultimate_contracts_1.need)(options?.entryExecution === undefined || options.entryExecution === "IOC_LIMIT_TO_APPROVED_BUDGET" ||
        (options.profit8 !== undefined && options.entryExecution === "IOC_LIMIT_COMMON_CAUSAL_30BPS"), "historical entry-execution option");
    if (options?.profit8 !== undefined) {
        (0, ultimate_contracts_1.need)(["NATIVE_MAX", "MAX_POSITIVE", "ROBUST_LOG"].includes(options.profit8?.mode) &&
            options.entryExecution === "IOC_LIMIT_COMMON_CAUSAL_30BPS" && options.continuous === true &&
            options.cashDividends === true && p.kind === "ALPACA_PROXY", "PROFIT8_FIXED_EXECUTION_CONTRACT");
        (0, ultimate_contracts_1.need)(limits.capitalUsd === 20000 &&
            Object.entries(exports.PROFIT8_REPLAY_LIMITS).every(([key, cap]) => limits[key] <= cap), "PROFIT8_LIMITS_MUST_BE_EXPLICIT_AND_NOT_RAISED");
        (0, ultimate_contracts_1.need)(folds.every(f => f.selected === "ALL:BASELINE" || f.selected === "CASH"), "PROFIT8_BASELINE_ONLY");
        signals.forEach(signal => assertProfit8Signal(signal, data));
    }
    (0, ultimate_contracts_1.need)(options?.externalCostPerSessionUsd === undefined ||
        (typeof options.externalCostPerSessionUsd === "number" && Number.isFinite(options.externalCostPerSessionUsd) &&
            options.externalCostPerSessionUsd >= 0), "modeled external session cost");
    if (options?.cashDividends)
        (0, ultimate_contracts_1.assertCashDividends)(data);
    const admissionMap = options?.admissions === undefined ? undefined : options.admissions instanceof Map
        ? new Map(options.admissions) : new Map(Object.entries(options.admissions));
    if (admissionMap)
        for (const [id, admission] of admissionMap)
            (0, ultimate_contracts_1.need)(typeof id === "string" && id.length > 0 &&
                typeof admission?.allow === "boolean" && typeof admission.rank === "number" && Number.isFinite(admission.rank), "funded admission identity, decision and rank");
    (0, ultimate_contracts_1.need)(sessions.length > 0 && sessions.every((s, i) => Number.isSafeInteger(s.open) &&
        Number.isSafeInteger(s.close) && s.open < s.close && (!i || s.open > sessions[i - 1].close)), "funded evaluation session chronology");
    (0, ultimate_contracts_1.need)(Object.values(limits).every(v => Number.isFinite(v) && v > 0) &&
        [limits.riskFraction, limits.openRiskFraction, limits.grossFraction,
            limits.assetFraction, limits.dailyLoss, limits.maxDrawdown].every(v => v <= 1) &&
        limits.riskFraction <= limits.openRiskFraction && limits.assetFraction <= limits.grossFraction, "funded limits");
    (0, ultimate_contracts_1.need)(new Set(signals.map(s => s.id)).size === signals.length &&
        signals.every((s, i) => Number.isSafeInteger(s.at) && (!i || s.at >= signals[i - 1].at)), "funded signal identities and chronology");
    (0, ultimate_contracts_1.need)(folds.every(f => f.test.length > 0 && (f.selected === "CASH" ||
        (options !== undefined && f.selected === "ALL:BASELINE") ||
        ultimate_contracts_1.HYPOTHESES.some(h => ultimate_contracts_1.EXIT_VARIANTS.some(v => f.selected === h + ":" + v)))), "funded frozen policy selection");
    const sessionKey = (s) => `${s.date}:${s.open}:${s.close}`;
    const calendarKeys = new Set(data.sessions.map(sessionKey));
    const evaluationKeys = new Set(sessions.map(sessionKey));
    const selectedKeys = folds.flatMap(f => f.test.map(sessionKey));
    if (options?.continuous)
        (0, ultimate_contracts_1.need)(data.sessions.filter(s => s.open >= sessions[0].open &&
            s.close <= sessions.at(-1).close).every(s => evaluationKeys.has(sessionKey(s))), "continuous account cannot omit intervening calendar sessions");
    (0, ultimate_contracts_1.need)(sessions.every(s => calendarKeys.has(sessionKey(s))) &&
        folds.every(f => f.test.every((s, i) => evaluationKeys.has(sessionKey(s)) &&
            (!i || s.open > f.test[i - 1].close))) &&
        new Set(selectedKeys).size === selectedKeys.length, "funded selection must be disjoint and inside the declared evaluation calendar");
    const bySymbol = Object.fromEntries(data.series.map(s => [s.symbol, s]));
    const funded = [];
    const states = [];
    const preEntryRefusals = [];
    const skipped = {};
    const closeKnownAt = new Map();
    const modeledNoFills = [];
    let reservationBook = (0, ultimate_reservations_1.emptyFundedReservationBook)();
    const purge = p.purgeHours * 3600000;
    const terminalAt = sessions.at(-1).close;
    const globalEntryCutoff = terminalAt - 72 * 3600000;
    const externalCostIsModeled = options?.externalCostPerSessionUsd !== undefined;
    const calendarCost = options?.calendarCostPerDayUsd;
    (0, ultimate_contracts_1.need)(calendarCost === undefined || (Number.isFinite(calendarCost) && calendarCost >= 0), "CALENDAR_COST");
    const externalCostAt = (at) => calendarCost !== undefined
        ? (at < sessions[0].open ? 0 : (Math.floor(at / 86400000) - Math.floor(sessions[0].open / 86400000) + 1) * calendarCost)
        : externalCostIsModeled
        ? sessions.reduce((n, session) => n + (session.open <= at ? options.externalCostPerSessionUsd : 0), 0) : 0;
    const dividendAt = (at, paid, symbol) => funded.reduce((n, t) => n +
        (symbol !== undefined && t.symbol !== symbol ? 0 : (t.dividendEntitlements ?? []).reduce((sum, d) => sum +
            (d.exAt <= at && (!paid || (d.payableAt !== null && d.payableAt <= at)) ? d.amountUsd : 0), 0)), 0);
    let peakEquity = limits.capitalUsd;
    const pnlAt = (t, at) => {
        if (at < t.opened)
            return 0;
        if ((closeKnownAt.get(t.id) ?? Infinity) <= at)
            return t.netUsd;
        const mark = t.marks.findLast(m => m.at <= at);
        if (mark)
            return mark.pnl;
        // Before the first post-fill bar is available, the existing position still
        // has value and execution friction. Use the same observable close basis
        // as inventory/sizing; entry price is not a zero-PnL valuation convention.
        const series = bySymbol[t.symbol];
        const reference = series ? causalReferencePrice({ at }, series) : null;
        if (reference?.status !== "AVAILABLE")
            throw new FundedPortfolioReplayError("FUNDED_CAUSAL_VALUATION_UNAVAILABLE", { at, symbol: t.symbol, campaignId: t.id,
                openedAt: t.opened, quantity: t.quantity, entryPrice: t.entry, reference,
                funded, states, reservationBook, economicPnlUsd: null });
        // Match subsequent campaign marks: entry fee already incurred plus one
        // modeled exit-fee allowance for still-open units, each counted once.
        return t.direction * (reference.price - t.entry) * t.quantity * series.pointValue -
            2 * t.quantity * p.costs.perSideUsd;
    };
    const equityAt = (at) => limits.capitalUsd + funded.reduce((n, t) => n + pnlAt(t, at), 0) +
        dividendAt(at, false) - externalCostAt(at);
    const cashPoolAt = (at) => limits.capitalUsd + funded.reduce((n, t) => n + ((closeKnownAt.get(t.id) ?? Infinity) <= at ? t.netUsd : 0), 0) +
        dividendAt(at, true) - externalCostAt(at);
    const profit8RiskEventSummary = options?.profit8 === undefined ? null : {
        scope: "EVERY_CAUSAL_VALUATION_AND_COMMITMENT;ADMISSION_CAPS_UNCHANGED;MARKET_MOVE_OVERAGES_ARE_DIAGNOSTIC",
        observations: 0, valuationObservations: 0, commitmentObservations: 0,
        maximumReservedRiskUsd: 0, maximumReservedNotionalUsd: 0, maximumReservedCashUsd: 0,
        maximumConservativeMarkedNotionalUsd: 0, maximumRiskFraction: 0, maximumGrossFraction: 0,
        riskOverageObservations: 0, grossOverageObservations: 0, cashDeficitObservations: 0,
        firstRiskOverage: null, firstGrossOverage: null, firstCashDeficit: null };
    const observeProfit8Risk = (at, equity, stage) => {
        if (profit8RiskEventSummary === null) return;
        const snapshot = (0, ultimate_reservations_1.snapshotFundedReservations)(reservationBook, at);
        let markedNotional = snapshot.notionalUsd;
        for (const reservation of snapshot.reservations) if (reservation.state === "OPENED") {
            const series = bySymbol[reservation.symbol], reference = causalReferencePrice({ at }, series);
            if (reference.status !== "AVAILABLE")
                throw new FundedPortfolioReplayError("PROFIT8_EVENT_REFERENCE_UNAVAILABLE", {
                    at, symbol: reservation.symbol, reservation, economicPnlUsd: null });
            markedNotional += Math.max(0, reservation.quantity * reference.price - reservation.notionalUsd);
        }
        const cash = cashPoolAt(at), summary = profit8RiskEventSummary;
        const row = { at, stage, equityUsd: equity, cashPoolUsd: cash,
            reservedRiskUsd: snapshot.riskUsd, reservedNotionalUsd: snapshot.notionalUsd,
            reservedCashUsd: snapshot.cashUsd, conservativeMarkedNotionalUsd: markedNotional,
            pending: snapshot.pending, opened: snapshot.opened };
        summary.observations++;
        summary[stage === "COMMITMENT" ? "commitmentObservations" : "valuationObservations"]++;
        summary.maximumReservedRiskUsd = Math.max(summary.maximumReservedRiskUsd, snapshot.riskUsd);
        summary.maximumReservedNotionalUsd = Math.max(summary.maximumReservedNotionalUsd, snapshot.notionalUsd);
        summary.maximumReservedCashUsd = Math.max(summary.maximumReservedCashUsd, snapshot.cashUsd);
        summary.maximumConservativeMarkedNotionalUsd = Math.max(summary.maximumConservativeMarkedNotionalUsd, markedNotional);
        if (equity > 0) {
            summary.maximumRiskFraction = Math.max(summary.maximumRiskFraction, snapshot.riskUsd / equity);
            summary.maximumGrossFraction = Math.max(summary.maximumGrossFraction, markedNotional / equity);
        }
        if (snapshot.riskUsd > equity * limits.openRiskFraction + 1e-8) {
            summary.riskOverageObservations++; summary.firstRiskOverage ??= row;
        }
        if (markedNotional > equity * limits.grossFraction + 1e-8) {
            summary.grossOverageObservations++; summary.firstGrossOverage ??= row;
        }
        if (snapshot.cashUsd > cash + 1e-8) {
            summary.cashDeficitObservations++; summary.firstCashDeficit ??= row;
        }
    };
    // Risk high-water marks belong to the account's observable event clock, not
    // to the subset of times at which a model happens to admit another signal.
    // Complete replay paths are retained, but only events <= the current decision
    // may enter this state. A future profitable mark must never tighten today's
    // drawdown limit. Consume pending events once rather than scanning every
    // historical mark for every candidate.
    let pendingValuationEvents = sessions.map(s => s.open);
    let observedValuationEvents = 0, maximumObservedEventDrawdown = 0;
    const recordEquityObservation = (at) => {
        const equity = equityAt(at);
        peakEquity = Math.max(peakEquity, equity);
        maximumObservedEventDrawdown = Math.max(maximumObservedEventDrawdown, 1 - equity / peakEquity);
        observeProfit8Risk(at, equity, "VALUATION");
        return equity;
    };
    const advanceValuationClock = (at) => {
        let used = 0;
        while (used < pendingValuationEvents.length && pendingValuationEvents[used] <= at) {
            recordEquityObservation(pendingValuationEvents[used++]);
            observedValuationEvents++;
        }
        pendingValuationEvents = pendingValuationEvents.slice(used);
        return recordEquityObservation(at);
    };
    const queueCampaignValuations = (trade, series, knownAt) => {
        const firstMarkAt = trade.marks[0]?.at ?? knownAt;
        const times = [trade.opened, knownAt, ...trade.marks.map(m => m.at),
            ...(trade.dividendEntitlements ?? []).map(d => d.exAt),
            // A preceding bar can arrive just after the fill, before the first
            // post-fill mark. It changes the causal fallback valuation too.
            ...series.bars.filter(b => b.availableAt >= trade.opened && b.availableAt < firstMarkAt)
                .map(b => b.availableAt)];
        pendingValuationEvents = [...new Set([...pendingValuationEvents,
                ...times.filter(at => at >= sessions[0].open && at <= terminalAt)])].sort((a, b) => a - b);
    };
    const refuse = (signal, reason, extra = {}) => {
        skipped[reason] = (skipped[reason] || 0) + 1;
        preEntryRefusals.push({ signalId: signal.id, symbol: signal.symbol, decisionAt: signal.at,
            reason, positionOpened: false, ...extra });
    };
    // The stable original order is retained for ties; scores never reorder time.
    const orderedSignals = admissionMap ? signals.map((signal, index) => ({ signal, index }))
        .sort((a, b) => a.signal.at - b.signal.at ||
        (admissionMap.get(b.signal.id)?.rank ?? -Infinity) - (admissionMap.get(a.signal.id)?.rank ?? -Infinity) ||
        a.index - b.index).map(x => x.signal) : signals;
    for (const rawSignal of orderedSignals) {
        const fold = folds.find(f => rawSignal.at >= f.test[0].open &&
            rawSignal.at <= f.test.at(-1).close - (options?.continuous ? 0 : purge));
        if (!fold || fold.selected === "CASH" || (fold.selected !== "ALL:BASELINE" &&
            !fold.selected.startsWith(rawSignal.hypothesis + ":")))
            continue;
        if (options?.continuous && options.profit8 === undefined && rawSignal.at > globalEntryCutoff) {
            refuse(rawSignal, "GLOBAL_TERMINAL_ENTRY_CUTOFF", { globalEntryCutoff });
            continue;
        }
        const admission = admissionMap?.get(rawSignal.id);
        if (admissionMap && (!admission || !admission.allow)) {
            refuse(rawSignal, admission ? "MODEL_ADMISSION_REFUSED" : "MODEL_ADMISSION_UNAVAILABLE", { admission: admission ?? null });
            continue;
        }
        if (p.kind === "FUTURES") {
            refuse(rawSignal, "HISTORICAL_MARGIN_UNAVAILABLE");
            continue;
        }
        if (rawSignal.direction !== 1) {
            refuse(rawSignal, "SHORT_PROXY_EXECUTION_NOT_SUPPORTED");
            continue;
        }
        const series = bySymbol[rawSignal.symbol];
        (0, ultimate_contracts_1.need)(series !== undefined && series.pointValue === 1, "funded cash-share series scope");
        // Derive a legacy signal's plan from its decision/calendar, never its old
        // future-bar index. The explicit causal plan remains authoritative.
        const plannedEntryAt = rawSignal.plannedEntryAt ?? planSignalEntryAt(rawSignal.at, data.sessions);
        if (plannedEntryAt === null) {
            refuse(rawSignal, "NO_CAUSAL_ENTRY_WINDOW");
            continue;
        }
        const signal = { ...rawSignal, plannedEntryAt };
        const holding = planCalendarHolding(signal, plannedEntryAt, data, p);
        if (holding.status === "REFUSED_BEFORE_ENTRY") {
            refuse(signal, holding.reason, { holding });
            continue;
        }
        if (options?.profit8 !== undefined && holding.deadlineAt > terminalAt) {
            refuse(signal, "TERMINAL_CALENDAR_DEADLINE_CUTOFF", { holding, terminalAt });
            continue;
        }
        const before = (0, ultimate_reservations_1.snapshotFundedReservations)(reservationBook, signal.at);
        const equity = advanceValuationClock(signal.at);
        const day = data.sessions.find(s => signal.at >= s.open && signal.at < s.close);
        (0, ultimate_contracts_1.need)(day !== undefined, "funded decision outside calendar");
        if (equity <= 0)
            throw new FundedPortfolioReplayError("FUNDED_INSOLVENCY", {
                signalId: signal.id, at: signal.at, equityUsd: equity, reservationBook,
                funded, states, lastObservedReservations: before, economicPnlUsd: null
            });
        if (equity <= peakEquity * (1 - limits.maxDrawdown) ||
            equity <= equityAt(day.open - (options === undefined ? 0 : 1)) * (1 - limits.dailyLoss)) {
            refuse(signal, "LOSS_LIMIT", { equityUsd: equity, causalPeakEquityUsd: peakEquity,
                drawdownFromCausalPeak: 1 - equity / peakEquity });
            continue;
        }
        if (before.symbols.includes(signal.symbol)) {
            refuse(signal, "SYMBOL_BUSY", { reservationSnapshot: before });
            continue;
        }
        // Pending entries use approved ceilings only. An observed open campaign
        // reserves at least its original ceiling and the full original quantity
        // marked at the latest available close. Ignoring partial-sale proceeds is
        // conservative; no unknown remaining quantity is invented.
        let notional = before.notionalUsd;
        const inventoryMarks = [];
        let missingInventoryMark = false;
        for (const reservation of before.reservations)
            if (reservation.state === "OPENED") {
                const inventorySeries = bySymbol[reservation.symbol];
                const reference = inventorySeries ? causalReferencePrice({ at: signal.at }, inventorySeries) : null;
                if (reference?.status !== "AVAILABLE") {
                    missingInventoryMark = true;
                    break;
                }
                const marked = reservation.quantity * reference.price * inventorySeries.pointValue;
                notional += Math.max(0, marked - reservation.notionalUsd);
                inventoryMarks.push({ id: reservation.id, symbol: reservation.symbol, reference,
                    fullOriginalQuantity: reservation.quantity, markedNotionalUsd: marked,
                    reservedNotionalUsd: Math.max(reservation.notionalUsd, marked) });
            }
        if (missingInventoryMark) {
            refuse(signal, "NO_CAUSAL_INVENTORY_MARK");
            continue;
        }
        const openRisk = before.riskUsd;
        const cashPoolUsd = cashPoolAt(signal.at);
        const cashBudgetUsd = cashPoolUsd - before.cashUsd;
        const plan = options?.profit8 !== undefined
            ? planProfit8FundedEntry(signal, series, p, limits, { equity, openRisk, notional, cashBudgetUsd })
            : planFundedEntry(signal, series, p, limits, { equity, openRisk, notional });
        const state = { opportunity: signal, selected: fold.selected,
            equity, causalPeakEquityUsd: peakEquity, openRisk, notional, reservationBefore: before, inventoryMarks, plan,
            day, status: "PLANNED", positionOpened: false };
        if (options !== undefined)
            Object.assign(state, { admission: admission ?? null,
                modeledExternalCostsAccruedUsd: externalCostIsModeled ? externalCostAt(signal.at) : null,
                dividendAccruedUsd: dividendAt(signal.at, false), dividendPaidUsd: dividendAt(signal.at, true),
                dividendReceivableUsd: dividendAt(signal.at, false) - dividendAt(signal.at, true) });
        states.push(state);
        if (plan.status !== "PLANNED") {
            state.status = "REFUSED_BEFORE_ENTRY";
            refuse(signal, "NO_CAUSAL_REFERENCE_PRICE");
            continue;
        }
        const sizing = options?.profit8 !== undefined && plan.quantity > 0
            ? selectProfit8Quantity(signal, plan.quantity, equity, plan.reference.price, options.profit8.mode) : null;
        const quantity = sizing?.quantity ?? plan.quantity;
        Object.assign(state, { quantity, px: plan.reference.price, riskUnit: plan.riskUnit,
            reference: plan.reference, ...(sizing ? { profit8Sizing: sizing } : {}) });
        if (quantity < 1) {
            state.status = "REFUSED_BEFORE_ENTRY";
            refuse(signal, sizing?.reason ?? (options?.profit8 !== undefined && cashBudgetUsd <= 0 ? "CASH_CAPACITY" : "INTEGER_RISK_OR_EXPOSURE"));
            continue;
        }
        if (options !== undefined && cashBudgetUsd <= 0) {
            Object.assign(state, { status: "REFUSED_BEFORE_ENTRY", cashPoolUsd, cashBudgetUsd });
            refuse(signal, "CASH_CAPACITY");
            continue;
        }
        const iocBudgets = { plannedQuantity: quantity,
            riskBudgetUsd: plan.riskBudgetUsd, notionalBudgetUsd: plan.notionalBudgetUsd, cashBudgetUsd };
        const iocPlan = options?.profit8 !== undefined
            ? planProfit8IocLimit(signal, series, p, iocBudgets)
            : options?.entryExecution === "IOC_LIMIT_TO_APPROVED_BUDGET"
                ? planFundedIocLimit(signal, series, p, iocBudgets) : null;
        if (iocPlan) {
            state.iocPlan = iocPlan;
            if (iocPlan.status !== "PLANNED") {
                state.status = "REFUSED_BEFORE_ENTRY";
                refuse(signal, iocPlan.reason);
                continue;
            }
        }
        const committed = options?.profit8 !== undefined
            ? { riskUsd: quantity * plan.riskUnit, notionalUsd: quantity * iocPlan.priceCeiling,
                cashUsd: quantity * (iocPlan.priceCeiling + p.costs.perSideUsd) }
            : { riskUsd: plan.riskBudgetUsd, notionalUsd: plan.notionalBudgetUsd,
                cashUsd: plan.notionalBudgetUsd + quantity * p.costs.perSideUsd };
        if (options?.profit8 !== undefined)
            state.profit8CommittedReservation = { ...committed, priceCeiling: iocPlan.priceCeiling,
                quantity, noPartialRelease: true, upperPriceBoundIsCausal: true };
        const reservation = (0, ultimate_reservations_1.reserveFundedEntry)(reservationBook, {
            id: signal.id, symbol: signal.symbol, decisionAt: signal.at, quantity, ...committed,
        }, { equity, cashAvailableUsd: cashPoolUsd, riskFraction: limits.riskFraction,
            openRiskFraction: limits.openRiskFraction, grossFraction: limits.grossFraction,
            assetFraction: limits.assetFraction });
        Object.assign(state, { cashPoolUsd, cashBudgetUsd, reservationStatus: reservation.status,
            reservationAfter: reservation.snapshot });
        if (reservation.status === "REFUSED") {
            state.status = "REFUSED_BEFORE_ENTRY";
            refuse(signal, reservation.reason);
            continue;
        }
        reservationBook = reservation.book;
        observeProfit8Risk(signal.at, equity, "COMMITMENT");
        try {
            if (iocPlan) {
                const first = series.bars.find(b => b.t === plannedEntryAt);
                // Missing data is not evidence of no fill. Let replayCampaign expose
                // its existing UNOBSERVED_ENTRY incident when the opening is absent.
                if (first) {
                    const friction = (p.costs.spreadBps / 2 + p.costs.slippageBps) / 10000;
                    const modeledOpeningFill = round(first.o * (1 + friction), series.tick, true);
                    (0, ultimate_contracts_1.need)(Number.isFinite(modeledOpeningFill) && modeledOpeningFill > 0, "IOC opening observation");
                    if (modeledOpeningFill > iocPlan.priceCeiling + 1e-8) {
                        reservationBook = (0, ultimate_reservations_1.recordFundedReservationObservation)(reservationBook, {
                            id: signal.id, kind: "NO_FILL", at: plannedEntryAt, knownAt: plannedEntryAt,
                            remainingQuantity: 0, pendingQuantity: 0
                        });
                        const noFill = { signalId: signal.id, symbol: signal.symbol, decisionAt: signal.at,
                            plannedEntryAt, resolutionAt: plannedEntryAt, priceCeiling: iocPlan.priceCeiling,
                            modeledOpeningFill, quantity, reason: "MODELED_OPEN_ABOVE_IOC_LIMIT",
                            positionOpened: false, modeledTradingPnlUsd: 0 };
                        modeledNoFills.push(noFill);
                        if (options?.profit8 !== undefined)
                            pendingValuationEvents = [...new Set([...pendingValuationEvents, plannedEntryAt])].sort((a, b) => a - b);
                        skipped[noFill.reason] = (skipped[noFill.reason] || 0) + 1;
                        Object.assign(state, { status: "MODELED_IOC_NO_FILL", positionOpened: false, noFill });
                        continue;
                    }
                }
            }
            const trade = replayCampaign(signal, series, data, p, fold.selected.split(":")[1], quantity, 1, options === undefined ? undefined : { cashDividends: options.cashDividends === true, forecastDecisions: options.forecastDecisions,
                ...(options.profit8 !== undefined ? { profit8Trace: true } : {}) });
            if (!trade)
                throw new FundedPortfolioReplayError("FUNDED_PATH_UNRESOLVED", {
                    signalId: signal.id, plannedEntryAt, plannedQuantity: quantity,
                    positionOpened: null, economicPnlUsd: null
                });
            reservationBook = (0, ultimate_reservations_1.recordFundedReservationObservation)(reservationBook, {
                id: trade.id, kind: "OPENED", at: trade.opened, knownAt: trade.opened,
                remainingQuantity: trade.quantity, pendingQuantity: 0
            });
            const receipt = verifyFundedEntryFill(trade, signal, series, p, {
                plannedQuantity: quantity, riskBudgetUsd: plan.riskBudgetUsd,
                notionalBudgetUsd: plan.notionalBudgetUsd, cashBudgetUsd
            });
            if (receipt.status !== "VERIFIED")
                throw new FundedEntryBudgetError(receipt);
            const knownAt = options?.profit8 !== undefined ? profit8KnownAt(trade)
                : Math.max(trade.closed, trade.marks.at(-1)?.at ?? trade.closed);
            reservationBook = (0, ultimate_reservations_1.recordFundedReservationObservation)(reservationBook, {
                id: trade.id, kind: "CLOSED", at: trade.closed, knownAt,
                remainingQuantity: 0, pendingQuantity: 0
            });
            closeKnownAt.set(trade.id, knownAt);
            funded.push(trade);
            queueCampaignValuations(trade, series, knownAt);
            Object.assign(state, { status: "MODELED_CAMPAIGN", positionOpened: true,
                fillBudgetReceipt: receipt, modeledOpenedAt: trade.opened,
                modeledClosedAt: trade.closed, modeledCloseKnownAt: knownAt });
        }
        catch (error) {
            const cause = error;
            throw new FundedPortfolioReplayError(cause.code ?? "FUNDED_REPLAY_FAILURE", {
                signalId: signal.id, symbol: signal.symbol, decisionAt: signal.at,
                plannedEntryAt, plannedQuantity: quantity, cause: cause.details ?? cause.message ?? String(error),
                reservationBook, decisionReservations: (0, ultimate_reservations_1.snapshotFundedReservations)(reservationBook, signal.at),
                funded, states, lastDecision: state, economicPnlUsd: null,
                ...(options === undefined ? {} : { modeledNoFills,
                    dividendReceivableUsd: dividendAt(signal.at, false) - dividendAt(signal.at, true),
                    modeledExternalCostsAccruedUsd: externalCostIsModeled ? externalCostAt(signal.at) : null })
            });
        }
    }
    advanceValuationClock(terminalAt);
    const feesAt = (trade, at) => {
        if (at < trade.opened)
            return 0;
        if ((closeKnownAt.get(trade.id) ?? Infinity) <= at)
            return trade.feesUsd;
        const events = (trade.inventoryEvents ?? []).filter(e => e.at <= at && e.knownAt <= at);
        return events.reduce((n, e) => n + e.feeUsd, 0) +
            events.reduce((n, e) => n + e.quantityDelta, 0) * p.costs.perSideUsd;
    };
    let priorEquity = limits.capitalUsd;
    const curve = sessions.map((session, index) => {
        const equity = equityAt(session.close), pnlUsd = equity - priorEquity;
        const netReturn = priorEquity > 0 && equity > 0 ? pnlUsd / priorEquity : null;
        const previousAt = index ? sessions[index - 1].close : session.open - 1;
        const assetTradingPnl = Object.fromEntries(data.series.map(s => [s.symbol, funded
                .filter(t => t.symbol === s.symbol).reduce((n, t) => n + pnlAt(t, session.close) - pnlAt(t, previousAt), 0)]));
        const dividendIncome = dividendAt(session.close, false) - dividendAt(previousAt, false);
        const externalCost = externalCostAt(session.close) - externalCostAt(previousAt);
        const tradingPnl = Object.values(assetTradingPnl).reduce((n, value) => n + value, 0);
        const fees = funded.reduce((n, t) => n + feesAt(t, session.close) - feesAt(t, previousAt), 0);
        const row = { session_id: session.date, start_at: previousAt, end_at: session.close,
            equity_start_usd: priorEquity, equity_end_usd: equity,
            modeled_trading_pnl_usd: options === undefined ? pnlUsd : tradingPnl,
            portfolio_return: netReturn, portfolio_log_return: netReturn === null ? null : Math.log1p(netReturn),
            asset_pnl_usd: Object.fromEntries(data.series.map(s => [s.symbol, assetTradingPnl[s.symbol] +
                    dividendAt(session.close, false, s.symbol) - dividendAt(previousAt, false, s.symbol)])),
            external_costs_usd: externalCostIsModeled ? externalCost : null,
            ...(options === undefined ? {} : { modeled_price_pnl_usd: tradingPnl + fees,
                modeled_trading_fees_usd: fees, dividend_income_usd: dividendIncome,
                dividend_cash_received_usd: dividendAt(session.close, true) - dividendAt(previousAt, true),
                dividend_receivable_usd: dividendAt(session.close, false) - dividendAt(session.close, true),
                conservative_cash_pool_usd: cashPoolAt(session.close),
                asset_trading_pnl_usd: assetTradingPnl,
                asset_dividend_income_usd: Object.fromEntries(data.series.map(s => [s.symbol,
                    dividendAt(session.close, false, s.symbol) - dividendAt(previousAt, false, s.symbol)])) }) };
        (0, ultimate_contracts_1.need)(Math.abs(Object.values(row.asset_pnl_usd).reduce((sum, value) => sum + value, 0) - externalCost - pnlUsd) <= 1e-8, "funded asset contributions must reconcile to continuous account change");
        priorEquity = equity;
        return row;
    });
    if (curve.some(row => row.portfolio_return === null))
        throw new FundedPortfolioReplayError("FUNDED_INSOLVENCY", {
            curve, reservationBook, funded, states, economicPnlUsd: null
        });
    const terminal = (0, ultimate_reservations_1.snapshotFundedReservations)(reservationBook, terminalAt);
    if (terminal.reservations.length)
        throw new FundedPortfolioReplayError("TERMINAL_FUNDED_EXPOSURE_UNRESOLVED", {
            terminalAt, reservationBook, terminalReservations: terminal,
            lastKnownMarks: terminal.reservations.map(r => ({ id: r.id, symbol: r.symbol,
                fullOriginalQuantity: r.quantity, remainingQuantity: null,
                lastKnownMark: funded.find(t => t.id === r.id)?.marks.findLast(m => m.at <= terminalAt) ?? null })),
            curve, funded, states, economicPnlUsd: null
        });
    (0, ultimate_contracts_1.need)(Math.abs(funded.reduce((sum, t) => sum + t.netUsd, 0) + dividendAt(terminalAt, false) - externalCostAt(terminalAt) -
        (curve.at(-1).equity_end_usd - limits.capitalUsd)) <= 1e-8, "closed funded campaigns must reconcile to terminal account equity");
    return {
        portfolio: { scope: "MODELED_SHARED_CAPITAL_INTEGER_LOTS_CAUSAL_RESERVATIONS", limits,
            oos: (0, ultimate_stats_1.metrics)(curve.map(r => r.portfolio_return), funded.map(t => t.netR)),
            netUsd: curve.at(-1).equity_end_usd - limits.capitalUsd, skipped },
        metadata: {
            reservationBasis: options?.profit8 !== undefined
                ? "COMMITTED_INTEGER_QUANTITY_AT_COMMON_IOC_WORST_PRICE_AND_STOP_RISK_UNTIL_OBSERVED_CLOSE;NO_PARTIAL_RELEASE;OPEN_NOTIONAL_AT_LEAST_CAUSAL_MARK"
                : "FULL_EX_ANTE_CEILINGS_UNTIL_OBSERVED_CLOSE;OPEN_NOTIONAL_AT_LEAST_CAUSAL_MARK",
            ...(options?.profit8 !== undefined ? { profit8: { mode: options.profit8.mode,
                commonIocBufferFraction: 0.003, iocRounding: "DOWN_TO_TICK",
                objective: "m/E-0.5*(v+m*m)/(E*E)-sqrt(meanVariance)/E", uncertaintyPenalty: 1,
                allocation: "SEQUENTIAL_INTEGER_QUANTITY;NOT_JOINT_MULTI_ASSET_OPTIMIZATION",
                targetBasis: "NET_EXECUTED_POLICY_PAYOFF_PLUS_DIVIDEND_ENTITLEMENT;NO_DOUBLE_COST_CHARGE",
                zeroQuantityAllowed: true, conservativeReservationsUntilObservedClose: true } } : {}),
            closeKnowledge: "LAST_MODELED_MARK_AVAILABILITY;NOT_BROKER_RECEIPTS",
            drawdownClock: "ALL_CAUSALLY_AVAILABLE_ACCOUNT_VALUATION_EVENTS;NOT_ADMITTED_SIGNAL_TIMES",
            causalPeakEquityUsd: peakEquity,
            maximumObservedEventDrawdown,
            observedValuationEvents,
            financialAcceptanceAllowed: false,
            ...(options === undefined ? {} : {
                executionNature: "HISTORICAL_MODELED_OHLCV;NOT_BROKER_RECEIPTS",
                continuous: options.continuous === true,
                entryCutoffAt: options.profit8 !== undefined ? null : options.continuous ? globalEntryCutoff : null,
                ...(options.profit8 !== undefined ? { entryDeadlineMustNotExceed: terminalAt,
                    terminalAdmissionBasis: "PER_SIGNAL_CALENDAR_DEADLINE;NO_BLANKET_72H_CUTOFF" } : {}),
                entryExecution: options.entryExecution ?? "MODELED_MARKET_AT_PLANNED_OPEN",
                sameTimestampPriority: admissionMap ? "DESCENDING_ADMISSION_RANK_STABLE_TIES" : "ORIGINAL_SIGNAL_ORDER",
                externalCostPerSessionUsd: options.externalCostPerSessionUsd ?? null,
                externalCostCoverage: externalCostIsModeled ? "EXPLICIT_MODEL_EACH_EVALUATION_SESSION_OPEN" : "NOT_SUPPLIED",
                dividends: options.cashDividends ? "EX_DATE_RECEIVABLE;PAYABLE_DATE_CASH;NO_REINVESTMENT_BEFORE_PAYMENT" : "NOT_ENABLED",
                cashBasis: "CONSERVATIVE_CLOSED_CAMPAIGN_CASH_PLUS_PAID_DIVIDENDS_MINUS_EXTERNAL_COSTS",
                pricePnlBasis: "EXECUTED_PRICES_WITH_MODELED_SPREAD_SLIPPAGE;EXPLICIT_FEES_SEPARATE"
            })
        },
        funded, states, curve, preEntryRefusals, reservationBook,
        ...(options?.profit8 === undefined ? {} : { profit8RiskEventSummary }),
        ...(options === undefined ? {} : { modeledNoFills,
            accounting: { modeledPricePnlUsd: funded.reduce((n, t) => n + t.netUsd + t.feesUsd, 0),
                modeledTradingFeesUsd: funded.reduce((n, t) => n + t.feesUsd, 0),
                modeledTradingPnlUsd: funded.reduce((n, t) => n + t.netUsd, 0),
                dividendAccruedUsd: dividendAt(terminalAt, false), dividendPaidUsd: dividendAt(terminalAt, true),
                dividendReceivableUsd: dividendAt(terminalAt, false) - dividendAt(terminalAt, true),
                modeledExternalCostsUsd: externalCostIsModeled ? externalCostAt(terminalAt) : null,
                terminalConservativeCashPoolUsd: cashPoolAt(terminalAt),
                netEconomicUsd: externalCostIsModeled ? curve.at(-1).equity_end_usd - limits.capitalUsd : null,
                reconciliationResidualUsd: curve.at(-1).equity_end_usd - limits.capitalUsd -
                    funded.reduce((n, t) => n + t.netUsd, 0) - dividendAt(terminalAt, false) + externalCostAt(terminalAt) } }),
    };
}

/** Fixed new-cycle contract. Existing replay behavior is unchanged without profit8. */
function assertProfit8Signal(signal, data) {
    const session = data.sessions.find(s => s.open <= signal.at && signal.at < s.close);
    (0, ultimate_contracts_1.need)(session !== undefined && signal.at === session.open + 3600000 + 1000 &&
        signal.hypothesis === "CLOSED_CHANNEL" && signal.direction === 1 &&
        [24, 72].includes(signal.metadata?.roadmapHorizonHours) &&
        !signal.metadata?.roadmapExit && !signal.metadata?.researchExit &&
        Number.isFinite(signal.stopDistance) && signal.stopDistance > 0 &&
        (signal.plannedEntryAt === undefined || signal.plannedEntryAt === planSignalEntryAt(signal.at, data.sessions)),
        "PROFIT8_FIXED_SIGNAL_CLOCK_POLICY_AND_HORIZON");
}
function commonProfit8Price(signal, series) {
    const reference = causalReferencePrice(signal, series);
    if (reference.status !== "AVAILABLE") return { status: "NO_CAUSAL_PRICE", reference };
    (0, ultimate_contracts_1.need)(series.pointValue === 1 && Number.isFinite(series.tick) && series.tick > 0,
        "PROFIT8_CASH_SHARE_TICK");
    const priceCeiling = round(reference.price * 1.003, series.tick, false);
    (0, ultimate_contracts_1.need)(priceCeiling >= series.tick, "PROFIT8_POSITIVE_IOC_PRICE");
    return { status: "PLANNED", reference, priceCeiling };
}
/** Quantity uses only the last known price, fixed IOC ceiling and current account. */
function planProfit8FundedEntry(signal, series, p, limits, state) {
    const common = commonProfit8Price(signal, series);
    if (common.status !== "PLANNED") return common;
    const { equity, openRisk, notional, cashBudgetUsd } = state;
    (0, ultimate_contracts_1.need)([equity, openRisk, notional, cashBudgetUsd].every(Number.isFinite) &&
        equity > 0 && openRisk >= 0 && notional >= 0, "PROFIT8_FUNDED_SIZING_STATE");
    const distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
    const fee = p.costs.perSideUsd;
    const friction = (p.costs.spreadBps / 2 + p.costs.slippageBps) / 10000;
    const riskUnit = distance + 2 * fee + 2 * common.priceCeiling * friction;
    (0, ultimate_contracts_1.need)(Number.isFinite(riskUnit) && riskUnit > 0, "PROFIT8_FINITE_WORST_RISK");
    const riskBudgetUsd = Math.max(0, Math.min(equity * limits.riskFraction,
        equity * limits.openRiskFraction - openRisk));
    const notionalBudgetUsd = Math.max(0, Math.min(equity * limits.assetFraction,
        equity * limits.grossFraction - notional));
    const quantity = Math.floor(Math.max(0, Math.min(riskBudgetUsd / riskUnit,
        notionalBudgetUsd / common.priceCeiling,
        cashBudgetUsd / (common.priceCeiling + fee))));
    (0, ultimate_contracts_1.need)(Number.isSafeInteger(quantity), "PROFIT8_SAFE_INTEGER_QUANTITY");
    return { ...common, quantity, riskUnit, riskBudgetUsd, notionalBudgetUsd, cashBudgetUsd,
        roundedStopDistance: distance, quantityBasis: "COMMON_IOC_WORST_PRICE_PLUS_FEES_AND_ROUNDED_STOP" };
}
/** Changing quantity cannot change this limit or the modeled opening fill event. */
function planProfit8IocLimit(signal, series, p, budgets) {
    const common = commonProfit8Price(signal, series);
    if (common.status !== "PLANNED") return common;
    const q = budgets.plannedQuantity;
    (0, ultimate_contracts_1.need)(signal.direction === 1 && Number.isSafeInteger(q) && q > 0 &&
        [budgets.riskBudgetUsd, budgets.notionalBudgetUsd, budgets.cashBudgetUsd].every(v =>
            typeof v === "number" && Number.isFinite(v) && v >= 0), "PROFIT8_IOC_BUDGET_CONTRACT");
    const distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
    const friction = (p.costs.spreadBps / 2 + p.costs.slippageBps) / 10000;
    const risk = q * (distance + 2 * p.costs.perSideUsd + 2 * common.priceCeiling * friction);
    (0, ultimate_contracts_1.need)(risk <= budgets.riskBudgetUsd + 1e-8 &&
        q * common.priceCeiling <= budgets.notionalBudgetUsd + 1e-8 &&
        q * (common.priceCeiling + p.costs.perSideUsd) <= budgets.cashBudgetUsd + 1e-8,
        "PROFIT8_QUANTITY_EXCEEDS_COMMON_IOC_BUDGET");
    return { ...common, reason: null, decisionAt: signal.at,
        plannedEntryAt: signal.plannedEntryAt ?? null, quantity: q,
        roundedStopDistance: distance, modeledWorstRiskUsd: risk,
        budgets: { ...budgets }, bufferFraction: 0.003,
        model: "BUY_IOC_AT_PLANNED_OPEN_ONLY;COMMON_CAUSAL_REFERENCE_PLUS_30BPS_DOWN_TO_TICK;NO_QUEUE_CLAIM" };
}
function profit8BasisWeights(quantity) {
    (0, ultimate_contracts_1.need)(Number.isSafeInteger(quantity) && quantity >= 0, "PROFIT8_BASIS_QUANTITY");
    const twicePartial = 2 * Math.floor(quantity / 4);
    return [twicePartial, quantity - twicePartial];
}
function profit8Covariance(matrix, name) {
    (0, ultimate_contracts_1.need)(Array.isArray(matrix) && matrix.length === 2 &&
        matrix.every(row => Array.isArray(row) && row.length === 2 && row.every(Number.isFinite)),
        "PROFIT8_" + name + "_FINITE_2X2");
    const a = matrix[0][0], d = matrix[1][1], b = (matrix[0][1] + matrix[1][0]) / 2;
    const scale = Math.max(Math.abs(matrix[0][1]), Math.abs(matrix[1][0]), 1e-30);
    (0, ultimate_contracts_1.need)(a >= 0 && d >= 0 &&
        Math.abs(matrix[0][1] - matrix[1][0]) <= 1e-10 * scale &&
        a * d - b * b >= -1e-10 * Math.max(a * d, b * b, 1e-30),
        "PROFIT8_" + name + "_SYMMETRIC_PSD");
    return [[a, b], [b, d]];
}
/** Net policy bases are already after trading costs: no second cost deduction. */
function selectProfit8Quantity(signal, qMax, equity, referencePrice, mode) {
    (0, ultimate_contracts_1.need)(Number.isSafeInteger(qMax) && qMax >= 0 && Number.isFinite(equity) &&
        equity > 0 && Number.isFinite(referencePrice) && referencePrice > 0 &&
        ["NATIVE_MAX", "MAX_POSITIVE", "ROBUST_LOG"].includes(mode), "PROFIT8_SIZING_ARGUMENTS");
    if (mode === "NATIVE_MAX") return { mode, qMax, quantity: qMax, reason: "NATIVE_COMMON_IOC_MAXIMUM",
        referencePrice, equityUsd: equity, candidates: [], forecastUsed: false };
    const f = signal.metadata?.profit8Forecast;
    (0, ultimate_contracts_1.need)(f && JSON.stringify(f.basis_order) === '["E","T"]' &&
        Array.isArray(f.mean) && f.mean.length === 2 && f.mean.every(Number.isFinite) &&
        Number.isFinite(f.normalizer_price) &&
        Math.abs(f.normalizer_price - referencePrice) <= 1e-10 * Math.max(1, referencePrice) &&
        Number.isSafeInteger(f.trained_through) && Number.isSafeInteger(f.available_at) &&
        f.trained_through < signal.at && f.trained_through <= f.available_at && f.available_at <= signal.at &&
        typeof f.model_id === "string" && f.model_id.length > 0, "PROFIT8_CAUSAL_FORECAST_CONTRACT");
    const covariance = profit8Covariance(f.covariance, "OUTCOME_COVARIANCE");
    const meanCovariance = profit8Covariance(f.mean_covariance, "MEAN_COVARIANCE");
    const quadratic = (a, matrix) => Math.max(0, a[0] * a[0] * matrix[0][0] +
        2 * a[0] * a[1] * matrix[0][1] + a[1] * a[1] * matrix[1][1]);
    const evaluate = q => {
        const a = profit8BasisWeights(q);
        const meanUsd = referencePrice * (a[0] * f.mean[0] + a[1] * f.mean[1]);
        const varianceUsd2 = referencePrice * referencePrice * quadratic(a, covariance);
        const meanVarianceUsd2 = referencePrice * referencePrice * quadratic(a, meanCovariance);
        const meanSeUsd = Math.sqrt(meanVarianceUsd2);
        const utility = meanUsd / equity - 0.5 * (varianceUsd2 + meanUsd * meanUsd) / (equity * equity) - meanSeUsd / equity;
        (0, ultimate_contracts_1.need)([meanUsd, varianceUsd2, meanVarianceUsd2, meanSeUsd, utility].every(Number.isFinite),
            "PROFIT8_FINITE_SIZING_OBJECTIVE");
        return { quantity: q, basisWeights: a, meanUsd, varianceUsd2, meanVarianceUsd2, meanSeUsd, utility };
    };
    const candidates = mode === "ROBUST_LOG"
        ? Array.from({ length: qMax + 1 }, (_, q) => evaluate(q))
        : qMax ? [evaluate(0), evaluate(qMax)] : [evaluate(0)];
    let chosen = candidates[0];
    if (mode === "MAX_POSITIVE") {
        if (candidates.at(-1).meanUsd > 0) chosen = candidates.at(-1);
    } else for (const candidate of candidates) if (candidate.utility > chosen.utility) chosen = candidate;
    return { mode, qMax, quantity: chosen.quantity,
        reason: chosen.quantity > 0 ? "POSITIVE_NET_POLICY_VALUE" : mode === "ROBUST_LOG"
            ? "NONPOSITIVE_ROBUST_LOG_UTILITY" : "NONPOSITIVE_EXPECTED_NET",
        referencePrice, equityUsd: equity, modelId: f.model_id, forecastUsed: true,
        meanBasis: f.mean, covariance, meanCovariance, uncertaintyPenalty: 1,
        objective: "m/E-0.5*(v+m*m)/(E*E)-sqrt(meanVariance)/E", chosen, candidates };
}
function profit8KnownAt(trade) {
    return Math.max(trade.closed, ...trade.marks.map(mark => mark.at),
        ...(trade.inventoryEvents ?? []).map(event => event.knownAt));
}
/**
 * Two exact payoff bases under the fixed native policy and common IOC fill:
 * T=P(1), E=(P(4)-2*T)/2; P(q)=2*floor(q/4)*E+(q-2*floor(q/4))*T.
 * A teacher is an independent hypothetical path, never a funded account trial.
 * Both targets mature at the complete requested deadline cohort, even after STOP.
 */
function replayProfit8Teacher(rawSignal, series, data, p) {
    assertProfit8Signal(rawSignal, data);
    (0, ultimate_contracts_1.need)(p.kind === "ALPACA_PROXY" && series.pointValue === 1,
        "PROFIT8_TEACHER_LONG_CASH_SHARE_SCOPE");
    const plannedEntryAt = rawSignal.plannedEntryAt ?? planSignalEntryAt(rawSignal.at, data.sessions);
    const signal = { ...rawSignal, plannedEntryAt };
    const common = commonProfit8Price(signal, series);
    const base = { signal_id: signal.id, symbol: signal.symbol, decision_at: signal.at,
        horizon_hours: signal.metadata.roadmapHorizonHours, planned_entry_at: plannedEntryAt,
        basis_order: ["E", "T"], origin: "HISTORICAL", execution: "MODELED_OHLCV",
        label_end: null, label_known_at: null, fill: null, fill_flag: null,
        E: null, T: null, E_usd: null, T_usd: null, net_basis: null,
        gross_deadline_return: null, quantity1_net_usd: null, quantity4_net_usd: null,
        financial_acceptance_allowed: false };
    if (common.status !== "PLANNED") return { ...base, status: "REFUSED_BEFORE_ENTRY", reason: "NO_CAUSAL_REFERENCE_PRICE" };
    const holding = planCalendarHolding(signal, plannedEntryAt, data, p);
    Object.assign(base, { ref_price: common.reference.price, limit_price: common.priceCeiling,
        reference_available_at: common.reference.sourceAvailableAt, label_end: holding.deadlineAt });
    if (holding.status !== "SCHEDULED") return { ...base, status: "REFUSED_BEFORE_ENTRY", reason: holding.reason };
    const first = series.bars.find(bar => bar.t === plannedEntryAt);
    const deadline = series.bars.find(bar => bar.t === holding.deadlineAt);
    if (!first || !deadline) return { ...base, status: "BLOCKED_UNOBSERVED_PATH",
        reason: !first ? "MISSING_PLANNED_ENTRY_BAR" : "MISSING_DEADLINE_COHORT_BAR" };
    if (data.splitEvents.some(e => e.symbol === signal.symbol && e.at > first.t && e.at <= holding.deadlineAt))
        return { ...base, status: "BLOCKED_UNOBSERVED_PATH", reason: "CORPORATE_ACTION_PATH_UNMODELED" };
    const friction = (p.costs.spreadBps / 2 + p.costs.slippageBps) / 10000;
    const modeledEntry = round(first.o * (1 + friction), series.tick, true);
    const cohortKnownAt = Math.max(first.availableAt, deadline.availableAt);
    Object.assign(base, { gross_entry_open: first.o, gross_deadline_open: deadline.o,
        deadline_bar_available_at: deadline.availableAt });
    if (modeledEntry > common.priceCeiling + 1e-8) return { ...base,
        status: "MODELED_IOC_NO_FILL", reason: "MODELED_OPEN_ABOVE_IOC_LIMIT", fill: false, fill_flag: 0,
        label_known_at: cohortKnownAt, resolution_at: plannedEntryAt, observed_open_fill_price: modeledEntry,
        E: 0, T: 0, E_usd: 0, T_usd: 0, net_basis: [0, 0],
        gross_deadline_return: 0, quantity1_net_usd: 0, quantity4_net_usd: 0 };
    try {
        const opts = { cashDividends: true, profit8Trace: true };
        const one = replayCampaign(signal, series, data, p, "BASELINE", 1, 1, opts);
        const four = replayCampaign(signal, series, data, p, "BASELINE", 4, 1, opts);
        (0, ultimate_contracts_1.need)(one && four && one.opened === four.opened && one.entry === four.entry &&
            one.closed === four.closed && one.reason === four.reason &&
            one.holdingDeadlineAt === four.holdingDeadlineAt &&
            one.inventoryEvents.at(-1).filledPrice === four.inventoryEvents.at(-1).filledPrice &&
            JSON.stringify(one.marks.map(mark => mark.at)) === JSON.stringify(four.marks.map(mark => mark.at)),
            "PROFIT8_TEACHER_QUANTITY_DEPENDENT_POLICY_PATH");
        const T = one.netEconomicUsd, E = (four.netEconomicUsd - 2 * T) / 2;
        const ref = common.reference.price;
        const trace = trade => ({ quantity: trade.quantity, opened: trade.opened, closed: trade.closed,
            holdingDeadlineAt: trade.holdingDeadlineAt, entry: trade.entry,
            inventoryEvents: trade.inventoryEvents, dividendEntitlements: trade.dividendEntitlements,
            netUsd: trade.netUsd, feesUsd: trade.feesUsd, dividendAccruedUsd: trade.dividendAccruedUsd,
            netEconomicUsd: trade.netEconomicUsd, maximum_policy_known_at: profit8KnownAt(trade) });
        return { ...base, status: "OBSERVED_MODELED_PATH", reason: null, fill: true, fill_flag: 1,
            label_known_at: Math.max(cohortKnownAt, profit8KnownAt(one), profit8KnownAt(four)),
            policy_closed_at: one.closed, policy_exit_reason: one.reason,
            entry_price: one.entry, terminal_exit_price: one.inventoryEvents.at(-1).filledPrice,
            E: E / ref, T: T / ref, E_usd: E, T_usd: T, net_basis: [E / ref, T / ref],
            gross_deadline_return: (deadline.o - first.o) / ref,
            quantity1_net_usd: one.netEconomicUsd, quantity4_net_usd: four.netEconomicUsd,
            quantity1_dividend_usd: one.dividendAccruedUsd, quantity4_dividend_usd: four.dividendAccruedUsd,
            quantity1_fees_usd: one.feesUsd, quantity4_fees_usd: four.feesUsd,
            quantity1_trace: trace(one), quantity4_trace: trace(four),
            maturity_basis: "MAX_DEADLINE_BAR_AVAILABLE_AT_AND_ALL_POLICY_MARKS_AND_INVENTORY_KNOWLEDGE",
            label_scope: "INDEPENDENT_POLICY_PAYOFF_BASES;NO_PORTFOLIO_OR_FIXED_CALENDAR_OVERHEAD" };
    } catch (error) {
        if (!(error instanceof UnobservedEntryError) && !(error instanceof UnresolvedHoldingExposureError)) throw error;
        return { ...base, status: "BLOCKED_UNOBSERVED_PATH", reason: error.details?.reason ?? error.code,
            error_code: error.code, details: error.details };
    }
}
