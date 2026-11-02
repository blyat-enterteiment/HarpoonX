"use strict";
// SYNTHETIC fault-injection broker/frames only. These tests are not market or profitability evidence.
const test = require("node:test"),
  assert = require("node:assert/strict");
const { Coordinator } = require("../runtime30/coordinator.js"),
  { fills } = require("../runtime30/policy.js");
const { protectionSnapshot } = require("../runtime30/exits.js");
const { AlpacaStreams } = require("../runtime30/streams.js");
const { encode, decode } = require("@msgpack/msgpack");
const {
  MemoryStore,
  FakeBroker,
  config,
  signal,
  prepare,
} = require("./xxx_fixtures.cjs");
const { profile } = require("../runtime/exit_profiles32.cjs");
const { FeeLedger, executionMetrics } = require("../runtime30/accounting.js");
class NativeBroker extends FakeBroker {
  constructor() {
    super();
    this.holdSellLimits = false;
    this.rejectNative = false;
    this.quoteBid = 100;
  }
  async request(p, m = "GET", b, market = false) {
    if (
      p === "/v2/orders" &&
      m === "POST" &&
      (b.order_class === "oco" ||
        b.type === "trailing_stop" ||
        (this.holdSellLimits && b.side === "sell" && b.type === "limit"))
    ) {
      this.calls.push({ path: p, method: m, body: structuredClone(b), market });
      if (this.rejectNative && b.order_class === "oco")
        throw Object.assign(Error("422 native not supported"), { status: 422 });
      const o = {
        ...b,
        id: "native-" + this.orders.size,
        filled_qty: "0",
        filled_avg_price: null,
        status: "new",
      };
      if (b.type === "trailing_stop")
        o.stop_price = String(this.quoteBid - Number(b.trail_price));
      this.orders.set(o.client_order_id, o);
      if (b.order_class === "oco") {
        const child = {
          id: o.id + "-stop",
          client_order_id: o.client_order_id + "-stop",
          symbol: o.symbol,
          side: "sell",
          qty: o.qty,
          type: "stop",
          stop_price: b.stop_loss.stop_price,
          time_in_force: "gtc",
          filled_qty: "0",
          filled_avg_price: null,
          status: "held",
        };
        o.legs = [child];
        this.orders.set(child.client_order_id, child);
      }
      return structuredClone(o);
    }
    if (p.startsWith("/v2/orders/") && m === "DELETE") {
      const o = [...this.orders.values()].find(
        (x) => x.id === p.split("/").at(-1),
      );
      const parent = [...this.orders.values()].find((x) =>
        x.legs?.some((y) => y.id === o?.id),
      );
      const root = parent || o;
      if (root?.order_class === "oco") {
        this.calls.push({ path: p, method: m });
        if (this.cancelImmediate) {
          root.status = "canceled";
          root.legs.forEach((x) => (x.status = "canceled"));
        }
        return null;
      }
    }
    return super.request(p, m, b, market);
  }
  fill(id, n, px) {
    const o = this.orders.get(id),
      old = Number(o.filled_qty),
      qty = Number(o.qty),
      p = this.positions.get(o.symbol);
    assert(o && p);
    assert(n > 0 && old + n <= qty);
    o.filled_qty = String(old + n);
    o.filled_avg_price = String(
      (old * Number(o.filled_avg_price || 0) + n * px) / (old + n),
    );
    o.status = old + n === qty ? "filled" : "partially_filled";
    const held = Number(p.qty) - n;
    assert(held >= 0);
    if (held) {
      p.qty = String(held);
      p.market_value = String(held * px);
    } else this.positions.delete(o.symbol);
    if (o.legs) {
      for (const l of o.legs) {
        l.qty = String(qty - old - n);
        if (old + n === qty) {
          l.qty = String(qty);
          l.status = "canceled";
        }
      }
    }
  }
}
async function ready(
  mode = "stop",
  api = new NativeBroker(),
  store = new MemoryStore(),
) {
  const cfg = config();
  cfg.nativeProtection = mode;
  cfg.streaming = false;
  const e = new Coordinator(store, api, cfg);
  await e.initialize(true);
  await e.market.catalog();
  const s = signal();
  prepare(e, s);
  await e.entries("equity");
  await e.reconcile();
  return { e, api, store, cfg };
}
const quote = (e, bid) =>
  (e.market.quotes.AAPL = {
    bid,
    ask: bid + 0.01,
    at: Date.now(),
    received: Date.now(),
  });
test("sub-0.5-percent virtual/native drift is visible and actually synchronized at tick precision", async () => {
  const { e, api } = await ready();
  await e.manage();
  await e.reconcile();
  const c = e.active()[0],
    protect = e.pending(c)[0];
  c.stop = Number(protect.payload.stop_price) + 0.4;
  c.protectionChangedAt = Date.now() - 6000;
  quote(e, 100);
  assert.equal(
    protectionSnapshot(
      c,
      e.state.intents,
      Number(e.position("AAPL").qty),
      Date.now(),
    ).aligned,
    false,
  );
  await e.manage();
  assert(protect.cancelAt);
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  const snap = e.view().positions[0].protectionState;
  assert(snap.aligned);
  assert.equal(snap.confirmedStop, Number(c.stop.toFixed(2)));
  assert(api.posts().some((x) => x.body.stop_price === c.stop.toFixed(2)));
});
test("TP survives protection cancel, restart and retracement with a durable minimum price", async () => {
  const { e, api, store, cfg } = await ready();
  await e.manage();
  await e.reconcile();
  api.holdSellLimits = true;
  quote(e, 104.5);
  await e.manage();
  const plan = structuredClone(e.active()[0].exitPlan);
  assert(plan && plan.minimumPrice > 103);
  assert.equal(api.posts().length, 2);
  const restarted = new Coordinator(store, api, cfg);
  await restarted.initialize(true);
  quote(restarted, 103);
  await restarted.manage();
  const tp = restarted.pending().find((i) => i.kind === "tp1");
  assert(tp);
  assert.equal(restarted.active()[0].exitPlan.id, plan.id);
  assert(Number(tp.payload.limit_price) >= plan.minimumPrice);
  assert.equal(api.posts().filter((x) => x.body.side === "buy").length, 1);
});
test("urgent stop preempts young TP and reconciles a partial fill during cancel before selling remainder", async () => {
  const { e, api } = await ready();
  await e.manage();
  await e.reconcile();
  api.holdSellLimits = true;
  quote(e, 104.5);
  await e.manage();
  await e.reconcile();
  await e.manage();
  await e.reconcile();
  const tp = e.pending().find((i) => i.kind === "tp1"),
    before = api.posts().length;
  assert(tp);
  api.cancelImmediate = false;
  quote(e, 101);
  await e.manage();
  assert(tp.cancelAt && Date.now() - tp.at < e.cfg.orderTtlMs);
  assert.equal(api.posts().length, before);
  api.fill(tp.id, 1, 103.5);
  api.orders.get(tp.id).status = "canceled";
  await e.reconcile();
  const held = Number(e.position("AAPL").qty);
  api.holdSellLimits = false;
  await e.manage();
  assert.equal(e.state.intents.at(-1).kind, "stop");
  assert.equal(Number(api.posts().at(-1).body.qty), held);
  assert.equal(api.positions.size, 0);
});
test("bounded pulse confirms cancellation through REST and advances exits without a five-second timer wait", async () => {
  const { e, api } = await ready();
  await e.pulse();
  quote(e, 104.5);
  const begin = api.calls.length;
  await e.pulse();
  const calls = api.calls.slice(begin),
    del = calls.findIndex((x) => x.method === "DELETE"),
    sell = calls.findIndex((x) => x.method === "POST");
  assert(del >= 0 && sell > del);
  assert(calls.slice(del + 1, sell).some((x) => x.path === "/v2/positions"));
  assert(fills(e.state.campaigns[0], e.state.intents).tpSold > 0);
});
for (const mode of ["oco", "oco_trailing"])
  test("real native payload/reconciliation lifecycle: " + mode, async () => {
    const { e, api, store, cfg } = await ready(mode);
    await e.pulse();
    const c = e.active()[0],
      roots = e.pending(c).filter((i) => !i.parentId);
    assert.equal(roots.length, 3);
    assert.equal(
      roots.filter((i) => i.payload.order_class === "oco").length,
      2,
    );
    assert.equal(
      roots.find((i) => i.nativeRole === "runner").payload.type,
      mode === "oco" ? "stop" : "trailing_stop",
    );
    assert.equal(e.reconcileError, "");
    assert(e.confirmedProtection(c));
    const tp = roots.find((i) => i.nativeRole === "tp1");
    api.fill(tp.id, 1, Number(tp.payload.limit_price));
    await e.onTradeUpdate({
      event: "partial_fill",
      order: structuredClone(api.orders.get(tp.id)),
    });
    assert.equal(fills(c, e.state.intents).tpSold, 1);
    assert.equal(e.reconcileError, "");
    assert(e.confirmedProtection(c));
    const count = api.posts().length;
    await e.pulse();
    assert.equal(api.posts().length, count);
    const restarted = new Coordinator(store, api, cfg);
    await restarted.initialize(true);
    quote(restarted, 100);
    await restarted.pulse();
    assert.equal(api.posts().length, count);
    assert.equal(restarted.reconcileError, "");
  });
test("broker rejection of native OCO causes an actual full-position stop fallback", async () => {
  const api = new NativeBroker();
  api.rejectNative = true;
  const { e } = await ready("oco", api);
  await e.pulse();
  assert(e.active()[0].nativeDisabledReason);
  assert(e.confirmedProtection(e.active()[0]));
  assert.equal(
    e.pending().find((i) => i.kind === "protect").payload.type,
    "stop",
  );
});
test("native urgent flatten cancels every group before one reconciled full exit", async () => {
  const { e, api } = await ready("oco");
  await e.pulse();
  await e.control("flatten");
  const held = Number(e.position("AAPL").qty);
  await e.pulse();
  assert.equal(api.posts().at(-1).body.type, "market");
  assert.equal(Number(api.posts().at(-1).body.qty), held);
  assert.equal(api.positions.size, 0);
  assert.equal(e.reconcileError, "");
});
test("experimental profiles require explicit PAPER acknowledgement and freeze only new campaigns", async () => {
  const { e } = await ready();
  const old = structuredClone(e.active()[0].policy);
  await assert.rejects(
    e.control("exit-profile", { profile: "REGIME_ADAPTIVE" }),
    /acknowledgement/,
  );
  await e.control("exit-profile", {
    profile: "TREND_RUNNER",
    confirmation: "EXPERIMENTAL_PAPER_ONLY",
  });
  assert.deepEqual(e.active()[0].policy, old);
  assert.equal(e.state.exitProfile, "TREND_RUNNER");
  assert.throws(() => profile(old, "REGIME_ADAPTIVE", {}), /observed/);
  const trend = profile(old, "REGIME_ADAPTIVE", { momentum_bps: 50, rvol: 3 });
  assert.equal(trend.regime, "TREND");
  assert.equal(trend.policy.tp1Fraction, 0.125);
});
class Socket {
  constructor() {
    this.sent = [];
    this.readyState = 0;
  }
  send(v) {
    this.sent.push(v);
  }
  close() {
    this.readyState = 3;
  }
  open() {
    this.readyState = 1;
    this.onopen();
  }
  emit(v) {
    this.onmessage({ data: v });
  }
}
const tick = () => new Promise((r) => setImmediate(r));
test("OPRA uses a MsgPack handshake/header and decodes observed quotes; PAPER orders use binary JSON", async () => {
  const sockets = [],
    quotes = [],
    trades = [],
    api = {
      keys: { key: "SYNTHETIC-KEY", secret: "SYNTHETIC-SECRET" },
      mode: "paper",
    },
    cfg = config();
  cfg.streaming = true;
  const stream = new AlpacaStreams(
    api,
    cfg,
    (s, q) => quotes.push([s, q]),
    async (e) => {
      trades.push(e);
    },
    undefined,
    undefined,
    (url, opts) => {
      const ws = new Socket();
      sockets.push({ ws, url, opts });
      return ws;
    },
  );
  stream.start({ stocks: [], crypto: [], options: ["AAPL261120C00100000"] });
  const opra = sockets.find((x) => x.url.endsWith("opra")),
    orders = sockets.find((x) => x.url.includes("paper-api"));
  assert.equal(opra.opts.headers["Content-Type"], "application/msgpack");
  opra.ws.open();
  assert.equal(decode(opra.ws.sent[0]).action, "auth");
  opra.ws.emit(encode([{ T: "success", msg: "authenticated" }]));
  await tick();
  assert.deepEqual(decode(opra.ws.sent[1]).quotes, ["AAPL261120C00100000"]);
  opra.ws.emit(
    encode([
      { T: "subscription", quotes: ["AAPL261120C00100000"] },
      {
        T: "q",
        S: "AAPL261120C00100000",
        bp: 5,
        ap: 5.1,
        bs: 7,
        as: 9,
        t: new Date().toISOString(),
      },
    ]),
  );
  await tick();
  assert.equal(quotes[0][1].bp, 5);
  assert.equal(quotes[0][1].bs, 7);
  assert.equal(quotes[0][1].as, 9);
  orders.ws.open();
  orders.ws.emit(
    Buffer.from(
      JSON.stringify({
        stream: "authorization",
        data: { status: "authorized" },
      }),
    ),
  );
  await tick();
  orders.ws.emit(
    Buffer.from(
      JSON.stringify({
        stream: "listening",
        data: { streams: ["trade_updates"] },
      }),
    ),
  );
  orders.ws.emit(
    Buffer.from(
      JSON.stringify({
        stream: "trade_updates",
        data: { event: "fill", order: { id: "OBSERVED-TEST" } },
      }),
    ),
  );
  await tick();
  assert.equal(trades.length, 1);
  assert(!JSON.stringify(stream.snapshot()).includes("SYNTHETIC-SECRET"));
  stream.stop();
  assert(stream.snapshot().channels.every((c) => c.state === "STOPPED"));
});
test("malformed stream frames trigger visible reconnect and invalidate flow warmup", async () => {
  const sockets = [],
    resets = [],
    api = { keys: { key: "SYNTHETIC", secret: "SYNTHETIC" }, mode: "paper" },
    cfg = config();
  cfg.streaming = true;
  const stream = new AlpacaStreams(
    api,
    cfg,
    () => {
      throw Error("unexpected quote");
    },
    async () => {
      throw Error("unexpected trade");
    },
    undefined,
    (n) => resets.push(n),
    () => {
      const w = new Socket();
      sockets.push(w);
      return w;
    },
  );
  stream.start({ stocks: ["AAPL"], crypto: [], options: [] });
  const ws = sockets[1];
  ws.open();
  ws.emit("not-json");
  await tick();
  assert.equal(
    stream.snapshot().channels.find((c) => c.name === "stocks").state,
    "RECONNECTING",
  );
  assert.deepEqual(resets, ["stocks"]);
  stream.stop();
});
test("reported fee ledger paginates, retains unpriced crypto fees and never certifies all-in net", async () => {
  const store = new MemoryStore(),
    calls = [],
    page = Array.from({ length: 100 }, (_, j) => ({
      id: "activity-" + j,
      activity_type: "FILL",
    }));
  page[0] = { id: "activity-0", activity_type: "FEE", net_amount: "-1.25" };
  const api = {
    request: async (p) => {
      calls.push(p);
      return calls.length === 1
        ? page
        : [
            {
              id: "crypto-fee",
              activity_type: "CFEE",
              qty: ".00001",
              symbol: "BTC/USD",
            },
          ];
    },
  };
  const ledger = new FeeLedger(api, store, "test-fees");
  await ledger.refresh(Date.now() - 86400000);
  assert(calls[1].includes("page_token=activity-99"));
  assert.equal(ledger.view().reportedUsdFees, 1.25);
  assert.equal(ledger.view().unpricedFees.length, 1);
  assert.equal(ledger.view().complete, false);
  const loaded = new FeeLedger(api, store, "test-fees");
  await loaded.load();
  assert.equal(loaded.view().reportedUsdFees, 1.25);
});
test("fee pagination failure remains ERROR without manufacturing a zero successful cost", async () => {
  const ledger = new FeeLedger(
    {
      request: async () => {
        throw Error("broker unavailable");
      },
    },
    new MemoryStore(),
    "failed-fees",
  );
  await assert.rejects(ledger.refresh(Date.now() - 1e6));
  assert.equal(ledger.view().status, "ERROR");
  assert.equal(ledger.view().lastSuccess, 0);
  assert.equal(ledger.view().reportedUsdFees, null);
});
test("execution metrics use actual fills, explicit estimated fees and no second slippage charge", async () => {
  const { e } = await ready();
  const c = e.active()[0];
  await e.control("flatten");
  await e.pulse();
  const f = fills(c, e.state.intents),
    m = executionMetrics(e.state.campaigns, e.state.intents, e.cfg);
  assert.equal(m.realizedGrossUsd, f.gross);
  assert.equal(m.estimatedNetUsd, f.gross);
  assert.equal(m.latency.submitToAck.samples, 1);
  assert.equal(m.closedCampaigns, 1);
});
test("execution journal preserves event type separately from the order intent kind", async () => {
  const { e } = await ready();
  assert(
    e.state.events.some(
      (x) => x.kind === "ORDER_ACK" && x.intentKind === "entry",
    ),
  );
  e.event("OBSERVED", { kind: "stop", at: 1 });
  const x = e.state.events.at(-1);
  assert.equal(x.kind, "OBSERVED");
  assert.equal(x.intentKind, "stop");
  assert(x.at > 1);
});
