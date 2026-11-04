"use strict";
/** Offline PROFIT8 bridge. The caller preregisters recipes before any historical run. */
const fs = require("node:fs"), path = require("node:path");
const { assertDataset } = require("../runtime30/ultimate_contracts.js");
const engine = require("../runtime30/profit8_replay.js");
const { researchProtocol, summarize } = require("./historical_bank.cjs");
const read = file => JSON.parse(fs.readFileSync(file, "utf8"));
const need = (ok, reason) => { if (!ok) throw Error(reason); };
function write(file, value) {
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, JSON.stringify(value) + "\n");
}
function prepareTeachers(protocol, data, signalArtifact, scenario) {
  const p = researchProtocol(protocol, scenario), checked = assertDataset(data, p);
  const signals = Array.isArray(signalArtifact) ? signalArtifact : signalArtifact.signals;
  need(Array.isArray(signals), "PROFIT8_TEACHER_SIGNAL_ARRAY");
  need(new Set(signals.map(s => s.id)).size === signals.length, "PROFIT8_TEACHER_UNIQUE_SIGNALS");
  const bySymbol = Object.fromEntries(checked.series.map(series => [series.symbol, series]));
  const counts = {};
  const labels = signals.map(signal => {
    need(bySymbol[signal.symbol], "PROFIT8_TEACHER_SYMBOL");
    const label = engine.replayProfit8Teacher(signal, bySymbol[signal.symbol], checked, p);
    counts[label.status] = (counts[label.status] ?? 0) + 1;
    return { ...label, known_at: label.label_known_at };
  });
  return { schema: "HARPOON_PROFIT8_POLICY_LABELS_1", scenario, labels, counts,
    origin: "HISTORICAL", execution: "MODELED_OHLCV",
    target_basis: ["E", "T"], normalization: "LAST_COMPLETED_CLOSE_AVAILABLE_AT_DECISION",
    exact_identity: "P(q)=2*floor(q/4)*E_usd+(q-2*floor(q/4))*T_usd",
    scope: "INDEPENDENT_TEACHER_TARGETS_NOT_FUNDED_POLICY_RESULTS",
    ioc_buffer_fraction: 0.003, no_fill_targets_retained_as_zero: true,
    maturity: "DEADLINE_COHORT_AVAILABLE_AT_INCLUDING_EARLY_STOPS_AND_NO_FILLS",
    fixed_calendar_overhead_in_target: false, financial_acceptance_allowed: false, liveApproved: false };
}
function run(protocol, data, bundle, recipe, scenario) {
  need(protocol.limits && Object.keys(engine.PROFIT8_REPLAY_LIMITS).every(key => Number.isFinite(protocol.limits[key])),
    "PROFIT8_EXPLICIT_LIMITS_REQUIRED");
  const p = researchProtocol(protocol, scenario), checked = assertDataset(data, p);
  const signals = bundle.signals?.[scenario]?.[recipe];
  need(Array.isArray(signals), "PROFIT8_RECIPE_SIGNALS_REQUIRED");
  const mode = bundle.recipe_modes?.[recipe] ?? (recipe.startsWith("H2_") ? "MAX_POSITIVE"
    : recipe.startsWith("H3_") ? "ROBUST_LOG" : "NATIVE_MAX");
  const sessions = checked.sessions.filter(s => protocol.periods.evaluation_start <= s.date && s.date <= protocol.periods.evaluation_end);
  const calendarCost = protocol.scenarios[scenario].external_cost_usd_per_calendar_day;
  need(Number.isFinite(calendarCost) && calendarCost >= 0, "PROFIT8_EXPLICIT_CALENDAR_COST_REQUIRED");
  const options = { continuous: true, cashDividends: true,
    entryExecution: "IOC_LIMIT_COMMON_CAUSAL_30BPS", externalCostPerSessionUsd: 0,
    calendarCostPerDayUsd: calendarCost, profit8: { mode },
    ...(bundle.admissions?.[scenario]?.[recipe] === undefined ? {} : {
      admissions: bundle.admissions[scenario][recipe] }) };
  const result = engine.replayFundedPortfolio(signals, checked, p,
    [{ test: sessions, selected: "ALL:BASELINE" }], sessions, protocol.limits, options);
  const report = { schema: "HARPOON_HISTORICAL_PORTFOLIO_1", study: "PROFIT8",
    origin: "HISTORICAL", execution: "MODELED_OHLCV", policy: recipe, scenario,
    ...result, financial_acceptance_allowed: false, liveApproved: false,
    native_control_is_production_coordinator: false, native_control: "NATIVE_HISTORICAL_ULTIMATE_PROFIT8" };
  report.metadata.externalCostCoverage = "UTC_CALENDAR_DATES_INCLUSIVE_FROM_FIRST_EVALUATION_OPEN";
  report.metadata.externalCostPerCalendarDayUsd = calendarCost;
  report.metadata.costSource = "REGISTERED_MODELED_ASSUMPTIONS_NOT_ACCOUNT_FEE_VERIFICATION";
  if (recipe.startsWith("GROSS_")) report.metadata.profit8.targetBasis = "GROSS_DEADLINE_MINUS_REGISTERED_VARIABLE_COST";
  report.summary = summarize(report, protocol);
  report.sizing_summary = { decisions: report.states.filter(s => s.profit8Sizing).length,
    quantities_below_qmax: report.states.filter(s => s.profit8Sizing && s.quantity < s.profit8Sizing.qMax).length,
    zero_quantity_decisions: report.states.filter(s => s.profit8Sizing && s.quantity === 0).length,
    mode, joint_multi_asset_optimizer: false };
  // Optional descriptive partitions share the same continuous account. They do
  // not restart capital or create extra strategy-selection trials.
  report.descriptive_windows = {};
  for (const [name, window] of Object.entries(protocol.reporting_windows ?? {})) {
    need(typeof window.start === "string" && typeof window.end === "string" && window.start <= window.end,
      "PROFIT8_REPORTING_WINDOW");
    if (!report.curve.some(row => window.start <= row.session_id && row.session_id <= window.end)) continue;
    const periods = { ...protocol.periods, validation_start: window.start, validation_end: window.end,
      test_start: window.start, test_end: window.end, evaluation_start: window.start, evaluation_end: window.end };
    report.descriptive_windows[name] = summarize(report, { ...protocol, periods }).CONTINUOUS;
  }
  return report;
}
function main(argv) {
  const mode = argv.shift(), args = {};
  need(["teacher", "replay"].includes(mode), "PROFIT8_MODE_TEACHER_OR_REPLAY");
  for (let i = 0; i < argv.length; i += 2) {
    need(argv[i].startsWith("--") && argv[i + 1], "PROFIT8_KEY_VALUE_ARGUMENTS");
    args[argv[i].slice(2)] = argv[i + 1];
  }
  need(args.protocol && args.scenario && args.output, "PROFIT8_PROTOCOL_SCENARIO_OUTPUT_REQUIRED");
  const protocol = read(args.protocol), data = read(args.dataset ?? protocol.dataset);
  need(protocol.origin === "HISTORICAL" && protocol.live_approved === false, "PROFIT8_OFFLINE_HISTORICAL_ONLY");
  if (mode === "teacher") {
    need(args.signals, "PROFIT8_TEACHER_SIGNALS_REQUIRED");
    const labels = prepareTeachers(protocol, data, read(args.signals), args.scenario);
    write(args.output, labels);
    process.stdout.write(JSON.stringify({ mode, scenario: args.scenario, labels: labels.labels.length, counts: labels.counts }) + "\n");
  } else {
    need(args.bundle && args.recipe, "PROFIT8_REPLAY_BUNDLE_RECIPE_REQUIRED");
    const report = run(protocol, data, read(args.bundle), args.recipe, args.scenario);
    write(args.output, report);
    process.stdout.write(JSON.stringify({ mode, recipe: args.recipe, scenario: args.scenario,
      net: report.summary.CONTINUOUS.economic_pnl_modeled_usd, campaigns: report.funded.length,
      sizing: report.sizing_summary }) + "\n");
  }
}
module.exports = { run, prepareTeachers };
if (require.main === module) try { main(process.argv.slice(2)); }
catch (error) { process.stderr.write(String(error.stack ?? error) + "\n"); process.exitCode = 2; }
