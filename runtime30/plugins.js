"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Plugins = void 0;
const types_1 = require("./types");
const policy_1 = require("./policy");
const sessions_1 = require("./sessions");
const avg = (a) => a.reduce((s, v) => s + v, 0) / Math.max(1, a.length);
class Plugins {
    cfg;
    legacy;
    models = {};
    selectors = {};
    lastFeatures = [];
    catalog;
    diagnostics = [];
    c32PrefilterTap;
    tape;
    stream;
    cryptoTape;
    streamSymbols = [];
    constructor(_store, cfg) {
        this.cfg = cfg;
        this.legacy = require("../runtime/legacy30.cjs").create();
        this.catalog = [
            ...this.legacy.catalog(),
            ...["call-breakout", "put-breakdown", "call-pullback"].map((id) => ({
                api: "harpoon.plugin/30",
                id: "options-" + id,
                version: "30.0.2",
                name: id,
                book: "options",
                family: id,
                binding: "fixed",
                params: { minDte: 7, maxDte: 45, minDelta: 0.35, maxDelta: 0.7 },
            })),
        ];
        this.validateSelection(cfg.enabledPlugins);
    }
    sector(factor) {
        return ({
            technology: "XLK",
            semiconductors: "SMH",
            consumer: "XLY",
            nasdaq: "QQQ",
            sp500: "SPY",
            smallcap: "IWM",
            financials: "XLF",
            biotech: "XBI",
            dow: "DIA",
        }[factor] || "SPY");
    }
    astraSymbols(enabled) {
        const books = this.catalog
            .filter((p) => enabled.includes(p.id) && p.family === "astra_second_wave")
            .map((p) => p.book);
        return this.cfg.universe
            .filter((i) => books.includes(i.book))
            .map((i) => i.symbol);
    }
    benchmarkSymbols() {
        return [
            ...new Set([
                "SPY",
                ...this.cfg.universe
                    .filter((i) => i.book !== "crypto")
                    .map((i) => this.sector(i.factor)),
            ]),
        ];
    }
    updateStreams(api, enabled, shared = false) {
        const targets = this.astraSymbols(enabled);
        if (targets.length) {
            if (!this.tape)
                this.tape = new this.legacy.HAstra.Tape();
            if (shared) {
                this.stream?.stop();
                this.stream = null;
            }
            if (!shared && !this.stream) {
                this.stream = new this.legacy.MarketStream(api, (s, q) => this.tape.quote(s, q), (status) => {
                    if (status !== "STREAM ACTIVO")
                        this.tape.reset();
                });
                this.stream.ondata = (r) => {
                    if (r.T === "t")
                        this.tape.trade(r, Date.now());
                };
            }
            if (!shared)
                this.stream.start(targets, this.cfg.stockFeed);
        }
        else {
            this.stream?.stop();
            this.stream = null;
            this.tape?.reset();
        }
        if (enabled.includes("crypto-shock-recovery")) {
            if (!this.cryptoTape) {
                this.cryptoTape = new this.legacy.CryptoTape(api);
                if (!shared)
                    this.cryptoTape.start();
            }
        }
        else {
            this.cryptoTape?.stop();
            this.cryptoTape = null;
        }
    }
    sharedFlow(r) {
        if (this.tape && r.T === "q")
            this.tape.quote(r.S, {
                bid: Number(r.bp),
                ask: Number(r.ap),
                at: Date.parse(r.t),
                received: Date.now(),
            });
        if (this.tape && r.T === "t")
            this.tape.trade(r, Date.now());
        if (this.cryptoTape && r.S?.includes("/")) {
            this.cryptoTape.ingest(r, Date.now());
            this.cryptoTape.state = "CAPTURANDO FLUJO COMPARTIDO";
        }
    }
    sharedReset(name) {
        if (name === "stocks")
            this.tape?.reset();
        if (name === "crypto" && this.cryptoTape) {
            this.cryptoTape.reset();
            this.cryptoTape.state = "DESCONECTADO · HISTORIA INVALIDADA";
        }
    }
    stop() {
        this.stream?.stop();
        this.cryptoTape?.stop();
    }
    astraObservation(symbol, m, now, params) {
        const L = this.legacy, factor = this.cfg.universe.find((i) => i.symbol === symbol)?.factor || "";
        const convert = (s) => (m.minutes[s] || []).map((b) => {
            const t = Date.parse(b.t), n = L.ny(t);
            return { ...b, t, available: t + 63000, day: n.day, minute: n.minute };
        });
        const sector = this.sector(factor), session = m.calendar.find((x) => x.date === L.ny(now).day);
        return L.HAstra.evaluate({
            symbol,
            at: now,
            source: "ALPACA_OBSERVED",
            feed: this.cfg.stockFeed,
            sessionOpen: session?.open,
            quote: m.quotes[symbol],
            bars: convert(symbol),
            market: convert("SPY"),
            sector: convert(sector),
            sectorSymbol: sector,
            flows: this.tape?.flow(symbol) || [],
            slippageBps: this.cfg.slippageBps,
            options: this.optionContext(symbol, m, now, params.holdHours || 72),
        }, params);
    }
    /** Native exit evidence supplements the shared XXX stop/TP policy; absence never fabricates a signal. */
    manageSignal(c, m, now, entry) {
        const plugin = this.catalog.find((p) => p.id === c.plugin), L = this.legacy;
        if (!plugin)
            return;
        try {
            if (plugin.family === "trend_xix") {
                const cfg = L.HXX.cryptoConfig(plugin, L.HC19.defaults), bars = L.HC19.normalize(m.daily[c.symbol] || [], now), s = L.HC19.signal(bars, cfg);
                if (now - s.available_at <= 86400000 && s.exit)
                    c.strategyClose ||= "CLOSED_DAILY_CHANNEL_EXIT";
            }
            else if (plugin.family === "warroom_trend") {
                const W = L.HWarRoom3, cfg = this.models[plugin.params.candidate]?.config || W.defaults(), s = W.signal(W.normalizeBars(m.daily[c.symbol] || [], 86400000, now), cfg, now);
                if (s && now - s.available_at <= 86400000 && s.exit)
                    c.strategyClose ||= "WARROOM_CHANNEL_EXIT";
            }
            else if (plugin.family === "astra_second_wave" &&
                (0, types_1.fresh)(m.quotes[c.symbol], now, this.cfg.quoteAgeMs)) {
                const native = {
                    entry,
                    peak: c.peak,
                    virtual_stop: c.stop,
                    risk_unit: c.risk,
                    atr: c.entryAtr,
                    stagnationMs: c.stagnationMs,
                    peakAt: now - (c.stagnationMs || 0),
                    exit_cost_bps: this.cfg.slippageBps,
                    astraLatest: this.astraObservation(c.symbol, m, now, plugin.params),
                    astraState: c.astraState,
                };
                L.HAstra.exit(native, m.quotes[c.symbol].bid, now, plugin.params);
                if ((0, types_1.positive)(native.virtual_stop))
                    c.stop = Math.max(c.stop, native.virtual_stop);
                c.astraState = native.astraState;
                if (native.closing)
                    c.strategyClose ||= native.closing;
            }
        }
        catch (e) {
            m.errors["exit-signal:" + c.symbol] = String(e);
        }
    }
    optionContext(symbol, m, now, hours) {
        const chain = m.chains[symbol], q = m.quotes[symbol];
        if (!chain || !(0, types_1.fresh)(q, now, this.cfg.quoteAgeMs))
            return null;
        const rv = this.legacy.HXI.realizedVol((m.daily[symbol] || [])
            .filter((b) => Date.parse(b.t) + 86400000 <= now)
            .slice(-21)
            .map((b) => b.c));
        return this.legacy.HXI.optionEvidence(symbol, chain.snapshots, (q.bid + q.ask) / 2, "opra", now, hours, rv, chain.complete, m.calendar);
    }
    validateSelection(ids) {
        if (!Array.isArray(ids) ||
            ids.length > 100 ||
            new Set(ids).size !== ids.length ||
            ids.some((id) => !this.catalog.some((p) => p.id === id)))
            throw Error("Unknown/duplicate plugin");
    }
    features(m, now) {
        const L = this.legacy, cfg = {
            ...L.settings,
            equity_factors: Object.fromEntries(this.cfg.universe.map((i) => [i.symbol, i.factor])),
        }, rows = [];
        const calendar = m.calendar || [], session = (0, sessions_1.sessionContext)(now, calendar);
        const histories = new Map();
        const history = (s) => {
            if (!histories.has(s))
                histories.set(s, (0, sessions_1.regularClosedBars)(m.bars[s] || [], now, calendar, false));
            return histories.get(s);
        };
        const closed = (s) => (0, sessions_1.regularClosedBars)(history(s), now, calendar), spy = closed("SPY"), spyMom = spy.length >= 4 && (0, sessions_1.contiguousBars)(spy.slice(-4)) ? (spy.at(-1).c / spy.at(-4).c - 1) * 10000 : null;
        for (const i of this.cfg.universe.filter((x) => x.book !== "crypto")) {
            this.c32PrefilterTap?.({
                site: "FEATURE_PRE_QUOTE", book: i.book, pluginId: null,
                symbol: i.symbol, asOf: now,
            });
            try {
                const q = m.quotes[i.symbol];
                if (!(0, types_1.fresh)(q, now, this.cfg.quoteAgeMs))
                    throw Error("STALE_QUOTE");
                const f = L.feature(i.symbol, history(i.symbol), m.daily[i.symbol] || [], q, now, cfg), bars = closed(i.symbol), tail = bars.slice(-4), prior = bars.slice(-7, -4), prev = bars.slice(0, -1), v = prev.reduce((n, b) => n + b.v, 0);
                if (!bars.length || session.open === null)
                    throw Error("REGULAR_SESSION_BARS_REQUIRED");
                if (bars.some((b) => !(0, types_1.positive)(b.vw)))
                    throw Error("OBSERVED_BAR_VWAP_REQUIRED");
                const sector = this.sector(i.factor), sectorBars = closed(sector), sectorMomentum = sectorBars.length >= 4 &&
                    (0, sessions_1.contiguousBars)(sectorBars.slice(-4)) &&
                    Date.parse(sectorBars.at(-1).t) === Date.parse(bars.at(-1).t) &&
                    Date.parse(sectorBars.at(-4).t) === Date.parse(bars.at(-4).t) &&
                    now - Date.parse(sectorBars.at(-1).t) <= 660000
                    ? (sectorBars.at(-1).c / sectorBars.at(-4).c - 1) * 10000
                    : null, side = i.book === "etf" && f.pair && i.symbol !== f.pair ? -1 : 1;
                Object.assign(f, {
                    book: i.book,
                    is_etf: Number(i.book === "etf"),
                    factor: i.factor,
                    leverage: i.leverage,
                    dollar_volume: bars.reduce((n, b) => n + b.c * b.v, 0),
                    volume_acceleration: prior.length === 3
                        ? avg(tail.slice(-3).map((b) => b.v)) /
                            Math.max(1, avg(prior.map((b) => b.v)))
                        : null,
                    relative_bps: spyMom === null || !(0, sessions_1.contiguousBars)(bars.slice(-4)) ||
                        Date.parse(spy.at(-1).t) !== Date.parse(bars.at(-1).t) || Date.parse(spy.at(-4).t) !== Date.parse(bars.at(-4).t)
                        ? null
                        : f.momentum_bps - side * spyMom * i.leverage,
                    session_minutes: Math.floor((now - session.open) / 60000),
                    opening_high: (0, sessions_1.openingRange)(bars, session),
                    previous_vwap_distance: v > 0
                        ? prev.at(-1).c /
                            (prev.reduce((n, b) => n + (b.vw || b.c) * b.v, 0) / v) -
                            1
                        : null,
                    sector_proxy: sector,
                    sector_relative_bps: sectorMomentum === null
                        ? null
                        : f.momentum_bps - side * i.leverage * sectorMomentum,
                    reset_base: Math.max(...tail.slice(0, -1).map((b) => b.h)),
                    consolidation_atr: (Math.max(...tail.slice(0, -1).map((b) => b.h)) -
                        Math.min(...tail.slice(0, -1).map((b) => b.l))) /
                        f.atr,
                    session_change: Date.parse(bars[0].t) === session.open ? q.ask / bars[0].o - 1 : null,
                    session_context: session,
                    streak_diagnostics: (0, sessions_1.streakDiagnostics)(bars, history(i.symbol), session, calendar),
                });
                rows.push(f);
            }
            catch (e) {
                this.diagnostics.push({
                    symbol: i.symbol,
                    book: i.book,
                    status: "WAIT_DATA",
                    reason: String(e),
                });
            }
        }
        this.lastFeatures = rows;
        return rows;
    }
    evaluate(book, m, enabled, now = Date.now()) {
        this.diagnostics = this.diagnostics.filter((d) => d.book !== book);
        const out = [], L = this.legacy, selected = this.catalog.filter((p) => p.book === book && enabled.includes(p.id));
        this.c32PrefilterTap?.({
            site: "EVALUATE_SOURCE_BEFORE_FEATURES", book,
            pluginId: null, symbol: null, asOf: now,
        });
        const features = book === "equity" || book === "etf"
            ? this.features(m, now).filter((f) => f.book === book)
            : [];
        for (const plugin of selected) {
            for (const i of this.cfg.universe.filter((i) => i.book === book)) {
                this.c32PrefilterTap?.({
                    site: "NATIVE_PAIR_PRE_QUOTE", book, pluginId: plugin.id,
                    symbol: i.symbol, asOf: now,
                });
                try {
                    const q = m.quotes[i.symbol];
                    if (!(0, types_1.fresh)(q, now, this.cfg.quoteAgeMs))
                        throw Error("STALE_QUOTE");
                    if ((q.ask / q.bid - 1) * 10000 > this.cfg.maxSpreadBps)
                        throw Error("WIDE_SPREAD");
                    let s = null;
                    if (book === "crypto") {
                        if (plugin.family === "shock_recovery") {
                            const snapshot = this.cryptoTape?.snapshot(i.symbol, now);
                            if (!snapshot)
                                throw Error("WAIT_OBSERVED_TAKER_FLOW");
                            const result = L.HPRecovery.evaluate(L.HXX.recovery(plugin), snapshot, {
                                feePerSideBps: this.cfg.cryptoFeeBps,
                                slippagePerSideBps: this.cfg.slippageBps,
                            });
                            if (!result.proposal)
                                throw Error(result.reason);
                            const p = result.proposal;
                            s = {
                                symbol: i.symbol,
                                book,
                                plugin: plugin.id,
                                at: now,
                                expires: p.expiresMs,
                                entry: p.entryCeiling,
                                stop: p.stop,
                                score: p.diagnostics.netRewardRisk,
                                reason: "shock_recovery",
                                exit: (0, policy_1.freezeExit)({ maxHoldHours: p.holdMs / 3600000 }, this.cfg),
                            };
                        }
                        else if (plugin.family === "warroom_trend") {
                            const W = L.HWarRoom3, evidence = this.models[plugin.params.candidate], model = evidence && evidence.validUntil >= now ? evidence : null, c = model?.config || W.defaults(), bars = W.normalizeBars(m.daily[i.symbol] || [], 86400000, now), sig = W.signal(bars, c, now), regime = W.regime(W.normalizeBars(m.h4, 14400000, now), now), d = W.entryDecision(plugin.params.candidate, sig, { bid: q.bid, ask: q.ask, t: q.at }, now, c, {
                                regime,
                                minLabels: model?.minLabels || 30,
                                model: model?.model,
                            });
                            if (!d.ok)
                                throw Error(d.reason);
                            const entry = q.ask * (1 + this.cfg.slippageBps / 10000);
                            s = {
                                symbol: i.symbol,
                                book,
                                plugin: plugin.id,
                                at: now,
                                expires: now + 15000,
                                entry,
                                stop: entry - c.atr_multiple * sig.atr,
                                score: 0,
                                reason: "WarRoom " + plugin.params.candidate,
                                exit: (0, policy_1.freezeExit)({}, this.cfg),
                            };
                        }
                        else {
                            const c = L.HXX.cryptoConfig(plugin, L.HC19.defaults), bars = L.HC19.normalize(m.daily[i.symbol] || [], now), r = L.HC19.signal(bars, c);
                            if (now - r.available_at > 86400000 || !r.enter)
                                throw Error("NO_CLOSED_DAILY_BREAKOUT");
                            const entry = q.ask * (1 + this.cfg.slippageBps / 10000);
                            if (q.ask > r.close * 1.02)
                                throw Error("CHASE_LIMIT");
                            s = {
                                symbol: i.symbol,
                                book,
                                plugin: plugin.id,
                                at: now,
                                expires: now + 15000,
                                entry,
                                stop: entry - c.atr_multiple * r.atr,
                                score: r.close / r.upper - 1,
                                reason: "closed_daily_breakout",
                                exit: (0, policy_1.freezeExit)({ maxHoldHours: c.hold_hours || 72 }, this.cfg),
                            };
                        }
                    }
                    else {
                        const row = features.find((r) => r.symbol === i.symbol);
                        if (!row)
                            throw Error("MISSING_FEATURES");
                        const profile = L.HXX.securities(plugin, {
                            ...L.settings.profile,
                            family: "canonical_exit",
                            hold_hours: 48,
                            selection_filter: "none",
                        }), cfg = {
                            ...L.settings,
                            slippage_bps: this.cfg.slippageBps,
                            profile,
                        };
                        if (profile.astra) {
                            const a = this.astraObservation(i.symbol, m, now, profile.astra);
                            row.astra = a;
                            if (!a.ready)
                                throw Error(a.reasons.join("; "));
                        }
                        if (profile.family === "option_context") {
                            const e = this.optionContext(i.symbol, m, now, profile.hold_hours || 48), lv = L.localLevels(row, cfg);
                            Object.assign(row, {
                                option_valid: e?.valid ? 1 : 0,
                                option_proxy: 0,
                                option_horizon_hours: e?.horizon_hours || 0,
                                option_max_hours: e?.expiry_at
                                    ? (e.expiry_at - now) / 3600000
                                    : 0,
                                option_range_r: e?.valid ? e.expected_range / lv.risk_unit : 0,
                            });
                        }
                        if (profile.selection_filter === "ridge_lcb" &&
                            !L.HXII.selection(row, this.selectors[book]?.validUntil >= now
                                ? this.selectors[book].model
                                : null, now).eligible)
                            throw Error("NO_VALIDATED_SELECTOR");
                        const chosen = L.localSelected(features, profile);
                        if (i.book === "etf" &&
                            !row.pair &&
                            row.perf5 > 0 &&
                            row.rvol >= profile.min_rvol &&
                            row.momentum_bps >= profile.momentum_bps)
                            chosen.add(i.symbol);
                        const lv = L.localLevels(row, cfg), decision = L.HPSecurities.entryDecision(row, profile, cfg, lv, chosen), quality = L.HX.quality(row, profile, 1000000, 0.5, lv, this.cfg.slippageBps);
                        if (decision.reasons.length || quality.reasons.length)
                            throw Error([...decision.reasons, ...quality.reasons].join("; "));
                        s = {
                            symbol: i.symbol,
                            book,
                            plugin: plugin.id,
                            at: now,
                            expires: now + 15000,
                            entry: lv.limit,
                            stop: lv.stop,
                            score: quality.score || 0,
                            reason: profile.family,
                            exit: (0, policy_1.freezeExit)({
                                tp1R: profile.tp1_r,
                                tp2R: profile.tp2_r,
                                tp1Fraction: profile.tp1_fraction,
                                tp2Fraction: profile.exit_layout === "single_target"
                                    ? 0
                                    : profile.tp2_fraction,
                                lockFraction: profile.lock_fraction,
                                trailR: (profile.trail_atr * row.atr) / lv.risk_unit,
                                maxHoldHours: profile.hold_hours || 48,
                                trailingMode: profile.trailing_mode || "entry_atr",
                                stagnationMinutes: profile.stagnation_minutes || 20,
                                progressR: profile.progress_r ?? 1,
                                reentry: profile.reentry === true,
                            }, this.cfg),
                            entryAtr: row.atr,
                            reentryFeature: {
                                ...row,
                                reentry_trigger: row.reset_base * (1 + cfg.breakout_pct),
                            },
                        };
                    }
                    if (s && s.stop > 0 && s.entry > s.stop) {
                        if (book === "crypto") {
                            const observed = (m.daily[i.symbol] || [])
                                .filter((b) => Date.parse(b.t) + 86400000 <= now)
                                .slice(-21);
                            if (observed.length === 21 &&
                                observed.every((b) => (0, types_1.positive)(b.c) && (0, types_1.positive)(b.v)))
                                s.exitObservation = {
                                    momentum_bps: (observed.at(-1).c / observed.at(-4).c - 1) * 10000,
                                    rvol: observed.at(-1).v /
                                        avg(observed.slice(0, -1).map((b) => b.v)),
                                };
                        }
                        else if (s.reentryFeature)
                            s.exitObservation = {
                                momentum_bps: s.reentryFeature.momentum_bps,
                                rvol: s.reentryFeature.rvol,
                            };
                        out.push(s);
                        this.diagnostics.push({
                            book,
                            plugin: plugin.id,
                            symbol: i.symbol,
                            status: "SIGNAL",
                            reason: s.reason,
                        });
                    }
                }
                catch (e) {
                    this.diagnostics.push({
                        book,
                        plugin: plugin.id,
                        symbol: i.symbol,
                        status: "WAIT",
                        reason: String(e),
                    });
                }
            }
            if (book === "options")
                out.push(...this.options(plugin, m, now));
        }
        return out.sort((a, b) => b.score - a.score || a.plugin.localeCompare(b.plugin));
    }
    options(p, m, now) {
        const out = [];
        for (const underlying of this.cfg.optionUnderlyings) {
            this.c32PrefilterTap?.({
                site: "OPTIONS_UNDERLYING_PRE_FILTERS", book: "options",
                pluginId: p.id, symbol: underlying, asOf: now,
            });
            try {
                const spot = m.quotes[underlying], daily = (m.daily[underlying] || []).filter((b) => Date.parse(b.t) + 86400000 <= now), bars = (m.bars[underlying] || [])
                    .filter((b) => Date.parse(b.t) + 303000 <= now)
                    .slice(-22);
                if (!(0, types_1.fresh)(spot, now, this.cfg.quoteAgeMs) ||
                    daily.length < 21 ||
                    bars.length < 22 ||
                    now - Date.parse(bars.at(-1).t) > 660000)
                    throw Error("UNDERLYING_DATA");
                const mean = avg(daily.slice(-20).map((b) => b.c)), last = bars.at(-1), prior = bars.slice(0, -1), call = p.family !== "put-breakdown", ok = p.family === "call-breakout"
                    ? spot.bid > mean && last.c > Math.max(...prior.map((b) => b.h))
                    : p.family === "put-breakdown"
                        ? spot.ask < mean && last.c < Math.min(...prior.map((b) => b.l))
                        : spot.bid > mean &&
                            last.c > bars.at(-2).c &&
                            prior.at(-1).c <= avg(prior.slice(-5).map((b) => b.c));
                if (!ok)
                    throw Error("NO_UNDERLYING_CONFIRMATION");
                const candidates = Object.values(m.assets)
                    .filter((a) => a.book === "options" &&
                    a.underlying === underlying &&
                    a.tradable &&
                    m.metadata[a.symbol]?.type === (call ? "call" : "put"))
                    .map((a) => ({ a, q: m.quotes[a.symbol], s: m.snapshots[a.symbol] }))
                    .filter(({ a, q, s }) => (0, types_1.fresh)(q, now, this.cfg.quoteAgeMs) &&
                    now - Number(s?.observedAt) <= 60000 &&
                    Math.abs(Number(s?.greeks?.delta)) >= 0.35 &&
                    Math.abs(Number(s?.greeks?.delta)) <= 0.7 &&
                    (q.ask / q.bid - 1) * 10000 <= this.cfg.maxOptionSpreadBps &&
                    Date.parse(a.expiry + "T00:00:00Z") - now >= 7 * 86400000 &&
                    Number(m.metadata[a.symbol]?.open_interest) >= 100)
                    .sort((x, y) => x.q.ask / x.q.bid - 1 - (y.q.ask / y.q.bid - 1));
                if (!candidates.length)
                    throw Error("NO_ELIGIBLE_OPRA_CONTRACT");
                const { a, q } = candidates[0], entry = q.ask * (1 + this.cfg.slippageBps / 10000);
                const regime = this.features(m, now).find((r) => r.symbol === underlying);
                out.push({
                    symbol: a.symbol,
                    book: "options",
                    plugin: p.id,
                    at: now,
                    expires: now + 15000,
                    entry,
                    stop: entry * 0.7,
                    score: 1 - (q.ask / q.bid - 1),
                    reason: p.family,
                    exit: (0, policy_1.freezeExit)({}, this.cfg),
                    ...(regime
                        ? {
                            exitObservation: {
                                momentum_bps: regime.momentum_bps * (call ? 1 : -1),
                                rvol: regime.rvol,
                            },
                        }
                        : {}),
                });
                this.diagnostics.push({
                    book: "options",
                    plugin: p.id,
                    symbol: a.symbol,
                    status: "SIGNAL",
                    reason: p.family,
                });
            }
            catch (e) {
                this.diagnostics.push({
                    book: "options",
                    plugin: p.id,
                    symbol: underlying,
                    status: "WAIT",
                    reason: String(e),
                });
            }
        }
        return out;
    }
}
exports.Plugins = Plugins;
