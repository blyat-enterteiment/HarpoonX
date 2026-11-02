"use strict";
// SYNTHETIC fixtures for numerical, causal and transport failure tests only.
const { defaultProtocol } = require("../runtime30/ultimate_contracts.js");
function dataset() {
  const protocol = {
    ...defaultProtocol("ALPACA_PROXY"),
    universe: ["SPY"],
    trainSessions: 60,
    testSessions: 10,
    holdoutSessions: 30,
    gapSessions: 1,
    bootstrapRuns: 500,
  };
  const sessions = [],
    bars = [],
    start = Date.parse("2024-01-01T14:30:00Z");
  for (let day = 0; day < 150; day++) {
    const open = start + day * 86400000,
      close = open + 18 * 300000;
    sessions.push({
      date: new Date(open).toISOString().slice(0, 10),
      open,
      close,
    });
    for (let j = 0; j < 18; j++) {
      const t = open + j * 300000,
        price = 100 + day * 0.04 + j * 0.06;
      bars.push({
        t,
        end: t + 300000,
        availableAt: t + 303000,
        o: price,
        h: price + 0.1,
        l: price - 0.1,
        c: price + 0.04,
        v: day % 5 === 0 ? 2000 : 1000,
        vw: price + 0.02,
      });
    }
  }
  return {
    protocol,
    data: {
      schema: "HARPOON-ULTIMATE-DATA-1",
      kind: "ALPACA_PROXY",
      provenance: {
        source: "SYNTHETIC_TEST_ONLY",
        feed: "SYNTHETIC",
        execution: "MODELED_OHLCV",
        files: [{ name: "SYNTHETIC", sha256: "a".repeat(64) }],
      },
      sessions,
      splitEvents: [],
      series: [{ symbol: "SPY", root: "SPY", pointValue: 1, tick: 0.01, bars }],
    },
  };
}
function futureContract() {
  return {
    root: "MES",
    symbol: "XCME:MES.Z27",
    lastTradeAt: Date.now() + 300 * 86400000,
  };
}
class SyntheticIronbeam {
  constructor() {
    this.posts = 0;
    this.orders = [];
    this.positions = [];
    this.failSubmit = false;
    this.now = Date.now();
    this.stale = false;
  }
  async request(route, method = "GET", body) {
    const accountId = "PAPER123";
    if (route.includes("/balance?"))
      return {
        status: "OK",
        balances: [
          {
            accountId,
            currencyCode: "USD",
            balanceType: "CURRENT_OPEN",
            totalEquity: 20000,
            netLiquidityAvailable: 20000,
          },
        ],
      };
    if (route.endsWith("/risk"))
      return {
        status: "OK",
        risks: [
          {
            accountId,
            currencyCode: "USD",
            startNetLiquidationValue: 20000,
            maxNetLiquidationValueMultiDay: 20000,
          },
        ],
      };
    if (route.endsWith("/positions"))
      return { status: "OK", positions: this.positions };
    if (route.endsWith("/ANY")) return { status: "OK", orders: this.orders };
    if (route.startsWith("/market/quotes"))
      return {
        status: "OK",
        Quotes: [
          {
            s: "XCME:MES.Z27",
            b: 100,
            a: 100.25,
            bt: this.stale ? 1 : this.now,
            at: this.now,
          },
        ],
      };
    if (route.startsWith("/info/security/margin"))
      return {
        status: "OK",
        securityMarginAndValues: [
          {
            exchSym: "XCME:MES.Z27",
            currentTime: this.now,
            initialMarginLong: 1000,
            initialMaginShort: 1000,
          },
        ],
      };
    if (route.endsWith("/place") && method === "POST") {
      this.posts++;
      if (this.failSubmit)
        throw Error("SYNTHETIC timeout after possible acceptance");
      this.orders.push({
        ...body,
        orderId: "ORDER1",
        fillQuantity: 0,
        status: "NEW",
      });
      return { status: "OK", orderId: "ORDER1", strategyId: 123 };
    }
    if (route.includes("/toorderid/"))
      return { status: "OK", orderId: "ORDER1" };
    throw Error("Unexpected synthetic route " + route);
  }
}
module.exports = { dataset, futureContract, SyntheticIronbeam };
