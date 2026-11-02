"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.fills = fills;
exports.exitDecision = exitDecision;
exports.observeExit = observeExit;
exports.availableSize = availableSize;
exports.freezeExit = freezeExit;
exports.deadlineFor = deadlineFor;
const types_1 = require("./types");
function fills(c, intents) {
    let bought = 0, sold = 0, paid = 0, received = 0, tpSold = 0;
    for (const i of intents.filter((i) => i.campaign === c.id)) {
        const q = Number(i.order?.filled_qty || 0), p = Number(i.order?.filled_avg_price || 0);
        if (q < 0 || !Number.isFinite(q) || (q > 0 && !(0, types_1.positive)(p)))
            throw Error("Invalid broker fill");
        if (i.kind === "entry") {
            bought += q;
            paid += q * p;
        }
        else {
            sold += q;
            received += q * p;
            if (i.kind === "tp1" ||
                i.kind === "tp2" ||
                (i.kind === "protect" &&
                    !i.parentId &&
                    ["tp1", "tp2"].includes(i.nativeRole || "") &&
                    i.payload.order_class === "oco"))
                tpSold += q;
        }
    }
    return {
        bought,
        sold,
        paid,
        received,
        tpSold,
        qty: Math.max(0, bought - sold),
        entry: bought ? paid / bought : 0,
        gross: (received - (bought ? paid / bought : 0) * sold) *
            c.instrument.multiplier,
    };
}
function exitDecision(c, intents, q, qty, now, cfg) {
    const f = fills(c, intents);
    if (qty <= 0 || !f.entry)
        return null;
    if (c.flatten)
        return { kind: "flatten", qty };
    if (c.strategyClose)
        return { kind: "signal", qty };
    // Close before expiration day to reduce assignment/exercise exposure, including holidays.
    if (c.instrument.expiry &&
        now >= Date.parse(c.instrument.expiry + "T00:00:00Z") - 86400000)
        return { kind: "expiry", qty };
    if (now >= (c.deadline || c.created + c.policy.maxHoldHours * 3600000))
        return { kind: "time", qty };
    if (!(0, types_1.fresh)(q, now, cfg.quoteAgeMs))
        return null;
    const friction = (c.book === "crypto" ? 2 * cfg.cryptoFeeBps : 0) + 2 * cfg.slippageBps;
    const cost = (f.entry * friction) / 10000 +
        (c.book === "options"
            ? (2 * cfg.optionsFeePerContract) / c.instrument.multiplier
            : 0);
    c.peak = Math.max(c.peak, q.bid);
    const profit = c.peak - f.entry - cost;
    // The trailing floor only tightens after the first target has genuinely traded in the bid.
    if (profit >= c.policy.tp1R * c.risk)
        c.stop = Math.max(c.stop, f.entry + cost + profit * c.policy.lockFraction, c.peak -
            c.policy.trailR *
                c.risk *
                (c.policy.trailingMode === "realized_vol" &&
                    (0, types_1.positive)(c.entryAtr) &&
                    (0, types_1.positive)(c.dynamicAtr)
                    ? c.dynamicAtr / c.entryAtr
                    : 1));
    if (q.bid <= c.stop)
        return { kind: "stop", qty };
    const net = q.bid - f.entry - cost;
    const target = net >= c.policy.tp2R * c.risk
        ? c.policy.tp1Fraction + c.policy.tp2Fraction
        : net >= c.policy.tp1R * c.risk
            ? c.policy.tp1Fraction
            : 0;
    if (target > 0) {
        const wanted = (0, types_1.floorStep)(Math.max(0, f.bought * target - f.tpSold), c.instrument.step);
        const n = Math.min(qty, wanted);
        if (n >= c.instrument.minQty)
            return { kind: target > c.policy.tp1Fraction ? "tp2" : "tp1", qty: n };
        // A one-contract option cannot be split. Realize it at TP2 instead of losing the target entirely.
        if (c.book === "options" && f.bought === 1 && net >= c.policy.tp2R * c.risk)
            return { kind: "tp2", qty };
    }
    if ((0, types_1.positive)(c.policy.stagnationMinutes) &&
        (c.stagnationMs || 0) >= c.policy.stagnationMinutes * 60000 &&
        net < (c.policy.progressR ?? 1) * c.risk)
        return { kind: "stagnation", qty };
    return null;
}
/** Update from observed quotes only. Closed sessions do not consume the stagnation clock. */
function observeExit(c, q, now, calendar, legacy) {
    const elapsed = c.book === "crypto"
        ? Math.max(0, now - (c.lastMark ?? c.created))
        : legacy.HX.tradingMillis(c.lastMark ?? c.created, now, calendar);
    c.stagnationMs = q.bid > c.peak ? 0 : (c.stagnationMs || 0) + elapsed;
    c.lastMark = now;
    if (c.policy.trailingMode === "realized_vol" && (0, types_1.positive)(c.entryAtr)) {
        const v = legacy.HXII.updateVol(c.volatility, q.bid, q.at, c.entryAtr);
        c.volatility = v.state;
        c.dynamicAtr = v.atr;
    }
}
function availableSize(s, asset, cfg, account, positions, campaigns, intents) {
    const equity = Math.min(Number(account.equity), cfg.capitalLimit), cash = Math.min(Number(account.cash), Number(account.buying_power));
    if (!(0, types_1.positive)(equity) ||
        !Number.isFinite(cash) ||
        cash <= 0 ||
        !asset.tradable ||
        !(0, types_1.positive)(s.entry) ||
        !(0, types_1.positive)(s.stop) ||
        s.stop >= s.entry)
        return 0;
    if (positions.length >= cfg.maxPositions ||
        positions.some((p) => String(p.symbol).replace("/", "") === s.symbol.replace("/", "")))
        return 0;
    const pending = intents.filter((i) => i.kind === "entry" && !types_1.TERMINAL.has(i.status));
    const reserve = pending.reduce((n, i) => n +
        Number(i.payload.qty) *
            Number(i.payload.limit_price) *
            (campaigns.find((c) => c.id === i.campaign)?.instrument.multiplier ||
                1), 0);
    let used = 0, factorUsed = 0, openRisk = 0;
    for (const c of campaigns.filter((c) => !c.closed)) {
        const f = fills(c, intents), nominal = Math.max(Math.max(0, f.qty) * f.entry * c.instrument.multiplier, Math.abs(Number(positions.find((p) => String(p.symbol).replace("/", "") === c.symbol.replace("/", ""))?.market_value) || 0));
        used += nominal;
        if (c.instrument.factor === asset.factor)
            factorUsed += nominal * c.instrument.leverage;
        openRisk +=
            f.qty *
                (c.book === "options" ? f.entry : c.risk) *
                c.instrument.multiplier;
    }
    // Market-value exposure includes unrealized gains; entry reservations include uncertain POSTs.
    used =
        Math.max(used, positions.reduce((n, p) => n + Math.abs(Number(p.market_value) || 0), 0)) + reserve;
    const bp = asset.book === "crypto"
        ? Number(account.non_marginable_buying_power)
        : asset.book === "options"
            ? Number(account.options_buying_power)
            : Number(account.buying_power);
    if (!Number.isFinite(bp) || bp <= 0)
        return 0;
    const cost = (s.entry *
        ((asset.book === "crypto" ? 2 * cfg.cryptoFeeBps : 0) +
            2 * cfg.slippageBps)) /
        10000 +
        (asset.book === "options"
            ? (2 * cfg.optionsFeePerContract) / asset.multiplier
            : 0);
    // Long-option allocation reserves the entire premium as loss, not a hypothetical stop fill.
    const unitRisk = (asset.book === "options" ? s.entry : s.entry - s.stop) + cost;
    const cap = Math.max(0, Math.min(cash - reserve, bp - reserve, equity * cfg.assetExposure, equity * cfg.totalExposure - used, (equity * cfg.factorExposure - factorUsed) / asset.leverage));
    const riskRoom = Math.max(0, Math.min(equity * cfg.riskFraction, equity * cfg.openRiskFraction - openRisk - reserve));
    const n = (0, types_1.floorStep)(Math.min(cap / (s.entry * asset.multiplier * (1 + cost / s.entry)), riskRoom / (unitRisk * asset.multiplier)), asset.step);
    return n >= asset.minQty ? n : 0;
}
function freezeExit(raw, cfg) {
    return {
        ...types_1.DEFAULT_EXIT,
        ...cfg.exit,
        ...raw,
        maxHoldHours: Math.min(72, raw.maxHoldHours || cfg.exit.maxHoldHours),
    };
}
function deadlineFor(book, now, hours, calendar, expiry) {
    const target = Math.min(now + Math.min(72, hours) * 3600000, expiry ? Date.parse(expiry + "T00:00:00Z") - 86400000 : Infinity);
    if (book === "crypto")
        return target;
    const rows = calendar
        .filter((s) => Number.isFinite(s.open) &&
        Number.isFinite(s.close) &&
        s.open <= target)
        .sort((a, b) => a.close - b.close), session = rows.at(-1);
    if (!session)
        throw Error("Calendar insufficient for exit deadline");
    const deadline = Math.min(target, session.close - 600000);
    if (deadline <= now)
        throw Error("No executable holding window");
    return deadline;
}
