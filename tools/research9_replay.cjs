"use strict";
const fs=require('node:fs'),path=require('node:path');
const {assertDataset}=require('../runtime30/ultimate_contracts.js');
const {replayFundedPortfolio}=require('../runtime30/ultimate_replay_research.js');
const {researchProtocol,summarize}=require('./historical_bank.cjs');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
function run(protocol,data,signals,policy,scenario){
 const p=researchProtocol(protocol,scenario),checked=assertDataset(data,p);
 const sessions=checked.sessions.filter(s=>protocol.periods.evaluation_start<=s.date&&s.date<=protocol.periods.evaluation_end);
 const folds=[{test:sessions.filter(s=>s.date<=protocol.periods.validation_end),selected:'ALL:BASELINE'},
 {test:sessions.filter(s=>s.date>=protocol.periods.test_start),selected:'ALL:BASELINE'}];
 const result=replayFundedPortfolio(signals,checked,p,folds,sessions,{...protocol.limits},{continuous:true,cashDividends:true,
 entryExecution:'IOC_LIMIT_TO_APPROVED_BUDGET',externalCostPerSessionUsd:protocol.scenarios[scenario].external_cost_usd_per_session});
 const report={schema:'HARPOON_HISTORICAL_PORTFOLIO_1',origin:'HISTORICAL',execution:'MODELED_OHLCV',policy,scenario,...result,
 financial_acceptance_allowed:false,liveApproved:false,study_id:'HARPOON_RESEARCH9_EXPLORATORY',
 native_control_is_production_coordinator:false,native_control:'NATIVE_HISTORICAL_ULTIMATE'};
 report.summary=summarize(report,protocol);return report;
}
if(require.main===module){
 const dir=process.argv[2],protocol=read('research/residual_30_18/protocol.json'),data=read(protocol.dataset),signals=read(path.join(dir,'signals.json'));
 for(const scenario of ['NOMINAL','STRESS'])for(const policy of ['CONTINUATION','STABILIZED_NORMALIZE','REVERSAL_INVALIDATE']){
  let report;
  try{report=run(protocol,data,signals[scenario][policy],policy,scenario);}
  catch(e){fs.writeFileSync(path.join(dir,scenario+'_'+policy+'.incident.json'),JSON.stringify({error:String(e),details:e.details??null,net_pnl_usd:null,level9_accredited:false})+'\n');console.log(scenario,policy,'INCIDENT_RETAINED');continue;}
  fs.writeFileSync(path.join(dir,scenario+'_'+policy+'.json'),JSON.stringify(report)+'\n');
  console.log(scenario,policy,report.summary.CONTINUOUS.economic_pnl_modeled_usd,report.funded.length);
 }
}
module.exports={run};
