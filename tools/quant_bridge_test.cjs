'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const bridge=require('../runtime/quant_bridge.cjs');
const {ready,signal,prepare}=require('./xxx_fixtures.cjs');
test('missing calibration returns BLOCKED through the actual Python worker',async()=>{
 const r=await bridge.worker({},{calibrationFile:'/__harpoon_missing_quant_model__.json',timeoutMs:8000});
 assert.equal(r.execution_allowed,false);assert.deepEqual(r.selected,[]);assert.equal(r.reason,'CALIBRATION_FILE_REQUIRED');
});
test('quant gate blocks a stock order without a calibrated allocation',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true,calibrationFile:'/__harpoon_missing_quant_model__.json'};
 const s=signal();prepare(e,s);await e.entries('equity');
 assert.equal([...api.orders.values()].filter(o=>o.side==='buy').length,0);
 assert(e.state.events.some(x=>x.kind==='QUANT_PLAN'&&x.execution_allowed===false));
});
test('quantified quantity caps the existing broker risk size',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true};const s=signal();prepare(e,s);
 const old=bridge.plan;
 try{bridge.plan=async()=>({execution_allowed:true,selected:[{id:s.plugin+'|'+s.symbol,quantity:1,robust_net_usd:2}],reason:'SYNTHETIC_CONTRACT_FIXTURE'});await e.entries('equity');}
 finally{bridge.plan=old;}
 const buys=[...api.orders.values()].filter(o=>o.side==='buy');assert.equal(buys.length,1);assert.equal(Number(buys[0].qty),1);
});
test('subprocess failure cannot authorize an order',async()=>{
 const r=await bridge.worker({},{python:'/__missing_python__',timeoutMs:200});assert.equal(r.execution_allowed,false);assert.equal(r.reason,'QUANT_WORKER_UNAVAILABLE');
});
test('stock net discovers only classified calibrated names and preserves inventory',async()=>{
 const {fixture,instrument,model}=require('./quant_discovery_fixtures.cjs');
 const f=fixture({universe:[instrument('HELD')],models:{NEW:model()},gainers:[{symbol:'NEW'},{symbol:'UNCAL'}],active:[{symbol:'HELD'}],campaigns:[{symbol:'HELD',book:'equity'}]});
 try{
  const r=await bridge.discover(f.engine);assert.deepEqual(r.added,['NEW']);assert(f.engine.cfg.universe.some(x=>x.symbol==='HELD'));assert.equal(r.rejected.UNCAL,'NO_CALIBRATED_CLASSIFIED_SECURITY');assert(f.calls.some(x=>x.includes('most-actives')));
 }finally{f.cleanup();}
});
test('slow numerical planning does not hold the order mutex needed by exits',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true};prepare(e,signal());
 const old=bridge.plan;let release;const pending=new Promise(resolve=>release=resolve);
 try{
  bridge.plan=()=>pending;const entries=e.entries('equity');await new Promise(r=>setImmediate(r));
  const ran=await Promise.race([e.mutex.run(0,async()=>true),new Promise(r=>setTimeout(()=>r(false),100))]);
  assert.equal(ran,true);release({execution_allowed:false,selected:[],reason:'SYNTHETIC_SLOW_MODEL'});await entries;
 }finally{bridge.plan=old;}
});
test('account changes during numerical planning invalidate entry authority',async()=>{
 const {e,api}=await ready();e.cfg.quant={enabled:true};const s=signal();prepare(e,s);
 const old=bridge.plan;
 try{bridge.plan=async()=>{e.account.cash=String(Number(e.account.cash)-1);return {execution_allowed:true,selected:[{id:s.plugin+'|'+s.symbol,quantity:1,robust_net_usd:2}]};};await e.entries('equity');}
 finally{bridge.plan=old;}
 assert.equal([...api.orders.values()].filter(o=>o.side==='buy').length,0);
 assert(e.state.events.some(x=>x.kind==='QUANT_PLAN_INVALIDATED'));
});
test('sized live quote reaches the L1 cache through the actual coordinator callback',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true,microstructure:{enabled:true}};
 e.onQuote('AAPL',{bp:100,ap:100.02,bs:40,as:50,c:['R'],t:new Date().toISOString()});
 const d=e.market.microData.AAPL;assert.equal(d.quotes[0].bs,40);assert.equal(d.quotes[0].as,50);assert.equal(d.sampling_schema,'ALPACA_L1_LAST_PER_SECOND');
 assert.equal(d.feed,e.cfg.stockFeed);
});
test('L1 sampling is bounded per second and records omitted events',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true,microstructure:{enabled:true}};
 const base=Math.floor(Date.now()/1000)*1000-2000;
 for(let i=0;i<100;i++)e.market.recordMicro('AAPL',{bp:100,ap:100.02,bs:40,as:50,t:new Date(base+i).toISOString()},'quote');
 assert.equal(e.market.microData.AAPL.quotes.length,1);assert.equal(e.market.microData.AAPL.omitted_events,99);
});
test('missing L1 sizes are not fabricated and reconnect clears its book history',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true,microstructure:{enabled:true}};
 e.market.recordMicro('AAPL',{bp:100,ap:100.02,t:new Date().toISOString()},'quote');assert.equal(e.market.microData.AAPL,undefined);
 e.market.recordMicro('AAPL',{bp:100,ap:100.02,bs:40,as:50,t:new Date().toISOString()},'quote');
 assert(e.market.microData.AAPL);e.market.resetMicro('stocks');assert.equal(e.market.microData.AAPL,undefined);
});
test('calibration context runs through Python independently of a return calibration file',async()=>{
 const r=await bridge.worker({now:Date.now(),config:{stockFeed:'sip',quant:{microstructure:{enabled:true}}},market:{assets:{},bars:{},micro_data:{}}},
  {calibrationFile:'/__harpoon_missing_quant_model__.json',timeoutMs:8000},'context');
 assert.equal(r.status,'CALIBRATION_CONTEXT');assert.equal(r.execution_allowed,false);assert.equal(r.curve.status,'NOT_READY');
});
test('microstructure preflight rejects malformed switches and unbounded settings',()=>{
 const {validateConfig}=require('../runtime30/types.js');
 const {config}=require('./xxx_fixtures.cjs');
 for(const micro of [{enabled:'true'},{enabled:true,windowSeconds:Infinity},{enabled:true,curveMaxSymbols:49},{enabled:true,curveMaxSymbols:2.5},{enabled:true,minWindowCoverageFraction:0}]){
  const cfg=config();cfg.quant={enabled:true,microstructure:micro};assert.throws(()=>validateConfig(cfg),/microstructure/i);
 }
});
test('performance worker computes Sortino and drawdown without authorizing trades',async()=>{
 const result=await bridge.worker({origin:'SYNTHETIC_ENGINEERING_ONLY',return_basis:'NET_FLOW_ADJUSTED',periods_per_year:365,sampling:'DAILY_UTC_CALENDAR',times:['2026-01-01T00:00:00Z','2026-01-02T00:00:00Z','2026-01-03T00:00:00Z'],returns:[.1,-.1,.05]}, {timeoutMs:8000},'metrics');
 assert.equal(result.status,'PERFORMANCE_REPORT');assert.equal(result.execution_allowed,false);assert(Math.abs(result.performance.max_drawdown-.1)<1e-12);assert(Number.isFinite(result.performance.sortino_per_period));
});
test('recursive calibrator runs without an opportunity panel and waits explicitly',async()=>{
 const fs=require('node:fs'),os=require('node:os'),path=require('node:path'),dir=fs.mkdtempSync(path.join(os.tmpdir(),'hq-loop-'));
 try{
  const {e,api}=await ready();e.cfg.quant={enabled:true,optimizer:{enabled:true,statePath:path.join(dir,'state.db'),panelFile:path.join(dir,'missing.json')}};
  const result=await bridge.optimize(e);assert.equal(result.status,'WAIT_DATA');assert.equal(result.execution_allowed,false);assert.equal(api.orders.size,0);
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
test('NAV capture does not mislabel unconfirmed cashflows as trading returns',async()=>{
 const {e}=await ready();e.cfg.quant={enabled:true,optimizer:{enabled:true}};
 const r=await bridge.performance(e);assert.equal(r.status,'WAIT_RECONCILED_PERFORMANCE');assert.equal(r.observations,0);assert.equal(r.cashflows_reconciled,false);
 assert.equal(r.source,'INTERNAL_ACCOUNT_LEDGER');assert.equal(r.accounting.economicNetPnlUsd,null);
 const again=await bridge.performance(e);assert.equal(again.observations,0);
});
test('optimizer preflight rejects infinite budgets and malformed controls',()=>{
 const {validateConfig}=require('../runtime30/types.js'),{config}=require('./xxx_fixtures.cjs');
 for(const optimizer of [{enabled:'true'},{enabled:true,maxTrials:Infinity},{enabled:true,lifetimeTrials:201},{enabled:true,maxGenerations:1.5},{enabled:true,minHoldoutTrades:0}]){
  const c=config();c.quant={enabled:true,optimizer};assert.throws(()=>validateConfig(c),/optimizer/i);
 }
});
