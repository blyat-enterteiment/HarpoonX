import fs from "node:fs";
import path from "node:path";
import vm from "node:vm";
import { assertOrder } from "./validators";
import type { Api, Json } from "./types";
/** Reuse the audited priority/rate-limited transport. Its market and trading queues are separate. */
export function alpaca(key: string, secret: string): Api {
  if (!key || !secret) throw Error("Alpaca PAPER credentials required");
  const ctx = vm.createContext({
    fetch,
    URL,
    URLSearchParams,
    AbortController,
    setTimeout,
    clearTimeout,
    Date,
    Math,
    JSON,
    Number,
    Error,
    console,
  });
  vm.runInContext(
    fs.readFileSync(path.join(__dirname, "../src/io.js"), "utf8"),
    ctx,
  );
  ctx.credentials = { key, secret };
  return vm.runInContext("new DirectAlpaca('paper',credentials)", ctx) as Api;
}
export function normalizeOrder(o: Json, clientId: string): Json {
  return assertOrder(o, clientId);
}
