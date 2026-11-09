"use strict";
/*
 * FWN9 C10 R3: a conditional pathwise wealth envelope on the ACTUAL native
 * cash-share receipt ledger. No broker, new market seed, alpha test or policy.
 * Ex-post price extrema are used only by the auditor; NEVER by a signal.
 */
const A = require("node:assert/strict");
const DAY = 86400000;
const near = (a,b) => Number.isFinite(a) && Number.isFinite(b) &&
  Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(a),Math.abs(b));
function check(x, tag){A.ok(x,"FWN9_C10_"+tag);}
function audit({native,data,limits,costPerDay=1,feePerShare=.005}){
  check(limits.capitalUsd===20000&&limits.grossFraction===.12&&
    limits.assetFraction===.12&&limits.riskFraction===.0025&&
    limits.openRiskFraction===.0025&&limits.dailyLoss===.02&&
    limits.maxDrawdown===.08,"ORIGINAL_LIMITS");
  check(data.provenance?.source==="SYNTHETIC_ENGINEERING_ONLY"&&
    data.series.length===2&&data.series.map(s=>s.symbol).sort().join(",")==="SYNA,SYNB"&&
    data.splitEvents.length===0&&data.cashDividends.length===0,
    "CASH_LONG_TWO_ASSET_SCOPE");
  check((costPerDay===1&&feePerShare===.005)||
    (costPerDay===2&&feePerShare===.01),"LOCKED_SCENARIOS");
  const start=data.sessions[0].open, end=data.sessions.at(-1).close;
  check(Number.isSafeInteger(start)&&Number.isSafeInteger(end)&&start<end,
    "VALID_CALENDAR");
  const map=new Map();
  for(const s of data.series){
    check(s.pointValue===1&&s.bars.length>0,"CASH_SHARES");
    let lo=Infinity,hi=0;
    for(const b of s.bars){
      check(Number.isSafeInteger(b.t)&&Number.isSafeInteger(b.availableAt)&&
        b.t<b.end&&b.end<=b.availableAt&&b.t>=start&&b.end<=end,
        "CAUSAL_BAR_CLOCK");
      check([b.o,b.h,b.l,b.c].every(p=>Number.isFinite(p)&&p>0)&&
        b.l<=Math.min(b.o,b.c)&&b.h>=Math.max(b.o,b.c),
        "POSITIVE_OHLC");
      lo=Math.min(lo,b.l);hi=Math.max(hi,b.h);
    }
    map.set(s.symbol,{lo,hi,series:s});
  }
  const events=[],lots=new Map();
  for(const t of native.funded){
    check(!lots.has(t.id)&&map.has(t.symbol)&&
      t.direction===1&&Number.isSafeInteger(t.quantity)&&t.quantity>0&&
      t.closed>=t.opened&&t.closed-t.opened<=72*3600000,
      "UNIQUE_NATIVE_LONG_LOT");
    lots.set(t.id,{symbol:t.symbol,max:t.quantity,remaining:0});
    for(const e of t.inventoryEvents){
      check(Number.isSafeInteger(e.at)&&Number.isSafeInteger(e.knownAt)&&
        e.at>=start&&e.at<=end&&e.knownAt>=e.at&&e.knownAt<=end,
        "CAUSAL_RECEIPT");
      check(Number.isSafeInteger(e.quantityDelta)&&e.quantityDelta!==0&&
        ((e.kind==="ENTRY"&&e.quantityDelta>0)||
         (e.kind==="EXIT"&&e.quantityDelta<0)),"INTEGER_SIDE");
      check(Number.isFinite(e.filledPrice)&&e.filledPrice>0&&
        Number.isFinite(e.feeUsd)&&e.feeUsd>=0&&
        near(e.feeUsd,Math.abs(e.quantityDelta)*feePerShare),
        "EXECUTED_COSTS");
      const p=map.get(t.symbol);
      p.lo=Math.min(p.lo,e.filledPrice);p.hi=Math.max(p.hi,e.filledPrice);
      events.push({tradeId:t.id,symbol:t.symbol,kind:e.kind,at:e.at,
        knownAt:e.knownAt,quantityDelta:e.quantityDelta,
        filledPrice:e.filledPrice,feeUsd:e.feeUsd});
    }
  }
  const range=Math.max(1,...[...map.values()].map(v=>v.hi/v.lo));
  check(Number.isFinite(range)&&range>=1,"FINITE_PRICE_RANGE");
  // Same effective instant: release a physical exit before a physical entry.
  // Receipts remain unknown until knownAt to the native admission decision.
  events.sort((a,b)=>a.at-b.at||
    (a.kind==="EXIT"?-1:1)-(b.kind==="EXIT"?-1:1)||
    a.tradeId.localeCompare(b.tradeId));
  let cash=20000, chargedDays=0, sales=0, minCash=20000;
  let shadowBefore=20000, maxShadowViolation=0;
  const currentShadow=()=>cash+[...lots.values()].reduce((n,l)=>
    n+l.remaining*map.get(l.symbol).lo,0);
  const dueDays=at=>at<start?0:Math.floor(at/DAY)-Math.floor(start/DAY)+1;
  const chargeCalendar=at=>{
    const days=dueDays(at);
    check(days>=chargedDays,"MONOTONE_CALENDAR");
    cash-=(days-chargedDays)*costPerDay;chargedDays=days;
    check(cash>=-1e-7,"NONNEGATIVE_CASH_CALENDAR");
    minCash=Math.min(minCash,cash);
  };
  for(const e of events){
    chargeCalendar(e.at);
    const lot=lots.get(e.tradeId);
    const before=currentShadow();
    check(before>=-1e-7&&cash>=-1e-7,"SHADOW_FINANCING_BEFORE");
    if(e.quantityDelta>0){
      lot.remaining+=e.quantityDelta;
      check(lot.remaining<=lot.max,"NO_OVERFILLED_LOT");
    }else{
      check(lot.remaining+e.quantityDelta>=0,"NO_SHORT_LOT");
      lot.remaining+=e.quantityDelta;
      sales++;
    }
    cash-=e.quantityDelta*e.filledPrice+e.feeUsd;
    check(cash>=-1e-7,"NONNEGATIVE_CASH_FILL");
    const after=currentShadow();
    if(e.quantityDelta>0){
      maxShadowViolation=Math.max(maxShadowViolation,after-before);
      check(after<=before+1e-6,"BUY_SHADOW_NONINCREASING");
    }else{
      maxShadowViolation=Math.max(maxShadowViolation,after-before*range);
      check(after<=before*range+1e-6,"SELL_SHADOW_RANGE_ENVELOPE");
    }
    minCash=Math.min(minCash,cash);shadowBefore=after;
  }
  chargeCalendar(end);
  const finalShadow=currentShadow();
  const value=[...lots.values()].reduce((n,l)=>{
    if(!l.remaining)return n;
    const s=map.get(l.symbol).series;
    const b=s.bars.filter(b=>b.availableAt<=end).at(-1);
    check(!!b,"TERMINAL_MARK_OBSERVABLE");
    return n+l.remaining*b.c;
  },0);
  const terminal=cash+value;
  check(terminal>0&&cash>=0&&finalShadow>=0,"POSITIVE_TERMINAL");
  check(value<=range*[...lots.values()].reduce((n,l)=>
    n+l.remaining*map.get(l.symbol).lo,0)+1e-6,
    "TERMINAL_MARK_RANGE");
  check(terminal<=range*finalShadow+1e-6,
    "TERMINAL_SHADOW_DOMINANCE");
  const logBound=Math.log(20000)+(sales+1)*Math.log(range);
  check(Math.log(terminal)<=logBound+1e-7,
    "ADMISSION_INDEPENDENT_LOG_UPPER");
  check([...lots.values()].every(l=>l.remaining===0),
    "TERMINAL_NATIVE_INVENTORY_CLOSED");
  check(near(terminal,native.curve.at(-1).equity_end_usd)&&
    near(native.portfolio.netUsd,terminal-20000),
    "INDEPENDENT_NATIVE_TERMINAL_RECONCILIATION");
  const bands=Object.fromEntries([...map].map(([symbol,v])=>
    [symbol,{min:v.lo,max:v.hi}]));
  return {schema:"FWN9_C10_NATIVE_WEALTH_ENVELOPE_1",
    scope:"EX_POST_PATHWISE_CONDITIONAL_NONNEGATIVE_CASH_LONG_ONLY",
    bands,range,sales,minCash,chargedDays,calendarCostUsd:chargedDays*costPerDay,
    feePerShare,physicalTerminalUsd:terminal,physicalCashUsd:cash,
    finalShadowUsd:finalShadow,logUpperTerminalUsd:logBound,
    maxShadowViolationUsd:maxShadowViolation,events,
    nativeTwoAssetFixtureVerified:true,
    universalNoBorrowM9Proven:false,
    fullM9WealthMomentIntegrationProven:false,
    OHLCSubstepPriceEquivalenceProven:false,
    N9SInfeasibilityCertified:false,N9SAccepted:false,
    newEconomicAccounts:0,alphaSpent:0,finalM10Opened:0};
}
module.exports={audit};
