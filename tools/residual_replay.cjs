"use strict";
/** Offline six-recipe residual experiment. No search, production or broker route. */
const fs=require('node:fs'),path=require('node:path'),{spawnSync}=require('node:child_process');
const {assertDataset}=require('../runtime30/ultimate_contracts.js');
const {replayFundedPortfolio}=require('../runtime30/ultimate_replay.js');
const {researchProtocol,summarize}=require('./historical_bank.cjs');
const ROOT=path.resolve(__dirname,'..'),read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const write=(p,v)=>fs.writeFileSync(p,JSON.stringify(v)+'\n');
function runOne(data,protocol,signalArtifact,policy,scenario){
 if(![...protocol.budget.policies,'CASH'].includes(policy)||!protocol.budget.scenarios.includes(scenario))throw Error('FIXED_RECIPES_ONLY');
 const p=researchProtocol(protocol,scenario),checked=assertDataset(data,p);
 const sessions=checked.sessions.filter(s=>protocol.periods.evaluation_start<=s.date&&s.date<=protocol.periods.evaluation_end);
 const signals=policy==='CASH'?[]:signalArtifact.signals[scenario][policy];
 const folds=[{test:sessions.filter(s=>s.date<=protocol.periods.validation_end),selected:policy==='CASH'?'CASH':'ALL:BASELINE'},
 {test:sessions.filter(s=>s.date>=protocol.periods.test_start),selected:policy==='CASH'?'CASH':'ALL:BASELINE'}];
 if(folds.reduce((n,f)=>n+f.test.length,0)!==sessions.length)throw Error('PHASE_COVERAGE_REQUIRED');
 const result=replayFundedPortfolio(signals,checked,p,folds,sessions,{...protocol.limits},{continuous:true,cashDividends:true,
 entryExecution:'IOC_LIMIT_TO_APPROVED_BUDGET',externalCostPerSessionUsd:protocol.scenarios[scenario].external_cost_usd_per_session});
 const report={schema:'HARPOON_HISTORICAL_PORTFOLIO_1',origin:'HISTORICAL',execution:'MODELED_OHLCV',policy,scenario,
 study_id:protocol.study_id,native_control:'NATIVE_HISTORICAL_ULTIMATE',native_control_is_production_coordinator:false,
 economic_hypothesis:'INTRADAY_SECTOR_RESIDUAL_RECOVERY',execution_template:'CLOSED_CHANNEL:BASELINE',
 parameter_selection:false,...result,financial_acceptance_allowed:false,liveApproved:false,
 diagnostic_scope:'RECAPTURE_OF_GLOBALLY_SEEN_PERIOD_NOT_CONFIRMATORY',
 controls_are_exactly_exposure_matched:false};
 report.summary=summarize(report,protocol);return report;
}
function main(){
 const [protocolFile,dataFile,outDir]=process.argv.slice(2),protocol=read(protocolFile);
 if(path.resolve(dataFile)!==path.resolve(ROOT,protocol.dataset))throw Error('REGISTERED_DATASET_PATH_REQUIRED');
 const verify=spawnSync(process.env.HARPOON_QUANT_PYTHON||'python3',['-B',path.join(__dirname,'residual_verify.py'),
 '--protocol',path.resolve(protocolFile),'--artifacts',path.resolve(outDir),'--output',path.join(outDir,'derivation_verification.json')],
 {cwd:ROOT,encoding:'utf8',timeout:1800000,maxBuffer:4*1024*1024,env:{...process.env,OPENBLAS_NUM_THREADS:'1',OMP_NUM_THREADS:'1'}});
 if(verify.status!==0)throw Error('REGISTERED_DERIVATION_FAILED:'+(verify.stdout||'')+(verify.stderr||''));
 const data=read(dataFile),signals=read(path.join(outDir,'signals.json')),reports={},incidents={};
 for(const scenario of protocol.budget.scenarios)for(const policy of [...protocol.budget.policies,'CASH']){
  const name=scenario+'_'+policy+'.json';
  try{const report=runOne(data,protocol,signals,policy,scenario);write(path.join(outDir,name),report);reports[scenario+':'+policy]=name;
  process.stdout.write(JSON.stringify({scenario,policy,net:report.summary.CONTINUOUS.economic_pnl_modeled_usd,campaigns:report.funded.length})+'\n');}
  catch(e){const incident=name+'.incident.json';write(path.join(outDir,incident),{schema:'HARPOON_RESIDUAL_INCIDENT_1',policy,scenario,error:String(e.code||e.name||'REPLAY_ERROR'),message:String(e.message||e).split(': {')[0],details:e.details??null,economic_pnl_usd:null,financial_acceptance_allowed:false});incidents[scenario+':'+policy]=incident;process.stdout.write(JSON.stringify({scenario,policy,status:'BLOCKED_RETAINED',error:String(e.code||e.name||'REPLAY_ERROR')})+'\n');}
 }
 write(path.join(outDir,'reports.json'),reports);write(path.join(outDir,'incidents.json'),incidents);
}
module.exports={runOne};if(require.main===module)main();
