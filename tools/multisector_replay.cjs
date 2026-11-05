"use strict";
// Offline adapter for one shared ledger; validate each symbol using the native
// proxy contract. Only the universe width differs from historical experiments.
const fs = require("node:fs");
const {researchProtocol, summarize} = require("./historical_bank.cjs");
const {assertDataset} = require("../runtime30/ultimate_contracts.js");
const engine = require("../runtime30/profit8_replay.js");
const read = file => JSON.parse(fs.readFileSync(file, "utf8"));
function run(protocol, data, bundle, recipe, scenario) {
  const symbols = protocol.universe;
  if (!Array.isArray(symbols) || symbols.length < 4 || symbols.length > 8 ||
      new Set(symbols).size !== symbols.length || !["CONFIRMED","SIMPLE","CASH"].includes(recipe))
    throw Error("REGISTERED_MULTISECTOR_DOMAIN");
  for (const symbol of symbols) researchProtocol({...protocol, universe:[symbol]}, scenario);
  const p = researchProtocol({...protocol, universe:symbols.slice(0,4)}, scenario);
  p.universe = symbols;
  const checked = assertDataset(data,p);
  const sessions = checked.sessions.filter(s=>protocol.periods.evaluation_start<=s.date && s.date<=protocol.periods.evaluation_end);
  const fixed = protocol.scenarios[scenario].external_cost_usd_per_calendar_day;
  const result = engine.replayFundedPortfolio(bundle.signals[scenario][recipe],checked,p,
    [{test:sessions,selected:"ALL:BASELINE"}],sessions,protocol.limits,{continuous:true,
      cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",externalCostPerSessionUsd:0,
      calendarCostPerDayUsd:fixed,profit8:{mode:"NATIVE_MAX"}});
  const report = {...result,schema:"HARPOON_HISTORICAL_PORTFOLIO_1",study:"PROFIT8",origin:"HISTORICAL",
    execution:"MODELED_OHLCV",policy:recipe,scenario,native_control:"NATIVE_HISTORICAL_ULTIMATE_PROFIT8",
    native_control_is_production_coordinator:false,financial_acceptance_allowed:false,liveApproved:false};
  report.metadata.externalCostPerCalendarDayUsd=fixed;
  report.summary=summarize(report,protocol);
  return report;
}
if(require.main===module){
  const [, , , ...pairs]=process.argv;
  const args={};
  for(let i=0;i<pairs.length;i+=2) args[pairs[i]]=pairs[i+1];
  const protocol=read(args["--protocol"]);
  fs.writeFileSync(args["--output"],JSON.stringify(run(protocol,read(protocol.dataset),read(args["--bundle"]),args["--recipe"],args["--scenario"])));
}
