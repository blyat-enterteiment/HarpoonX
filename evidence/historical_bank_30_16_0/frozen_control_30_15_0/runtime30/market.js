"use strict";
Object.defineProperty(exports, "__esModule", { value: true });
exports.Market = void 0;
const types_1 = require("./types");
const validators_1 = require("./validators");
class Market {
    api;
    cfg;
    validators;
    quotes = {};
    watched = {};
    daily = {};
    bars = {};
    minutes = {};
    assets = {};
    snapshots = {};
    metadata = {};
    errors = {};
    updated = {};
    calendar = [];
    chains = {};
    microData = {};
    h4 = [];
    constructor(api, cfg, validators = new validators_1.Validators()) {
        this.api = api;
        this.cfg = cfg;
        this.validators = validators;
    }
    recordMicro(symbol, raw, kind) {
        if (!this.cfg.quant?.microstructure?.enabled || !symbol)
            return;
        const book = this.assets[symbol]?.book || (symbol.includes("/") ? "crypto" : "equity");
        const feed = book === "crypto" ? "us" : book === "options" ? "opra" : this.cfg.stockFeed;
        const now = Date.now(), at = Date.parse(raw.t instanceof Date ? raw.t.toISOString() : raw.t);
        if (!Number.isFinite(at) || at > now + 1000 || now - at > 300000)
            return;
        if (kind === "quote" && ![raw.bp, raw.ap, raw.bs, raw.as].every(types_1.positive))
            return;
        if (kind === "trade" && ![raw.p, raw.s].every(types_1.positive))
            return;
        if (!this.microData[symbol] && Object.keys(this.microData).length >= 128)
            return;
        const data = this.microData[symbol] ||= { feed, quotes: [], trades: [], sampling_schema: "ALPACA_L1_LAST_PER_SECOND", omitted_events: 0 };
        const key = kind === "quote" ? "quotes" : "trades", rows = data[key];
        const event = { ...raw, t: raw.t instanceof Date ? raw.t.toISOString() : raw.t, known_at: new Date(now).toISOString(), bucket: Math.floor(at / 1000) };
        const index = rows.findIndex(r => r.bucket === event.bucket);
        if (index >= 0) {
            if (rows[index].t === event.t)
                return;
            if (Date.parse(rows[index].t) <= at)
                rows[index] = event;
            data.omitted_events++;
        }
        else
            rows.push(event);
        rows.sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
        data[key] = rows.filter(r => now - Date.parse(r.t) <= 300000).slice(-360);
    }
    resetMicro(name) {
        for (const symbol of Object.keys(this.microData)) {
            const book = this.assets[symbol]?.book || "equity";
            if (name === "stocks" && (book === "equity" || book === "etf") || name === book)
                delete this.microData[symbol];
        }
    }
    async catalog() {
        for (const i of this.cfg.universe) {
            try {
                const a = await this.api.request("/v2/assets/" + encodeURIComponent(i.symbol));
                if (a.symbol !== i.symbol ||
                    a.class !== (i.book === "crypto" ? "crypto" : "us_equity"))
                    throw Error("Asset class mismatch");
                const x = {
                    ...i,
                    tradable: a.tradable === true && a.status === "active",
                    ...(i.book === "crypto"
                        ? {
                            step: Number(a.min_trade_increment),
                            minQty: Number(a.min_order_size),
                            tick: Number(a.price_increment),
                        }
                        : {}),
                };
                if (![x.step, x.minQty, x.tick].every(types_1.positive))
                    throw Error("Missing asset precision");
                // A restored dynamic symbol remains disabled until this broker verification.
                if (i.discovery_managed === true)
                    i.tradable = x.tradable;
                this.assets[i.symbol] = x;
                delete this.errors["asset:" + i.symbol];
            }
            catch (e) {
                this.errors["asset:" + i.symbol] = String(e);
            }
        }
    }
    async quotesFor(book, held = []) {
        const candidates = Object.values(this.assets).filter((i) => i.book === book);
        const watched = book === "options"
            ? candidates
                .sort((a, b) => Math.abs(Math.abs(Number(this.snapshots[a.symbol]?.greeks?.delta || 0)) - 0.5) -
                Math.abs(Math.abs(Number(this.snapshots[b.symbol]?.greeks?.delta || 0)) - 0.5))
                .slice(0, 24)
            : candidates;
        const symbols = [...new Set([...held, ...watched.map((i) => i.symbol)])];
        this.watched[book] = symbols;
        if (!symbols.length)
            return;
        const p = book === "crypto"
            ? "/v1beta3/crypto/us/latest/quotes"
            : book === "options"
                ? "/v1beta1/options/quotes/latest"
                : "/v2/stocks/quotes/latest";
        const args = new URLSearchParams({
            symbols: symbols.join(","),
            ...(book === "crypto"
                ? {}
                : { feed: book === "options" ? "opra" : this.cfg.stockFeed }),
        });
        const r = await this.api.request(p + "?" + args, "GET", undefined, true), now = Date.now();
        for (const s of symbols) {
            const raw = r.quotes?.[s], q = {
                bid: Number(raw?.bp),
                ask: Number(raw?.ap),
                at: Date.parse(raw?.t),
                received: now,
            };
            try {
                this.validators.run("quote-" + book, () => (0, validators_1.assertFreshQuote)(q, now, this.cfg.quoteAgeMs));
                this.quotes[s] = q;
                this.recordMicro(s, raw, "quote");
                delete this.errors["quote:" + s];
            }
            catch {
                delete this.quotes[s];
                this.errors["quote:" + s] = "Cotización ausente, vencida o inválida";
            }
        }
        this.updated["quotes:" + book] = now;
    }
    async fetchBars(symbols, crypto, timeframe, start, end) {
        const out = {}, seen = new Set();
        let token = "";
        for (let page = 0; page < 30; page++) {
            const args = new URLSearchParams({
                symbols: symbols.join(","),
                timeframe,
                start: new Date(start).toISOString(),
                end: new Date(end).toISOString(),
                limit: "10000",
                sort: "asc",
                ...(crypto ? {} : { feed: this.cfg.stockFeed, adjustment: "split" }),
                ...(token ? { page_token: token } : {}),
            });
            const r = await this.api.request((crypto ? "/v1beta3/crypto/us/bars" : "/v2/stocks/bars") + "?" + args, "GET", undefined, true);
            for (const [s, rows] of Object.entries(r.bars || {})) {
                this.validators.run("bars-" + (crypto ? "crypto" : "securities"), () => (0, validators_1.assertBars)(rows));
                if (!Array.isArray(rows) ||
                    rows.some((b) => ![b.o, b.h, b.l, b.c].every(types_1.positive) ||
                        !Number.isFinite(b.v) ||
                        b.v < 0 ||
                        !Number.isFinite(Date.parse(b.t)) ||
                        b.h < Math.max(b.o, b.c, b.l) ||
                        b.l > Math.min(b.o, b.c)))
                    throw Error("Invalid OHLCV bars");
                (out[s] ??= []).push(...rows);
            }
            token = r.next_page_token;
            if (!token) {
                for (const rows of Object.values(out)) {
                    if (new Set(rows.map((b) => b.t)).size !== rows.length)
                        throw Error("Duplicate bars");
                    rows.sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
                }
                return out;
            }
            if (seen.has(token))
                throw Error("Repeated bar page");
            seen.add(token);
        }
        throw Error("Truncated bar history; reduce universe");
    }
    async history(book) {
        if (book === "options")
            return;
        const symbols = this.cfg.universe
            .filter((i) => i.book === book)
            .map((i) => i.symbol);
        if (!symbols.length)
            return;
        const now = Date.now(), crypto = book === "crypto", key = "bars:" + book, last = this.updated[key] || 0;
        const raw = await this.fetchBars(symbols, crypto, crypto ? "15Min" : "5Min", last ? last - 1800000 : now - (crypto ? 25 : 50) * 86400000, now);
        for (const s of symbols) {
            const map = new Map((this.bars[s] || []).map((b) => [b.t, b]));
            for (const b of raw[s] || [])
                map.set(b.t, b);
            this.bars[s] = [...map.values()]
                .filter((b) => Date.parse(b.t) > now - (crypto ? 25 : 50) * 86400000)
                .sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
        }
        if (!this.updated["daily:" + book] ||
            new Date(this.updated["daily:" + book]).toISOString().slice(0, 10) !==
                new Date(now).toISOString().slice(0, 10)) {
            Object.assign(this.daily, await this.fetchBars(symbols, crypto, "1Day", now - 100 * 86400000, now));
            this.updated["daily:" + book] = now;
        }
        this.updated[key] = now;
    }
    async detailedHistory(symbols) {
        const now = Date.now();
        for (const s of symbols) {
            const previous = this.minutes[s] || [], raw = await this.fetchBars([s], false, "1Min", previous.length ? now - 1800000 : now - 35 * 86400000, now), map = new Map(previous.map((b) => [b.t, b]));
            for (const b of raw[s] || [])
                map.set(b.t, b);
            this.minutes[s] = [...map.values()]
                .filter((b) => Date.parse(b.t) > now - 35 * 86400000 &&
                Date.parse(b.t) + 63000 <= now)
                .sort((a, b) => Date.parse(a.t) - Date.parse(b.t));
        }
    }
    async benchmarkHistory(symbols) {
        const missing = symbols.filter((s) => !this.cfg.universe.some((i) => i.symbol === s));
        if (!missing.length)
            return;
        const now = Date.now();
        Object.assign(this.bars, await this.fetchBars(missing, false, "5Min", now - 86400000, now));
    }
    async fourHour() {
        const r = await this.fetchBars(["BTC/USD"], true, "4Hour", Date.now() - 60 * 86400000, Date.now());
        this.h4 = r["BTC/USD"] || [];
    }
    async optionChains() {
        const now = Date.now();
        for (const underlying of this.cfg.optionUnderlyings) {
            try {
                const spot = this.quotes[underlying];
                if (!(0, types_1.fresh)(spot, now, this.cfg.quoteAgeMs))
                    continue;
                const args = new URLSearchParams({
                    underlying_symbols: underlying,
                    expiration_date_gte: new Date(now + 7 * 86400000)
                        .toISOString()
                        .slice(0, 10),
                    expiration_date_lte: new Date(now + 45 * 86400000)
                        .toISOString()
                        .slice(0, 10),
                    status: "active",
                    limit: "1000",
                    strike_price_gte: String(spot.bid * 0.85),
                    strike_price_lte: String(spot.ask * 1.15),
                });
                const contracts = [];
                let token = "";
                const seen = new Set();
                do {
                    const r = await this.api.request("/v2/options/contracts?" +
                        args +
                        (token ? "&page_token=" + encodeURIComponent(token) : ""));
                    contracts.push(...(r.option_contracts || []));
                    token = r.next_page_token || "";
                    if (token) {
                        if (seen.has(token) || seen.size >= 5)
                            throw Error("Option catalog truncated");
                        seen.add(token);
                    }
                } while (token);
                const snap = await this.api.request("/v1beta1/options/snapshots/" +
                    encodeURIComponent(underlying) +
                    "?" +
                    new URLSearchParams({
                        feed: "opra",
                        limit: "1000",
                        expiration_date_gte: new Date(now + 7 * 86400000)
                            .toISOString()
                            .slice(0, 10),
                        expiration_date_lte: new Date(now + 45 * 86400000)
                            .toISOString()
                            .slice(0, 10),
                        strike_price_gte: String(spot.bid * 0.85),
                        strike_price_lte: String(spot.ask * 1.15),
                    }), "GET", undefined, true);
                this.chains[underlying] = {
                    snapshots: snap.snapshots || {},
                    complete: !snap.next_page_token,
                };
                // A bounded subset is sufficient for selection; no claim that a truncated chain is complete.
                for (const c of contracts) {
                    const s = c.symbol, q = snap.snapshots?.[s]?.latestQuote;
                    if (!q || c.tradable !== true || Number(c.size) !== 100)
                        continue;
                    this.assets[s] = {
                        symbol: s,
                        book: "options",
                        factor: this.assets[underlying]?.factor || underlying,
                        leverage: 1,
                        multiplier: 100,
                        step: 1,
                        minQty: 1,
                        tick: 0.01,
                        underlying,
                        expiry: c.expiration_date,
                        tradable: true,
                    };
                    this.metadata[s] = c;
                    this.snapshots[s] = { ...snap.snapshots[s], observedAt: Date.now() };
                    this.quotes[s] = {
                        bid: Number(q.bp),
                        ask: Number(q.ap),
                        at: Date.parse(q.t),
                        received: Date.now(),
                    };
                }
                delete this.errors["chain:" + underlying];
                this.updated["chain:" + underlying] = Date.now();
            }
            catch (e) {
                this.errors["chain:" + underlying] = String(e);
            }
        }
    }
}
exports.Market = Market;
