'use strict';
const test=require('node:test'),assert=require('node:assert/strict');
const bridge=require('../runtime/quant_bridge.cjs');
const {fixture,instrument,model}=require('./quant_discovery_fixtures.cjs');
async function run(options,fn){const f=fixture(options);try{await fn(f);}finally{f.cleanup();}}

test('discovery preserves ETF classification, leverage and separate quote book',async()=>{
 await run({models:{ETFNEW:model('etf',{leverage:3}),STOCKNEW:model()},gainers:[{symbol:'STOCKNEW'},{symbol:'ETFNEW'}]},async f=>{
  const r=await bridge.discover(f.engine);assert.deepEqual(r.added,['ETFNEW','STOCKNEW']);
  assert.equal(f.engine.market.assets.ETFNEW.book,'etf');assert.equal(f.engine.market.assets.ETFNEW.leverage,3);
  assert.deepEqual(f.quoteBooks,['etf','equity']);assert.equal(r.health,'READY');assert.equal(r.snapshot.candidates.length,2);
  assert.equal(r.snapshot.sources.movers.rows.gainers.length,2);assert.match(r.snapshot_id,/^[a-f0-9]{64}$/);
 });
});
test('missing factor, metadata and ETF leverage cannot be invented by discovery',async()=>{
 await run({models:{NOFACTOR:model('equity',{factor:null}),NOREF:model('equity',{metadata_reference:''}),NOLEV:model('etf',{leverage:null})},gainers:[{symbol:'NOFACTOR'},{symbol:'NOREF'},{symbol:'NOLEV'}]},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.added.length,0);assert.equal(r.rejected.NOLEV,'VERIFIED_LEVERAGE_REQUIRED');
  assert.equal(r.rejected.NOFACTOR,'VERIFIED_CLASSIFICATION_AND_FACTOR_REQUIRED');assert.equal(r.rejected.NOREF,'VERIFIED_CLASSIFICATION_AND_FACTOR_REQUIRED');
  assert.equal(f.historyCalls.length,0);assert.equal(r.health,'WAITING');
 });
});
test('legacy discovery limit48 is clamped to40 total across books and records every exclusion',async()=>{
 const universe=[...Array.from({length:35},(_,i)=>instrument('OLD'+i)),instrument('ETFONE','etf'),instrument('ETFTWO','etf'),instrument('BTC/USD','crypto'),instrument('ETH/USD','crypto')];
 await run({universe,models:{AAA:model(),BBB:model()},gainers:[{symbol:'BBB'},{symbol:'AAA'}]},async f=>{
  f.engine.cfg.quant.discoveryLimit=48;const r=await bridge.discover(f.engine);
  assert.equal(f.engine.cfg.universe.length,40);assert.deepEqual(r.added,['AAA']);assert.equal(r.rejected.BBB,'EXCLUDED_CAPACITY');
  assert.equal(r.capacity.effective_total_limit,40);assert.equal(r.capacity.clamped,true);
 });
});
test('a full static universe is preserved and every new candidate is rejected explicitly',async()=>{
 await run({universe:Array.from({length:40},(_,i)=>instrument('OLD'+i)),models:{AAA:model(),BBB:model()},gainers:[{symbol:'AAA'},{symbol:'BBB'}]},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.removed.length,0);assert.equal(r.added.length,0);
  assert.deepEqual(r.rejected,{AAA:'EXCLUDED_CAPACITY',BBB:'EXCLUDED_CAPACITY'});assert.equal(f.historyCalls.length,0);
 });
});
test('dynamic watchlist rotates only unexposed managed instruments and preserves configured names',async()=>{
 await run({universe:[instrument('STATIC'),instrument('OLD','equity',true)],models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  f.engine.cfg.quant.discoveryLimit=2;const r=await bridge.discover(f.engine);
  assert.deepEqual(r.removed,['OLD']);assert.deepEqual(r.added,['NEW']);assert.deepEqual(f.engine.cfg.universe.map(i=>i.symbol),['STATIC','NEW']);
  assert.equal(f.engine.market.assets.OLD,undefined);assert.equal(f.engine.market.assets.NEW.discovery_managed,true);
 });
});
for(const [name,protection] of [
 ['position',{positions:[{symbol:'OLD',qty:'1'}]}],
 ['partial fill pending cancellation',{positions:[{symbol:'OLD',qty:'.5'}],pending:[{symbol:'OLD',status:'pending_cancel'}]}],
 ['cancel requested without confirmation',{pending:[{symbol:'OLD',status:'new',cancelAt:Date.now()}]}],
 ['open broker order',{openOrders:[{symbol:'OLD',status:'pending_cancel'}]}],
 ['active campaign',{campaigns:[{symbol:'OLD',closed:false}]}],
])test('watchlist protects '+name,async()=>{
 await run({universe:[instrument('STATIC'),instrument('OLD','equity',true)],models:{NEW:model()},gainers:[{symbol:'NEW'}],...protection},async f=>{
  f.engine.cfg.quant.discoveryLimit=2;const r=await bridge.discover(f.engine);
  assert.deepEqual(r.added,[]);assert.deepEqual(r.removed,[]);assert(f.engine.cfg.universe.some(i=>i.symbol==='OLD'));
 });
});
test('late fill while historical data loads prevents a planned watchlist eviction',async()=>{
 await run({universe:[instrument('STATIC'),instrument('OLD','equity',true)],models:{NEW:model()},gainers:[{symbol:'NEW'}],
  historyOverride:async(names,timeframe,engine)=>{if(timeframe==='1Day')engine.positions=[{symbol:'OLD',qty:'1'}];}},async f=>{
   f.engine.cfg.quant.discoveryLimit=2;const r=await bridge.discover(f.engine);
   assert.deepEqual(r.added,[]);assert.deepEqual(r.removed,[]);assert.equal(r.rejected.NEW,'EXCLUDED_CAPACITY_PROTECTED_OR_CHANGED');
  });
});
for(const failing of ['5Min','1Day'])test('failed '+failing+' bootstrap is atomic and retries the complete range',async()=>{
 let failures=1;
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}],historyOverride:async(names,timeframe)=>{if(timeframe===failing && failures-- >0)throw Error('SYNTHETIC_TIMEOUT');}},async f=>{
  const first=await bridge.discover(f.engine);assert.equal(first.health,'DEGRADED');assert.equal(first.rejected.NEW,'HISTORY_REQUEST_FAILED');
  assert(!f.engine.cfg.universe.some(i=>i.symbol==='NEW'));assert.equal(f.engine.market.bars.NEW,undefined);
  const second=await bridge.discover(f.engine);assert.deepEqual(second.added,['NEW']);assert.equal(second.health,'READY');
  const calls=f.historyCalls.filter(c=>c.timeframe==='5Min');assert.equal(calls.length,2);for(const c of calls)assert(Math.abs((c.end-c.start)/86400000-50)<.01);
 });
});
test('partial history admits ready symbols and retries missing symbols without polluting universe',async()=>{
 let first=true;
 await run({models:{AAA:model(),BBB:model()},gainers:[{symbol:'AAA'},{symbol:'BBB'}],historyOverride:async(names,timeframe)=>{
  if(first && timeframe==='5Min'){first=false;return {AAA:require('./quant_discovery_fixtures.cjs').histories().bars,BBB:[]};}
 }},async f=>{
  const one=await bridge.discover(f.engine);assert.deepEqual(one.added,['AAA']);assert.deepEqual(one.pending_symbols,['BBB']);assert.equal(one.health,'DEGRADED');
  const two=await bridge.discover(f.engine);assert.deepEqual(two.added,['BBB']);assert.equal(f.engine.cfg.universe.filter(i=>i.symbol==='AAA').length,1);
  assert.deepEqual(f.historyCalls.at(-1).names,['BBB']);
 });
});
test('candidate ranking is invariant to screener concatenation and row ordering',async()=>{
 const chosen=[];
 for(const gainers of [[{symbol:'ZZZ'},{symbol:'AAA'}],[{symbol:'AAA'},{symbol:'ZZZ'}]])await run({models:{ZZZ:model(),AAA:model(),MMM:model()},gainers,losers:[{symbol:'MMM'}],active:[{symbol:'MMM'}]},async f=>{
  f.engine.cfg.quant.discoveryLimit=2;const r=await bridge.discover(f.engine);chosen.push(r.added);
  assert.equal(Object.keys(r.rejected).length,2);assert.equal(r.snapshot.candidates.find(c=>c.symbol==='MMM').rank,1);
 });
 assert.deepEqual(chosen,[['MMM'],['MMM']]);
});
for(const offset of [-900001,2000])test('stale or future snapshot is blocked: '+offset,async()=>{
 await run({timeOffset:offset,models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.status,'BLOCKED');assert.equal(r.reason,'STALE_OR_FUTURE_SCREENER');assert.equal(r.added.length,0);assert.equal(f.historyCalls.length,0);
 });
});
test('invalid symbols remain visible as rejected observations without broker requests',async()=>{
 await run({gainers:[{symbol:'../../bad'},{symbol:null},{symbol:'UNCAL'}]},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.snapshot.candidates.length,3);assert.equal(r.snapshot.candidates.filter(c=>c.reason==='INVALID_SYMBOL').length,2);
  assert.equal(r.rejected.UNCAL,'NO_CALIBRATED_CLASSIFIED_SECURITY');assert.equal(f.calls.filter(p=>p.startsWith('/v2/assets/')).length,0);
 });
});
test('SVR research guard makes zero requests and preserves universe',async()=>{
 await run({calibration:{model_kind:'SVR_RBF'},models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  const before=JSON.stringify(f.engine.cfg.universe),r=await bridge.discover(f.engine);
  assert.equal(r.reason,'SVR_RESEARCH_ONLY');assert.equal(r.health,'BLOCKED');assert.equal(f.calls.length,0);assert.equal(JSON.stringify(f.engine.cfg.universe),before);
 });
});
test('concurrent discovery calls share one preparation and cannot duplicate symbols',async()=>{
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  const [one,two]=await Promise.all([bridge.discover(f.engine),bridge.discover(f.engine)]);
  assert.equal(one.snapshot_id,two.snapshot_id);assert.equal(f.calls.filter(p=>p.includes('/movers')).length,1);assert.equal(f.engine.cfg.universe.filter(i=>i.symbol==='NEW').length,1);
 });
});
test('configuration replaced while history loads aborts admission',async()=>{
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}],historyOverride:async(names,timeframe,e)=>{if(timeframe==='1Day')e.cfg={...e.cfg,universe:[instrument('OTHER')]};}},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.reason,'CONFIGURATION_CHANGED_DURING_DISCOVERY');assert.deepEqual(f.engine.cfg.universe.map(i=>i.symbol),['OTHER']);
 });
});
test('quote failure stays degraded after history preparation and never reports ready',async()=>{
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}],quoteFailure:true},async f=>{
  const r=await bridge.discover(f.engine);assert.deepEqual(r.added,['NEW']);assert.equal(r.health,'DEGRADED');assert.deepEqual(r.ready_symbols,[]);
 });
});
test('broker identity mismatch cannot admit a candidate',async()=>{
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}],apiOverride:async p=>p.startsWith('/v2/assets/')?{symbol:'OTHER',class:'us_equity',tradable:true,status:'active'}:undefined},async f=>{
  const r=await bridge.discover(f.engine);assert.deepEqual(r.added,[]);assert.equal(r.rejected.NEW,'ASSET_NOT_TRADABLE_OR_IDENTITY_MISMATCH');assert.equal(f.historyCalls.length,0);
 });
});
test('source request failure is an explicit blocked receipt',async()=>{
 await run({apiOverride:async p=>{if(p.includes('/most-actives'))throw Error('SYNTHETIC_NETWORK_FAILURE');}},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.status,'BLOCKED');assert.equal(r.reason,'SCREENER_REQUEST_FAILED');assert.equal(r.snapshot.sources.movers.rows.gainers.length,0);assert.equal(r.added.length,0);
 });
});
test('an existing protected symbol left with incomplete history is backfilled without reclassification',async()=>{
 await run({universe:[instrument('HELD')],models:{HELD:model()},gainers:[{symbol:'HELD'}],positions:[{symbol:'HELD',qty:'1'}]},async f=>{
  f.engine.market.bars.HELD=f.rows.bars.slice(-4);f.engine.market.daily.HELD=[];
  const original=JSON.stringify(f.engine.cfg.universe),r=await bridge.discover(f.engine);
  assert.deepEqual(r.added,[]);assert.deepEqual(r.removed,[]);assert.deepEqual(r.repaired,['HELD']);
  assert.equal(JSON.stringify(f.engine.cfg.universe),original);assert.equal(f.engine.market.bars.HELD.length,100);assert.equal(f.engine.market.daily.HELD.length,24);
  assert.equal(r.health,'READY');assert(Math.abs((f.historyCalls[0].end-f.historyCalls[0].start)/86400000-50)<.01);
 });
});
test('failed repair preserves existing partial history and retries without removing inventory',async()=>{
 let fail=true;
 await run({universe:[instrument('HELD')],models:{HELD:model()},gainers:[{symbol:'HELD'}],pending:[{symbol:'HELD',status:'pending_cancel'}],historyOverride:async()=>{if(fail){fail=false;throw Error('SYNTHETIC_REPAIR_FAILURE');}}},async f=>{
  f.engine.market.bars.HELD=f.rows.bars.slice(-4);const partial=JSON.stringify(f.engine.market.bars.HELD);
  const one=await bridge.discover(f.engine);assert.equal(one.health,'DEGRADED');assert.equal(JSON.stringify(f.engine.market.bars.HELD),partial);assert.equal(f.engine.cfg.universe.length,1);
  const two=await bridge.discover(f.engine);assert.deepEqual(two.repaired,['HELD']);assert.equal(f.engine.market.bars.HELD.length,100);
 });
});
test('open option campaign protects its instrument underlying from rotation',async()=>{
 await run({universe:[instrument('STATIC'),instrument('OLD','equity',true)],models:{NEW:model()},gainers:[{symbol:'NEW'}],campaigns:[{symbol:'OLD261120C00100000',book:'options',instrument:{underlying:'OLD'},closed:false}]},async f=>{
  f.engine.cfg.quant.discoveryLimit=2;const r=await bridge.discover(f.engine);assert.deepEqual(r.removed,[]);assert.deepEqual(r.added,[]);assert(f.engine.cfg.universe.some(i=>i.symbol==='OLD'));
 });
});
for(const uncertainty of ['stale','error'])test('uncertain reconciliation blocks rotation: '+uncertainty,async()=>{
 await run({universe:[instrument('STATIC'),instrument('OLD','equity',true)],models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  f.engine.cfg.quant.discoveryLimit=2;if(uncertainty==='stale')f.engine.syncAt=Date.now()-16000;else f.engine.reconcileError='SYNTHETIC_POSITION_MISMATCH';
  const r=await bridge.discover(f.engine);assert.deepEqual(r.removed,[]);assert.deepEqual(r.added,[]);assert.equal(r.rejected.NEW,'ROTATION_REQUIRES_RECENT_RECONCILIATION');assert.equal(r.health,'DEGRADED');
 });
});
test('fresh quote and complete historical warmup cannot mask missing current-session bars',async()=>{
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}],historyOverride:async(names,timeframe)=>timeframe==='5Min'?Object.fromEntries(names.map(s=>[s,require('./quant_discovery_fixtures.cjs').histories().bars.slice(0,-4)])):undefined},async f=>{
  const r=await bridge.discover(f.engine);assert.deepEqual(r.added,['NEW']);assert.equal(r.health,'WAITING');assert.deepEqual(r.ready_symbols,[]);assert.equal(r.snapshot.candidates[0].readiness_reason,'NO_CLOSED_CURRENT_SESSION_BAR');
 });
});
test('persisted registry rehydrates a restart without authorizing tradability or losing metadata',async()=>{
 await run({models:{ETFNEW:model('etf',{leverage:3})},gainers:[{symbol:'ETFNEW'}]},async f=>{
  const r=await bridge.discover(f.engine);
  await run({},async next=>{
   const result=require('../runtime/discovery.cjs').restore(next.engine,JSON.parse(JSON.stringify(r.registry)));
   assert.equal(result.status,'RESTORED');assert.equal(result.health,'WAITING');assert.deepEqual(result.restored,['ETFNEW']);
   assert.equal(next.engine.market.assets.ETFNEW.book,'etf');assert.equal(next.engine.market.assets.ETFNEW.leverage,3);assert.equal(next.engine.market.assets.ETFNEW.tradable,false);assert.equal(next.calls.length,0);
  });
 });
});
test('tampered registry and insufficient capacity for exposed symbols fail without partial restore',async()=>{
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  const r=await bridge.discover(f.engine), module=require('../runtime/discovery.cjs');
  await run({universe:Array.from({length:40},(_,i)=>instrument('OLD'+i)),positions:[{symbol:'NEW',qty:'1'}]},async next=>{
   const before=JSON.stringify(next.engine.cfg.universe),tampered=JSON.parse(JSON.stringify(r.registry));tampered.items[0].leverage=2;
   assert.equal(module.restore(next.engine,tampered).reason,'DISCOVERY_REGISTRY_HASH_MISMATCH');
   assert.equal(module.restore(next.engine,r.registry).reason,'DISCOVERY_RESTORE_CAPACITY_FOR_EXPOSURE');assert.equal(JSON.stringify(next.engine.cfg.universe),before);
  });
 });
});
for(const at of ['future','invalid'])test('declared metadata time must be valid and available: '+at,async()=>{
 await run({models:{NEW:model('equity',{metadata_available_at:at==='future'?new Date(Date.now()+86400000).toISOString():'bad-date'})},gainers:[{symbol:'NEW'}]},async f=>{
  const r=await bridge.discover(f.engine);assert.deepEqual(r.added,[]);assert.equal(r.rejected.NEW,'INVALID_OR_FUTURE_METADATA_TIME');assert.equal(f.historyCalls.length,0);
 });
});
test('snapshot expiring while bootstrap runs cannot commit a candidate',async t=>{
 const originalNow=Date.now();
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}],historyOverride:async(names,timeframe)=>{
  if(timeframe==='1Day')t.mock.method(Date,'now',()=>originalNow+901000);
 }},async f=>{
  const r=await bridge.discover(f.engine);assert.equal(r.reason,'SCREENER_EXPIRED_DURING_PREPARATION');assert.equal(r.status,'BLOCKED');
  assert.deepEqual(r.added,[]);assert(!f.engine.cfg.universe.some(i=>i.symbol==='NEW'));assert.equal(f.engine.market.bars.NEW,undefined);
 });
});
test('restart reaches READY only after actual catalog verification and restored history loading',async()=>{
 const m={ETFNEW:model('etf',{leverage:3})},g=[{symbol:'ETFNEW'}];
 await run({models:m,gainers:g},async f=>{
  const receipt=await bridge.discover(f.engine);
  await run({models:m,gainers:g},async next=>{
   const restored=require('../runtime/discovery.cjs').restore(next.engine,receipt.registry);assert.equal(restored.health,'WAITING');
   next.engine.market.cfg=next.engine.cfg;next.engine.market.api=next.engine.api;next.engine.market.errors={};
   const before=await bridge.discover(next.engine);assert.equal(before.health,'WAITING');assert.equal(before.snapshot.candidates[0].readiness_reason,'CATALOG_VERIFICATION_REQUIRED');
   await require('../runtime30/market.js').Market.prototype.catalog.call(next.engine.market);
   const after=await bridge.discover(next.engine);assert.equal(after.health,'READY');assert.deepEqual(after.ready_symbols,['ETFNEW']);
   assert.equal(next.engine.market.assets.ETFNEW.tradable,true);assert.equal(next.engine.cfg.universe.find(i=>i.symbol==='ETFNEW').tradable,true);
   assert.equal(next.engine.cfg.universe.filter(i=>i.symbol==='ETFNEW').length,1);
  });
 });
});
test('registry checksum survives JSON object key reordering by a persistent store',async()=>{
 const reverse=v=>Array.isArray(v)?v.map(reverse):v && typeof v==='object'?Object.fromEntries(Object.keys(v).reverse().map(k=>[k,reverse(v[k])])):v;
 await run({models:{NEW:model()},gainers:[{symbol:'NEW'}]},async f=>{
  const receipt=await bridge.discover(f.engine);
  await run({},async next=>assert.equal(require('../runtime/discovery.cjs').restore(next.engine,reverse(receipt.registry)).status,'RESTORED'));
 });
});
