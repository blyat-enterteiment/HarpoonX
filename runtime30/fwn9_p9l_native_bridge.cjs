"use strict";
/** FWN9 M11/P9L: READ-ONLY source-to-P9K integration on an actual native replay.
 * Market-modeled campaign receipts stay explicitly MODELED; no broker, orders,
 * extrapolated OHLC fill, new signals, or economic promotion.
 */
const A=require("node:assert/strict");
const N=require("./profit8_replay.js");
const M9=require("./modulation9_exit.cjs");
const R=require("./ultimate_reservations.js");
const H=require("./fwn9_p9h_cash_ledger.cjs");
const J=require("./fwn9_p9j_native_risk_clock.cjs");
const {FaultMatrix}=require("./fwn9_p9k_fault_matrix_r2.cjs");
const EPS=1e-6;
const CELL=Object.freeze({SYNA:"EQUITY",SYNB:"CRYPTO"});
const allowed=new Set(["MODELED_CAMPAIGN","MODELED_IOC_NO_FILL"]);
function need(ok,tag){A.ok(ok,"P9L_"+tag);}
function approx(a,b){return Number.isFinite(a)&&Number.isFinite(b)&&
  Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));}
function extract({native,signals,data,protocol,limits,costPerCalendarDayUsd=1}){
 need(native?.metadata?.executionNature?.startsWith("HISTORICAL_MODELED_OHLCV") &&
   native.reservationBook?.schema==="HARPOON_FUNDED_RESERVATIONS_1" &&
   Array.isArray(native.funded)&&Array.isArray(native.states)&&
   Array.isArray(native.modeledNoFills),"EXACT_MODELED_SOURCE_REPLAY_REQUIRED");
 need(limits.capitalUsd===20000&&limits.grossFraction===.12&&
   limits.openRiskFraction===.0025&&limits.dailyLoss===.02&&limits.maxDrawdown===.08,
   "ORIGINAL_RISK_LIMITS_REQUIRED");
 need(protocol.costs.perSideUsd===.005&&
   (costPerCalendarDayUsd===1||costPerCalendarDayUsd===2)&&
   data.splitEvents?.length===0&&data.cashDividends?.length===0,
   "REGISTERED_ENGINEERING_SCOPE_ONLY");
 need(Array.isArray(signals)&&signals.length>0&&
   signals.every((v,i)=>i===0||v.at>=signals[i-1].at),
   "SOURCE_ORDER_REQUIRED");
 const signalIds=new Set(signals.map(s=>s.id));
 need(signalIds.size===signals.length,"DUPLICATE_SOURCE_SIGNAL_ID");
 const sourceStates=new Map(native.states.map(s=>[s.opportunity.id,s]));
 need(sourceStates.size===native.states.length &&
   native.states.every(s=>signalIds.has(s.opportunity.id)),"UNKNOWN_NATIVE_DECISION");
 const refusals=new Set(native.preEntryRefusals.map(r=>r.signalId));
 need(signals.every(s=>sourceStates.has(s.id)||refusals.has(s.id)),
   "MISSING_SOURCE_DISPOSITION");
 const sourceReservations=new Map(native.reservationBook.reservations.map(r=>[r.id,r]));
 need(sourceReservations.size===native.reservationBook.reservations.length,
   "DUPLICATE_SOURCE_RESERVATIONS");
 const funded=new Map(native.funded.map(t=>[t.id,t]));
 need(funded.size===native.funded.length,"DUPLICATE_SOURCE_CAMPAIGN");
 const noFill=new Map(native.modeledNoFills.map(n=>[n.signalId,n]));
 need(noFill.size===native.modeledNoFills.length,
   "DUPLICATE_SOURCE_NO_FILL");
 const prices=M9.causalPriceLookup(data.series,N.causalReferencePrice);
 const operations=[],sourceAccepted=[],allStates=[],decisionRows=[];
 let n=0;
 const add=(body,priority)=>operations.push({
   ...body,id:"native:"+String(n++).padStart(6,"0")+":"+body.type,
   __priority:priority});
 const emitQuote=(symbol,at)=>{
   const series=data.series.find(s=>s.symbol===symbol);
   need(series&&series.pointValue===1,"UNKNOWN_ASSET_OR_POINT_VALUE");
   const q=prices({at},series);
   need(q?.status==="AVAILABLE"&&q.sourceAvailableAt<=at&&
     Number.isFinite(q.price)&&q.price>0,"SOURCE_CAUSAL_QUOTE_MISSING");
   add({type:"QUOTE",symbol,price:q.price,
     effectiveAt:q.sourceAvailableAt,knownAt:at,
     sourceMarketAvailableAt:q.sourceAvailableAt},0);
 };
 const seenRes=new Set();
 for(const signal of signals){
   const s=sourceStates.get(signal.id);
   if(!s){allStates.push({id:signal.id,status:"EARLY_REFUSED"});continue;}
   if(s.reservationStatus!=="RESERVED"){
     need(s.status==="REFUSED_BEFORE_ENTRY"||s.status==="PLANNED",
       "NONRESERVED_STATE_UNKNOWN");
     allStates.push({id:signal.id,status:s.status});continue;
   }
   need(allowed.has(s.status)&&!seenRes.has(signal.id),
     "RESERVED_STATUS_UNSUPPORTED");
   seenRes.add(signal.id);
   const r=sourceReservations.get(signal.id);
   const committed=s.profit8CommittedReservation,qp=s.iocPlan;
   need(r&&committed&&qp?.status==="PLANNED"&&
     r.quantity===s.quantity&&r.quantity===committed.quantity&&
     approx(r.notionalUsd,committed.notionalUsd)&&
     approx(r.riskUsd,committed.riskUsd)&&
     approx(r.cashUsd,committed.cashUsd)&&
     approx(r.notionalUsd,r.quantity*qp.priceCeiling)&&
     Number.isSafeInteger(r.decisionAt)&&r.decisionAt===signal.at,
     "SOURCE_RESERVATION_CONTRACT_MISMATCH");
   const riskDistance=r.riskUsd/r.quantity-2*protocol.costs.perSideUsd;
   need(riskDistance>0&&Number.isFinite(riskDistance),
     "SOURCE_RISK_DISTANCE_INVALID");
   for(const symbol of Object.keys(CELL))emitQuote(symbol,signal.at);
   add({type:"ADMIT",orderId:signal.id,cell:CELL[signal.symbol],
     symbol:signal.symbol,quantity:r.quantity,
     limitPrice:qp.priceCeiling,stopDistance:riskDistance,
     effectiveAt:signal.at,knownAt:signal.at},3);
   const f=funded.get(signal.id),nf=noFill.get(signal.id);
   need(Boolean(f)!==Boolean(nf),"SOURCE_EXECUTION_DISPOSITION_AMBIGUOUS");
   if(nf){
     need(s.status==="MODELED_IOC_NO_FILL"&&
       nf.plannedEntryAt===nf.resolutionAt&&nf.plannedEntryAt>signal.at&&
       nf.positionOpened===false&&nf.modeledTradingPnlUsd===0,
       "SOURCE_IOC_NO_FILL_CHRONOLOGY");
     const receipts=r.observations;
     need(receipts.length===1&&receipts[0].kind==="NO_FILL" &&
       receipts[0].knownAt===nf.resolutionAt,
       "SOURCE_IOC_NO_FILL_RESERVATION_MISMATCH");
     add({type:"ENTRY_NO_FILL",orderId:signal.id,
       effectiveAt:nf.plannedEntryAt,knownAt:nf.resolutionAt},1);
   }else{
     need(s.status==="MODELED_CAMPAIGN"&&f.direction===1&&
       f.quantity===r.quantity&&f.symbol===signal.symbol&&
       Array.isArray(f.inventoryEvents)&&f.inventoryEvents.length>=2,
       "SOURCE_NATIVE_FUNDED_TRACE_MISSING");
     const entry=f.inventoryEvents.filter(e=>e.kind==="ENTRY");
     need(entry.length===1&&entry[0].at===f.opened&&
       entry[0].knownAt===f.opened&&entry[0].quantityDelta===f.quantity&&
       approx(entry[0].filledPrice,f.entry),"SOURCE_ENTRY_MODEL_RECEIPT");
     add({type:"ENTRY_FILL",orderId:signal.id,quantity:f.quantity,
       price:entry[0].filledPrice,effectiveAt:f.opened,knownAt:f.opened},1);
     const xs=f.inventoryEvents.filter(e=>e.kind==="EXIT");
     need(xs.length>0,"SOURCE_EXIT_TRACE_REQUIRED");
     for(const x of xs){
       need(Number.isSafeInteger(x.at)&&Number.isSafeInteger(x.knownAt)&&
         x.knownAt>=x.at&&Number.isSafeInteger(-x.quantityDelta)&&
         x.quantityDelta<0&&x.filledPrice>=0,"SOURCE_EXIT_RECEIPT_INVALID");
       add({type:"EXIT_FILL",orderId:signal.id,quantity:-x.quantityDelta,
         price:x.filledPrice,effectiveAt:x.at,knownAt:x.knownAt},1);
     }
     need(xs.reduce((v,x)=>v-x.quantityDelta,0)===f.quantity,
       "SOURCE_EXIT_QUANTITY_NOT_CONSERVED");
   }
   sourceAccepted.push(signal.id);
   decisionRows.push({id:signal.id,at:signal.at,
     sourceReservation:r,sourceState:s});
   allStates.push({id:signal.id,status:s.status});
 }
 need(seenRes.size===sourceReservations.size,
   "ORPHAN_SOURCE_RESERVATION");
 need(funded.size+noFill.size===seenRes.size,
   "SOURCE_FUNDED_NOFILL_PARTITION");
 operations.sort((a,b)=>a.knownAt-b.knownAt ||
   a.__priority-b.__priority ||
   a.effectiveAt-b.effectiveAt ||
   a.id.localeCompare(b.id));
 return {operations:operations.map(({__priority,...e})=>e),
   sourceAccepted,allStates,decisionRows,sourceReservations,
   sourceFunded:funded,sourceNoFill:noFill,costPerCalendarDayUsd};
}
function bridge(args){
 const x=extract(args),{native,signals,data,protocol,limits}=args;
 const engine=new FaultMatrix({calendarCostPerDayUsd:x.costPerCalendarDayUsd,
   perSideFeeUsd:protocol.costs.perSideUsd});
 const rowById=new Map(x.decisionRows.map(x=>[x.id,x]));
 const accounted=[];
 for(const e of x.operations){
   const result=engine.apply(e);
   if(e.type==="ADMIT"){
     need(result.status==="RESERVED","P9K_REJECTS_NATIVE_SOURCE_ADMISSION");
     const state=rowById.get(e.orderId);
     const own=engine.state.book.reservations.find(r=>r.id===e.orderId);
     need(own&&approx(own.riskUsd,state.sourceReservation.riskUsd)&&
       approx(own.notionalUsd,state.sourceReservation.notionalUsd)&&
       approx(own.cashUsd,state.sourceReservation.cashUsd),
       "P9K_NATIVE_APPROVAL_CAPACITY_OR_COMMITMENT_PARITY");
     const pending=R.snapshotFundedReservations(engine.state.book,e.knownAt);
     const nativeAtDecision=state.sourceState.reservationAfter;
     need(approx(nativeAtDecision.riskUsd,pending.riskUsd)&&
       approx(nativeAtDecision.notionalUsd,pending.notionalUsd),
       "P9K_NATIVE_PREVIOUS_RESERVATION_PARITY");
     // Source quote/cash are audited in source time, not falsely assumed equal
     // to conservative closed-campaign cashPoolAt().
     const proof=H.auditDecision({nativeReplay:native,data,protocol,limits,
       state:state.sourceState,costPerCalendarDayUsd:x.costPerCalendarDayUsd});
     accounted.push({id:e.orderId,at:e.knownAt,
       sourcePhysicalCashUsd:proof.physicalCashUsd,
       shadowPhysicalCashUsd:result.physicalCashUsd,
       nativeCashPoolUsd:proof.nativeClosedCampaignPoolUsd,
       sourceEquityUsd:proof.observedNativeEquityUsd,
       shadowEquityUsd:result.equityUsd,
       sourceRiskUsd:nativeAtDecision.riskUsd,
       shadowRiskUsd:pending.riskUsd,
       sourceFullMarkUsd:proof.conservativeNotionalUsd});
   }
 }
 const risk=J.checkNativeRiskClock({native,signals,data,protocol,limits});
 const s=engine.snapshot(),last=native.curve.at(-1);
 need(last&&Number.isFinite(last.equity_end_usd),
   "NATIVE_EQUITY_MISSING");
 // The final native curve retains full 176-calendar-day charges; P9K derives
 // its own calendar from observed receipts, so only compare when clock covers
 // the native evaluation terminal. Never silently normalize the mismatch.
 const terminal=data.sessions.at(-1).close;
 const already=engine.state.clock;
 if(already<terminal){
   const priceInputs=data.series.map(series=>{
     const q=pricesAtTerminal(data,series,terminal);
     return {id:"native:terminal:"+series.symbol,type:"QUOTE",
       symbol:series.symbol,price:q.price,effectiveAt:q.availableAt,
       knownAt:terminal};
   });
   for(const e of priceInputs)engine.apply(e);
 }
 const final=engine.audit();
 need(approx(final.equityUsd,last.equity_end_usd),
   "P9K_NATIVE_TERMINAL_EQUITY_MISMATCH");
 need(approx(final.feesPaidUsd,
   native.funded.reduce((v,t)=>v+t.feesUsd,0)),
   "P9K_NATIVE_TERMINAL_FEE_MISMATCH");
 need(final.reservationCount===0&&final.positions===0,
   "P9K_NATIVE_TERMINAL_INVENTORY_OR_RESERVE");
 return {schema:"HARPOON_FWN9_P9L_NATIVE_EVENT_BRIDGE_1",
   sourceNature:"HISTORICAL_MODELED_OHLCV_NOT_BROKER_RECEIPTS",
   native_decisions:signals.length,source_accepted:x.sourceAccepted.length,
   source_funded:native.funded.length,source_nofill:native.modeledNoFills.length,
   bridge_events:x.operations.length,all_source_acceptances_checked:true,
   native_ledger_decisions:accounted,nativeRiskClockParity:risk.nativeRiskClockParity,
   sourceWealthUsd:last.equity_end_usd,
   p9kWealthUsd:final.equityUsd,sourceFeeParity:true,
   nativePriceExecutability:false,fullM9Population:false,
   optimizerEligible:false,executionAllowed:false,
   sourceReceiptTape:x.operations,finalSnapshot:final,
   pureOffline:true};
}
function pricesAtTerminal(data,series,at){
 const b=series.bars.filter(b=>b.availableAt<=at).at(-1);
 need(b&&b.c>0,"NO_TERMINAL_CAUSAL_QUOTE");
 return {price:b.c,availableAt:b.availableAt};
}
module.exports={extract,bridge};
