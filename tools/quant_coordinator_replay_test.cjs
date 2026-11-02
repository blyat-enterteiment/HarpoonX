"use strict";
// SYNTHETIC operational validation. No financial training or broker execution.
const test=require("node:test"),assert=require("node:assert/strict");
const {validateRequest,executeReplay,runReplay,verifyReport,compareReplays,hash}=require("./coordinator_replay.cjs");
const {syntheticRequest}=require("./fixtures/coordinator_replay_fixture.cjs");
const {fromObservationExport}=require("./observation_replay_input.cjs");
const clone=x=>structuredClone(x);
function push(r,id,offset,type,extra={}){r.events.push({id,at:r.start_at+offset,type,...extra});return r;}
function quote(r,id,offset,bid,qty=1000,symbol="AAPL"){return push(r,id,offset,"market",{quotes:[{symbol,market_at:r.start_at+offset,bid,ask:bid+.01,executable_qty:qty}]});}
function partialRequest(){const r=syntheticRequest();r.events.find(e=>e.id==="future-fill-quote").quotes[0].executable_qty=3;return r;}
function tpRequest(){
  const r=syntheticRequest();quote(r,"tp-observation",2000,103);push(r,"detect-tp-and-cancel-stop",2000,"manage");
  push(r,"stop-terminal-confirmed",2001,"cancel_confirm",{order:{symbol:"AAPL",kind:"protect"}});
  push(r,"cancel-reconciled",2002,"reconcile");push(r,"tp-submit",2002,"manage");
  quote(r,"tp-future-fill",3000,103);push(r,"tp-reconciled",3000,"reconcile");push(r,"protect-remainder",3001,"manage");push(r,"protection-reconciled",3002,"reconcile");
  quote(r,"trailing-stop-quote",4000,102.1);push(r,"trailing-reconciled",4000,"reconcile");push(r,"trailing-close",4001,"pulse");
  return r;
}
function cryptoRequest(){
  const r=syntheticRequest(),base=clone(require("../config/examples/xxx.json"));
  r.id="synthetic-crypto-72h";r.config.universe=base.universe.filter(a=>a.symbol==="BTC/USD");r.config.enabledPlugins=["crypto-canonical-host"];
  const end=Math.floor(r.start_at/86400000)*86400000;
  r.events[0]={id:"history",at:r.start_at,type:"market",daily:{"BTC/USD":Array.from({length:50},(_,i)=>{const t=end-(50-i)*86400000;return {t:new Date(t).toISOString(),o:100,h:i===49?105:101,l:99,c:i===49?104:100,v:100,known_at:t+86400000};})},quotes:[{symbol:"BTC/USD",market_at:r.start_at,bid:104,ask:104.01,executable_qty:0}]};
  for(const e of r.events){if(e.book)e.book="crypto";if(e.id==="future-fill-quote")e.quotes=[{symbol:"BTC/USD",market_at:e.at,bid:104,ask:104.01,executable_qty:1000}];}
  return r;
}

test("replay reuses real plugin, coordinator entry, reconciliation and protection",async()=>{
  const r=await runReplay(syntheticRequest());
  assert(r.result.decisions[0].signals.length>0);assert.equal(r.result.decisions[0].signals[0].plugin,"equity-canonical-host");
  assert.equal(r.result.decisions[0].signals[0].reentryFeature.streak_diagnostics.availability,"EXPLICIT_AVAILABILITY");
  assert.deepEqual(r.result.final_state.intents.map(i=>i.kind),["entry","protect"]);
  assert.equal(r.result.final_state.reconcile_error,"");assert(r.checks.every(c=>c.passed));
  assert.equal(r.policy_parity_verified,true);assert.equal(r.financial_acceptance_allowed,false);assert.equal(r.execution_origin,"MODELED");
  assert.equal(r.result.fills[0].origin,"MODELED");assert(r.result.fills[0].market_at>r.result.fills[0].submitted_at);
});
test("cost ledger includes open inventory, per-fill fees and external costs once",async()=>{
  const input=syntheticRequest(),r=await executeReplay(input),fill=r.fills[0];
  const fees=fill.qty*fill.price*input.execution_model.fees_bps_per_side/10000+input.execution_model.fee_per_fill_usd;
  assert(Math.abs(r.metrics.fees_usd-fees)<1e-10);
  assert(Math.abs(r.metrics.account_pnl_net_usd-(101.1-fill.price)*fill.qty+fees)<1e-8);
  assert.equal(r.metrics.economic_pnl_net_usd,r.metrics.account_pnl_net_usd-1);
  assert.equal(r.metrics.open_inventory.length,1);assert.equal(r.metrics.realized_pnl_only,false);
});
test("leveraged ETF uses real ETF plugin and exposure sizing without multiplying traded share PnL twice",async()=>{
  const r=syntheticRequest();r.config.universe=clone(require("../config/examples/xxx.json").universe.filter(a=>a.symbol==="SPXL"));r.config.enabledPlugins=["etf-canonical-host"];
  r.events[0].bars.SPXL=r.events[0].bars.AAPL;r.events[0].daily.SPXL=r.events[0].daily.AAPL;
  for(const e of r.events){if(e.book)e.book="etf";for(const q of e.quotes||[])if(q.symbol==="AAPL")q.symbol="SPXL";}
  const out=await executeReplay(r),signal=out.decisions[0].signals[0],fill=out.fills[0];assert.equal(signal.plugin,"etf-canonical-host");assert.equal(signal.reentryFeature.leverage,3);
  assert(Math.abs(out.metrics.account_pnl_net_usd-((101.1-fill.price)*fill.qty-fill.fee_usd))<1e-8);
});
test("future bars, quotes and unordered event receipts are rejected",()=>{
  let r=syntheticRequest();r.events[0].quotes[0].market_at=r.start_at+1;assert.throws(()=>validateRequest(r),/FUTURE_QUOTE/);
  r=syntheticRequest();r.events[0].bars.AAPL.at(-1).known_at=r.start_at+1;assert.throws(()=>validateRequest(r),/BAR_NOT_CLOSED/);
  r=syntheticRequest();r.events[0].bars.AAPL.at(-1).t=new Date(r.start_at).toISOString();assert.throws(()=>validateRequest(r),/BAR_NOT_CLOSED/);
  r=syntheticRequest();r.events.at(-1).at=r.start_at-1;assert.throws(()=>validateRequest(r),/NONCAUSAL/);
});
test("an order cannot fill against its deciding quote or its timestamp",async()=>{
  const r=syntheticRequest();r.events.find(e=>e.id==="future-fill-quote").quotes[0].market_at=r.start_at+1;
  const out=await executeReplay(r);assert.equal(out.fills.length,0);assert.equal(out.final_state.positions.length,0);
});
test("unknown execution costs and liquidity cannot silently become zero",()=>{
  for(const key of ["fees_bps_per_side","fee_per_fill_usd","slippage_bps","external_cost_usd"]){const r=syntheticRequest();r.execution_model[key]=null;assert.throws(()=>validateRequest(r),/UNKNOWN_COST/);}
  const r=syntheticRequest();delete r.events[0].quotes[0].executable_qty;assert.throws(()=>validateRequest(r),/UNKNOWN_LIQUIDITY/);
});
test("replayed quote cannot create a second liquidity budget at the same market timestamp",async()=>{
  const r=partialRequest();push(r,"duplicate-market-event",2000,"market",{quotes:[{symbol:"AAPL",market_at:r.start_at+1000,bid:101.1,ask:101.11,executable_qty:3}]});
  await assert.rejects(executeReplay(r),/DUPLICATE_QUOTE_TIMESTAMP/);
});
test("stale received quotes are rejected; an aging accepted quote blocks price decisions",async()=>{
  let r=syntheticRequest();r.events[0].quotes[0].market_at=r.start_at-r.config.quoteAgeMs-1;assert.throws(()=>validateRequest(r),/QUOTE_STALE/);
  r=syntheticRequest();push(r,"fresh-account-stale-price",18000,"reconcile");push(r,"manage-stale-price",18000,"manage");
  const out=await executeReplay(r);assert.equal(out.final_state.campaigns[0].evaluation.outcome,"STALE_DATA");assert.equal(out.final_state.entry_ready,false);assert.equal(out.fills.length,1);
});
test("cancel request acknowledgement leaves partially filled entry nonterminal and protects no fictitious flat account",async()=>{
  const out=await executeReplay(partialRequest()),last=out.final_state;
  assert.equal(last.positions[0].qty,"3");assert.equal(last.intents[0].status,"partially_filled");assert(last.intents[0].cancelAt);
  assert.equal(last.campaigns[0].partialEntryRisk.status,"WAIT_CANCEL");assert.equal(last.entry_ready,false);
  assert.equal(out.order_actions.filter(a=>a.method==="POST"&&a.body.side==="sell").length,0);
});
test("late fill after cancel request survives restart and real protection covers final reconciled quantity",async()=>{
  const r=partialRequest();push(r,"restart",2000,"restart");quote(r,"late-fill",3000,101.1,2);
  push(r,"late-reconciliation",3000,"reconcile");push(r,"entry-terminal-cancel",3001,"cancel_confirm",{order:{symbol:"AAPL",kind:"entry"}});
  push(r,"terminal-reconciliation",3002,"reconcile");push(r,"cover-late-inventory",3002,"pulse");
  const out=await executeReplay(r);assert.equal(out.restarts,1);assert.equal(out.final_state.positions[0].qty,"5");
  assert.equal(out.fills.at(-1).after_cancel_request,true);assert.equal(out.final_state.campaigns[0].partialEntryRisk.resolution,"CONFIRMED_PROTECTION");
  assert.equal(out.order_actions.filter(a=>a.method==="POST"&&a.body.side==="buy").length,1);
  assert.equal(out.final_state.intents.find(i=>i.kind==="protect").payload.qty,"5");
});
test("partial entry protection deadline is not reset by restart or an overdue pulse",async()=>{
  const r=partialRequest();push(r,"restart",2000,"restart");push(r,"overdue-reconcile",25000,"reconcile");push(r,"overdue-pulse",25000,"pulse");
  const out=await executeReplay(r),first=out.snapshots.find(s=>s.event_id==="protect").campaigns[0].partialEntryRisk,last=out.final_state.campaigns[0].partialEntryRisk;
  assert.equal(last.firstObservedAt,first.firstObservedAt);assert.equal(last.deadlineAt,first.deadlineAt);assert.equal(last.overdue,true);assert.equal(out.final_state.entry_ready,false);
});
test("real take-profit fractions, terminal cancellation and trailing stop manage continuous inventory",async()=>{
  const out=await executeReplay(tpRequest());
  assert(out.final_state.intents.some(i=>["tp1","tp2"].includes(i.kind)));
  assert(out.fills.some(f=>["tp1","tp2"].includes(f.kind)&&f.side==="sell"));
  assert.equal(out.final_state.positions.length,0);assert.equal(out.final_state.campaigns[0].closed,true);
  assert(out.final_state.campaigns[0].stop>100.76);assert(out.fills.some(f=>f.kind==="protect"&&f.side==="sell"));
});
test("72-hour holding cap uses real time-exit policy and never invents a closure",async()=>{
  const r=cryptoRequest(),deadline=72*3600000+2;
  quote(r,"holding-clock-quote",deadline,104,0,"BTC/USD");push(r,"holding-reconcile",deadline,"reconcile");push(r,"holding-detect-time",deadline,"manage");
  push(r,"holding-cancel-confirmed",deadline+1,"cancel_confirm",{order:{symbol:"BTC/USD",kind:"protect"}});
  push(r,"holding-cancel-reconcile",deadline+2,"reconcile");push(r,"holding-exit-submit",deadline+2,"manage");
  quote(r,"holding-exit-fill",deadline+3,104,1000,"BTC/USD");push(r,"holding-exit-reconcile",deadline+3,"reconcile");
  const out=await executeReplay(r),campaign=out.final_state.campaigns[0];
  assert(campaign.deadline<=campaign.created+72*3600000);assert(out.final_state.intents.some(i=>i.kind==="time"));assert.equal(out.final_state.positions.length,0);
  const before=out.snapshots.find(s=>s.event_id==="holding-detect-time");assert.equal(before.positions.length,1);assert.equal(before.campaigns[0].closed,false);
});
test("LLM transport failure cannot disable deterministic position protection",async()=>{
  const r=syntheticRequest();push(r,"llm-down",2000,"llm_unavailable");
  const out=await executeReplay(r);assert.equal(out.io_failures.length,1);assert.match(out.io_failures[0].error,/EXTERNAL_IO_DENIED/);assert.equal(out.io_failures[0].external_request_sent,false);
  assert.equal(out.final_state.coverage.state,"ALIVE");assert.equal(out.final_state.positions.length,1);
});
test("offline isolation restores process APIs and bridge identity after replay",async()=>{
  const bridge=require("../runtime/quant_bridge.cjs"),before={Date:global.Date,fetch:global.fetch,spawn:require("node:child_process").spawn,plan:bridge.plan,request:require("node:http").request};
  await executeReplay(syntheticRequest());assert.equal(global.Date,before.Date);assert.equal(global.fetch,before.fetch);assert.equal(require("node:child_process").spawn,before.spawn);assert.equal(require("node:http").request,before.request);assert.equal(bridge.plan,before.plan);
});
test("production mode, streaming, research-guard overrides and unsupported OCO are rejected",()=>{
  for(const patch of [{mode:"live"},{streaming:true},{nativeProtection:"oco"},{quant:{enabled:true}}]){const r=syntheticRequest();Object.assign(r.config,patch);assert.throws(()=>validateRequest(r),/SCOPE|GUARDS/);}
  const r=syntheticRequest();r.config.exit.maxHoldHours=73;assert.throws(()=>validateRequest(r),/HOLD_LIMIT/);
});
test("forged action, inventory or cost invalidates reproducible report even after rehashing",async()=>{
  const input=syntheticRequest(),original=await runReplay(input);
  for(const mutate of [r=>{r.result.order_actions[0].body.qty="999";},r=>{r.result.final_state.positions[0].qty="0";},r=>{r.result.metrics.fees_usd=0;}]){
    const forged=clone(original);mutate(forged);forged.artifact_hash=hash({...forged,artifact_hash:undefined});
    const check=await verifyReport(input,forged);assert.equal(check.verified,false);assert(check.mismatches.includes("result"));
  }
});
test("source or request binding tampering is rejected and exact replay verifies",async()=>{
  const input=syntheticRequest(),report=await runReplay(input);assert.equal((await verifyReport(input,report)).verified,true);
  const forged=clone(report);forged.source_hashes["xxx/policy.ts"]="0".repeat(64);forged.input_hash="0".repeat(64);forged.artifact_hash=hash({...forged,artifact_hash:undefined});
  const result=await verifyReport(input,forged);assert(result.mismatches.includes("source_hashes"));assert(result.mismatches.includes("input_hash"));
});
test("paired receipt comparison changes only predictor and keeps external SVR authorization false",async()=>{
  const c0=syntheticRequest(),base=await executeReplay(c0),decision=base.decisions.find(d=>d.event_id==="entry"),signal=decision.request.signals[0];
  const variants=["RIDGE","SVR"].map(name=>{
    const r=clone(c0);r.id+="-"+name;const receipt={event_id:"entry",request_hash:decision.request_hash,selected:[{id:signal.plugin+"|"+signal.symbol,quantity:signal.max_qty,robust_net_usd:1}]};receipt.receipt_hash=hash(receipt);
    r.predictor={name,mode:"PRECOMPUTED_OFFLINE",external_execution_allowed:false,model_hash:hash({name,synthetic:true}),trained_until:r.start_at-1,receipts:[receipt]};return r;
  });
  const out=await compareReplays([c0,...variants]);assert.equal(out.reports.length,3);assert.equal(out.financial_acceptance_allowed,false);
  assert(out.reports.every(r=>r.external_execution_allowed===false));assert(out.reports.slice(1).every(r=>r.predictor_parity_verified===false));
  assert.deepEqual(out.reports[0].result.order_actions,out.reports[2].result.order_actions);
});
test("paired comparison rejects changed costs and unverifiable or future predictor receipts",async()=>{
  const first=syntheticRequest(),second=clone(first);second.execution_model.slippage_bps=1;await assert.rejects(compareReplays([first,second]),/COMPARISON_POLICY/);
  second.execution_model.slippage_bps=0;second.predictor={name:"SVR",mode:"PRECOMPUTED_OFFLINE",external_execution_allowed:true,receipts:[]};assert.throws(()=>validateRequest(second),/EXTERNAL_EXECUTION/);
});
function observationBundle(){
  const r=syntheticRequest(),sourceConfig=clone(r.config);sourceConfig.expected_account_id="SOURCE-ACCOUNT";sourceConfig.nativeProtection="oco";sourceConfig.quant={enabled:true};sourceConfig.streaming=true;
  const market=r.events[0],input={now:r.start_at,config:sourceConfig,market:{calendar:r.calendar,assets:Object.fromEntries(sourceConfig.universe.map(a=>[a.symbol,a])),quotes:Object.fromEntries(market.quotes.map(q=>[q.symbol,{bid:q.bid,ask:q.ask,at:q.market_at,received:q.market_at}])),bars:clone(market.bars),daily:clone(market.daily)},observation_coverage:{selected_symbols:["AAPL"],registered_symbols:["AAPL","OTHER"],complete_registered_universe:false}};
  const frame={schema:"HARPOON_PROSPECTIVE_FRAME_1",account_id:"SOURCE-ACCOUNT",data_origin:"RUNTIME_OBSERVATION_UNVERIFIED",external_authenticity_verified:false,runtime_input:input,observation:{execution_allowed:false,liveApproved:false},sampled_execution_depth:null,policy_parity_verified:false,financial_acceptance_allowed:false};
  frame.source_frame_sha256=require("node:crypto").createHash("sha256").update(JSON.stringify(frame)).digest("hex");
  return {bundle:{schema:"HARPOON_OBSERVATION_EXPORT_1",account_id:"SOURCE-ACCOUNT",frames:[frame],complete_export:false,execution_allowed:false,liveApproved:false},assumptions:{initial_cash_usd:r.initial_cash_usd,execution_model:r.execution_model}};
}
test("prospective adapter verifies hashes and evaluates real plugins without manufacturing depth or fills",async()=>{
  const {bundle,assumptions}=observationBundle(),input=fromObservationExport(bundle,assumptions),out=await runReplay(input);
  assert(input.events.filter(e=>e.type==="market").every(e=>e.quotes.every(q=>q.executable_qty===0)));
  assert.equal(out.result.order_actions.length,0);assert.equal(out.result.fills.length,0);assert(out.result.decisions[0].signals.length>0);
  assert.equal(out.scope.components.includes("Coordinator.entries"),false);assert.equal(out.scope.observation_adapter.frames[0].coverage.complete_registered_universe,false);
  assert.equal(out.financial_acceptance_allowed,false);assert.equal(input.source_evidence.source_account_positions_adopted,false);
});
test("prospective adapter rejects altered frames and refuses unspecified hypothetical costs",()=>{
  let {bundle,assumptions}=observationBundle();bundle.frames[0].runtime_input.market.quotes.AAPL.bid=1;assert.throws(()=>fromObservationExport(bundle,assumptions),/FRAME_HASH_MISMATCH/);
  ({bundle,assumptions}=observationBundle());assumptions.execution_model.fees_bps_per_side=null;assert.throws(()=>fromObservationExport(bundle,assumptions),/UNKNOWN_COST/);
});
test("missing daily history remains missing in a sampled frame and cannot claim plugin parity",async()=>{
  const {bundle,assumptions}=observationBundle(),frame=bundle.frames[0];delete frame.runtime_input.market.daily;delete frame.source_frame_sha256;frame.source_frame_sha256=require("node:crypto").createHash("sha256").update(JSON.stringify(frame)).digest("hex");
  const input=fromObservationExport(bundle,assumptions),out=await executeReplay(input);assert(input.source_evidence.frames[0].missing_histories.includes("daily"));assert.equal(out.decisions[0].signals.length,0);
});
test("a repeated snapshot quote preserves original receipt and creates no extra observations of liquidity",async()=>{
  const {bundle,assumptions}=observationBundle(),second=clone(bundle.frames[0]);second.runtime_input.now+=1000;delete second.source_frame_sha256;second.source_frame_sha256=require("node:crypto").createHash("sha256").update(JSON.stringify(second)).digest("hex");bundle.frames.push(second);
  const input=fromObservationExport(bundle,assumptions);assert(input.source_evidence.rejections.some(r=>r.reason==="REPEATED_OR_REGRESSING_QUOTE_NO_NEW_LIQUIDITY"));assert.equal(input.events.filter(e=>e.type==="market")[1].quotes.length,0);
  const out=await executeReplay(input);assert.equal(out.fills.length,0);
});
module.exports={tpRequest,partialRequest,cryptoRequest};
