"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.DEFAULT_REPLAY_LIMITS = exports.UnresolvedHoldingExposureError = void 0;
exports.planCalendarHolding = planCalendarHolding;
exports.opportunities = opportunities;
exports.nextTrailingStop = nextTrailingStop;
exports.replayCampaign = replayCampaign;
exports.runStudy = runStudy;
const ultimate_contracts_1 = require("./ultimate_contracts");
const ultimate_stats_1 = require("./ultimate_stats");
const ultimate_frequency_1 = require("./ultimate_frequency");
const policy_1 = require("./policy");
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
    let target;
    try {
        // Runtime anchors at decision/submission time, not a later pending fill.
        target = (0, policy_1.deadlineFor)("equity", signal.at, 72, data.sessions);
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
const efficiency = (a) => {
    const changes = a.slice(1).map((b, i) => Math.abs(b.c - a[i].c)), sum = changes.reduce((x, y) => x + y, 0);
    return sum > 0 ? Math.abs(a.at(-1).c - a[0].c) / sum : 0;
};
const atr = (a) => (0, ultimate_stats_1.mean)(a
    .slice(1)
    .map((b, i) => Math.max(b.h - b.l, Math.abs(b.h - a[i].c), Math.abs(b.l - a[i].c))));
const round = (n, tick, up) => (up ? Math.ceil(n / tick - 1e-8) : Math.floor(n / tick + 1e-8)) * tick;
/** All feature values come from bars available at signal.at; current daily close is never a feature. */
function opportunities(data, p) {
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
            if (bars.length !== (session.close - session.open) / 300000 ||
                bars[0].t !== session.open ||
                bars.at(-1).end !== session.close ||
                bars.some((b, i) => i && b.t !== bars[i - 1].end)) {
                funnel.incompleteSessions++;
                continue;
            }
            const fired = new Set(), prior = previousDays.slice(-50), daily = prior.map((x) => x.daily);
            const priorBars = prior.slice(-2).flatMap((x) => x.bars);
            let vol = 0, vwSum = 0, square = 0;
            for (let j = 0; j < bars.length; j++) {
                const b = bars[j], x = b.vw ?? (b.h + b.l + b.c) / 3;
                vol += b.v;
                vwSum += x * b.v;
                square += x * x * b.v;
                if (j < 3 || prior.length < 20 || !b.v || !vol) {
                    funnel.warmup++;
                    continue;
                }
                const fillIndex = indexes.get(b) + (b.availableAt > b.end ? 2 : 1), next = series.bars[fillIndex];
                if (!next ||
                    next.t < b.availableAt ||
                    next.t - b.end > 300000 ||
                    next.t >= session.close - 300000) {
                    funnel.dataGap++;
                    continue;
                }
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
            previousDays.push({
                bars,
                daily: {
                    t: session.open,
                    end: session.close,
                    availableAt: session.close + 3000,
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
function replayCampaign(signal, series, data, p, policy, quantity = 4, costMultiplier = 1) {
    (0, ultimate_contracts_1.need)(Number.isInteger(quantity) && quantity > 0 && costMultiplier >= 1, "replay size/cost");
    const first = series.bars[signal.index], dir = signal.direction, friction = ((p.costs.spreadBps / 2 + p.costs.slippageBps) * costMultiplier) / 10000;
    if (!first || first.t < signal.at)
        return null;
    const entry = round(first.o * (1 + dir * friction), series.tick, dir === 1), distance = Math.ceil(signal.stopDistance / series.tick) * series.tick;
    let stop = entry - dir * distance, remaining = quantity, realized = -p.costs.perSideUsd * quantity * costMultiplier, fees = -realized, peak = entry, peakPnl = 0, ambiguous = 0, reason = "DATA_ENDED", closed = first.t, pendingStop;
    const session = data.sessions.find((s) => first.t >= s.open && first.t < s.close);
    // Match the existing cash-equity runtime deadline. The supplied session
    // calendar is the scheduling input; no later price or future bar existence
    // chooses the deadline. Calendar publication-time provenance remains a data
    // requirement, not something reconstructed from a successful historical fill.
    const holdingPlan = planCalendarHolding(signal, first.t, data, p), calendarHolding = holdingPlan.status !== "NOT_APPLICABLE";
    let deadline;
    if (calendarHolding) {
        if (holdingPlan.status === "REFUSED_BEFORE_ENTRY")
            return null;
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
    if (data.splitEvents.some((e) => e.symbol === series.symbol && e.at > first.t && e.at <= deadline))
        return null;
    const marks = [], tpDone = [false, false];
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
    const close = (qty, px, at, why) => {
        if (qty <= 0)
            return;
        const filled = round(px * (1 - dir * friction), series.tick, dir !== 1), charge = qty * p.costs.perSideUsd * costMultiplier;
        realized += dir * (filled - entry) * qty * series.pointValue - charge;
        fees += charge;
        remaining -= qty;
        closed = at;
        reason = why;
    };
    for (let i = signal.index; i < series.bars.length && remaining; i++) {
        const b = series.bars[i], prior = series.bars[i - 1];
        if (i > signal.index &&
            b.t !== prior.end &&
            !data.sessions.some((s) => s.open === b.t &&
                s.close >= b.end &&
                prior.end === data.sessions.find((z) => z.close === prior.end)?.close)) {
            if (calendarHolding)
                unresolved("MISSING_BAR_WITH_OPEN_EXPOSURE", b.t);
            return null;
        }
        if (pendingStop && b.t >= pendingStop.at) {
            stop = pendingStop.price;
            pendingStop = undefined;
        }
        if (calendarHolding &&
            b.t > Math.min(deadline, contractDeadline))
            unresolved("NO_EXECUTABLE_BAR_AT_PLANNED_DEADLINE", b.t);
        if (b.t >= Math.min(deadline, contractDeadline)) {
            close(remaining, b.o, b.t, b.t >= contractDeadline ? "CONTRACT_DEADLINE" : "TIME");
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
            close(remaining, dir === 1 ? Math.min(b.o, stop) : Math.max(b.o, stop), b.end, "STOP");
        else {
            if (signal.hypothesis === "VWAP_REVERSION" &&
                signal.target &&
                (dir === 1
                    ? b.h >= signal.target && signal.target > entry
                    : b.l <= signal.target && signal.target < entry))
                close(remaining, signal.target, b.end, "VWAP");
            for (let j = 0; j < 2 && remaining; j++) {
                const target = round(entry + dir * targets[j] * distance, series.tick, dir === 1), qty = Math.floor(quantity * 0.25);
                if (!tpDone[j] &&
                    Number.isFinite(target) &&
                    (dir === 1 ? b.h >= target : b.l <= target)) {
                    close(Math.min(qty, remaining), target, b.end, "TP" + (j + 1));
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
        if (calendarHolding)
            unresolved("DATA_ENDED_WITH_OPEN_EXPOSURE", null);
        return null; // Other legacy research scopes retain their explicit incomplete-path exclusion.
    }
    const riskUsd = quantity * distance * series.pointValue;
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
        ...(calendarHolding
            ? { holdingDeadlineAt: deadline, holdingClockStartedAt: signal.at }
            : {}),
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
    // Funded replay has independent integer sizing and shared capital. Futures require historical margin observations.
    const funded = [], portfolioSkips = {};
    const skip = (reason) => {
        portfolioSkips[reason] = (portfolioSkips[reason] || 0) + 1;
    };
    let peakEquity = limits.capitalUsd;
    for (const opportunity of common) {
        const fold = folds.find((f) => opportunity.at >= f.test[0].open &&
            opportunity.at <= f.test.at(-1).close - purge);
        if (!fold ||
            fold.selected === "CASH" ||
            !fold.selected.startsWith(opportunity.hypothesis + ":"))
            continue;
        if (p.kind === "FUTURES") {
            skip("HISTORICAL_MARGIN_UNAVAILABLE");
            continue;
        }
        const active = funded.filter((t) => t.opened <= opportunity.at && t.closed > opportunity.at);
        const equityAt = (at) => limits.capitalUsd +
            funded.reduce((n, t) => n +
                (t.closed <= at
                    ? t.netUsd
                    : t.opened <= at
                        ? (t.marks.findLast((m) => m.at <= at)?.pnl ?? 0)
                        : 0), 0);
        const equity = equityAt(opportunity.at), day = data.sessions.find((s) => opportunity.at >= s.open && opportunity.at < s.close);
        peakEquity = Math.max(peakEquity, equity);
        if (equity <= peakEquity * (1 - limits.maxDrawdown) ||
            equity <= equityAt(day.open) * (1 - limits.dailyLoss)) {
            skip("LOSS_LIMIT");
            continue;
        }
        if (active.some((t) => t.symbol === opportunity.symbol)) {
            skip("SYMBOL_BUSY");
            continue;
        }
        const s = bySymbol[opportunity.symbol], px = s.bars[opportunity.index].o;
        const riskUnit = opportunity.stopDistance * s.pointValue +
            2 * p.costs.perSideUsd +
            (2 * px * s.pointValue * (p.costs.spreadBps / 2 + p.costs.slippageBps)) /
                10000;
        const notional = active.reduce((n, t) => n + t.quantity * t.entry, 0), openRisk = active.reduce((n, t) => n + t.riskUsd, 0);
        const quantity = Math.floor(Math.min((equity * limits.riskFraction) / riskUnit, Math.max(0, equity * limits.openRiskFraction - openRisk) / riskUnit, Math.max(0, equity * limits.grossFraction - notional) / px, (equity * limits.assetFraction) / px));
        if (quantity < 1) {
            skip("INTEGER_RISK_OR_EXPOSURE");
            continue;
        }
        const t = replayCampaign(opportunity, s, data, p, fold.selected.split(":")[1], quantity);
        if (t)
            funded.push(t);
        else
            skip("INCOMPLETE_PATH");
    }
    const fundedPnl = oos.map((s, i) => {
        const at = (time) => funded.reduce((n, t) => n +
            (time < t.opened
                ? 0
                : time >= t.closed
                    ? t.netUsd
                    : (t.marks.findLast((m) => m.at <= time)?.pnl ?? 0)), 0);
        return at(s.close) - at(i ? oos[i - 1].close : s.open - 1);
    });
    let eq = limits.capitalUsd;
    const fundedReturns = fundedPnl.map((pnl) => {
        const r = pnl / eq;
        eq += pnl;
        return r;
    });
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
        fundedPortfolio: {
            scope: "MODELED_SHARED_CAPITAL_INTEGER_LOTS",
            limits,
            oos: (0, ultimate_stats_1.metrics)(fundedReturns, funded.map((t) => t.netR)),
            netUsd: funded.reduce((n, t) => n + t.netUsd, 0),
            skipped: portfolioSkips,
        },
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
