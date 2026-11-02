"use strict";
const fs = require("node:fs"),
  os = require("node:os"),
  { performance } = require("node:perf_hooks"),
  { exitDecision } = require("../runtime30/policy.js"),
  { DEFAULT_EXIT } = require("../runtime30/types.js"),
  cfg = require("../config/examples/xxx.json");
const n = 20000,
  times = [],
  c = {
    id: "benchmark",
    symbol: "SYNTHETIC",
    book: "equity",
    created: Date.now(),
    instrument: { multiplier: 1, step: 1, minQty: 1 },
    policy: { ...DEFAULT_EXIT },
    risk: 2,
    peak: 100,
    stop: 98,
  },
  intents = [
    {
      campaign: "benchmark",
      kind: "entry",
      order: { filled_qty: "8", filled_avg_price: "100" },
    },
  ],
  now = Date.now(),
  q = { bid: 104, ask: 104.01, at: now, received: now };
for (let i = 0; i < 1000; i++) exitDecision({ ...c }, intents, q, 8, now, cfg);
const begin = performance.now();
for (let i = 0; i < n; i++) {
  const t = performance.now();
  exitDecision({ ...c }, intents, q, 8, now, cfg);
  times.push(performance.now() - t);
}
const ms = performance.now() - begin;
times.sort((a, b) => a - b);
const result = {
  source: "SYNTHETIC_MICROBENCHMARK",
  node: process.version,
  platform: process.platform,
  architecture: process.arch,
  cpu: os.cpus()[0].model,
  iterations: n,
  elapsedMs: ms,
  operationsPerSecond: (n / ms) * 1000,
  p50Ms: times[Math.floor(n * 0.5)],
  p95Ms: times[Math.floor(n * 0.95)],
  p99Ms: times[Math.floor(n * 0.99)],
  scope:
    "Pure exit decision only. Excludes network, broker, SQLite, UI and full runtime. Not a latency or profit guarantee.",
};
fs.writeFileSync(
  require("node:path").join(process.env.HARPOON_QA_OUTPUT_DIR || "evidence/operational-30.3.1", "benchmark.json"),
  JSON.stringify(result, null, 2),
);
console.log(JSON.stringify(result, null, 2));
