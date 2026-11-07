"use strict";
// Reproducible deterministic engineering timing only; never a selection trial.
const fs = require("node:fs"), path = require("node:path");
const B = require("../../tools/modulation9_bridge.cjs");
const R = require("../../runtime30/profit8_replay.js");
const DAY = 86400000, BAR = 300000;
let at = Date.UTC(2024, 0, 8, 14, 30);
const sessions = [];
while (sessions.length < 182) {
  const weekday = new Date(at).getUTCDay();
  if (weekday !== 0 && weekday !== 6)
    sessions.push({ date: new Date(at).toISOString().slice(0, 10), open: at, close: at + 78 * BAR });
  at += DAY;
}
const symbols = ["SYNA", "SYNB", "SYNM"];
const series = symbols.map(symbol => ({ symbol, root: symbol, tick: .01, pointValue: 1,
  bars: sessions.flatMap(s => Array.from({ length: 78 }, (_, j) => ({
    t: s.open + j * BAR, end: s.open + (j + 1) * BAR,
    availableAt: s.open + (j + 1) * BAR + 1000,
    o: 100, h: 100.1, l: 99.9, c: 100, v: 1000 }))) }));
const dataset = { schema: "HARPOON-ULTIMATE-DATA-1", kind: "ALPACA_PROXY",
  sessions, series, splitEvents: [], cashDividends: [],
  provenance: { execution: "MODELED_OHLCV", source: "SYNTHETIC_ENGINEERING_BENCHMARK_ONLY",
    feed: "DETERMINISTIC_FLAT_TAPE", files: [{ name: "engineering_fixture", sha256: "0".repeat(64) }] } };
const evaluation = sessions.slice(50, 176);
const signals = evaluation.flatMap((s, i) => symbols.slice(0, 2).map(symbol => ({
  id: `${symbol}:${i}`, symbol, hypothesis: "CLOSED_CHANNEL", direction: 1, index: 0,
  at: s.open + 3600000 + 1000, plannedEntryAt: s.open + 65 * 60000,
  stopDistance: 2, regime: .4, metadata: { roadmapHorizonHours: 72 } })));
const scenarios = {
  NOMINAL: { spread_bps: 2, slippage_bps: 2, commission_usd_per_share_per_side: .005,
    external_cost_usd_per_calendar_day: 1 },
  STRESS: { spread_bps: 4, slippage_bps: 4, commission_usd_per_share_per_side: .01,
    external_cost_usd_per_calendar_day: 2 }
};
const protocol = { origin: "SYNTHETIC", live_approved: false, execution_allowed: false,
  universe: symbols, limits: { ...R.PROFIT8_REPLAY_LIMITS },
  periods: { evaluation_start: evaluation[0].date, evaluation_end: evaluation.at(-1).date }, scenarios };
const variants = Object.keys(B.PROFILES).map(exit => ({
  id: "ENGINEERING_" + exit, entry: "CONFIRMED", exit, risk: .0025 }));
const started = performance.now();
const out = B.runBatch({ dataset, protocol, signals: { CONFIRMED: signals }, variants });
const elapsed = performance.now() - started;
const report = { scope: "DETERMINISTIC_SYNTHETIC_ENGINEERING_ONLY_NOT_SELECTION_OR_FINANCIAL_EVIDENCE",
  node: process.version, accounts: out.account_executions, signals_per_account: signals.length,
  bars_per_symbol: series[0].bars.length, symbols: symbols.length,
  elapsed_ms: elapsed, ms_per_account: elapsed / out.account_executions,
  heap_used_mb: process.memoryUsage().heapUsed / 1048576,
  all_terminal_reconciled: out.all_terminal_reconciled, source_sha256: out.source_sha256 };
const destination = process.argv[2] ?? path.join(__dirname, "bridge_benchmark_indexed.json");
fs.writeFileSync(destination, JSON.stringify(report, null, 2) + "\n");
process.stdout.write(JSON.stringify({ accounts: report.accounts, elapsed_ms: report.elapsed_ms,
  ms_per_account: report.ms_per_account, heap_used_mb: report.heap_used_mb,
  all_terminal_reconciled: report.all_terminal_reconciled }) + "\n");
