import fs from "node:fs";
import path from "node:path";
import http from "node:http";
import { createHash } from "node:crypto";
import { Coordinator } from "./coordinator";
import { alpaca } from "./broker";
import type { Config, Json, Store } from "./types";
import { ULTIMATE_VERSION } from "./version";
import { FuturesGateway, IronbeamPaperApi } from "./ultimate_futures";
import { operationalCapabilities } from "./operational_status";
const { DurableStore } = require("../runtime/store30.cjs");
const { basicAuth } = require("../deploy/managed.cjs");
function readSecret(name: string) {
  const f = process.env[name + "_FILE"];
  return f ? fs.readFileSync(f, "utf8").trim() : process.env[name] || "";
}
export function paperAutostart(value = process.env.HARPOON_START_PAPER) {
  if (value !== undefined && value !== "0" && value !== "1")
    throw Error("HARPOON_START_PAPER must be 0 or 1");
  return value !== "0";
}
export function server(
  engine: Coordinator,
  password: string,
  html: string,
  origin?: string,
) {
  if (password.length < 32)
    throw Error("Panel password must contain at least 32 characters");
  const hashes = (tag: string) =>
    [
      ...html.matchAll(
        new RegExp("<" + tag + "(?:\\s[^>]*)?>([\\s\\S]*?)</" + tag + ">", "g"),
      ),
    ]
      .map(
        (m) =>
          "'sha256-" + createHash("sha256").update(m[1]).digest("base64") + "'",
      )
      .join(" ");
  const handle = async (
    req: http.IncomingMessage,
    res: http.ServerResponse,
  ) => {
    res.setHeader("Cache-Control", "no-store");
    res.setHeader("X-Content-Type-Options", "nosniff");
    res.setHeader("Referrer-Policy", "no-referrer");
    res.setHeader("X-Frame-Options", "DENY");
    res.setHeader(
      "Content-Security-Policy",
      `default-src 'none'; script-src ${hashes("script")}; style-src ${hashes("style")}; connect-src 'self'; img-src 'self' data:; base-uri 'none'; frame-ancestors 'none'; form-action 'none'`,
    );
    const send = (code: number, data: unknown) => {
      res.statusCode = code;
      res.setHeader("Content-Type", "application/json");
      res.end(JSON.stringify(data));
    };
    if (req.method === "GET" && req.url === "/healthz")
      return send(engine.stopping ? 503 : 200, {
        status: engine.stopping ? "STOPPING" : "HTTP_ALIVE",
        startedAt: engine.probe.startedAt,
        uptimeSeconds: process.uptime(),
        serverTime: Date.now(),
        version: ULTIMATE_VERSION,
      });
    if (!basicAuth(req.headers.authorization, password)) {
      res.setHeader("WWW-Authenticate", 'Basic realm="HARPOON XXX"');
      return send(401, { error: "Acceso privado" });
    }
    if (
      req.headers["sec-fetch-site"] === "cross-site" ||
      (req.headers.origin && req.headers.origin !== origin)
    )
      return send(403, { error: "Origen no permitido" });
    if (req.method === "GET" && req.url === "/") {
      res.setHeader("Content-Type", "text/html; charset=utf-8");
      return res.end(html);
    }
    if (req.method === "GET" && req.url === "/readyz")
      return send(
        Date.now() - engine.syncAt < 15000 &&
          !engine.reconcileError &&
          !engine.storageError
          ? 200
          : 503,
        {
          syncAt: engine.syncAt,
          reconciliation: engine.reconcileError,
          storageError: engine.storageError,
        },
      );
    if (req.method === "GET" && req.url === "/v1/health")
      return send(200, engine.view().health);
    if (req.method === "GET" && ["/v1/operational", "/operational-readyz"].includes(req.url || "")) {
      const report = operationalCapabilities(engine);
      return send(req.url === "/operational-readyz" && !report.operational_ready ? 503 : 200, report);
    }
    if (req.method === "GET" && req.url === "/v1/quant/observations/snapshot") {
      try { return send(200, await engine.quantObservations.snapshotExport()); }
      catch (error) { return send(422, {error: String(error), execution_allowed: false}); }
    }
    if (req.method === "GET" && req.url?.startsWith("/v1/quant/observations?")) {
      const params = new URL(req.url, "http://localhost").searchParams;
      try {
        const offset = Number(params.get("offset") || 0), limit = Number(params.get("limit") || 100);
        return send(200, params.has("snapshot_id") ?
          await engine.quantObservations.exportSnapshot(params.get("snapshot_id")!, offset, limit) :
          await engine.quantObservations.exportFrames(offset, limit));
      } catch (error) { return send(422, {error: String(error), execution_allowed: false}); }
    }
    if (req.method === "GET" && (req.url === "/v1/accounting/history" || req.url?.startsWith("/v1/accounting/history?"))) {
      const params = new URL(req.url, "http://localhost").searchParams;
      try {
        return send(200, await engine.netLedger.exportHistory(Number(params.get("offset") || 0), Number(params.get("limit") || 1000)));
      } catch (error) { return send(422, {error: String(error), execution_allowed: false}); }
    }
    if (req.method === "GET" && req.url === "/v1/quant/calibrator")
      return send(200, {performance: engine.quantPerformance, optimizer: engine.quantResearch, binding: require("../runtime/quant_bridge.cjs").binding(engine)});
    if (req.method === "GET" && req.url?.startsWith("/v1/ultimate/export?")) {
      const id =
        new URL(req.url, "http://localhost").searchParams.get("id") || "";
      return send(200, engine.ultimateLab.export(id));
    }
    if (req.method === "GET" && req.url === "/v1/ultimate")
      return send(200, engine.view().ultimate);
    if (req.method === "GET" && req.url === "/v1/exit-research")
      return send(200, engine.exitResearchReport);
    if (req.method === "GET" && req.url?.startsWith("/v1/selector-data?")) {
      const trialId =
        new URL(req.url, "http://localhost").searchParams.get("trialId") || "";
      return send(200, await engine.selectors.dataset(trialId));
    }
    if (
      req.method === "GET" &&
      ["/v1/state", "/v1/export"].includes(req.url || "")
    )
      return send(
        200,
        req.url === "/v1/export" ? engine.evidence() : engine.view(),
      );
    if (
      req.method !== "POST" ||
      ![
        "/v1/control",
        "/v1/research",
        "/v1/selector-data",
        "/v1/ultimate",
      ].includes(req.url || "")
    )
      return send(404, { error: "Ruta desconocida" });
    if (
      req.headers["x-harpoon-action"] !== "1" ||
      req.headers["content-type"]?.split(";")[0] !== "application/json"
    )
      return send(403, { error: "Acción explícita JSON requerida" });
    const chunks: Buffer[] = [];
    let size = 0;
    for await (const part of req) {
      size += part.length;
      if (
        size >
        (["/v1/research", "/v1/selector-data", "/v1/ultimate"].includes(
          req.url || "",
        )
          ? 64000000
          : 30000)
      )
        return send(413, { error: "Solicitud excesiva" });
      chunks.push(part);
    }
    const body = JSON.parse(Buffer.concat(chunks).toString("utf8")) as Json;
    if (!body || Array.isArray(body) || typeof body !== "object")
      return send(400, { error: "Objeto requerido" });
    if (req.url === "/v1/ultimate") {
      switch (body.action) {
        case "register":
          return send(201, await engine.ultimateLab.register(body.protocol));
        case "import":
          return send(
            200,
            await engine.ultimateLab.importData(body.id, body.data),
          );
        case "run":
          return send(202, await engine.ultimateLab.queue(body.id));
        case "futures-plan":
          return send(200, engine.futures.plan(body.plan));
        case "futures-paper-order":
          return send(202, await engine.futures.place(body.plan));
        default:
          return send(400, { error: "Acción Ultimate desconocida" });
      }
    }
    if (req.url === "/v1/selector-data")
      return send(
        200,
        await engine.selectors.importData(body.trialId, body.data),
      );
    if (req.url === "/v1/research") {
      await engine.queueResearch(body);
      return send(202, { queued: true });
    }
    return send(200, await engine.control(body.action, body));
  };
  return http.createServer((req, res) => {
    handle(req, res).catch((e) => {
      if (!res.headersSent) {
        res.statusCode = 409;
        res.setHeader("Content-Type", "application/json");
        res.end(
          JSON.stringify({
            error: e instanceof Error ? e.message : "Request failed",
          }),
        );
      } else res.destroy();
    });
  });
}
export async function main() {
  process.umask(0o077);
  const directory = process.env.HARPOON_DATA || "/var/data";
  fs.mkdirSync(directory, { recursive: true });
  const api = alpaca(
      readSecret("APCA_API_KEY_ID"),
      readSecret("APCA_API_SECRET_KEY"),
    ),
    account = await api.request("/v2/account");
  const cfg = JSON.parse(
    fs.readFileSync(
      process.env.HARPOON_CONFIG ||
        path.join(__dirname, "../config/examples/xxx.json"),
      "utf8",
    ),
  ) as Config;
  // Initial account binding is permitted only after the coordinator verifies an empty PAPER account.
  cfg.expected_account_id =
    process.env.HARPOON_EXPECTED_ACCOUNT_ID ||
    cfg.expected_account_id ||
    account.id;
  const store: Store = await new DurableStore(
      path.join(directory, "xxx.sqlite"),
    ).open(),
    engine = new Coordinator(store, api, cfg);
  const ibUsername = readSecret("IRONBEAM_USERNAME"),
    ibPassword = readSecret("IRONBEAM_PASSWORD"),
    ibKey = readSecret("IRONBEAM_API_KEY");
  if (ibUsername || ibPassword || ibKey) {
    engine.futures = new FuturesGateway(
      store,
      cfg,
      engine.validators,
      new IronbeamPaperApi(ibUsername, ibPassword, ibKey),
      readSecret("IRONBEAM_ACCOUNT_ID"),
      JSON.parse(process.env.HARPOON_FUTURES_CONTRACTS || "[]"),
      process.env.HARPOON_FUTURES_PAPER_ORDERS === "1",
      process.env.IRONBEAM_COMMISSION_PER_SIDE_USD
        ? Number(process.env.IRONBEAM_COMMISSION_PER_SIDE_USD)
        : null,
    );
  }
  await engine.initialize(paperAutostart());
  const origin =
    process.env.RENDER_EXTERNAL_URL ||
    process.env.HARPOON_PUBLIC_ORIGIN ||
    "http://127.0.0.1:" + (process.env.PORT || 10000);
  if (
    origin &&
    (new URL(origin).origin !== origin ||
      !["https:", "http:"].includes(new URL(origin).protocol) ||
      (new URL(origin).protocol === "http:" &&
        !["localhost", "127.0.0.1"].includes(new URL(origin).hostname)))
  )
    throw Error("HTTPS origin required outside localhost");
  const app = server(
    engine,
    readSecret("HARPOON_PANEL_PASSWORD"),
    fs.readFileSync(path.join(__dirname, "../deploy/dashboard30.html"), "utf8"),
    origin,
  );
  app.listen(
    Number(process.env.PORT || 10000),
    process.env.BIND_HOST || "0.0.0.0",
  );
  engine.start();
  let closing = false;
  const close = async () => {
    if (closing) return;
    closing = true;
    app.close();
    const deadline = setTimeout(() => process.exit(1), 55000);
    try {
      await engine.stop();
      clearTimeout(deadline);
      process.exit(0);
    } catch {
      process.exit(1);
    }
  };
  process.once("SIGTERM", close);
  process.once("SIGINT", close);
  console.log(
    JSON.stringify({
      event: "XXX_STARTED",
      mode: "paper",
      accountSuffix: account.id.slice(-4),
      paused: engine.state.paused,
    }),
  );
}
if (require.main === module)
  main().catch((e) => {
    console.error(
      JSON.stringify({
        event: "XXX_START_FAILED",
        message: e instanceof Error ? e.message : "Unknown error",
      }),
    );
    process.exit(1);
  });
