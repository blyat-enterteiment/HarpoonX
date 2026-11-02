'use strict';
// All brokers/data in this suite are synthetic engineering fixtures.
const test=require('node:test'),assert=require('node:assert/strict');
const fs=require('node:fs'),os=require('node:os'),path=require('node:path');
const {ready,signal,prepare,config,MemoryStore,FakeBroker}=require('./xxx_fixtures.cjs');
const {histories}=require('./quant_discovery_fixtures.cjs');
const {Coordinator}=require('../runtime30/coordinator.js');
const {QuantObservationJournal}=require('../runtime30/quant_observations.js');
const {entryOperationalFailures,operationalCapabilities}=require('../runtime30/operational_status.js');
const {server}=require('../runtime30/server.js');
const {digest}=require('../runtime30/ultimate_contracts.js');
const bridge=require('../runtime/quant_bridge.cjs');

async function prepared(){
 const x=await ready(); x.e.cfg.quant={enabled:true,calibrationFile:'/__missing_model_for_observation__.json'};
 const h=histories();x.e.market.calendar=h.calendar;
 for(const s of ['AAPL','SPY']){
  x.e.market.bars[s]=h.bars;x.e.market.quotes[s]={bid:100,ask:100.01,at:Date.now(),received:Date.now()};
 }
 return x;
}
function receipt(input,accepted=false){
 return {schema:'HARPOON_RUNTIME_OBSERVATION_1',status:accepted?'OBSERVATION_CAPTURED':'WAIT_FEATURE_DATA',
  asof:new Date(input.now).toISOString(),observations:accepted?input.signals.map(s=>({id:s.plugin+'|'+s.symbol,
   asof:new Date(input.now).toISOString(),known_at:new Date(input.now).toISOString(),features:Array(8).fill(0)})):[],
  rejected:accepted?{}:Object.fromEntries(input.signals.map(s=>[s.plugin+'|'+s.symbol,'SYNTHETIC_MISSING_DATA'])),
  selected:[],execution_allowed:false,liveApproved:false};
}
async function mocked(name,value,run){const old=bridge[name];bridge[name]=value;try{return await run();}finally{bridge[name]=old;}}

test('actual observation worker captures causal features with no calibration model and no order authority',async()=>{
 const {e,api}=await prepared();const result=await bridge.observe(e);
 assert.equal(result.persisted,true);assert.equal(result.latest.accepted,2);
 const out=await e.quantObservations.exportFrames();
 assert.equal(out.frames.length,1);assert.equal(out.frames[0].observation.observations[0].features.length,8);
 assert.equal(out.frames[0].observation.execution_allowed,false);
 assert.equal(out.frames[0].sampled_execution_depth,null);
 assert.equal(out.frames[0].financial_acceptance_allowed,false);
 assert.equal(api.posts().length,0);assert.equal(out.frames[0].runtime_input.signals[0].max_qty,0);
});

test('observation input is frozen before asynchronous inference while live quotes continue changing',async()=>{
 const {e}=await prepared();const before=e.market.quotes.AAPL.ask;
 const pending=bridge.observe(e);e.market.quotes.AAPL.ask=999;
 await pending;const out=await e.quantObservations.exportFrames();
 assert.equal(out.frames[0].runtime_input.market.quotes.AAPL.ask,before);
});

test('missing feature data is persisted with exhaustive exclusions instead of fabricated labels or zeros',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};
 const r=await bridge.observe(e);assert.equal(r.status,'WAIT_FEATURE_DATA');
 const out=await e.quantObservations.exportFrames(),o=out.frames[0].observation;
 assert.equal(o.observations.length,0);assert(Object.keys(o.rejected).length>0);
 assert.equal(o.target_return,undefined);assert.equal(r.complete_opportunity_paths,false);
});

test('observation persistence failure holds new risk without stopping existing deterministic exits',async()=>{
 const {e,api,store}=await ready();prepare(e,signal());await e.entries('equity');await e.reconcile();
 e.cfg.quant={enabled:true};
 const put=store.put.bind(store);store.put=async(k,v)=>{if(k===e.key+'-quant-observations')throw Error('SYNTHETIC_INDEX_WRITE_FAILURE');return put(k,v);};
 await assert.rejects(e.captureQuantObservations(),/INDEX_WRITE_FAILURE/);
 const buys=api.posts().filter(x=>x.body.side==='buy').length;
 await e.entries('crypto');assert.equal(api.posts().filter(x=>x.body.side==='buy').length,buys);
 assert(entryOperationalFailures(e).includes('OBSERVATION_PERSISTENCE_OR_CONTRACT'));
 e.market.quotes.AAPL={bid:110,ask:110.01,at:Date.now(),received:Date.now()};
 await e.manage();assert.equal(api.posts().at(-1).body.side,'sell');
});

test('failed index commit never advances cursor and is recoverable from the unchanged control',async()=>{
 const {e,store}=await prepared();const input=bridge.observationInput(e),r=receipt(input);
 const put=store.put.bind(store);let fail=true;
 store.put=async(k,v)=>{if(k===e.key+'-quant-observations'&&fail)throw Error('INDEX_FAILED');return put(k,v);};
 await assert.rejects(e.quantObservations.capture(input,r),/INDEX_FAILED/);
 assert.equal(e.quantObservations.view().frames,0);fail=false;
 await e.quantObservations.capture(input,r);assert.equal(e.quantObservations.view().frames,1);
 const restored=new QuantObservationJournal(store,e.key+'-quant-observations',e.cfg.expected_account_id);
 await restored.load();assert.equal(restored.view().frames,1);
});

test('changed index, account identity and compressed frame content are rejected on load or export',async()=>{
 const {e,store}=await prepared();const input=bridge.observationInput(e);
 await e.quantObservations.capture(input,receipt(input));
 const key=e.key+'-quant-observations',saved=await store.get(key);
 const other=new QuantObservationJournal(store,key,'OTHER_ACCOUNT');await assert.rejects(other.load(),/BINDING/);
 const tampered=structuredClone(saved);tampered.frames[0].at++;
 await store.put(key,tampered);const changed=new QuantObservationJournal(store,key,e.cfg.expected_account_id);
 await assert.rejects(changed.load(),/INTEGRITY/);await store.put(key,saved);
 const frameKey=saved.frames[0].frame_key,packed=await store.get(frameKey);packed.data=Buffer.from('CORRUPTED').toString('base64');
 await store.put(frameKey,packed);await assert.rejects(e.quantObservations.exportFrames());
});

test('observation validator rejects incomplete coverage, future features and inference authority',async()=>{
 for(const mutate of [r=>{r.rejected={};},r=>{r.execution_allowed=true;},r=>{r.liveApproved=true;},
  r=>{r.observations[0].known_at='invalid';},r=>{r.observations[0].known_at=new Date(Date.now()+1).toISOString();}]){
  const {e}=await prepared(),input=bridge.observationInput(e),r=receipt(input,true);
  if(mutate.toString().includes('rejected=')){r.observations=[];r.rejected={};}
  mutate(r);await assert.rejects(e.quantObservations.capture(input,r),/CONTRACT/);
 }
});

test('retention and clock bounds halt collection without deleting previous evidence',async()=>{
 const store=new MemoryStore(),j=new QuantObservationJournal(store,'Q','ACCOUNT',{maxFrames:2,maxArchives:0});await j.load();
 const original=Date.now;let now=original();
 const make=()=>({now,config:{expected_account_id:'ACCOUNT'},signals:[],market:{calendar:[]}});
 try{Date.now=()=>now;let input=make();await j.capture(input,receipt(input));
  await assert.rejects(j.capture(input,receipt(input)),/NON_INCREASING/);
  now+=60000;input=make();await j.capture(input,receipt(input));
  now+=60000;input=make();await assert.rejects(j.capture(input,receipt(input)),/ARCHIVE_REQUIRED/);
  assert.equal((await j.exportFrames()).frames.length,2);
 }finally{Date.now=original;}
});

test('oversized observation frames and invalid export bounds are refused before silently truncating data',async()=>{
 const store=new MemoryStore(),j=new QuantObservationJournal(store,'Q','ACCOUNT',{maxFrameBytes:1024});await j.load();
 const input={now:Date.now(),config:{expected_account_id:'ACCOUNT'},signals:[],market:{calendar:[],padding:'x'.repeat(2000)}};
 await assert.rejects(j.capture(input,receipt(input)),/BYTES_BOUND/);
 await assert.rejects(j.exportFrames(0,101),/EXPORT_LIMIT/);assert.equal(j.view().frames,0);
});

test('economic performance consumes internal ledger evidence and keeps missing costs explicit',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true,optimizer:{performanceFile:'/__unused_external_performance__.json'}};
 const r=await bridge.performance(e);
 assert.equal(r.source,'INTERNAL_ACCOUNT_LEDGER');assert.equal(r.status,'WAIT_RECONCILED_PERFORMANCE');
 assert.equal(r.accounting.economicNetPnlUsd,null);assert.equal(await e.store.get(e.key+'-quant-nav'),null);
});

test('required net-account reconciliation blocks entries with an operational reason, not a fabricated zero cost',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true,operational:{requireAccountLedgerForEntries:true}};prepare(e,signal());
 await e.entries('equity');assert.equal(api.posts().length,0);
 assert(entryOperationalFailures(e).includes('ACCOUNT_LEDGER_NOT_RECONCILED'));
 const report=operationalCapabilities(e);assert.equal(report.state,'HALT_NEW_RISK');
 assert.equal(report.financial_profitability_demonstrated,false);
});

test('a new operational hold during numerical planning is rechecked under the order mutex',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true};const s=signal();prepare(e,s);
 await mocked('plan',async()=>{e.quantObservationError='INJECTED_TRACE_FAILURE';return {execution_allowed:true,selected:[{id:s.plugin+'|'+s.symbol,quantity:1}]};},()=>e.entries('equity'));
 assert.equal(api.posts().length,0);assert(e.state.events.some(x=>x.reason==='OPERATIONAL_VALIDATORS'));
});

test('quant heartbeat wires accounting and observations even when optimizer and model are absent',async()=>{
 const cfg=config();cfg.quant={enabled:true,calibrationFile:'/__missing__.json'};
 const e=new Coordinator(new MemoryStore(),new FakeBroker(),cfg);await e.initialize(true);
 const names=e.scheduler.lanes.map(x=>x.name);
 for(const id of ['net-account-ledger','quant-prospective-observations','quant-performance','quant-economic-evidence'])assert(names.includes(id));
 assert(!names.includes('quant-recursive-calibration'));
});

test('a healthy HTTP process cannot claim operational or economic readiness from a boolean report',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};e.quantEconomicGate={dictamen:'CANDIDATO_PARA_VALIDACION_FORWARD',report_integrity_verified:false};
 const report=operationalCapabilities(e);
 assert.equal(report.operational_ready,false);assert.equal(report.full_autonomous_economic_cycle_verified,false);
 assert.equal(report.checks.find(x=>x.id==='net_economic_gate').status,'NOT_PROVEN');
});

test('economic evidence verification blocks missing or forged files and never returns execution authority',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};
 assert.equal((await bridge.verifyEconomicGate(e)).status,'WAIT_ECONOMIC_EVIDENCE');
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'harpoon-gate-input-'));
 try{
  const file=path.join(dir,'forged.json');fs.writeFileSync(file,JSON.stringify({dictamen:'CANDIDATO_PARA_VALIDACION_FORWARD',execution_allowed:true}));
  e.cfg.quant.operational={economicGate:{protocolFile:file,reportFile:file,evidenceFile:file,artifactRoot:dir}};
  const r=await bridge.verifyEconomicGate(e);assert.equal(r.status,'BLOCKED');
  assert.equal(r.execution_allowed,false);assert.equal(r.liveApproved,false);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});

test('operational HTTP endpoints require authentication and expose current blockers',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};const password='synthetic-password-with-more-than-32-characters';
 const app=server(e,password,'<html></html>');
 async function call(url,authenticated=true){
  return new Promise((resolve,reject)=>{
   const req={method:'GET',url,headers:authenticated?{authorization:'Basic '+Buffer.from('trader:'+password).toString('base64')}:{}};
   const res={statusCode:200,setHeader(){},end(body){resolve({status:this.statusCode,body:JSON.parse(body)});}};
   try{app.emit('request',req,res);}catch(error){reject(error);}
  });
 }
 try{
  assert.equal((await call('/v1/operational',false)).status,401);
  const readiness=await call('/operational-readyz');assert.equal(readiness.status,503);
  assert.equal(readiness.body.operational_ready,false);
  const invalid=await call('/v1/quant/observations?limit=101');assert.equal(invalid.status,422);
 }finally{app.close();}
});

test('observation index seal remains stable across object key ordering in durable storage',async()=>{
 const {e,store}=await prepared(),input=bridge.observationInput(e);await e.quantObservations.capture(input,receipt(input));
 const key=e.key+'-quant-observations',old=await store.get(key),{integrity_hash,...body}=old;
 const reorder=x=>Array.isArray(x)?x.map(reorder):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).reverse().map(k=>[k,reorder(x[k])])):x;
 assert.equal(digest(reorder(body)),integrity_hash);await store.put(key,reorder(old));
 const restored=new QuantObservationJournal(store,key,e.cfg.expected_account_id);await restored.load();
 assert.equal(restored.view().frames,1);
});

test('readiness becomes false for paused, stopping, halted and broker-blocked engines even with valid data',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};
 e.netLedger.view=()=>({status:'OBSERVED_ECONOMIC_NET',reconciled:true,economicComplete:true,returnComplete:true,
  lastSuccess:Date.now(),baseline:{at:Date.now()},blockers:[]});
 e.quantObservations.view=()=>({status:'OBSERVATION_CAPTURED',persisted:true,lastSuccess:Date.now()});
 e.quantLastPlan={status:'RESEARCH_ONLY',engine:'HARPOON_QUANT_1',origin:'OBSERVED',research_only:false,
  reason:'CONDITIONAL_MODEL_ALLOCATION',execution_allowed:true,model_hash:'a'.repeat(64),completed_at:Date.now()};
 assert.equal(operationalCapabilities(e).operational_ready,true);
 for(const [target,key,value] of [[e.state,'paused',true],[e,'stopping',true],[e.state,'halt','LIMIT'],[e.account,'trading_blocked',true]]){
  const old=target[key];target[key]=value;
  assert.equal(operationalCapabilities(e).operational_ready,false,key);
  target[key]=old;
 }
 e.quantLastPlan.origin='SYNTHETIC_ENGINEERING_ONLY';
 assert.equal(operationalCapabilities(e).operational_ready,false);
 e.quantLastPlan.origin='OBSERVED';e.quantLastPlan.reason='NO_VALUABLE_CANDIDATES';e.quantLastPlan.execution_allowed=false;
 assert.equal(operationalCapabilities(e).operational_ready,true,'a validated abstention is operational, not positive profit');
 e.netLedger.view=()=>({status:'OBSERVED_ECONOMIC_NET',reconciled:true,baseline:{at:Date.now()},insolvency:{account:false,economic:true}});
 assert(entryOperationalFailures(e).includes('INSOLVENCY_OBSERVED_NO_CAPITAL_RESET'));
 assert.equal(operationalCapabilities(e).operational_ready,false);
});

test('a gate result is not bound to the running engine by verdict and booleans alone',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};
 e.quantEconomicGate={dictamen:'CANDIDATO_PARA_VALIDACION_FORWARD',recomputed_identically:true,
  report_integrity_verified:true,observed_at:Date.now(),runtime_binding_matches:false};
 assert.equal(operationalCapabilities(e).net_candidate_bound_to_runtime,false);
 e.quantEconomicGate.runtime_binding_matches=true;e.quantEconomicGate.observed_at=Date.now()-900001;
 assert.equal(operationalCapabilities(e).net_candidate_bound_to_runtime,false);
 assert.equal(operationalCapabilities(e).full_autonomous_economic_cycle_verified,false);
});

test('numerical subprocess budget bounds concurrency, queued work and total wait without broker authority',async()=>{
 const requests=Array.from({length:12},()=>bridge.worker({}, {calibrationFile:'/__missing__.json',timeoutMs:250}));
 const peak=bridge.workerStatus();assert.equal(peak.running,1);assert.equal(peak.queued,8);
 const results=await Promise.all(requests);await new Promise(resolve=>setImmediate(resolve));
 assert(results.every(r=>r.execution_allowed===false&&r.selected.length===0));
 assert(results.some(r=>r.reason==='QUANT_QUEUE_CAPACITY'));
 assert(results.some(r=>r.reason==='QUANT_QUEUE_DEADLINE'));
 const end=bridge.workerStatus();assert.equal(end.max_observed_running,1);assert.equal(end.queued,0);assert.equal(end.running,0);
 assert.equal(end.position_management_uses_this_pool,false);
});
