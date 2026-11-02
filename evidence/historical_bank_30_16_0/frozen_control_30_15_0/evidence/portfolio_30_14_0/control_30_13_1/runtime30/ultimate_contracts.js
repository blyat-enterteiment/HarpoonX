"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.FUTURES_SPECS = exports.EXIT_VARIANTS = exports.HYPOTHESES = exports.ULTIMATE_VERSION = void 0;
exports.need = need;
exports.digest = digest;
exports.defaultProtocol = defaultProtocol;
exports.assertProtocol = assertProtocol;
exports.assertDataset = assertDataset;
const node_crypto_1 = require("node:crypto");
const validators_1 = require("./validators");
exports.ULTIMATE_VERSION = "30.3.0";
exports.HYPOTHESES = [
    "OPENING_BREAKOUT",
    "CLOSED_CHANNEL",
    "VWAP_REVERSION",
];
exports.EXIT_VARIANTS = ["BASELINE", "RUNNER", "REGIME"];
function need(ok, detail) {
    if (!ok)
        throw new validators_1.ContractError("ultimate", detail);
}
function digest(value) {
    function canonical(x) {
        if (Array.isArray(x))
            return x.map(canonical);
        if (x && typeof x === "object")
            return Object.fromEntries(Object.keys(x)
                .sort()
                .map((k) => [k, canonical(x[k])]));
        return x;
    }
    return (0, node_crypto_1.createHash)("sha256")
        .update(JSON.stringify(canonical(value)))
        .digest("hex");
}
exports.FUTURES_SPECS = Object.freeze({
    MES: {
        pointValue: 5,
        tick: 0.25,
        factor: "US_EQUITY",
        settlement: "CASH",
        stage: 1,
    },
    MNQ: {
        pointValue: 2,
        tick: 0.25,
        factor: "US_EQUITY",
        settlement: "CASH",
        stage: 1,
    },
    MGC: {
        pointValue: 10,
        tick: 0.1,
        factor: "GOLD",
        settlement: "PHYSICAL_ACE",
        stage: 2,
    },
    MCL: {
        pointValue: 100,
        tick: 0.01,
        factor: "WTI",
        settlement: "CASH",
        stage: 3,
    },
    M6E: {
        pointValue: 12500,
        tick: 0.0001,
        factor: "EURUSD",
        settlement: "PHYSICAL_FX",
        stage: 3,
    },
});
function defaultProtocol(kind = "FUTURES") {
    return {
        schema: "HARPOON-ULTIMATE-PROTOCOL-1",
        kind,
        universe: kind === "FUTURES" ? ["MES", "MNQ"] : ["SPY", "XLK"],
        trainSessions: 126,
        testSessions: 21,
        holdoutSessions: 63,
        purgeHours: 72,
        gapSessions: 3,
        bootstrapRuns: 2000,
        blockSessions: 5,
        familyTrials: 72,
        minOosCampaigns: 100,
        minHoldoutCampaigns: 30,
        knownHistoryThrough: Date.parse("2026-10-17T00:00:00Z"),
        costs: {
            spreadBps: kind === "FUTURES" ? 0 : 2,
            slippageBps: 2,
            perSideUsd: kind === "FUTURES" ? 1.5 : 0,
        },
    };
}
function assertProtocol(raw) {
    const p = structuredClone(raw);
    need(p?.schema === "HARPOON-ULTIMATE-PROTOCOL-1", "protocol schema");
    need(["FUTURES", "ALPACA_PROXY"].includes(p.kind), "research kind");
    need(Array.isArray(p.universe) &&
        p.universe.length > 0 &&
        p.universe.length <= 4 &&
        new Set(p.universe).size === p.universe.length, "universe length/duplicates");
    need(p.universe.every((s) => typeof s === "string" &&
        (p.kind === "FUTURES"
            ? Object.hasOwn(exports.FUTURES_SPECS, s)
            : /^[A-Z]{1,8}$/.test(s))), "unsupported universe");
    for (const [key, lo, hi] of [
        ["trainSessions", 60, 756],
        ["testSessions", 10, 63],
        ["holdoutSessions", 30, 252],
        ["gapSessions", 1, 20],
        ["bootstrapRuns", 500, 10000],
        ["blockSessions", 2, 30],
        ["familyTrials", 9 * p.universe.length, 128],
        ["minOosCampaigns", 100, 10000],
        ["minHoldoutCampaigns", 30, 10000],
    ])
        need(Number.isInteger(p[key]) && p[key] >= lo && p[key] <= hi, "invalid " + key);
    need(Number.isFinite(p.purgeHours) && p.purgeHours >= 72 && p.purgeHours <= 720, "purge must cover 72 hour labels");
    need(Number.isFinite(p.knownHistoryThrough) &&
        p.knownHistoryThrough >= Date.parse("2026-10-17T00:00:00Z") &&
        p.knownHistoryThrough <= Date.now(), "known historical cutoff");
    need(p.costs &&
        Object.values(p.costs).length === 3 &&
        Object.values(p.costs).every((x) => Number.isFinite(x) && x >= 0 && x <= 100), "cost assumptions");
    need(p.kind !== "FUTURES" || p.costs.perSideUsd >= 1.5, "championship micro commission floor excludes additional fees");
    return p;
}
function assertDataset(raw, p, now = Date.now()) {
    const d = raw;
    need(d?.schema === "HARPOON-ULTIMATE-DATA-1" && d.kind === p.kind, "dataset schema/kind");
    need(d.provenance?.execution === "MODELED_OHLCV" &&
        typeof d.provenance.source === "string" &&
        d.provenance.source.length > 0 &&
        d.provenance.source.length <= 200 &&
        typeof d.provenance.feed === "string", "provenance required");
    need(Array.isArray(d.provenance.files) &&
        d.provenance.files.length > 0 &&
        d.provenance.files.length <= 1000 &&
        d.provenance.files.every((f) => typeof f.name === "string" &&
            f.name.length <= 240 &&
            /^[a-f0-9]{64}$/.test(f.sha256)), "source file checksums");
    need(Array.isArray(d.sessions) &&
        d.sessions.length >=
            p.trainSessions +
                p.testSessions +
                p.holdoutSessions +
                2 * p.gapSessions &&
        d.sessions.length <= 3000, "insufficient/excess sessions");
    let previous = 0;
    const days = new Set();
    for (const s of d.sessions) {
        need(/^\d{4}-\d{2}-\d{2}$/.test(s.date) &&
            !days.has(s.date) &&
            Number.isSafeInteger(s.open) &&
            Number.isSafeInteger(s.close) &&
            s.open >= previous &&
            s.open < s.close &&
            s.close <= now, "invalid/overlapping/future session");
        previous = s.close;
        days.add(s.date);
    }
    need(Array.isArray(d.splitEvents) &&
        d.splitEvents.length <= 1000 &&
        d.splitEvents.every((e) => typeof e.symbol === "string" &&
            Number.isSafeInteger(e.at) &&
            e.at <= now &&
            Number.isFinite(e.ratio) &&
            e.ratio > 0), "corporate action manifest required");
    need(Array.isArray(d.series) &&
        d.series.length > 0 &&
        d.series.length <= 24 &&
        new Set(d.series.map((x) => x.symbol)).size === d.series.length, "series length/duplicates");
    let total = 0;
    for (const s of d.series) {
        need(typeof s.symbol === "string" &&
            /^[A-Z0-9:._]{1,130}$/.test(s.symbol) &&
            p.universe.includes(s.root), "series root/symbol");
        need(Number.isFinite(s.pointValue) &&
            s.pointValue > 0 &&
            Number.isFinite(s.tick) &&
            s.tick > 0, "multiplier/tick");
        if (p.kind === "FUTURES") {
            const spec = exports.FUTURES_SPECS[s.root];
            need(s.pointValue === spec.pointValue &&
                s.tick === spec.tick &&
                s.symbol !== s.root, "futures contract must be a dated contract with official multiplier");
            need(Number.isSafeInteger(s.lastTradeAt) && s.lastTradeAt > 0, "last trade deadline required");
            if (spec.settlement !== "CASH")
                need(Number.isSafeInteger(s.firstNoticeAt) && s.firstNoticeAt > 0, "physical delivery deadline required");
        }
        else
            need(s.symbol === s.root && s.pointValue === 1, "proxy is not a futures contract");
        need(Array.isArray(s.bars) &&
            s.bars.length > 0 &&
            (total += s.bars.length) <= 300000, "bar limit");
        let end = 0, sessionIndex = 0;
        for (const b of s.bars) {
            need([b.t, b.end, b.availableAt].every(Number.isSafeInteger) &&
                b.t >= end &&
                b.end - b.t === 300000 &&
                b.availableAt >= b.end &&
                b.availableAt <= b.end + 60000 &&
                b.availableAt <= now, "overlap, future or unsupported bar availability");
            need([b.o, b.h, b.l, b.c, b.v].every(Number.isFinite) &&
                b.l > 0 &&
                b.v >= 0 &&
                b.h >= Math.max(b.o, b.l, b.c) &&
                b.l <= Math.min(b.o, b.c), "OHLCV contract");
            need(b.vw === undefined ||
                (Number.isFinite(b.vw) && b.vw >= b.l && b.vw <= b.h), "VWAP outside bar");
            while (sessionIndex < d.sessions.length &&
                b.t >= d.sessions[sessionIndex].close)
                sessionIndex++;
            const session = d.sessions[sessionIndex];
            need(session && b.t >= session.open && b.end <= session.close, "bar outside declared sessions");
            need(p.kind !== "FUTURES" || b.end < s.lastTradeAt, "expired contract data");
            end = b.end;
        }
    }
    need(p.universe.every((root) => d.series.some((s) => s.root === root)), "missing universe coverage");
    return d;
}
