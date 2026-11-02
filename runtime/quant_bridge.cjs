'use strict';
const path=require('node:path');
const {spawn}=require('node:child_process');
const {performance:monotonic}=require('node:perf_hooks');
const workerPool={running:0,queue:[],maxObservedRunning:0,completed:0,rejected:0};
const WORKER_LIMIT=1,QUEUE_LIMIT=8;
const blocked=reason=>({status:'BLOCKED',execution_allowed:false,selected:[],liveApproved:false,reason});
function request(engine,signals){
 const cfg=engine.cfg,now=Date.now(),rows=[];
 for(const signal of signals){
  const asset=engine.market.assets[signal.symbol];
  if(!asset)continue;
  const size=require('../runtime30/policy.js').availableSize(signal,asset,cfg,engine.account,engine.positions,engine.state.campaigns,engine.state.intents);
  if(size>0)rows.push({...signal,max_qty:size});
 }
 return {runtime_snapshot:true,now,optimizer_binding:cfg.quant?.optimizer?.enabled?binding(engine):undefined,config:cfg,signals:rows,account:{equity:engine.account.equity,cash:engine.account.cash,buying_power:engine.account.buying_power},positions:engine.positions,pending:engine.pending(),daily_pnl:Number(engine.account.equity)-Number(engine.state.dayEquity||engine.account.equity),drawdown_fraction:Math.max(0,1-Number(engine.account.equity)/Number(engine.state.peakEquity||engine.account.equity)),market:{assets:engine.market.assets,quotes:engine.market.quotes,bars:engine.market.bars,snapshots:engine.market.snapshots,micro_data:engine.market.microData||{},calendar:engine.market.calendar||[]}};
}
function spawnWorker(serialized,config={},action="worker"){
 const cwd=path.join(__dirname,'../quant');
 const args=['-m','harpoon_quant',action,'--model',process.env.HARPOON_QUANT_MODEL||config.calibrationFile||path.join(process.env.HARPOON_DATA||'/var/data','quant_calibration.json')];
 return new Promise(resolve=>{
  let done=false,stdout='',stderr='',stopReason=null;
  const end=result=>{if(done)return;done=true;clearTimeout(timer);resolve(result);};
  const child=spawn(config.python||process.env.HARPOON_QUANT_PYTHON||'python3',args,{cwd,stdio:['pipe','pipe','pipe'],env:{...process.env,OPENBLAS_NUM_THREADS:'1',OMP_NUM_THREADS:'1'}});
  const terminate=reason=>{if(done||stopReason)return;stopReason=reason;child.kill('SIGKILL');};
  const timer=setTimeout(()=>terminate('QUANT_WORKER_TIMEOUT'),config.timeoutMs||8000);
  child.on('error',()=>end({status:'BLOCKED',execution_allowed:false,selected:[],reason:'QUANT_WORKER_UNAVAILABLE'}));
  child.stdout.on('data',d=>{if(stopReason)return;stdout+=d;if(stdout.length>2e6)terminate('QUANT_OUTPUT_LIMIT');});
  child.stderr.on('data',d=>{stderr+=d;if(stderr.length>10000)stderr=stderr.slice(-10000);});
  child.on('close',()=>{if(stopReason){end(blocked(stopReason));return;}try{const result=JSON.parse(stdout);if(!Array.isArray(result.selected)||typeof result.execution_allowed!=='boolean')throw Error('schema');end(result);}catch{end({status:'BLOCKED',execution_allowed:false,selected:[],reason:'QUANT_OUTPUT_SCHEMA_OR_DEPENDENCY'});}});
  child.stdin.on('error',()=>{});child.stdin.end(serialized);
 });
}
function drainWorkers(){
 if(workerPool.running>=WORKER_LIMIT)return;
 const job=workerPool.queue.shift();if(!job)return;
 clearTimeout(job.timer);
 const remaining=job.deadline-monotonic.now();
 if(remaining<=0){workerPool.rejected++;job.resolve(blocked('QUANT_QUEUE_DEADLINE'));drainWorkers();return;}
 workerPool.running++;workerPool.maxObservedRunning=Math.max(workerPool.maxObservedRunning,workerPool.running);
 void spawnWorker(job.serialized,{...job.config,timeoutMs:Math.max(1,Math.floor(remaining))},job.action)
  .then(job.resolve,error=>job.resolve(blocked('QUANT_WORKER_ERROR:'+String(error))))
  .finally(()=>{workerPool.running--;workerPool.completed++;drainWorkers();});
}
function worker(input,config={},action='worker'){
 let serialized;
 try{serialized=JSON.stringify(input);}catch{return Promise.resolve(blocked('QUANT_INPUT_SERIALIZATION'));}
 if(typeof serialized!=='string'||Buffer.byteLength(serialized)>33554432)return Promise.resolve(blocked('QUANT_INPUT_LIMIT'));
 const budget=config.timeoutMs||8000;
 if(!Number.isFinite(budget)||budget<=0||budget>30000)return Promise.resolve(blocked('QUANT_TIMEOUT_BUDGET'));
 if(workerPool.queue.length>=QUEUE_LIMIT){workerPool.rejected++;return Promise.resolve(blocked('QUANT_QUEUE_CAPACITY'));}
 return new Promise(resolve=>{
  const priority=({worker:0,observe:1,metrics:2,context:3,optimize:4,'verify-gate':4})[action]??4;
  const job={serialized,config,action,resolve,priority,deadline:monotonic.now()+budget};
  job.timer=setTimeout(()=>{const index=workerPool.queue.indexOf(job);if(index>=0){workerPool.queue.splice(index,1);workerPool.rejected++;resolve(blocked('QUANT_QUEUE_DEADLINE'));}},budget);
  workerPool.queue.push(job);workerPool.queue.sort((a,b)=>a.priority-b.priority);drainWorkers();
 });
}
async function plan(engine,signals){return worker(request(engine,signals),engine.cfg.quant||{});}
module.exports={request,worker,plan};
module.exports.workerStatus=()=>({running:workerPool.running,queued:workerPool.queue.length,
 max_running:WORKER_LIMIT,max_queued:QUEUE_LIMIT,max_observed_running:workerPool.maxObservedRunning,
 completed:workerPool.completed,rejected:workerPool.rejected,timeout_includes_queue:true,
 position_management_uses_this_pool:false});
function observationInput(engine){
 const input=request(engine,[]),journal=engine.quantObservations;
 const symbols=[...new Set([...engine.cfg.universe.map(a=>a.symbol),...Object.keys(engine.market.assets)])]
  .filter(s=>['equity','etf','crypto','options'].includes(engine.market.assets[s]?.book||engine.cfg.universe.find(a=>a.symbol===s)?.book)).sort();
 const capacity=journal.maxSymbolsPerCapture,cursor=journal.view().cursor;
 const selected=Array.from({length:Math.min(capacity,symbols.length)},(_,i)=>symbols[(cursor+i)%symbols.length]);
 const needed=new Set(['SPY',...(engine.plugins?.benchmarkSymbols?.()||[]),...selected,
  ...selected.map(s=>engine.market.assets[s]?.underlying).filter(Boolean)]);
 input.market={...input.market,
  assets:Object.fromEntries(selected.map(s=>[s,engine.market.assets[s]||engine.cfg.universe.find(a=>a.symbol===s)])),
  quotes:Object.fromEntries([...needed].filter(s=>input.market.quotes[s]).map(s=>[s,input.market.quotes[s]])),
  bars:Object.fromEntries([...needed].filter(s=>input.market.bars[s]).map(s=>[s,input.market.bars[s]])),
  daily:Object.fromEntries([...needed].filter(s=>engine.market.daily?.[s]).map(s=>[s,engine.market.daily[s]])),
  minutes:Object.fromEntries([...needed].filter(s=>engine.market.minutes?.[s]).map(s=>[s,engine.market.minutes[s]])),
  snapshots:Object.fromEntries(selected.filter(s=>input.market.snapshots[s]).map(s=>[s,input.market.snapshots[s]])),
  micro_data:Object.fromEntries(selected.filter(s=>input.market.micro_data[s]).map(s=>[s,input.market.micro_data[s]]))};
 input.signals=selected.map(symbol=>({plugin:'observation-only',symbol,entry:input.market.quotes[symbol]?.ask,max_qty:0}));
 input.observation_coverage={registered_symbols:symbols,selected_symbols:selected,cursor,
  complete_registered_universe:selected.length===symbols.length,interval_ms:journal.intervalMs,
  selection_rule:'SORTED_ROTATION_WITHOUT_PRICE_OR_RETURN_SELECTION',executable_depth:null};
 // Copy before awaiting Python: streamed quotes cannot mutate an in-flight frame.
 return JSON.parse(JSON.stringify(input));
}
module.exports.observationInput=observationInput;
module.exports.observe=async engine=>{
 const input=observationInput(engine);
 if(Buffer.byteLength(JSON.stringify(input))>engine.quantObservations.maxFrameBytes*.9)
  throw Error('OBSERVATION_INPUT_BYTES_BOUND');
 const result=await worker(input,engine.cfg.quant||{},'observe');
 return engine.quantObservations.capture(input,result);
};
async function discover(engine){return require('./discovery.cjs').discover(engine);}
module.exports.discover=discover;

module.exports.context=engine=>worker(request(engine,[]),engine.cfg.quant||{},"context");
function binding(engine){
 const fs=require('node:fs'),crypto=require('node:crypto'),hash=x=>crypto.createHash('sha256').update(x).digest('hex');
 const cfg=engine.cfg,model=process.env.HARPOON_QUANT_MODEL||cfg.quant?.calibrationFile||'/var/data/quant_calibration.json';
 const sources=['../runtime30/policy.js','../runtime30/exits.js','../runtime30/plugins.js','../runtime30/coordinator.js',
  '../runtime30/net_accounting.js','../runtime30/net_ledger_archive.js','../runtime30/net_ledger_verify.js','../runtime30/cost_receipts.js',
  '../runtime30/quant_observations.js','../runtime30/operational_status.js',
  '../quant/harpoon_quant/core.py','../quant/harpoon_quant/bridge.py','../quant/harpoon_quant/performance.py',
  '../quant/harpoon_quant/economic_gate.py','../quant/harpoon_quant/optimization.py','../quant/harpoon_quant/recursive.py',
  '../quant/harpoon_quant/calibration.py','../quant/harpoon_quant/scalar_svr.py','../quant/harpoon_quant/support.py'];
 return {account_id:cfg.expected_account_id,legacy_research_head:engine.ultimateLab?.state.chain.at(-1)?.hash||'GENESIS',execution_hash:hash(sources.map(p=>fs.readFileSync(path.join(__dirname,p),'utf8')).join('\n')),forecast_hash:fs.existsSync(model)?hash(fs.readFileSync(model)):'MISSING',configuration_hash:hash(JSON.stringify({quant:cfg.quant?.config||{},exit:cfg.exit,profile:engine.state.exitProfile,fees:[cfg.slippageBps,cfg.cryptoFeeBps,cfg.optionsFeePerContract],stockFeed:cfg.stockFeed,optionFeed:cfg.optionFeed,quoteAgeMs:cfg.quoteAgeMs})),
  universe_hash:hash(JSON.stringify([cfg.universe,cfg.optionUnderlyings,cfg.enabledPlugins,engine.state.plugins])),
  risk_limits:{initial_equity:cfg.capitalLimit,base_quality_bps:cfg.quant?.config?.min_robust_return_bps||0,risk_fraction:cfg.riskFraction,open_risk_fraction:cfg.openRiskFraction,gross_fraction:cfg.totalExposure,asset_fraction:cfg.assetExposure,factor_fraction:cfg.factorExposure,max_positions:cfg.maxPositions,max_drawdown:cfg.maxDrawdown}};
}
module.exports.binding=binding;
module.exports.optimize=async engine=>{
 const input={config:engine.cfg,optimizer_binding:binding(engine),optimizer_asof:new Date().toISOString(),research_paused:engine.state.researchPaused,drawdown_fraction:Math.max(0,1-Number(engine.account.equity)/Number(engine.state.peakEquity||engine.account.equity))};
 input.legacy_research={registered_slots:engine.ultimateLab?.state.spent||0,runs:engine.state.research.runs};
 const result=await worker(input,{...engine.cfg.quant,timeoutMs:30000},'optimize');
 if(result.status==='WAIT_DATA'&&engine.quantObservations){
  return {...result,internal_observations:engine.quantObservations.view(),
   missing_evidence:'FUNDED_POLICY_PATHS_AND_REPRODUCIBLE_PREDICTORS',
   scope:'Prospective sampled frames are collected automatically; they are not completed executable opportunity paths.'};
 }
 return result;
};
module.exports.verifyEconomicGate=async engine=>{
 const cfg=engine.cfg.quant?.operational?.economicGate;
 const empty={status:'WAIT_ECONOMIC_EVIDENCE',dictamen:'VENTAJA_NO_DEMOSTRADA',
  execution_allowed:false,liveApproved:false,recomputed_identically:false,report_integrity_verified:false};
 if(!cfg)return {...empty,reason:'PREREGISTERED_NET_COMPARISON_ARTIFACTS_REQUIRED'};
 try{
  const fs=require('node:fs/promises'),input={artifact_root:cfg.artifactRoot};
  for(const [field,file] of [['report',cfg.reportFile],['protocol',cfg.protocolFile],['evidence',cfg.evidenceFile]]){
   if(typeof file!=='string'||!file)throw Error('ECONOMIC_GATE_PATH_REQUIRED:'+field);
   const stat=await fs.stat(file);
   if(!stat.isFile()||stat.size>16777216)throw Error('ECONOMIC_GATE_FILE_BOUND:'+field);
   const bytes=await fs.readFile(file);
   if(bytes.length>16777216)throw Error('ECONOMIC_GATE_FILE_BOUND:'+field);
   input[field]=JSON.parse(bytes.toString('utf8'));
  }
  const result=await worker(input,{...engine.cfg.quant,timeoutMs:30000},'verify-gate');
  const stable=require('../runtime30/ultimate_contracts.js').digest;
  const currentBinding=binding(engine),registeredBinding=input.protocol.runtime_binding;
  const bindingMatches=registeredBinding!==undefined&&stable(registeredBinding)===stable(currentBinding);
  return {...result,status:result.recomputed_identically===true?'VERIFIED_LOCAL_RECOMPUTATION':'BLOCKED',
   runtime_binding_matches:bindingMatches,runtime_binding_hash:stable(currentBinding),
   observed_at:Date.now(),execution_allowed:false,liveApproved:false};
 }catch(error){return {...empty,status:'BLOCKED',reason:String(error),observed_at:Date.now()};}
};
const archivedPerformanceCache=new WeakMap();
module.exports.performance=async engine=>{
 if(engine.netLedger){
  const ledger=engine.netLedger.view(),archived=Number(ledger.archive?.segments)>0;
  let input;
  if(archived&&typeof engine.netLedger.performanceInputWithArchive==='function'){
   const now=Date.now(),prior=archivedPerformanceCache.get(engine),cfg=engine.cfg.quant?.accounting||{};
   const interval=cfg.performanceArchiveRefreshMs??900000,limit=cfg.performanceArchiveMaxObservations??100000;
   if(!Number.isSafeInteger(interval)||interval<60000||!Number.isSafeInteger(limit)||limit<3||limit>100000)
    throw Error('ARCHIVED_PERFORMANCE_BUDGET_INVALID');
   const closed=ledger.closedEconomic||{};
   const current=ledger.persisted&&ledger.reconciled&&closed.completeReturns===true&&
    closed.comparablePeriodGrid===true&&closed.observationCount>=3&&!ledger.economicRestatementRequired&&
    !['STALE','ERROR','BLOCKED'].includes(ledger.status)&&ledger.archive.verified===true&&
    !ledger.insolvency?.account&&!ledger.insolvency?.economic;
   if(!current)archivedPerformanceCache.delete(engine);
   else if(prior&&now>=prior.at&&now-prior.at<interval&&prior.head===ledger.archive.head&&
    prior.accountId===ledger.accountId&&prior.policyHash===ledger.policyHash&&
    prior.costCoverageHash===ledger.costCoverage?.sourceHash&&prior.economicPrefixHash===closed.evidenceHash&&
    prior.brokerCoverage===JSON.stringify(closed.brokerAccruals??null)){
    return {...prior.result,calculated_at:prior.at,cached:true,cache_age_ms:now-prior.at,
     current_accounting:ledger.accounting,
     scope:'Statistics through the recorded calculation time; current accounting is reported separately.'};
   }
   input=current?await engine.netLedger.performanceInputWithArchive(now,limit):null;
  }else input=engine.netLedger.performanceInput();
  if(!input)return {status:'WAIT_RECONCILED_PERFORMANCE',source:'INTERNAL_ACCOUNT_LEDGER',
   observations:ledger.observations_count??ledger.observations?.length??null,accounting:ledger.accounting,blockers:ledger.blockers,
   last:ledger.lastSuccess||null,cashflows_reconciled:ledger.reconciled,
   scope:'Continuous broker account accounting; missing costs or comparable returns remain explicit.'};
  const result=await worker(input,engine.cfg.quant||{},'metrics');
  const output={...result,source:'INTERNAL_ACCOUNT_LEDGER',accounting:ledger.accounting,
   ledger_evidence:ledger.evidence,annualization_authorized:false,calculated_at:Date.now(),cached:false};
  if(archived&&result.status==='PERFORMANCE_REPORT')archivedPerformanceCache.set(engine,{at:Date.now(),head:ledger.archive.head,
   accountId:ledger.accountId,policyHash:ledger.policyHash,
   costCoverageHash:ledger.costCoverage?.sourceHash,economicPrefixHash:ledger.closedEconomic?.evidenceHash,
   brokerCoverage:JSON.stringify(ledger.closedEconomic?.brokerAccruals??null),result:output});
  return output;
 }
 const fs=require('node:fs'),cfg=engine.cfg.quant?.optimizer||{},key=engine.key+'-quant-nav';
 const rows=await engine.store.get(key)||[];const at=new Date().toISOString(),day=at.slice(0,10);
 if(!Number.isFinite(Number(engine.account.equity)))return {status:'WAIT_ACCOUNT',observations:rows.length};
 const observation={at,equity:Number(engine.account.equity),day,cashflows_reconciled:false};
 if(rows.at(-1)?.day===day)rows[rows.length-1]=observation;else if(rows.length<2000)rows.push(observation);else throw Error('NAV observation budget requires explicit archive');
 await engine.store.put(key,rows);
 if(!cfg.performanceFile||!fs.existsSync(cfg.performanceFile))return {status:'WAIT_RECONCILED_PERFORMANCE',observations:rows.length,last:observation,scope:'Observed broker NAV; cashflows and all-in fees not reconciled, no return ratio certified.'};
 if(fs.statSync(cfg.performanceFile).size>32*1024*1024)throw Error('Performance file exceeds data bound');
 const input=JSON.parse(fs.readFileSync(cfg.performanceFile,'utf8'));
 if(input.origin!=='OBSERVED'||input.cashflows_confirmed!==true||input.net_costs_confirmed!==true)return {status:'UNRECONCILED_PERFORMANCE_FILE',observations:rows.length};
 return worker(input,engine.cfg.quant||{},'metrics');
};
