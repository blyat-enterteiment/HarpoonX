import type { Api, Config, Json } from "./types";
import WebSocket from "ws";
import { decode, encode } from "@msgpack/msgpack";
type SocketFactory = (
  url: string,
  options?: { headers?: Record<string, string> },
) => WebSocket;
interface Channel {
  name: string;
  url: string;
  symbols: string[];
  socket?: WebSocket;
  generation: number;
  attempts: number;
  state: string;
  lastMessageAt: number;
  lastEventAt: number;
  subscribedAt: number;
  errors: number;
  error: string;
  retry?: ReturnType<typeof setTimeout>;
  watch?: ReturnType<typeof setInterval>;
}
/** Actual Alpaca authenticated streams. REST remains the inventory and mutation authority. */
export class AlpacaStreams {
  channels: Record<string, Channel> = {};
  private stopped = true;
  constructor(
    private api: Api,
    private cfg: Config,
    private quote: (symbol: string, raw: Json) => void,
    private trade: (raw: Json) => Promise<void>,
    private flow?: (raw: Json) => void,
    private disconnected?: (name: string) => void,
    private factory: SocketFactory = (url, options) =>
      new WebSocket(url, options),
    private active?: (name: string) => boolean,
  ) {}
  start(symbols: { stocks: string[]; crypto: string[]; options: string[] }) {
    if (this.cfg.streaming === false) return;
    this.stopped = false;
    const keys = (this.api as Json).keys;
    if (!keys?.key || !keys?.secret || (this.api as Json).mode !== "paper")
      return;
    const targets = [
      ["orders", "wss://paper-api.alpaca.markets/stream", []],
      [
        "stocks",
        "wss://stream.data.alpaca.markets/v2/" + this.cfg.stockFeed,
        symbols.stocks,
      ],
      [
        "crypto",
        "wss://stream.data.alpaca.markets/v1beta3/crypto/us",
        symbols.crypto,
      ],
      [
        "options",
        "wss://stream.data.alpaca.markets/v1beta1/opra",
        symbols.options,
      ],
    ] as [string, string, string[]][];
    for (const [name, url, raw] of targets) {
      const list = [...new Set(raw)].sort(),
        old = this.channels[name];
      if (name !== "orders" && !list.length) {
        if (old) this.close(old);
        delete this.channels[name];
        continue;
      }
      if (old && JSON.stringify(old.symbols) === JSON.stringify(list)) continue;
      if (old) this.close(old);
      const c: Channel = {
        name,
        url,
        symbols: list,
        generation: 0,
        attempts: 0,
        state: "CONNECTING",
        lastMessageAt: 0,
        lastEventAt: 0,
        subscribedAt: 0,
        errors: 0,
        error: "",
      };
      this.channels[name] = c;
      this.connect(c);
    }
  }
  private connect(c: Channel) {
    if (this.stopped) return;
    const generation = ++c.generation,
      keys = (this.api as Json).keys;
    c.state = "CONNECTING";
    let ws: WebSocket;
    try {
      ws = this.factory(
        c.url,
        c.name === "options"
          ? { headers: { "Content-Type": "application/msgpack" } }
          : undefined,
      );
      c.socket = ws;
      ws.binaryType = "arraybuffer";
    } catch (e) {
      this.fail(c, String(e));
      return;
    }
    ws.onopen = () => {
      if (generation !== c.generation || this.stopped) return;
      c.state = "AUTHENTICATING";
      this.send(c, { action: "auth", key: keys.key, secret: keys.secret });
    };
    let queue = Promise.resolve();
    ws.onmessage = (event) => {
      queue = queue
        .then(async () => {
          if (generation !== c.generation || this.stopped) return;
          const bytes = event.data;
          const buffer =
            typeof bytes === "string"
              ? Buffer.from(bytes)
              : bytes instanceof ArrayBuffer
                ? Buffer.from(bytes)
                : ArrayBuffer.isView(bytes)
                  ? Buffer.from(
                      bytes.buffer,
                      bytes.byteOffset,
                      bytes.byteLength,
                    )
                  : null;
          if (!buffer) throw Error("Unsupported stream frame");
          if (buffer.byteLength > 4e6)
            throw Error("Stream frame exceeds bound");
          const parsed =
            c.name === "options"
              ? decode(buffer)
              : JSON.parse(buffer.toString("utf8"));
          const rows = Array.isArray(parsed) ? parsed : [parsed];
          if (rows.length > 10000) throw Error("Stream batch exceeds bound");
          for (const r of rows) await this.frame(c, r);
        })
        .catch((e) => {
          if (generation === c.generation)
            this.fail(c, e instanceof Error ? e.message : String(e));
        });
    };
    ws.onerror = () => {
      if (generation === c.generation)
        this.fail(c, "WebSocket transport error");
    };
    ws.onclose = () => {
      if (generation === c.generation && !this.stopped) {
        c.socket = undefined;
        this.fail(c, c.error || "Stream disconnected");
      }
    };
    c.watch = setInterval(() => {
      if (
        c.name !== "orders" &&
        (!this.active || this.active(c.name)) &&
        c.subscribedAt &&
        Date.now() - Math.max(c.lastEventAt, c.subscribedAt) > 45000
      )
        this.fail(c, "No fresh quote events; REST fallback active");
    }, 15000);
    c.watch.unref?.();
  }
  private send(c: Channel, data: Json) {
    c.socket?.send(c.name === "options" ? encode(data) : JSON.stringify(data));
  }
  private async frame(c: Channel, r: Json) {
    if (!r || typeof r !== "object") throw Error("Invalid stream event");
    c.lastMessageAt = Date.now();
    if (
      r.T === "error" ||
      (r.stream === "authorization" && r.data?.status !== "authorized")
    )
      throw Error(
        "Alpaca stream rejected authentication/subscription: " +
          String(r.code || r.data?.status || "ERROR"),
      );
    const authed =
      (r.T === "success" && r.msg === "authenticated") ||
      (r.stream === "authorization" && r.data?.status === "authorized");
    if (authed) {
      c.state = "AUTHENTICATED";
      this.send(
        c,
        c.name === "orders"
          ? { action: "listen", data: { streams: ["trade_updates"] } }
          : {
              action: "subscribe",
              quotes: c.symbols,
              ...(c.name !== "options" ? { trades: c.symbols } : {}),
              ...(c.name === "crypto" ? { orderbooks: c.symbols } : {}),
            },
      );
      return;
    }
    if (r.T === "subscription" || r.stream === "listening") {
      if (c.name === "orders" && !r.data?.streams?.includes("trade_updates"))
        throw Error("Order stream not subscribed");
      if (c.name !== "orders" && c.symbols.some((s) => !r.quotes?.includes(s)))
        throw Error("Incomplete quote subscription");
      c.state = "SUBSCRIBED";
      c.subscribedAt = Date.now();
      c.attempts = 0;
      c.error = "";
      return;
    }
    if (r.T === "q") {
      if (c.state !== "SUBSCRIBED" || !c.symbols.includes(r.S))
        throw Error("Quote before matching subscription");
      this.quote(r.S, {
        ...r,
        t: r.t instanceof Date ? r.t.toISOString() : r.t,
      });
      this.flow?.(r);
      c.lastEventAt = Date.now();
      return;
    }
    if (
      ["t", "o"].includes(r.T) &&
      c.state === "SUBSCRIBED" &&
      c.symbols.includes(r.S)
    )
      this.flow?.(r);
    if (r.stream === "trade_updates") {
      if (c.name !== "orders" || c.state !== "SUBSCRIBED")
        throw Error("Trade update before subscription");
      await this.trade(r.data);
      c.lastEventAt = Date.now();
    }
  }
  private fail(c: Channel, error: string) {
    if (this.stopped || c.retry) return;
    c.error = error.slice(0, 240);
    c.errors++;
    c.state = "RECONNECTING";
    c.generation++;
    this.disconnected?.(c.name);
    if (c.watch) clearInterval(c.watch);
    c.watch = undefined;
    const ws = c.socket;
    c.socket = undefined;
    try {
      ws?.close();
    } catch (e) {
      c.error += "; close failed: " + String(e).slice(0, 80);
    }
    const delay = Math.min(60000, 1000 * 2 ** Math.min(6, c.attempts++));
    c.retry = setTimeout(() => {
      c.retry = undefined;
      this.connect(c);
    }, delay);
    c.retry.unref?.();
  }
  private close(c: Channel) {
    c.generation++;
    if (c.retry) clearTimeout(c.retry);
    if (c.watch) clearInterval(c.watch);
    c.retry = undefined;
    c.watch = undefined;
    try {
      c.socket?.close();
    } catch (e) {
      c.error = String(e).slice(0, 160);
    }
    c.socket = undefined;
    c.state = "STOPPED";
  }
  stop() {
    this.stopped = true;
    for (const c of Object.values(this.channels)) this.close(c);
  }
  snapshot() {
    return {
      enabled: this.cfg.streaming !== false,
      available: !!(this.api as Json).keys?.key,
      source: "ALPACA_WEBSOCKET",
      channels: Object.values(this.channels).map((c) => ({
        name: c.name,
        state: c.state,
        lastMessageAt: c.lastMessageAt,
        lastEventAt: c.lastEventAt,
        subscribedAt: c.subscribedAt,
        eventAgeMs: c.lastEventAt ? Date.now() - c.lastEventAt : null,
        symbols: c.symbols.length,
        errors: c.errors,
        error: c.error,
      })),
      fallback: "REST_RECONCILIATION_REQUIRED",
    };
  }
}
