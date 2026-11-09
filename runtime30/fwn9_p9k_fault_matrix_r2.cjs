"use strict";
/**
 * FWN9/M11 P9K — offline event-sourced, two-cell execution-fault laboratory.
 * It exercises REAL frozen reservation contracts; fills are explicit input
 * receipts, never generated from OHLC, and no broker or order interface exists.
 * This is an engineering harness, NOT a native market-equivalence certificate.
 */
const A=require("node:assert/strict");
const R=require("./ultimate_reservations.js");
const DAY=86400000, HOLD=72*3600000, EPS=1e-7;
const SYMBOL_CELL=Object.freeze({SYNA:"EQUITY",SYNB:"CRYPTO"});
const LIMITS=Object.freeze({capital:20000,gross:.12,asset:.12,
  openRisk:.0025,risk:.0025,loss:.02,drawdown:.08,holdMs:HOLD});
function need(ok,code){A.ok(ok,"P9K_"+code);}
function positive(v){return typeof v==="number"&&Number.isFinite(v)&&v>0;}
function nonnegative(v){return typeof v==="number"&&Number.isFinite(v)&&v>=0;}
function natural(v){return Number.isSafeInteger(v)&&v>=0;}
function assertTime(ev){
  need(natural(ev.knownAt)&&natural(ev.effectiveAt)&&
    ev.effectiveAt<=ev.knownAt,"INVALID_KNOWNAT");
}
function eventEquity(s){
  let inventory=0,exitFee=0;
  for(const p of Object.values(s.positions)){
    const q=s.quotes[p.symbol];
    need(q&&positive(q.price)&&q.knownAt<=s.clock,"UNOBSERVED_POSITION_QUOTE");
    inventory+=p.remaining*q.price;
    exitFee+=p.remaining*s.perSideFee;
  }
  const equity=s.cash+inventory-exitFee;
  need(Number.isFinite(equity)&&equity>0,"NONPOSITIVE_EQUITY");
  return {equity,inventory,exitFee};
}
function pendingCash(s){
  return Object.values(s.orders).filter(o=>o.pending>0)
    .reduce((n,o)=>n+o.pending*o.limitPrice+o.pending*s.perSideFee,0);
}
function totals(s){
  const e=eventEquity(s);
  const snapshot=R.snapshotFundedReservations(s.book,s.clock);
  return {...e,equityUsd:e.equity,inventoryUsd:e.inventory,
    exitFeeUsd:e.exitFee,physicalCashUsd:s.cash,feesPaidUsd:s.feesPaid,
    externalCostsUsd:s.externalCosts,impactShortfallUsd:s.impactShortfall,
    pendingCashUsd:pendingCash(s),availablePhysicalUsd:s.cash-pendingCash(s),
    reservedRiskUsd:snapshot.riskUsd,
    reservedNotionalUsd:snapshot.notionalUsd,
    reservationCount:snapshot.reservations.length,
    originalReservationExposureUsd:snapshot.notionalUsd,
    peakEquityUsd:s.peak,sessionBaselineUsd:s.sessionBaseline,
    observedDrawdown:1-e.equity/s.peak,
    currentExposureFraction:e.inventory/e.equity,
    clock:s.clock,halted:s.outage};
}
function roll(s,now){
  const day=Math.floor(now/DAY);
  if(s.startDay===null){
    need(s.clock===-1&&s.startDay===null,"START_DAY_INVARIANT");
    s.startDay=day;s.lastDay=day;s.sessionBaseline=LIMITS.capital;
    s.externalCosts+=s.calendarCost;s.cash-=s.calendarCost;
  }else if(day>s.lastDay){
    s.sessionBaseline=eventEquity(s).equity;
    const newDays=day-s.lastDay;
    s.externalCosts+=newDays*s.calendarCost;
    s.cash-=newDays*s.calendarCost;
    s.lastDay=day;
  }
}
function observe(s){
  const e=eventEquity(s);
  s.peak=Math.max(s.peak,e.equity);
  s.observations++;
  return e.equity;
}
function gate(s){
  const equity=eventEquity(s).equity;
  need(equity>s.sessionBaseline*(1-LIMITS.loss),"DAILY_LOSS_ADMISSION");
  need(equity>s.peak*(1-LIMITS.drawdown),"DRAWDOWN_ADMISSION");
  for(const p of Object.values(s.positions))
    need(s.clock-p.openEffectiveAt<=HOLD,"EXPIRED_UNSETTLED_POSITION");
}
function request(s,ev){
  need(!s.outage,"OUTAGE_HALTS_ADMISSION");
  need(ev.cell===SYMBOL_CELL[ev.symbol],"CELL_ASSET_MAPPING");
  need(typeof ev.orderId==="string"&&ev.orderId.length>0&&!s.orders[ev.orderId],
    "ORDER_ID_DUPLICATE");
  need(Number.isSafeInteger(ev.quantity)&&ev.quantity>0&&
    positive(ev.limitPrice)&&positive(ev.stopDistance),"INVALID_ORDER");
  const quote=s.quotes[ev.symbol];
  need(quote&&quote.knownAt<=ev.knownAt&&quote.effectiveAt<=ev.knownAt,
    "FUTURE_OR_MISSING_ADMISSION_QUOTE");
  need(ev.limitPrice<=quote.price*1.003+0.011,
    "IOC_CEILING_ABOVE_REGISTERED_30BPS");
  gate(s);
  const n=ev.quantity, fees=2*n*s.perSideFee;
  const reservation={id:ev.orderId,symbol:ev.symbol,decisionAt:ev.knownAt,
    quantity:n,riskUsd:n*ev.stopDistance+fees,
    notionalUsd:n*ev.limitPrice,cashUsd:n*(ev.limitPrice+s.perSideFee)};
  need(s.cash-pendingCash(s)>=reservation.cashUsd-EPS,
    "INSUFFICIENT_PHYSICAL_CASH");
  const physical=s.cash;
  const spent=Object.values(s.orders).reduce((v,o)=>v+o.filled*o.entryCostPerShare,0);
  // Source book conserves full original commitments even after partial exits.
  // The physical cash gate above is separate and does not double count spent principal.
  const accepted=R.reserveFundedEntry(s.book,reservation,{
    equity:eventEquity(s).equity,cashAvailableUsd:physical+spent,
    riskFraction:LIMITS.risk,openRiskFraction:LIMITS.openRisk,
    grossFraction:LIMITS.gross,assetFraction:LIMITS.asset});
  if(accepted.status!=="RESERVED")
    return {status:"REFUSED",reason:accepted.reason,cell:ev.cell};
  s.book=accepted.book;
  s.orders[ev.orderId]={id:ev.orderId,cell:ev.cell,symbol:ev.symbol,
    decisionAt:ev.knownAt,limitPrice:ev.limitPrice,original:n,
    filled:0,pending:n,entryCostPerShare:0,status:"PENDING",
    effectiveOpenedAt:null,entrySpendUsd:0,exitProceedsUsd:0,
    totalEntryFeesUsd:0,totalExitFeesUsd:0};
  return {status:"RESERVED",cell:ev.cell,orderId:ev.orderId};
}
function receipt(s,ev){
  need(!s.outage,"OUTAGE_RECEIPT_NOT_YET_OBSERVED");
  const o=s.orders[ev.orderId];
  need(o&&o.decisionAt<=ev.effectiveAt&&o.decisionAt<=ev.knownAt,
    "UNKNOWN_OR_PREDECISION_RECEIPT");
  const qty=ev.quantity;
  const type=ev.type;
  if(type==="ENTRY_FILL"){
    need(Number.isSafeInteger(qty)&&qty>0&&qty<=o.pending,
      "ENTRY_OVERFILL_OR_NONPOSITIVE");
    need(positive(ev.price)&&ev.price<=o.limitPrice+EPS,
      "ENTRY_PRICE_EXCEEDS_IOC_CEILING");
    need(!["NO_FILL","CLOSED","REJECTED"].includes(o.status),
      "FILL_AFTER_TERMINAL");
    need(ev.effectiveAt>=o.decisionAt&&
      (o.effectiveOpenedAt===null||ev.effectiveAt>=o.effectiveOpenedAt),
      "ENTRY_EFFECTIVE_CLOCK_REGRESSION");
    const spent=qty*(ev.price+s.perSideFee);
    need(s.cash>=spent-EPS,"PHYSICAL_CASH_EXHAUSTED");
    s.cash-=spent;s.feesPaid+=qty*s.perSideFee;
    s.impactShortfall+=qty*Math.max(0,ev.price-s.quotes[o.symbol].price);
    o.pending-=qty;o.filled+=qty;o.entrySpendUsd+=qty*ev.price;
    o.totalEntryFeesUsd+=qty*s.perSideFee;
    o.entryCostPerShare=o.entrySpendUsd/o.filled;
    o.effectiveOpenedAt??=ev.effectiveAt;
    o.status=o.pending>0?"PARTIAL":"OPEN";
    const p=s.positions[o.id]??{id:o.id,cell:o.cell,symbol:o.symbol,
      remaining:0,openEffectiveAt:o.effectiveOpenedAt};
    p.remaining+=qty;s.positions[o.id]=p;
    s.book=R.recordFundedReservationObservation(s.book,{id:o.id,kind:"OPENED",
      at:ev.effectiveAt,knownAt:ev.knownAt,
      remainingQuantity:p.remaining,pendingQuantity:o.pending});
    const q=s.quotes[o.symbol];
    if(q.knownAt<=ev.knownAt)s.quotes[o.symbol]={price:ev.price,
      knownAt:ev.knownAt,effectiveAt:ev.effectiveAt};
    return {status:o.status,filled:o.filled,pending:o.pending};
  }
  if(type==="ENTRY_REJECT"||type==="ENTRY_NO_FILL"||type==="ENTRY_EXPIRE"){
    need(o.pending>0,"NO_PENDING_ENTRY_TO_RESOLVE");
    o.pending=0;
    if(o.filled===0){
      o.status=type==="ENTRY_NO_FILL"?"NO_FILL":"REJECTED";
      s.book=R.recordFundedReservationObservation(s.book,{id:o.id,
        kind:"NO_FILL",at:ev.effectiveAt,knownAt:ev.knownAt,
        remainingQuantity:0,pendingQuantity:0});
      return {status:o.status,inventory:0,reservationReleased:true};
    }
    // Partial pending cancellation does NOT release original opened reservation.
    o.status="PARTIAL_LOCKED";
    const p=s.positions[o.id];
    s.book=R.recordFundedReservationObservation(s.book,{id:o.id,kind:"OPENED",
      at:ev.effectiveAt,knownAt:ev.knownAt,
      remainingQuantity:p.remaining,pendingQuantity:0});
    return {status:o.status,inventory:p.remaining,reservationReleased:false};
  }
  if(type==="EXIT_FILL"){
    need(Number.isSafeInteger(qty)&&qty>0&&nonnegative(ev.price),
      "INVALID_EXIT_FILL");
    need(o.filled>0&&s.positions[o.id]&&qty<=s.positions[o.id].remaining,
      "EXIT_OVERDRAW");
    need(o.pending===0,"EXIT_WITH_UNRESOLVED_PENDING_ENTRY");
    need(ev.effectiveAt>=o.effectiveOpenedAt&&
      ev.effectiveAt-o.effectiveOpenedAt<=HOLD,
      "HOLD_72H_BREACH");
    const amount=qty*(ev.price-s.perSideFee);
    s.cash+=amount;s.feesPaid+=qty*s.perSideFee;
    s.impactShortfall+=qty*Math.max(0,s.quotes[o.symbol].price-ev.price);
    o.exitProceedsUsd+=qty*ev.price;o.totalExitFeesUsd+=qty*s.perSideFee;
    const p=s.positions[o.id];p.remaining-=qty;
    const remaining=p.remaining;
    if(remaining===0){
      delete s.positions[o.id];o.status="CLOSED";
    }else o.status="REDUCED";
    s.book=R.recordFundedReservationObservation(s.book,{id:o.id,
      kind:remaining===0?"CLOSED":"OPENED",
      at:ev.effectiveAt,knownAt:ev.knownAt,
      remainingQuantity:remaining,pendingQuantity:0});
    return {status:o.status,remaining,netCashReceiptUsd:amount};
  }
  need(false,"UNSUPPORTED_EXECUTION_RECEIPT");
}
class FaultMatrix {
 constructor({calendarCostPerDayUsd=1,perSideFeeUsd=.005}={}){
   need(calendarCostPerDayUsd===1||calendarCostPerDayUsd===2,
     "REGISTERED_COST_WORLD_ONLY");
   need(perSideFeeUsd===.005,"ENGINEERING_REGISTERED_FEE_ONLY");
   this.state={schema:"FWN9_P9K_FAULT_MATRIX_1",clock:-1,startDay:null,lastDay:null,
     calendarCost:calendarCostPerDayUsd,perSideFee:perSideFeeUsd,
     cash:20000,externalCosts:0,feesPaid:0,impactShortfall:0,
     book:R.emptyFundedReservationBook(),quotes:{},positions:{},orders:{},
     processed:{},log:[],peak:20000,sessionBaseline:20000,
     observations:0,outage:false};
 }
 apply(ev){
   need(ev&&typeof ev.id==="string"&&ev.id.length>0,
     "EVENT_ID_REQUIRED");
   const existing=this.state.processed[ev.id];
   if(existing){
     need(existing===JSON.stringify(ev),"CONFLICTING_EVENT_ID");
     return {status:"IDEMPOTENT",...this.snapshot()};
   }
   assertTime(ev);
   need(ev.knownAt>=this.state.clock,"RECEIPT_CLOCK_REGRESSION");
   const s=structuredClone(this.state);
   roll(s,ev.knownAt);s.clock=ev.knownAt;
   let result;
   if(ev.type==="QUOTE"){
     need(ev.symbol in SYMBOL_CELL&&positive(ev.price),"INVALID_QUOTE");
     const prev=s.quotes[ev.symbol];
     need(!prev||ev.effectiveAt>=prev.effectiveAt,"QUOTE_EVENT_TIME_REGRESSION");
     s.quotes[ev.symbol]={price:ev.price,knownAt:ev.knownAt,
       effectiveAt:ev.effectiveAt};
     result={status:"QUOTE_OBSERVED"};
   }else if(ev.type==="ADMIT")result=request(s,ev);
   else if(ev.type==="OUTAGE"){
     need(!s.outage,"DUPLICATE_OUTAGE");s.outage=true;
     result={status:"HALTED"};
   }else if(ev.type==="RECOVER"){
     need(s.outage,"RECOVERY_WITHOUT_OUTAGE");s.outage=false;
     result={status:"RECOVERED",ordersUnchanged:true};
   }else if(ev.type==="ENTRY_FILL"||ev.type==="ENTRY_REJECT"||
       ev.type==="ENTRY_NO_FILL"||ev.type==="ENTRY_EXPIRE"||
       ev.type==="EXIT_FILL")result=receipt(s,ev);
   else if(ev.type==="CANCEL_REQUEST"){
     const o=s.orders[ev.orderId];
     need(o&&o.pending>0,"CANCEL_WITHOUT_PENDING");
     result={status:"CANCEL_REQUEST_NOT_RECEIPT",reservationReleased:false};
   }else need(false,"UNSUPPORTED_EVENT");
   observe(s);
   const t=totals(s);
   need(t.availablePhysicalUsd>=-EPS,"UNFUNDED_PENDING_COMMITMENT");
   s.processed[ev.id]=JSON.stringify(ev);
   s.log.push({id:ev.id,type:ev.type,at:ev.effectiveAt,knownAt:ev.knownAt,
     status:result.status,equityUsd:t.equity,physicalCashUsd:t.physicalCashUsd});
   this.state=s;
   return {...result,...this.snapshot()};
 }
 snapshot(){
   const s=this.state;
   if(s.clock<0)return {equityUsd:20000,physicalCashUsd:20000,
      reservations:0,positions:0,unopened:true};
   const t=totals(s);
   return {...t,positions:Object.keys(s.positions).length,
     cells:{"EQUITY":Object.values(s.positions).filter(p=>p.cell==="EQUITY").length,
      "CRYPTO":Object.values(s.positions).filter(p=>p.cell==="CRYPTO").length}};
 }
 audit(){
   const s=this.state,t=this.snapshot();
   need(t.availablePhysicalUsd>=-EPS,"UNFUNDED_CASH_AUDIT");
   need(s.book.reservations.every(r=>r.decisionAt<=s.clock),
     "FUTURE_RESERVATION");
   const ss=R.snapshotFundedReservations(s.book,s.clock);
   for(const r of ss.reservations){
     need(s.orders[r.id]&&s.orders[r.id].status!=="CLOSED"&&
        s.orders[r.id].status!=="NO_FILL"&&
        s.orders[r.id].status!=="REJECTED",
        "PHANTOM_RESERVATION");
   }
   for(const p of Object.values(s.positions)){
     need(p.remaining>0&&s.orders[p.id]&&
       s.clock-p.openEffectiveAt<=HOLD,"INVENTORY_OR_HOLD_UNRESOLVED");
   }
   const sourceFees=Object.values(s.orders).reduce((n,o)=>
     n+o.totalEntryFeesUsd+o.totalExitFeesUsd,0);
   need(Math.abs(sourceFees-s.feesPaid)<=EPS,"FEE_RECONCILIATION");
   return {schema:"FWN9_P9K_FAULT_MATRIX_AUDIT_1",accountedEvents:s.log.length,
     sourceReserveBookVersion:s.book.schema,
     feeReconciliation:true,inventoryConsistent:true,
     pendingCashFullyBacked:true,sharedPortfolio:true,
     noLiveOrders:true,allNativeM9PathsProven:false,
     fullPartialRejectOutageImpactProvedUnderM9:false,
     multicellEngineParityProvedUnderM9:false,
     nativeOHLCExecutable:false,n9sEligible:false,
     ...t};
 }
}
module.exports={FaultMatrix,LIMITS};
