"use strict";
// Causality and fixed-size fill constraints; synthetic values, no fitted strategy.
const test=require("node:test"),assert=require("node:assert/strict");
const {defaultProtocol}=require("../runtime30/ultimate_contracts.js");
const {causalReferencePrice,planFundedEntry,verifyFundedEntryFill,DEFAULT_REPLAY_LIMITS}=require("../runtime30/ultimate_replay.js");
const BAR=300000,BASE=Date.parse("2026-10-15T13:30:00Z");
function fixture(){
  const bars=Array.from({length:4},(_,i)=>({t:BASE+i*BAR,end:BASE+(i+1)*BAR,availableAt:BASE+(i+1)*BAR+3000,o:100+i,h:101+i,l:99+i,c:100+i,v:1000}));
  const signal={id:"SYNTHETIC-CAUSAL-SIZE",symbol:"SPY",hypothesis:"CLOSED_CHANNEL",direction:1,at:BASE+2*BAR+3000,index:3,stopDistance:2,regime:.4};
  const series={symbol:"SPY",root:"SPY",pointValue:1,tick:.01,bars};
  const protocol=defaultProtocol("ALPACA_PROXY"),state={equity:20000,openRisk:0,notional:0};
  return {signal,series,protocol,state};
}
function fill(f,overrides={}){return {id:f.signal.id,symbol:f.signal.symbol,direction:1,opened:f.series.bars[3].t,quantity:10,entry:100,...overrides};}
const budgets={riskBudgetUsd:50,notionalBudgetUsd:2400,cashBudgetUsd:20000,plannedQuantity:10};
test("changing a future fill bar cannot alter the causal price, quantity or decision dates",()=>{
  const f=fixture(),before=planFundedEntry(f.signal,f.series,f.protocol,DEFAULT_REPLAY_LIMITS,f.state);
  assert.equal(before.status,"PLANNED");assert.equal(before.reference.price,101);
  assert.equal(before.reference.sourceAvailableAt,BASE+2*BAR+3000);
  assert.equal(before.quantity,23);
  Object.assign(f.series.bars[3],{o:500,h:501,l:499,c:500});
  Object.assign(f.series.bars[2],{o:700,h:701,l:699,c:700});
  const after=planFundedEntry(f.signal,f.series,f.protocol,DEFAULT_REPLAY_LIMITS,f.state);
  assert.deepEqual(after,before);
});
test("absence of an available completed bar is explicit non-admission, not a zero price",()=>{
  const f=fixture();f.signal.at=BASE+3000;
  const ref=causalReferencePrice(f.signal,f.series);
  assert.equal(ref.status,"NO_CAUSAL_PRICE");assert.equal(ref.price,null);
  const plan=planFundedEntry(f.signal,f.series,f.protocol,DEFAULT_REPLAY_LIMITS,f.state);
  assert.equal(plan.status,"NO_CAUSAL_PRICE");assert.equal("quantity" in plan,false);
});
test("an invalid latest available close cannot fall back silently to a stale valid close",()=>{
  const f=fixture();f.series.bars[1].c=NaN;
  const r=causalReferencePrice(f.signal,f.series);
  assert.equal(r.status,"NO_CAUSAL_PRICE");assert.equal(r.reason,"INVALID_LAST_AVAILABLE_CLOSE");
  assert.equal(r.price,null);assert.equal(r.sourceBarAt,f.series.bars[1].t);
});
test("a price gap breaching the approved notional preserves quantity and unresolved exposure",()=>{
  const f=fixture(),trade=fill(f,{entry:250}),original=JSON.stringify(trade);
  const r=verifyFundedEntryFill(trade,f.signal,f.series,f.protocol,budgets);
  assert.equal(r.status,"NO_FACTIBLE");assert(r.breaches.includes("MODELED_FILL_NOTIONAL_EXCEEDS_EX_ANTE_BUDGET"));
  assert.equal(r.exposure.remainingQuantityAtEntry,10);assert.equal(r.economicPnlUsd,null);
  assert.equal(JSON.stringify(trade),original);
});
test("rounded stop distance and trading friction remain inside the risk budget check",()=>{
  const f=fixture();f.signal.stopDistance=5.001;
  const r=verifyFundedEntryFill(fill(f),f.signal,f.series,f.protocol,budgets);
  assert.equal(r.status,"NO_FACTIBLE");assert(r.modeledRiskUsd>50);
  assert(r.breaches.includes("MODELED_FILL_RISK_EXCEEDS_EX_ANTE_BUDGET"));
});
test("missing or insufficient conservative cash cannot masquerade as funded execution",()=>{
  const f=fixture();
  let r=verifyFundedEntryFill(fill(f),f.signal,f.series,f.protocol,{...budgets,cashBudgetUsd:null});
  assert.equal(r.status,"NO_FACTIBLE");assert(r.breaches.includes("CONSERVATIVE_CASH_BUDGET_UNVERIFIABLE"));
  r=verifyFundedEntryFill(fill(f),f.signal,f.series,f.protocol,{...budgets,cashBudgetUsd:999});
  assert.equal(r.status,"NO_FACTIBLE");assert(r.breaches.includes("MODELED_FILL_COST_EXCEEDS_CONSERVATIVE_CASH"));
});
test("a valid fill check neither reads future exit PnL nor approves another signal's position",()=>{
  const f=fixture(),trade=fill(f),before=verifyFundedEntryFill(trade,f.signal,f.series,f.protocol,budgets);
  assert.equal(before.status,"VERIFIED");
  const later=verifyFundedEntryFill({...trade,netUsd:999999,closed:BASE+100*BAR},f.signal,f.series,f.protocol,budgets);
  assert.deepEqual(later,before);
  const wrong=verifyFundedEntryFill({...trade,id:"OTHER"},f.signal,f.series,f.protocol,budgets);
  assert.equal(wrong.status,"NO_FACTIBLE");assert(wrong.breaches.includes("MODELED_FILL_NOT_BOUND_TO_SIGNAL"));
});
