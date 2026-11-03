"use strict";
/** Offline bridge: existing funded ledger, six fixed candidates and controls. */
const fs = require("node:fs"), path = require("node:path");
const {assertDataset} = require("../runtime30/ultimate_contracts.js");
const engine = require("../runtime30/ultimate_replay_roadmap9.js");
const {researchProtocol, summarize} = require("./historical_bank.cjs");
const read = f => JSON.parse(fs.readFileSync(f,"utf8"));
function run(protocol, data, bundle, recipe, scenario) {
  const p = researchProtocol(protocol, scenario), checked = assertDataset(data,p);
  const sessions = checked.sessions.filter(s => protocol.periods.evaluation_start <= s.date && s.date <= protocol.periods.evaluation_end);
  const options = {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_TO_APPROVED_BUDGET",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:protocol.scenarios[scenario].external_cost_usd_per_calendar_day,
    forecastDecisions:bundle.exit_forecasts};
  const result = engine.replayFundedPortfolio(bundle.signals[scenario][recipe],checked,p,
    [{test:sessions,selected:"ALL:BASELINE"}],sessions,protocol.limits,options);
  const report = {schema:"HARPOON_HISTORICAL_PORTFOLIO_1",origin:"HISTORICAL",execution:"MODELED_OHLCV",
    policy:recipe,scenario,...result,financial_acceptance_allowed:false,liveApproved:false,
    native_control_is_production_coordinator:false,native_control:"NATIVE_HISTORICAL_ULTIMATE_ROADMAP9"};
  report.metadata.externalCostCoverage = "UTC_CALENDAR_DATES_INCLUSIVE_FROM_FIRST_EVALUATION_OPEN";
  report.metadata.externalCostPerCalendarDayUsd = options.calendarCostPerDayUsd;
  report.metadata.costSource = "REGISTERED_MODELED_ASSUMPTIONS_NOT_ACCOUNT_FEE_VERIFICATION";
  report.summary = summarize(report,protocol);
  return report;
}
function pairedExits(protocol,data,bundle,baseline,recipe,scenario) {
  const p=researchProtocol(protocol,scenario),bySymbol=Object.fromEntries(data.series.map(s=>[s.symbol,s]));
  const source = new Map(bundle.signals[scenario][recipe].map(s=>[s.metadata.source_signal_id,s]));
  const pairs = [];
  for (const t of baseline.funded) {
    const signal=source.get(t.id);
    if(!signal)throw Error("PAIRED_ENTRY_ID_MISSING");
    const changed=engine.replayCampaign(signal,bySymbol[t.symbol],data,p,"BASELINE",t.quantity,1,
      {cashDividends:true,forecastDecisions:bundle.exit_forecasts});
    if(!changed || changed.opened!==t.opened || changed.entry!==t.entry || changed.quantity!==t.quantity)
      throw Error("PAIRED_INITIAL_POSITION_MISMATCH");
    pairs.push({baseline_id:t.id,candidate_id:changed.id,symbol:t.symbol,quantity:t.quantity,
      entered_at:t.opened,entry_price:t.entry,baseline_closed:t.closed,candidate_closed:changed.closed,
      baseline_net_usd:t.netUsd+(t.dividendAccruedUsd??0),candidate_net_usd:changed.netUsd+(changed.dividendAccruedUsd??0),
      delta_usd:changed.netUsd+(changed.dividendAccruedUsd??0)-t.netUsd-(t.dividendAccruedUsd??0)});
  }
  return {schema:"HARPOON_PAIRED_EXIT_ATTRIBUTION_1",recipe,scenario,pairs,
    same_entries_quantities_and_prices:true,delta_usd:pairs.reduce((s,x)=>s+x.delta_usd,0),
    capital_reuse_included:false,standalone_portfolio_return:false,
    scope:"PAIRED_CAMPAIGN_EXIT_ATTRIBUTION_NOT_ADDITIONAL_POLICY_SELECTION",promotion_allowed:false};
}
if(require.main===module) {
  const [directory,recipe,scenario]=process.argv.slice(2),protocol=read("research/roadmap9/protocol.json");
  const data=read(protocol.dataset),bundle=read(path.join(directory,"signals.json"));
  const report=run(protocol,data,bundle,recipe,scenario);
  fs.writeFileSync(path.join(directory,`${scenario}_${recipe}.json`),JSON.stringify(report)+"\n");
  if(recipe.startsWith("H3_")) {
    const baseline=read(path.join(directory,`${scenario}_BASE_CONTINUATION.json`));
    fs.writeFileSync(path.join(directory,`${scenario}_${recipe}.paired.json`),JSON.stringify(pairedExits(protocol,data,bundle,baseline,recipe,scenario))+"\n");
  }
  console.log(JSON.stringify({recipe,scenario,net:report.summary.CONTINUOUS.economic_pnl_modeled_usd,campaigns:report.funded.length}));
}
module.exports={run,pairedExits};
