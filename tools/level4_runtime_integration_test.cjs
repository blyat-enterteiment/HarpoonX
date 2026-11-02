'use strict';
// Synthetic engineering tests. No broker, credentials or external orders.
const test=require('node:test'),assert=require('node:assert/strict');
const bridge=require('../runtime/quant_bridge.cjs');
const {server}=require('../runtime30/server.js');

function metrics(){return {
 origin:'SYNTHETIC_ENGINEERING_ONLY',return_basis:'NET_FLOW_ADJUSTED',initial_equity:20000,
 initial_at:'2026-10-15T13:30:00+00:00',times:['2026-10-15T13:31:00+00:00','2026-10-15T13:32:00+00:00'],
 returns:[-3/20000,0],sampling:'FIXED_INTERVAL_OBSERVATIONS',declared_interval_ms:60000,
 periods_per_year:1,annualization_authorized:false,risk_free_annual:0,target_annual:0
};}
function fixture(){
 const counters={materializations:0,legacy:0,limit:null};
 const view={persisted:true,reconciled:true,economicComplete:true,returnComplete:true,
  status:'OBSERVED_ECONOMIC_NET',archive:{segments:1,verified:true,head:'SEGMENT_1'},
  accountId:'SYNTHETIC_ACCOUNT',policyHash:'POLICY',costCoverage:{sourceHash:'COST_1'},
  insolvency:{account:false,economic:false},accounting:{economicNetPnlUsd:-3},
  closedEconomic:{completeReturns:true,comparablePeriodGrid:true,observationCount:3,evidenceHash:'PREFIX_3'},
  evidence:{executionNature:'SYNTHETIC_ENGINEERING_ONLY'},observations_count:3};
 const engine={cfg:{quant:{timeoutMs:8000}},netLedger:{
  view:()=>structuredClone(view),
  performanceInput:()=>{counters.legacy++;return metrics();},
  performanceInputWithArchive:async(now,limit)=>{counters.materializations++;counters.limit=limit;return metrics();}
 }};
 return {engine,view,counters};
}

test('archived metrics materialize complete history once and label reused statistics with original calculation time',async()=>{
 const {engine,view,counters}=fixture();
 const a=await bridge.performance(engine);
 assert.equal(a.status,'PERFORMANCE_REPORT');assert.equal(a.cached,false);
 assert.equal(a.performance.origin,'SYNTHETIC_ENGINEERING_ONLY');
 assert(Math.abs(a.performance.net_profit_usd_on_adjusted_initial_capital+3)<1e-7);
 view.accounting.economicNetPnlUsd=-4;
 const b=await bridge.performance(engine);
 assert.equal(b.cached,true);assert.equal(b.current_accounting.economicNetPnlUsd,-4);
 assert.equal(b.accounting.economicNetPnlUsd,-3);
 assert.equal(counters.materializations,1);assert.equal(counters.legacy,0);
 assert.equal(counters.limit,100000);assert(b.cache_age_ms>=0);
 assert.equal(b.execution_allowed,false);assert.equal(b.annualization_authorized,false);
});

test('missing costs and insolvency suppress archived performance without reading segments or starting inference',async()=>{
 for(const mutate of [v=>v.closedEconomic.completeReturns=false,v=>v.closedEconomic.comparablePeriodGrid=false,v=>v.closedEconomic.observationCount=2,v=>v.economicRestatementRequired=true,v=>v.reconciled=false,
  v=>v.persisted=false,v=>v.archive.verified=false,v=>v.status='STALE',
  v=>v.insolvency.account=true,v=>v.insolvency.economic=true]){
  const {engine,view,counters}=fixture();mutate(view);
  assert.equal((await bridge.performance(engine)).status,'WAIT_RECONCILED_PERFORMANCE');
  assert.equal(counters.materializations,0);assert.equal(counters.legacy,0);
 }
});

test('a closed cost-covered prefix remains measurable when the latest account mark is not yet covered',async()=>{
 const {engine,view,counters}=fixture();
 view.economicComplete=false;view.returnComplete=false;view.accounting.economicNetPnlUsd=null;
 view.closedEconomic.latestUncoveredAt=Date.now();
 const result=await bridge.performance(engine);
 assert.equal(result.status,'PERFORMANCE_REPORT');assert.equal(result.accounting.economicNetPnlUsd,null);
 assert.equal(result.performance.origin,'SYNTHETIC_ENGINEERING_ONLY');assert.equal(counters.materializations,1);
});

test('a reconciliation failure invalidates previously cached statistics before the next safe refresh',async()=>{
 const {engine,view,counters}=fixture();await bridge.performance(engine);
 view.status='ERROR';assert.equal((await bridge.performance(engine)).status,'WAIT_RECONCILED_PERFORMANCE');
 view.status='OBSERVED_ECONOMIC_NET';
 assert.equal((await bridge.performance(engine)).cached,false);
 assert.equal(counters.materializations,2);
});

test('archive head, account, policy and cost changes force recomputation instead of cross-binding cache reuse',async()=>{
 const {engine,view,counters}=fixture();await bridge.performance(engine);
 for(const mutate of [v=>v.archive.head='SEGMENT_2',v=>v.accountId='OTHER_SYNTHETIC_ACCOUNT',
  v=>v.policyHash='POLICY_2',v=>v.costCoverage.sourceHash='COST_2',v=>v.closedEconomic.evidenceHash='PREFIX_4',
  v=>v.closedEconomic.brokerAccruals={verified:true,documentSha256:'DOCUMENT_CHANGED'}]){
  mutate(view);assert.equal((await bridge.performance(engine)).cached,false);
 }
 assert.equal(counters.materializations,7);
});

test('archive refresh interval expiry causes a new calculation with bounded observation count',async()=>{
 const {engine,counters}=fixture();engine.cfg.quant.accounting={performanceArchiveRefreshMs:60000,performanceArchiveMaxObservations:250};
 const original=Date.now;let clock=original();
 try{Date.now=()=>clock;await bridge.performance(engine);clock+=60000;
  assert.equal((await bridge.performance(engine)).cached,false);
  assert.equal(counters.materializations,2);assert.equal(counters.limit,250);
 }finally{Date.now=original;}
});

test('invalid archive memory or refresh budgets fail before materialization',async()=>{
 for(const cfg of [{performanceArchiveRefreshMs:1000},{performanceArchiveMaxObservations:100001},
  {performanceArchiveMaxObservations:2},{performanceArchiveRefreshMs:60000.5}]){
  const {engine,counters}=fixture();engine.cfg.quant.accounting=cfg;
  await assert.rejects(bridge.performance(engine),/ARCHIVED_PERFORMANCE_BUDGET_INVALID/);
  assert.equal(counters.materializations,0);
 }
});

test('without an archive the existing accounting path remains the source of metrics',async()=>{
 const {engine,view,counters}=fixture();view.archive.segments=0;
 assert.equal((await bridge.performance(engine)).status,'PERFORMANCE_REPORT');
 assert.equal(counters.legacy,1);assert.equal(counters.materializations,0);
});

function httpFixture(){
 const calls=[];const password='synthetic-password-with-more-than-32-characters';
 const engine={netLedger:{exportHistory:async(offset,limit)=>{
  calls.push({offset,limit});
  if(!Number.isSafeInteger(offset)||offset<0||!Number.isSafeInteger(limit)||limit<1||limit>5000)throw Error('EXPORT_BOUNDS');
  return {schema:'HARPOON_NET_HISTORY_PAGE_1',offset,limit,records:[],execution_allowed:false};
 }}};
 const app=server(engine,password,'<html></html>','https://panel.example');
 const auth={authorization:'Basic '+Buffer.from('trader:'+password).toString('base64')};
 const call=(url,headers=auth,method='GET')=>new Promise((resolve,reject)=>{
  const req={method,url,headers},res={statusCode:200,setHeader(){},end(body){resolve({status:this.statusCode,body:JSON.parse(body)});}};
  try{app.emit('request',req,res);}catch(error){reject(error);}
 });
 return {app,call,calls,auth};
}

test('account history export requires authentication and same-origin context before touching account data',async()=>{
 const f=httpFixture();
 try{
  assert.equal((await f.call('/v1/accounting/history',{})).status,401);
  assert.equal((await f.call('/v1/accounting/history',{...f.auth,origin:'https://other.example'})).status,403);
  assert.equal((await f.call('/v1/accounting/history',{...f.auth,'sec-fetch-site':'cross-site'})).status,403);
  assert.equal(f.calls.length,0);
 }finally{f.app.close();}
});

test('account export carries exact pagination arguments and does not invoke the broker',async()=>{
 const f=httpFixture();
 try{
  const result=await f.call('/v1/accounting/history?offset=200&limit=100',{...f.auth,origin:'https://panel.example'});
  assert.equal(result.status,200);assert.deepEqual(f.calls,[{offset:200,limit:100}]);
  assert.equal(result.body.execution_allowed,false);
  assert.equal((await f.call('/v1/accounting/history')).status,200);
  assert.deepEqual(f.calls.at(-1),{offset:0,limit:1000});
 }finally{f.app.close();}
});

test('malformed pagination is an explicit 422 with no execution authority',async()=>{
 const f=httpFixture();
 try{for(const query of ['offset=-1','offset=abc','limit=5001','limit=0','limit=1.5']){
  const result=await f.call('/v1/accounting/history?'+query);
  assert.equal(result.status,422);assert.match(result.body.error,/EXPORT_BOUNDS/);
  assert.equal(result.body.execution_allowed,false);
 }}finally{f.app.close();}
});

test('history export has no mutation route',async()=>{
 const f=httpFixture();
 try{assert.equal((await f.call('/v1/accounting/history',f.auth,'POST')).status,404);assert.equal(f.calls.length,0);}
 finally{f.app.close();}
});
