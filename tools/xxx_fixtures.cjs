"use strict";
// SYNTHETIC TEST BROKER. No network calls, real credentials, or performance evidence.
const { Coordinator } = require("../runtime30/coordinator.js"),
  { DEFAULT_EXIT } = require("../runtime30/types.js");
class MemoryStore {
  constructor() {
    this.data = new Map();
    this.leased = true;
  }
  async get(k) {
    return structuredClone(this.data.get(k) || null);
  }
  async put(k, v) {
    if (this.fail) throw Error("disk full");
    this.data.set(k, structuredClone(v));
    return true;
  }
  async lease() {
    return this.leased;
  }
  async scan(prefix,limit=100000) { return [...this.data.entries()].filter(([k])=>k.startsWith(prefix)).sort(([a],[b])=>a.localeCompare(b)).slice(0,limit).map(([,v])=>structuredClone(v)); }
  async close() {}
}
class FakeBroker {
  constructor() {
    this.calls = [];
    this.orders = new Map();
    this.positions = new Map();
    this.equity = 20000;
    this.account = {
      id: "SYNTHETIC-PAPER-ACCOUNT",
      status: "ACTIVE",
      equity: "20000",
      cash: "20000",
      buying_power: "20000",
      non_marginable_buying_power: "20000",
      options_buying_power: "20000",
      options_trading_level: 2,
    };
    this.open = true;
    this.mode = "fill";
    this.cancelImmediate = true;
  }
  async request(path, method = "GET", body, market = false) {
    this.calls.push({ path, method, body: structuredClone(body), market });
    if (path === "/v2/account")
      return { ...this.account, equity: String(this.equity) };
    if (path === "/v2/positions")
      return [...this.positions.values()].map((p) => ({ ...p }));
    if (path === "/v2/clock")
      return {
        timestamp: new Date().toISOString(),
        is_open: this.open,
        next_close: new Date(Date.now() + 4 * 3600000).toISOString(),
        next_open: new Date(Date.now() + 24 * 3600000).toISOString(),
      };
    if (path.startsWith("/v2/calendar"))
      return [
        {
          date: new Date().toISOString().slice(0, 10),
          open: "09:30",
          close: "16:00",
        },
      ];
    if (path.startsWith("/v2/orders?"))
      return [...this.orders.values()]
        .filter(
          (o) =>
            !["filled", "canceled", "rejected", "expired"].includes(o.status),
        )
        .map((o) => ({ ...o }));
    if (path.startsWith("/v2/orders:by_client_order_id")) {
      const id = new URL("http://fixture" + path).searchParams.get(
          "client_order_id",
        ),
        o = this.orders.get(id);
      if (!o) throw Object.assign(Error("not found"), { status: 404 });
      return { ...o };
    }
    if (path.startsWith("/v2/orders/") && method === "DELETE") {
      const o = [...this.orders.values()].find(
        (o) => o.id === path.split("/").at(-1),
      );
      if (this.cancelImmediate) o.status = "canceled";
      return null;
    }
    if (path === "/v2/orders" && method === "POST") {
      if (this.mode === "timeout-before") throw Error("timeout");
      const o = {
        ...body,
        id: "broker-" + this.orders.size,
        filled_qty: "0",
        filled_avg_price: null,
        status: "new",
      };
      this.orders.set(o.client_order_id, o);
      if (!["stop", "stop_limit"].includes(body.type)) {
        const qty = Number(body.qty),
          symbol = body.symbol,
          option = /\d{6}[CP]\d{8}$/.test(symbol),
          mult = option ? 100 : 1,
          price = Number(body.limit_price || 100),
          old = this.positions.get(symbol),
          n = Number(old?.qty || 0) + (body.side === "buy" ? qty : -qty);
        o.status = "filled";
        o.filled_qty = String(qty);
        o.filled_avg_price = String(price);
        if (n < 0) throw Error("FIXTURE OVERSOLD");
        if (n)
          this.positions.set(symbol, {
            symbol,
            qty: String(n),
            market_value: String(n * price * mult),
            avg_entry_price:
              body.side === "buy" ? String(price) : old.avg_entry_price,
          });
        else this.positions.delete(symbol);
      }
      if (this.mode === "timeout-after") throw Error("timeout after accepted");
      return { ...o };
    }
    if (path.startsWith("/v2/assets/")) {
      const symbol = decodeURIComponent(path.split("/").at(-1));
      return {
        symbol,
        class: symbol.includes("/") ? "crypto" : "us_equity",
        status: "active",
        tradable: true,
        min_trade_increment: ".0001",
        min_order_size: ".0001",
        price_increment: ".01",
      };
    }
    throw Error("Unexpected fixture request: " + method + " " + path);
  }
  posts() {
    return this.calls.filter((c) => c.method === "POST");
  }
}
function config() {
  const c = structuredClone(require("../config/examples/xxx.json"));
  c.expected_account_id = "SYNTHETIC-PAPER-ACCOUNT";
  c.nativeProtection = "stop";
  c.streaming = false;
  // Legacy lifecycle tests isolate their original risk path. New quant gating has
  // its own positive/negative contract tests and remains enabled in release config.
  c.quant = {enabled:false};
  return c;
}
async function ready(store = new MemoryStore(), api = new FakeBroker()) {
  const e = new Coordinator(store, api, config());
  await e.initialize(true);
  await e.market.catalog();
  return { e, api, store };
}
function signal(book = "equity", symbol) {
  symbol ??= {
    equity: "AAPL",
    etf: "SPXL",
    crypto: "BTC/USD",
    options: "SPY261218C00600000",
  }[book];
  const p = {
    equity: "equity-canonical-host",
    etf: "etf-canonical-host",
    crypto: "crypto-canonical-host",
    options: "options-call-breakout",
  }[book];
  return {
    symbol,
    book,
    plugin: p,
    at: Date.now(),
    expires: Date.now() + 60000,
    entry: book === "options" ? 0.2 : 100,
    stop: book === "options" ? 0.14 : 98,
    score: 1,
    reason: "SYNTHETIC_TEST_SIGNAL",
    exit: { ...DEFAULT_EXIT },
  };
}
function prepare(e, s) {
  if (s.book === "options")
    e.market.assets[s.symbol] = {
      symbol: s.symbol,
      book: s.book,
      factor: "sp500",
      leverage: 1,
      multiplier: 100,
      step: 1,
      minQty: 1,
      tick: 0.01,
      expiry: "2026-12-18",
      underlying: "SPY",
      tradable: true,
    };
  e.market.quotes[s.symbol] = {
    bid: s.entry * 0.999,
    ask: s.entry,
    at: Date.now(),
    received: Date.now(),
  };
  e.plugins.evaluate = () => [s];
}
module.exports = { MemoryStore, FakeBroker, config, ready, signal, prepare };
