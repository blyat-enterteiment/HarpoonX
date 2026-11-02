"use strict";
/** Finite diagnostic adapter. No broker, optimizer or production promotion. */
const fs=require('node:fs'), path=require('node:path');
const {spawnSync}=require('node:child_process');
const {assertDataset}=require('../runtime30/ultimate_contracts.js');
const {replayFundedPortfolio}=require('../runtime30/ultimate_replay.js');
const {researchProtocol,summarize,prepare}=require('./historical_bank.cjs');
const read=p=>JSON.parse(fs.readFileSync(p,'utf8'));
const write=(p,v)=>fs.writeFileSync(p,JSON.stringify(v)+'\n');
function runOne(data,base,study,signals,legacy,novel,policy,scenario){
  const p=researchProtocol(base,scenario),checked=assertDataset(data,p);
  const sessions=checked.sessions.filter(s=>base.periods.evaluation_start<=s.date&&s.date<=base.periods.evaluation_end);
  const limits={...base.limits};
  if(policy==='HUBER_REGIME_CAP')for(const k of ['riskFraction','openRiskFraction','grossFraction','assetFraction'])limits[k]*=study.regime_cap.limit_multiplier;
  const options={continuous:true,cashDividends:true,entryExecution:base.entry_execution,
    externalCostPerSessionUsd:base.scenarios[scenario].external_cost_usd_per_session};
  if(['RIDGE','SVR'].includes(policy))options.admissions=legacy.admissions[policy];
  else if(!['C0','CASH'].includes(policy))options.admissions=novel.admissions[scenario][policy];
  const folds=[{test:sessions.filter(s=>s.date<=base.periods.validation_end),selected:policy==='CASH'?'CASH':'ALL:BASELINE'},
    {test:sessions.filter(s=>s.date>=base.periods.test_start),selected:policy==='CASH'?'CASH':'ALL:BASELINE'}];
  const result=replayFundedPortfolio(signals.signals,checked,p,folds,sessions,limits,options);
  const report={schema:'HARPOON_HISTORICAL_PORTFOLIO_1',origin:'HISTORICAL',execution:'MODELED_OHLCV',policy,scenario,
    study_id:study.study_id,native_control:base.native_control,native_control_is_production_coordinator:false,
    parameter_selection:false,...result,financial_acceptance_allowed:false,liveApproved:false};
  report.summary=summarize(report,base);
  report.diagnostic_scope='REUSED_SEEN_HOLDOUT_NOT_CONFIRMATORY';
  return report;
}
function main(){
  const [mode,protocolFile,dataFile,outDir]=process.argv.slice(2);
  const study=read(protocolFile),base=read(study.base_protocol),data=read(dataFile);
  const root=path.resolve(__dirname,'..');
  if(path.resolve(dataFile)!==path.resolve(root,study.dataset))throw Error('REGISTERED_DATASET_PATH_REQUIRED');
  const verify=(artifacts)=>{
    const args=['-B',path.join(__dirname,'quant8_verify.py'),'--protocol',path.resolve(protocolFile),
      '--manifest',path.join(root,'research/quant8/source_manifest.json'),
      '--registration-dir',path.join(root,'evidence/core_quant8_30_17_0/registration'),
      '--output',path.join(outDir,artifacts?'derivation_verification.json':'replay_preflight.json')];
    if(artifacts)args.push('--artifacts',path.resolve(outDir));
    const result=spawnSync(process.env.HARPOON_QUANT_PYTHON||'python3',args,{cwd:root,encoding:'utf8',timeout:1800000,
      env:{...process.env,PYTHONPATH:path.join(root,'quant'),OPENBLAS_NUM_THREADS:'1',OMP_NUM_THREADS:'1'}});
    if(result.status!==0)throw Error('QUANT8_REGISTERED_DERIVATION_FAILED:'+(result.stdout||'')+(result.stderr||''));
  };
  verify(false);
  if(mode==='prepare'){
    const artifacts=prepare(data,base);write(path.join(outDir,'signals.json'),artifacts.signals);write(path.join(outDir,'training_labels.json'),artifacts.labels);return;
  }
  if(mode!=='replay')throw Error('MODE_PREPARE_OR_REPLAY');
  const signals=read(path.join(outDir,'signals.json')),legacy=read(path.join(outDir,'legacy_admissions.json')),novel=read(path.join(outDir,'novel_admissions.json'));
  const regenerated=prepare(data,base);
  if(JSON.stringify(signals)!==JSON.stringify(regenerated.signals)||JSON.stringify(read(path.join(outDir,'training_labels.json')))!==JSON.stringify(regenerated.labels))throw Error('CAUSAL_DERIVATION_CHANGED');
  verify(true);
  const reports={};
  for(const scenario of study.budget.scenarios)for(const policy of [...study.budget.policies,'CASH']){
    const name=scenario+'_'+policy+'.json';
    try{const report=runOne(data,base,study,signals,legacy,novel,policy,scenario);write(path.join(outDir,name),report);reports[scenario+':'+policy]=name;
      process.stdout.write(JSON.stringify({scenario,policy,net:report.summary.CONTINUOUS.economic_pnl_modeled_usd,campaigns:report.funded.length})+'\n');}
    catch(e){write(path.join(outDir,name+'.incident.json'),{error:String(e.stack||e),economic_pnl_usd:null,details:e.details??null});throw e;}
  }
  write(path.join(outDir,'reports.json'),reports);
}
module.exports={runOne};
if(require.main===module)main();
