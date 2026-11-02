"use strict";
// Local synthetic storage benchmark. No market, model, order or network access.
const fs = require("node:fs"), os = require("node:os"), path = require("node:path");
const { performance } = require("node:perf_hooks");
const { DurableStore } = require(path.resolve(process.argv[2], "runtime/store30.cjs"));
const directory = fs.mkdtempSync(path.join(os.tmpdir(), "harpoon-store-benchmark-"));
const samples = [], n = 200;
const percentile = (values, q) => {
  const sorted = [...values].sort((a, b) => a - b);
  return sorted[Math.ceil(q * sorted.length) - 1];
};
(async () => {
  const store = new DurableStore(path.join(directory, "state.sqlite"));
  try {
    const start = performance.now();
    await store.open();
    await store.get("benchmark:ready");
    const readyMs = performance.now() - start;
    for (let i = 0; i < 20; i++) await store.put("benchmark:warmup", { i, synthetic: true });
    const payload = { synthetic: true, value: 123.25, text: "x".repeat(1024) };
    for (let i = 0; i < n; i++) {
      const before = performance.now();
      await store.put("benchmark:row:" + String(i).padStart(4, "0"), payload);
      samples.push(performance.now() - before);
    }
    const readStart = performance.now();
    const rows = await store.scan("benchmark:row:");
    const scanMs = performance.now() - readStart;
    if (rows.length !== n) throw Error("BENCHMARK_ROW_COUNT_MISMATCH");
    const closeStart = performance.now();
    await store.close();
    const closeMs = performance.now() - closeStart;
    process.stdout.write(JSON.stringify({
      scope: "SYNTHETIC_LOCAL_SQLITE_RPC_NOT_BROKER_LATENCY", node: process.version,
      python_executable: process.env.PYTHON || "python3", samples: n, warmup: 20,
      payload_json_bytes: Buffer.byteLength(JSON.stringify(payload)),
      ready_including_first_read_ms: readyMs, scan_200_rows_ms: scanMs, close_ms: closeMs,
      put_roundtrip_ms: { mean: samples.reduce((a, b) => a + b, 0) / n,
        p50: percentile(samples, .50), p95: percentile(samples, .95),
        p99: percentile(samples, .99), max: Math.max(...samples) },
      raw_put_samples_ms: samples, process_rss_bytes: process.memoryUsage().rss,
      financial_trials_created: 0, external_orders: 0,
      limitations: ["Same host and local filesystem; no deployment or broker measurement",
        "200 synthetic requests per run; tail percentiles are descriptive and not latency guarantees",
        "Node RSS excludes the Python child; no claim about total system memory"]
    }, null, 2) + "\n");
  } finally {
    if (store.process?.exitCode === null && store.process?.signalCode === null) {
      await new Promise(resolve => {
        const timer = setTimeout(() => { store.process.kill("SIGKILL"); resolve(); }, 5000);
        store.process.once("exit", () => { clearTimeout(timer); resolve(); });
      });
    }
    fs.rmSync(directory, { recursive: true, force: true });
  }
})().catch(error => { process.stderr.write(error.stack + "\n"); process.exitCode = 1; });
