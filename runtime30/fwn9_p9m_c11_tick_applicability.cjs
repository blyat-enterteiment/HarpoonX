"use strict";
/* M11-C11: EX-POST audit, not a trading model. Nonnegative zero-tick SELL
 * proceeds are admissible, positive acquisition prices and OHLC are required.
 * All original engine parameters remain untouched. */
const A=require("node:assert/strict");
const DAY=86400000;
const near=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&
 Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(a),Math.abs(b));
const requireC=(v,msg)=>A.ok(v,"C11_"+msg);
function audit({native,data,limits,costPerDay=1,feePerShare=.005}){
 requireC(limits.capitalUsd===20000&&limits.grossFraction===.12&&
  limits.assetFraction===.12&&limits.riskFraction===.0025&&
  limits.openRiskFraction===.0025&&limits.dailyLoss===.02&&
  limits.maxDrawdown===.08,"LOCKED_LIMITS");
 requireC(data.provenance?.source==="SYNTHETIC_ENGINEERING_ONLY"&&
  data.series.length===2&&data.series.map(s=>s.symbol).sort().join(",")==="SYNA,SYNB"&&
  data.splitEvents.length===0&&data.cashDividends.length===0,"SCOPE");
 requireC((costPerDay===1&&feePerShare===.005)||
  (costPerDay===2&&feePerShare===.01),"COSTS_UNCHANGED");
 const start=data.sessions[0].open,end=data.sessions.at(-1).close;
 const priceMap=new Map();
 for(const s of data.series){
  let lo=Infinity,hi=0;
  requireC(s.pointValue===1&&s.tick===.01,"TICK_SCOPE");
  for(const b of s.bars){
   requireC([b.o,b.h,b.l,b.c].every(p=>Number.isFinite(p)&&p>0)&&
    b.l<=Math.min(b.o,b.c)&&b.h>=Math.max(b.o,b.c)&&
    Number.isSafeInteger(b.t)&&b.end>b.t&&b.availableAt>=b.end,"MARKS");
   lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);
  }
  requireC(lo>0&&Number.isFinite(lo)&&Number.isFinite(hi),"POSITIVE_MARKS");
  priceMap.set(s.symbol,{lo,hi,series:s});
 }
 const events=[],lots=new Map();
 for(const t of native.funded){
  requireC(t.direction===1&&priceMap.has(t.symbol)&&!lots.has(t.id)&&
   Number.isSafeInteger(t.quantity)&&t.quantity>0&&
   t.closed>=t.opened&&t.closed-t.opened<=72*3600000,"NATIVE_LONG_HOLD");
  lots.set(t.id,{symbol:t.symbol,cap:t.quantity,remaining:0});
  for(const e of t.inventoryEvents){
   requireC(Number.isSafeInteger(e.at)&&Number.isSafeInteger(e.knownAt)&&
    e.at>=start&&e.at<=end&&e.knownAt>=e.at&&e.knownAt<=end,"RECEIPT_CAUSAL");
   requireC(Number.isSafeInteger(e.quantityDelta)&&e.quantityDelta!==0&&
    ((e.kind==="ENTRY"&&e.quantityDelta>0)||
     (e.kind==="EXIT"&&e.quantityDelta<0)),"RECEIPT_SIGN");
   requireC(Number.isFinite(e.filledPrice)&&
    (e.kind==="ENTRY"?e.filledPrice>0:e.filledPrice>=0)&&
    Number.isFinite(e.feeUsd)&&e.feeUsd>=0&&
    near(e.feeUsd,Math.abs(e.quantityDelta)*feePerShare),"NONNEGATIVE_SELL_COSTS");
   const v=priceMap.get(t.symbol);
   // DO NOT include a zero sale price in m; it cannot increase the shadow book.
   if(e.kind==="ENTRY")v.lo=Math.min(v.lo,e.filledPrice);
   v.hi=Math.max(v.hi,e.filledPrice);
   events.push({tradeId:t.id,symbol:t.symbol,kind:e.kind,at:e.at,
    knownAt:e.knownAt,quantityDelta:e.quantityDelta,
    filledPrice:e.filledPrice,feeUsd:e.feeUsd});
  }
 }
 const range=Math.max(1,...[...priceMap.values()].map(v=>v.hi/v.lo));
 requireC(Number.isFinite(range)&&range>=1,"FINITE_RANGE");
 events.sort((a,b)=>a.at-b.at||
  (a.kind==="EXIT"?-1:1)-(b.kind==="EXIT"?-1:1)||
  a.tradeId.localeCompare(b.tradeId));
 let cash=20000,days=0,exits=0,zeroExits=0,minCash=cash,violations=0;
 const shadow=()=>cash+[...lots.values()].reduce((n,l)=>
  n+l.remaining*priceMap.get(l.symbol).lo,0);
 const charge=at=>{
  const due=Math.floor(at/DAY)-Math.floor(start/DAY)+1;
  requireC(due>=days,"CALENDAR_ORDER");
  cash-=(due-days)*costPerDay;days=due;
  requireC(cash>=-1e-7,"CASH_DAILY");
  minCash=Math.min(minCash,cash);
 };
 for(const e of events){
  charge(e.at);
  const lot=lots.get(e.tradeId),before=shadow();
  requireC(cash>=-1e-7&&before>=-1e-7,"CASH_BEFORE");
  lot.remaining+=e.quantityDelta;
  requireC(lot.remaining>=0&&lot.remaining<=lot.cap,"QUANTITY_INTEGRITY");
  if(e.kind==="EXIT"){exits++;if(e.filledPrice===0)zeroExits++;}
  cash-=e.quantityDelta*e.filledPrice+e.feeUsd;
  requireC(cash>=-1e-7,"CASH_AFTER");
  const after=shadow();
  const allowance=e.kind==="ENTRY"?before:before*range;
  violations=Math.max(violations,after-allowance);
  requireC(after<=allowance+1e-6,e.kind==="ENTRY"?
   "PURCHASE_SHADOW_MONOTONE":"SELL_SHADOW_ENVELOPE");
  minCash=Math.min(minCash,cash);
 }
 charge(end);
 requireC([...lots.values()].every(x=>x.remaining===0),"CLOSED_INVENTORY");
 const physicalTerminal=cash;
 requireC(physicalTerminal>0&&near(physicalTerminal,native.curve.at(-1).equity_end_usd)&&
  near(native.portfolio.netUsd,physicalTerminal-20000),"INDEPENDENT_CASH_RECONCILE");
 const logBound=Math.log(20000)+(exits+1)*Math.log(range);
 requireC(Math.log(physicalTerminal)<=logBound+1e-7,"LOG_ENVELOPE");
 return {schema:"FWN9_C11_TICK_SUPPORT_AUDIT_1",range,exits,zeroExits,
  minCash,days,feePerShare,costPerDay,physicalTerminal,logBound,violations,
  priceBands:Object.fromEntries([...priceMap].map(([k,v])=>[k,{min:v.lo,max:v.hi}])),
  events,claims:{nativeZeroSellPossible:zeroExits>0,positiveFillGlobal:false,
   revisedNonnegativeSaleEnvelopeScoped:true,nonvacuousWEAKMomentBound:false,
   OHLCSubstepEquivalent:false,N9SInfeasibility:false,N9SAccepted:false},
  budget:{newEconomicAccounts:0,alphaSpent:0,finalM10Opened:0}};
}
module.exports={audit};
