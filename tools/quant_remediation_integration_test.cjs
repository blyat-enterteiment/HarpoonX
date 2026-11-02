'use strict';
// Synthetic engineering integration; FakeBroker only, never external orders.
const test = require('node:test');
const assert = require('node:assert/strict');
const {ready, signal, prepare, config, MemoryStore, FakeBroker} = require('./xxx_fixtures.cjs');
const {Coordinator} = require('../runtime30/coordinator.js');
const {digest} = require('../runtime30/ultimate_contracts.js');
const bridge = require('../runtime/quant_bridge.cjs');
const {registry} = require('../runtime/discovery.cjs');

function receipt(health='READY') {
 const at=Date.now(),snapshot={started_at:at,completed_at:at,sources:{},candidates:[
  {symbol:'AAPL',state:'READY',reason:null},
  {symbol:'SPY',state:'EXCLUDED',reason:'SYNTHETIC_METADATA_UNAVAILABLE'},
 ]};
 return {status:health==='BLOCKED'?'BLOCKED':'OBSERVED_DISCOVERY',health,
  reason:'SYNTHETIC_ENGINEERING_CONTRACT',at,snapshot_id:digest(snapshot),snapshot,
  added:[],removed:[],ready_symbols:health==='READY'?['AAPL']:[],pending_symbols:[],
  rejected:{SPY:'SYNTHETIC_METADATA_UNAVAILABLE'}};
}
async function mocked(name, fn, run) {
 const old=bridge[name];bridge[name]=fn;
 try{return await run();}finally{bridge[name]=old;}
}

test('catalog verification does not mutate static configuration or break a journal-bound restart',async()=>{
 const cfg=config(),original=JSON.stringify(cfg),store=new MemoryStore(),api=new FakeBroker();
 const e=new Coordinator(store,api,cfg);await e.initialize(true);await e.market.catalog();
 assert.equal(JSON.stringify(e.cfg),original);
 assert.equal(e.market.assets.AAPL.tradable,true,'catalog state is verified independently of configuration');
 const next=new Coordinator(store,api,e.cfg);await next.initialize();
 assert.equal(next.state.accountId,e.state.accountId);
});

test('discovery snapshot is durable, complete and reports usable data separately from scheduler ALIVE',async()=>{
 const {e,store}=await ready();e.cfg.quant={enabled:true,discovery:true};
 const r=receipt();
 await mocked('discover',async()=>r,()=>e.discoverStocks());
 const saved=await store.get(e.key+'-discovery-snapshot-'+r.snapshot_id);
 assert.deepEqual(saved.snapshot,r.snapshot);assert.equal(saved.accountId,e.cfg.expected_account_id);
 assert.equal(e.quantDiscovery.persisted,true);assert.equal(e.discoveryHold,false);
 const component=e.view().health.components.find(x=>x.id==='stock-etf-discovery-data');
 assert.equal(component.state,'READY');assert.deepEqual(component.readySymbols,['AAPL']);
});

test('blocked discovery is visible as ERROR and does not freeze unrelated engines after durable exclusion',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true,discovery:true};
 e.scheduler.add('discovery-test',900000,()=>e.discoverStocks());
 await mocked('discover',async()=>receipt('BLOCKED'),()=>e.scheduler.once(e.scheduler.lanes.at(-1)));
 assert.equal(e.scheduler.view().at(-1).health,'ERROR');
 assert.equal(e.quantDiscovery.health,'BLOCKED');assert.equal(e.quantDiscovery.persisted,true);
 assert.equal(e.discoveryHold,false,'a recorded candidate/data rejection does not freeze every book');
});

test('snapshot persistence failure holds new entries but existing position exits remain independent',async()=>{
 const {e,api,store}=await ready(),s=signal();prepare(e,s);
 await e.entries('equity');await e.reconcile();
 e.cfg.quant={enabled:true,discovery:true};
 const originalPut=store.put.bind(store);
 store.put=async(key,value)=>{if(key.includes('-discovery-snapshot-'))throw Error('SYNTHETIC_SNAPSHOT_DISK_FAILURE');return originalPut(key,value);};
 await mocked('discover',async()=>receipt(),()=>assert.rejects(e.discoverStocks(),/DISK_FAILURE/));
 assert.equal(e.discoveryHold,true);assert.equal(e.quantDiscovery.persisted,false);
 const buys=api.posts().filter(x=>x.body.side==='buy').length;
 await e.entries('crypto');assert.equal(api.posts().filter(x=>x.body.side==='buy').length,buys);
 e.market.quotes.AAPL={bid:110,ask:110.01,at:Date.now(),received:Date.now()};
 await e.manage();assert.equal(api.posts().at(-1).body.side,'sell');
});

test('snapshot immutability survives JSONB key reordering and rejects changed bytes',async()=>{
 const {e,store}=await ready();e.cfg.quant={enabled:true,discovery:true};const r=receipt();
 const reorder=x=>Array.isArray(x)?x.map(reorder):x&&typeof x==='object'?Object.fromEntries(Object.keys(x).reverse().map(k=>[k,reorder(x[k])])):x;
 await store.put(e.key+'-discovery-snapshot-'+r.snapshot_id,{accountId:e.cfg.expected_account_id,snapshot:reorder(r.snapshot)});
 await mocked('discover',async()=>r,()=>e.discoverStocks());assert.equal(e.discoveryHold,false);
 const broken=structuredClone(r);broken.snapshot.candidates[0].symbol='CHANGED';
 await mocked('discover',async()=>broken,()=>assert.rejects(e.discoverStocks(),/HASH_MISMATCH/));
 assert.equal(e.discoveryHold,true);
});

test('two decisions in one session retain unique durable identities and pre-planning quotes',async()=>{
 const {e,store}=await ready();e.cfg.quant={enabled:true};prepare(e,signal());
 const before=e.market.quotes.AAPL.ask;
 await mocked('plan',async()=>{e.market.quotes.AAPL={...e.market.quotes.AAPL,ask:before+1};return {execution_allowed:false,selected:[],rejected:{AAPL:'SYNTHETIC_ABSTENTION'},model_hash:'MODEL',config_hash:'CONFIG'};},async()=>{
  await e.entries('equity');await e.entries('equity');
 });
 const decisions=await store.scan(e.key+'-quant-decision-');
 assert.equal(decisions.length,2);assert.notEqual(decisions[0].decision_id,decisions[1].decision_id);
 const first=decisions.find(x=>x.decision_id.endsWith(':1'));
 assert.equal(first.opportunities[0].quote.ask,before);
 assert.equal(first.rejected.AAPL,'SYNTHETIC_ABSTENTION');
 assert(first.session_context.phase);assert.equal(first.session_context.authorizes_orders,false);
});

test('failed decision persistence cannot authorize an otherwise selected order',async()=>{
 const {e,api,store}=await ready();e.cfg.quant={enabled:true};const s=signal();prepare(e,s);
 const originalPut=store.put.bind(store);store.put=async(key,value)=>{if(key.includes('-quant-decision-'))throw Error('SYNTHETIC_TRACE_FAILURE');return originalPut(key,value);};
 await mocked('plan',async()=>({execution_allowed:true,selected:[{id:s.plugin+'|'+s.symbol,quantity:1}]}),()=>assert.rejects(e.entries('equity'),/TRACE_FAILURE/));
 assert.equal(api.posts().length,0);assert(e.state.events.some(x=>x.kind==='QUANT_TRACE_BLOCKED'));
});

test('universe change during planning invalidates the old allocation',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true};const s=signal();prepare(e,s);
 await mocked('plan',async()=>{e.cfg.universe.push({...e.cfg.universe[0],symbol:'NEWWATCH'});return {execution_allowed:true,selected:[{id:s.plugin+'|'+s.symbol,quantity:1}]};},()=>e.entries('equity'));
 assert.equal(api.posts().length,0);assert(e.state.events.some(x=>x.kind==='QUANT_PLAN_INVALIDATED'));
});

test('hold acquired during planning is rechecked before order authority',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true};const s=signal();prepare(e,s);
 await mocked('plan',async()=>{e.discoveryHold=true;return {execution_allowed:true,selected:[{id:s.plugin+'|'+s.symbol,quantity:1}]};},()=>e.entries('equity'));
 assert.equal(api.posts().length,0);assert(e.state.events.some(x=>x.reason==='DISCOVERY_OR_PERSISTENCE_UNRESOLVED'));
});

test('LLM/research failure does not prevent deterministic exit management',async()=>{
 const {e,api}=await ready();prepare(e,signal());await e.entries('equity');await e.reconcile();
 e.ultimateLab.tick=async()=>{throw Error('SYNTHETIC_LLM_UNAVAILABLE');};
 const lane=e.scheduler.lanes.find(x=>x.name==='ultimate-research-worker');await e.scheduler.once(lane);
 assert.equal(lane.failures,1);
 e.market.quotes.AAPL={bid:110,ask:110.01,at:Date.now(),received:Date.now()};
 await e.manage();assert.equal(api.posts().at(-1).body.side,'sell');
});

test('entry cutoff remains ten minutes before both normal and early closes',async()=>{
 const {e}=await ready(),oldNow=Date.now;
 try{
  for(const close of ['2026-10-15T20:00:00Z','2026-11-27T18:00:00Z']){
   const c=Date.parse(close);let now=c-600001;Date.now=()=>now;e.clockAt=now;e.clock={is_open:true,next_close:close};
   assert.equal(e.session('equity',true),true);now=c-600000;e.clockAt=now;
   assert.equal(e.session('equity',true),false);assert.equal(e.session('equity',false),true);
  }
 }finally{Date.now=oldNow;}
});

test('restored discovery registry cannot cross its account/config binding',async()=>{
 const cfg=config();cfg.quant={enabled:true,discovery:true};const store=new MemoryStore(),api=new FakeBroker();
 const e=new Coordinator(store,api,cfg);await e.initialize(true);
 await store.put(e.key+'-discovery-registry',{accountId:'DIFFERENT_ACCOUNT',baseConfigHash:await store.get(e.key+'-config'),registry:registry(e)});
 const next=new Coordinator(store,api,cfg);await next.initialize(true);
 assert.equal(next.quantDiscovery.health,'BLOCKED');assert.equal(next.discoveryHold,true);
 assert.match(next.quantDiscovery.reason,/ACCOUNT_OR_CONFIG_MISMATCH/);assert.equal(api.posts().length,0);
});
