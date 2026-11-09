"use strict";
/**
 * SYNTHETIC-only bridge. Prices, signals and variants are external frozen input.
 * This module performs no fitting, recipe selection or random generation.
 * Source-bound v2; all 47 registered v1 sources are verified before/after a batch.
 * Signal sourceAvailableAt is a declared cutoff, not proof of feature provenance.
 * File CLI: --input input.json --output output.json
 * NDJSON CLI: --stream (one self-contained request/result per line).
 */
const fs = require("node:fs");
const path = require("node:path");
const crypto = require("node:crypto");
const readline = require("node:readline");
const C = require("../runtime30/ultimate_contracts.js");
const engine = require("../runtime30/modulation10_replay.cjs");
const reservations = require("../runtime30/ultimate_reservations.js");
const PROFILES = engine.MODULATION10_PROFILES;
const DAY = 86400000, HOUR = 3600000, TOL = 1e-7;
const need = (ok, reason) => { if (!ok) throw new Error(reason); };
const read = file => JSON.parse(fs.readFileSync(file, "utf8"));
const BASE_PROTOCOL = read(path.resolve(__dirname, "../research/modulation9/protocol.json"));

function researchProtocol(protocol, scenario) {
  const cost = protocol.scenarios?.[scenario];
  need(["NOMINAL", "STRESS"].includes(scenario) && cost,
    "MODULATION10_REGISTERED_COST_SCENARIO");
  need(Number.isFinite(cost.external_cost_usd_per_calendar_day) &&
    cost.external_cost_usd_per_calendar_day >= 0,
    "MODULATION10_EXPLICIT_CALENDAR_OVERHEAD");
  return C.assertProtocol({ ...C.defaultProtocol("ALPACA_PROXY"),
    trainSessions: 60, testSessions: 21, holdoutSessions: 63,
    universe: protocol.universe,
    costs: { spreadBps: cost.spread_bps, slippageBps: cost.slippage_bps,
      perSideUsd: cost.commission_usd_per_share_per_side } });
}

function prepareInput(input) {
  need(input && typeof input === "object", "MODULATION10_INPUT_OBJECT");
  const protocol = input.protocol;
  need(protocol?.schema === "HARPOON_MODULATION10_PROTOCOL_1" &&
    protocol.origin === "SYNTHETIC" && protocol.live_approved === false &&
    protocol.execution_allowed === false, "MODULATION10_SYNTHETIC_OFFLINE_ONLY");
  need(protocol.limits && Object.entries(engine.PROFIT8_REPLAY_LIMITS)
    .every(([key, cap]) => Number.isFinite(protocol.limits[key]) &&
      protocol.limits[key] > 0 && protocol.limits[key] <= cap) &&
    protocol.limits.capitalUsd === 20000,
    "MODULATION10_EXPLICIT_NATIVE_LIMITS_NO_INCREASE");
  need(protocol.entry_schedules && typeof protocol.entry_schedules === "object" &&
    protocol.entry_rules && typeof protocol.entry_rules === "object",
    "MODULATION10_REGISTERED_ENTRY_RULES_AND_CLOCKS");
  for (const scenario of ["NOMINAL", "STRESS"]) {
    const expected = BASE_PROTOCOL.scenarios[scenario], actual = protocol.scenarios?.[scenario];
    need(actual && Object.keys(actual).length === Object.keys(expected).length &&
      Object.entries(expected).every(([key, value]) => actual[key] === value),
      "MODULATION10_COSTS_IDENTICAL_TO_REGISTERED_MODULATION9");
  }
  const dataset = typeof input.dataset === "string" ? read(input.dataset) : input.dataset;
  need(typeof dataset?.provenance?.source === "string" &&
    /SYNTHETIC/i.test(dataset.provenance.source), "MODULATION10_SYNTHETIC_PROVENANCE_REQUIRED");
  const scenarios = input.scenario_names ?? ["NOMINAL", "STRESS"];
  need(Array.isArray(scenarios) && scenarios.length > 0 &&
    new Set(scenarios).size === scenarios.length,
    "MODULATION10_UNIQUE_COST_SCENARIOS");
  const nativeProtocols = {};
  for (const scenario of scenarios) nativeProtocols[scenario] = researchProtocol(protocol, scenario);
  // Dataset contract is cost-invariant. Validate the shared object once.
  const checked = C.assertDataset(dataset, nativeProtocols[scenarios[0]]);
  const from = protocol.periods?.evaluation_start ?? checked.sessions[0].date;
  const through = protocol.periods?.evaluation_end ?? checked.sessions.at(-1).date;
  need(typeof from === "string" && typeof through === "string" && from <= through,
    "MODULATION10_EVALUATION_DATES");
  const wanted = input.sessions === undefined ? null : new Set(input.sessions);
  need(wanted === null || (Array.isArray(input.sessions) && wanted.size === input.sessions.length &&
    input.sessions.every(s => typeof s === "string")), "MODULATION10_SESSION_IDS");
  const sessions = checked.sessions.filter(s => from <= s.date && s.date <= through &&
    (wanted === null || wanted.has(s.date)));
  need(sessions.length > 0 && (wanted === null || sessions.length === wanted.size),
    "MODULATION10_EVALUATION_SESSIONS");
  const variants = input.variants ?? protocol.variants;
  need(Array.isArray(variants) && variants.length > 0 && variants.length <= 128 &&
    new Set(variants.map(v => v.id)).size === variants.length,
    "MODULATION10_UNIQUE_BOUNDED_VARIANTS");
  need(input.signals && typeof input.signals === "object" && !Array.isArray(input.signals),
    "MODULATION10_ENTRY_SIGNAL_MAP");
  for (const variant of variants) {
    need(typeof variant.id === "string" && variant.id.length > 0 && variant.id.length <= 120 &&
      typeof variant.entry === "string" && Object.hasOwn(PROFILES, variant.exit) &&
      Number.isFinite(variant.risk) && variant.risk > 0 &&
      variant.risk <= protocol.limits.riskFraction && variant.risk <= protocol.limits.openRiskFraction,
      "MODULATION10_VARIANT_CONTRACT");
    need(variant.entry === "CASH" || (Array.isArray(input.signals[variant.entry]) &&
      Object.hasOwn(protocol.entry_schedules, variant.entry) &&
      (variant.entry === "SIMPLE" || Object.hasOwn(protocol.entry_rules, variant.entry))),
      "MODULATION10_VARIANT_SIGNALS_AND_REGISTERED_SCHEDULE_REQUIRED");
  }
  const detailed = new Set(input.detailed ?? []);
  need(Array.isArray(input.detailed ?? []) && [...detailed].every(id => variants.some(v => v.id === id)),
    "MODULATION10_DETAILED_IDS");
  return { input, protocol, checked, nativeProtocols, scenarios, variants, sessions, detailed };
}

function ledgerAudit(result, sessions, capital) {
  const at = sessions.at(-1).close;
  const snapshot = reservations.snapshotFundedReservations(result.reservationBook, at);
  let net = 0, maxTradeError = 0, terminalQuantity = 0;
  for (const trade of result.funded) {
    let balance = 0, qty = 0;
    for (const event of trade.inventoryEvents) {
      need(Number.isFinite(event.filledPrice) && Number.isFinite(event.feeUsd),
        "MODULATION10_LEDGER_PRICES_AND_FEES_REQUIRED");
      qty += event.quantityDelta;
      balance -= event.quantityDelta * event.filledPrice + event.feeUsd;
    }
    maxTradeError = Math.max(maxTradeError, Math.abs(balance - trade.netUsd));
    terminalQuantity += Math.abs(qty);
    net += balance;
  }
  const impliedEquity = capital + net + result.accounting.dividendAccruedUsd -
    result.accounting.modeledExternalCostsUsd;
  const error = result.curve.at(-1).equity_end_usd - impliedEquity;
  return { terminal_reconciled: snapshot.reservations.length === 0 &&
      terminalQuantity === 0 && maxTradeError <= TOL && Math.abs(error) <= TOL &&
      Math.abs(result.accounting.reconciliationResidualUsd) <= TOL,
    terminal_inventory_quantity: terminalQuantity,
    terminal_reservations: snapshot.reservations.length,
    max_trade_ledger_error: maxTradeError, cash_reconciliation_error: error,
    native_reconciliation_error: result.accounting.reconciliationResidualUsd };
}

function summarize(result, sessions, capital, signalCount) {
  const audit = ledgerAudit(result, sessions, capital);
  need(audit.terminal_reconciled, "MODULATION10_TERMINAL_LEDGER_RECONCILIATION");
  let peak = capital, dailyDd = 0;
  for (const row of result.curve) {
    peak = Math.max(peak, row.equity_end_usd);
    dailyDd = Math.max(dailyDd, 1 - row.equity_end_usd / peak);
  }
  const finalEquity = result.curve.at(-1).equity_end_usd;
  const calendarDays = Math.floor(sessions.at(-1).close / DAY) -
    Math.floor(sessions[0].open / DAY) + 1;
  const returns = result.curve.map(row => row.portfolio_return);
  const gains = result.funded.reduce((sum, t) => sum + Math.max(t.netEconomicUsd, 0), 0);
  const losses = -result.funded.reduce((sum, t) => sum + Math.min(t.netEconomicUsd, 0), 0);
  const best = Math.max(0, ...result.funded.map(t => t.netEconomicUsd));
  return { net_pnl_usd: finalEquity - capital, final_equity: finalEquity,
    total_return: finalEquity / capital - 1,
    total_log_return: Math.log(finalEquity / capital),
    mean_calendar_day_log_return: Math.log(finalEquity / capital) / calendarDays,
    calendar_days: calendarDays, sessions: sessions.length,
    max_event_drawdown: result.metadata.maximumObservedEventDrawdown,
    max_session_drawdown: dailyDd,
    worst_session_return: Math.min(...returns),
    max_hold_hours: Math.max(0, ...result.funded.map(t => (t.closed - t.opened) / HOUR)),
    max_signal_to_exit_hours: Math.max(0, ...result.funded.map(t =>
      (t.closed - t.holdingClockStartedAt) / HOUR)),
    closed_campaigns: result.funded.length, candidate_signals: signalCount,
    winning_campaigns: result.funded.filter(t => t.netEconomicUsd > 0).length,
    profit_factor: losses > 0 ? gains / losses : null,
    best_campaign_usd: best, net_without_best_campaign_usd: finalEquity - capital - best,
    fixed_costs_usd: result.accounting.modeledExternalCostsUsd,
    fees_usd: result.accounting.modeledTradingFeesUsd,
    explicit_costs_usd: result.accounting.modeledExternalCostsUsd + result.accounting.modeledTradingFeesUsd,
    price_pnl_after_spread_slippage_before_commissions_usd: result.accounting.modeledPricePnlUsd,
    spread_slippage_cost_usd: null,
    spread_slippage_reporting: "EMBEDDED_IN_EXECUTED_PRICES_NOT_SEPARATELY_IDENTIFIED",
    dividend_accrued_usd: result.accounting.dividendAccruedUsd,
    dividend_receivable_usd: result.accounting.dividendReceivableUsd,
    denied: result.preEntryRefusals.length, no_fills: result.modeledNoFills.length,
    denied_reasons: result.portfolio.skipped,
    ambiguous_bars: result.funded.reduce((sum, t) => sum + t.ambiguousBars, 0),
    ...audit };
}

function compactTrade(t) {
  return { id: t.id, symbol: t.symbol, quantity: t.quantity,
    opened: t.opened, closed: t.closed, terminal_known_at: t.chronology.terminalKnownAt,
    holding_deadline_at: t.holdingDeadlineAt, holding_hours: (t.closed - t.opened) / HOUR,
    entry: t.entry, risk_usd: t.riskUsd, net_usd: t.netEconomicUsd,
    trading_net_usd: t.netUsd, fees_usd: t.feesUsd,
    close_mark_peak_pnl_usd: t.peakClosePnl, giveback_usd: t.givebackUsd,
    reason: t.reason, ambiguous_bars: t.ambiguousBars,
    exit_fills: t.inventoryEvents.filter(e => e.kind === "EXIT").map(e => ({
      at: e.at, known_at: e.knownAt, quantity: -e.quantityDelta,
      price: e.filledPrice, fee_usd: e.feeUsd, reason: e.reason })) };
}

function runAccount(prepared, variant, scenario) {
  const { protocol, checked, nativeProtocols, sessions, input, detailed } = prepared;
  const profile = PROFILES[variant.exit];
  const signals = variant.entry === "CASH" ? [] : input.signals[variant.entry].map(signal => ({
    ...signal, metadata: { ...signal.metadata, roadmapHorizonHours: profile.horizonHours,
      modulation10: { entry: variant.entry, profile: profile.profile } } }));
  const options = { continuous: true, cashDividends: true,
    entryExecution: "IOC_LIMIT_COMMON_CAUSAL_30BPS", externalCostPerSessionUsd: 0,
    calendarCostPerDayUsd: protocol.scenarios[scenario].external_cost_usd_per_calendar_day,
    profit8: { mode: "NATIVE_MAX" }, researchModulation: true, researchModulation10: true,
    modulation10EntrySchedules: protocol.entry_schedules };
  const limits = { ...protocol.limits, riskFraction: variant.risk };
  const result = engine.replayFundedPortfolio(signals, checked, nativeProtocols[scenario],
    [{ test: sessions, selected: variant.entry === "CASH" ? "CASH" : "ALL:BASELINE" }],
    sessions, limits, options);
  const count = signals.filter(s => sessions[0].open <= s.at && s.at <= sessions.at(-1).close).length;
  const summary = summarize(result, sessions, limits.capitalUsd, count);
  const output = { id: variant.id, entry: variant.entry, exit: variant.exit,
    risk: variant.risk, scenario, ...(variant.role ? { role: variant.role } : {}),
    economic_exit_profile: profile.economicProfile, stop_receipt_policy: profile.stopReceipt,
    summary, terminal_reconciled: summary.terminal_reconciled,
    curve: result.curve.map(row => ({ date: row.session_id,
      portfolio_log_return: row.portfolio_log_return, portfolio_return: row.portfolio_return,
      equity: row.equity_end_usd, fixed_costs_usd: row.external_costs_usd })),
    trades: result.funded.map(compactTrade), event_risk: result.profit8RiskEventSummary };
  if (detailed.has(variant.id)) {
    // The native scope label is historical because it predates this bridge.
    // Relabel only descriptive metadata; preserve all native arithmetic/events.
    result.metadata.executionNature = "SYNTHETIC_MODELED_OHLCV;NOT_BROKER_RECEIPTS";
    output.detail = { origin: "SYNTHETIC", execution: "MODELED_OHLCV", ...result,
      financial_acceptance_allowed: false, liveApproved: false };
  }
  return output;
}

function sourceHashes() {
  return Object.fromEntries(["../runtime30/profit8_replay.js", "../runtime30/modulation9_exit.cjs",
    "../runtime30/modulation10_replay.cjs", "modulation10_bridge.cjs", "modulation10_test.cjs"].map(relative => {
    const file = path.resolve(__dirname, relative);
    return [path.relative(path.resolve(__dirname, ".."), file),
      crypto.createHash("sha256").update(fs.readFileSync(file)).digest("hex")];
  }));
}

function runBatch(input) {
  const before = engine.verifyModulation9Sources();
  const prepared = prepareInput(input), accounts = [];
  for (const variant of prepared.variants) for (const scenario of prepared.scenarios)
    accounts.push(runAccount(prepared, variant, scenario));
  return { schema: "HARPOON_MODULATION10_BATCH_1", origin: "SYNTHETIC",
    execution: "MODELED_OHLCV", financial_acceptance_allowed: false, liveApproved: false,
    source_sha256: sourceHashes(), profiles: PROFILES,
    source_binding: { before, after: engine.verifyModulation9Sources() },
    accounts, account_executions: accounts.length,
    all_terminal_reconciled: accounts.every(a => a.terminal_reconciled) };
}

async function main(argv) {
  if (argv.length === 1 && argv[0] === "--stream") {
    const lines = readline.createInterface({ input: process.stdin, crlfDelay: Infinity });
    for await (const line of lines) {
      if (!line.trim()) continue;
      const output = runBatch(JSON.parse(line));
      process.stdout.write(JSON.stringify(output) + "\n");
    }
    return;
  }
  const args = {};
  for (let i = 0; i < argv.length; i += 2) {
    need(["--input", "--output"].includes(argv[i]) && argv[i + 1],
      "MODULATION10_USAGE_--input_INPUT_--output_OUTPUT_OR_--stream");
    args[argv[i].slice(2)] = argv[i + 1];
  }
  need(args.input && args.output, "MODULATION10_INPUT_OUTPUT_REQUIRED");
  const output = runBatch(read(args.input));
  fs.mkdirSync(path.dirname(args.output), { recursive: true });
  fs.writeFileSync(args.output, JSON.stringify(output) + "\n");
  process.stdout.write(JSON.stringify({ schema: output.schema,
    account_executions: output.account_executions,
    all_terminal_reconciled: output.all_terminal_reconciled }) + "\n");
}

module.exports = { PROFILES, researchProtocol, prepareInput, ledgerAudit, summarize,
  runAccount, runBatch, main };
if (require.main === module) main(process.argv.slice(2)).catch(error => {
  process.stderr.write(String(error.stack ?? error) + "\n");
  process.exitCode = 2;
});
