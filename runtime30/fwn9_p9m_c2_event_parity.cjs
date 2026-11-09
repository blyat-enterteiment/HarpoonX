"use strict";
/**
 * FWN9 P9M-C2: native two-symbol event/IOC/reserve audit.
 * Offline synthetic engineering only; does NOT certify executable OHLC prices,
 * observed fills, native population WEAK infeasibility or N9-S.
 */
const A=require("node:assert/strict");
const N=require("./profit8_replay.js");
const R=require("./ultimate_reservations.js");
const C=require("./fwn9_p9j_native_risk_clock.cjs");
const DAY=86400000,HOLD=72*3600000;
const close=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&
  Math.abs(a-b)<1e-7*Math.max(1,Math.abs(a),Math.abs(b));
function need(ok,tag){A.ok(ok,"P9MC2_"+tag);}
function audit({data,signals,native,protocol,limits}){
 need(data.provenance?.source==="SYNTHETIC_ENGINEERING_ONLY" &&
      data.series.length===2 && data.splitEvents.length===0 &&
      data.cashDividends.length===0,"SYNTHETIC_TWO_ASSET_SCOPE");
 need(limits.capitalUsd===20000&&limits.grossFraction===.12&&
      limits.assetFraction===.12&&limits.openRiskFraction===.0025&&
      limits.maxDrawdown===.08&&limits.dailyLoss===.02,
      "UNCHANGED_ADMISSION_LIMITS");
 need(protocol.costs.perSideUsd===.005&&protocol.costs.spreadBps===2&&
      protocol.costs.slippageBps===2,"UNCHANGED_NOMINAL_COSTS");
 need(signals.length===2 && new Set(signals.map(s=>s.symbol)).size===2 &&
      signals.every((s,i)=>i===0||s.at>signals[i-1].at),
      "TWO_DISTINCT_ORDERED_SYMBOLS");
 need(native.funded.length===1&&native.modeledNoFills.length===1,
      "ONE_FILLED_ONE_NO_FILL_REQUIRED");
 const checked=C.checkNativeRiskClock({data,signals,native,protocol,limits});
 need(checked.nativeRiskClockParity&&checked.noFillClockInsertions===1,
      "NATIVE_RISK_CLOCK_PARITY");
 const maps=new Map(data.series.map(s=>[s.symbol,s]));
 const byId=new Map(signals.map(s=>[s.id,s]));
 const states=new Map(native.states.map(s=>[s.opportunity.id,s]));
 const reservationById=new Map(native.reservationBook.reservations.map(r=>[r.id,r]));
 need(reservationById.size===2,"TWO_CANONICAL_RESERVATIONS");
 let causalMarks=0;
 for(const s of signals){
   const row=states.get(s.id),source=maps.get(s.symbol);
   need(row?.reference?.status==="AVAILABLE"&&source,"NATIVE_SOURCE_REFERENCE");
   const ref=N.causalReferencePrice(s,source);
   need(ref.status==="AVAILABLE"&&ref.sourceAvailableAt<=s.at&&
     row.reference.sourceAvailableAt===ref.sourceAvailableAt&&
     row.reference.sourceBarAt===ref.sourceBarAt&&
     close(ref.price,row.reference.price),"CAUSAL_MARK_REFERENCE");
   need(ref.sourceAvailableAt>=source.bars[0].availableAt,
     "MARK_SOURCE_NOT_EMPTY");
   causalMarks++;
 }
 const noFill=native.modeledNoFills[0],missing=byId.get(noFill.signalId);
 need(missing&&noFill.positionOpened===false &&
      noFill.decisionAt===missing.at &&
      noFill.plannedEntryAt===missing.plannedEntryAt &&
      noFill.resolutionAt===noFill.plannedEntryAt &&
      !native.funded.some(t=>t.id===missing.id),
      "NO_FILL_MUST_BE_SOURCE_DECIDED");
 const nr=reservationById.get(missing.id);
 need(nr?.observations.length===1&&nr.observations[0].kind==="NO_FILL"&&
      nr.observations[0].knownAt===noFill.resolutionAt &&
      nr.observations[0].at===noFill.plannedEntryAt &&
      nr.observations[0].pendingQuantity===0 &&
      nr.observations[0].remainingQuantity===0,
      "NO_FILL_SOURCE_RECEIPT_CLOCK");
 const before=R.snapshotFundedReservations(native.reservationBook,noFill.resolutionAt-1);
 const after=R.snapshotFundedReservations(native.reservationBook,noFill.resolutionAt);
 need(before.reservations.some(r=>r.id===missing.id) &&
      !after.reservations.some(r=>r.id===missing.id),
      "NO_EARLY_RELEASE_NO_STALE_RESERVATION");
 need(states.get(missing.id)?.status==="MODELED_IOC_NO_FILL",
      "SOURCE_STATE_NO_FILL");
 const trade=native.funded[0],sourceSignal=byId.get(trade.id);
 need(sourceSignal&&trade.symbol===sourceSignal.symbol&&
      states.get(trade.id)?.status==="MODELED_CAMPAIGN" &&
      trade.opened===sourceSignal.plannedEntryAt &&
      trade.closed>=trade.opened&&trade.closed-sourceSignal.at<=HOLD &&
      trade.inventoryEvents.length>=2,"FILLED_CAMPAIGN_CONTRACT");
 const tr=reservationById.get(trade.id);
 need(tr?.observations.length===2&&tr.observations[0].kind==="OPENED"&&
      tr.observations[1].kind==="CLOSED"&&tr.observations[0].at===trade.opened,
      "TRADE_CANONICAL_RESERVATION_OBSERVATIONS");
 need(tr.observations[1].knownAt>=tr.observations[1].at &&
      tr.observations[1].remainingQuantity===0,
      "TRADE_TERMINAL_RECEIPT");
 const events=[];
 let left=0,fees=0,tradingCash=20000,priorKnown=-1;
 for(const e of trade.inventoryEvents){
   need(e.kind==="ENTRY"||e.kind==="EXIT","EVENT_KIND");
   need(Number.isSafeInteger(e.at)&&Number.isSafeInteger(e.knownAt)&&
        e.knownAt>=e.at&&e.at>=sourceSignal.at&&
        e.at-sourceSignal.at<=HOLD,"EVENT_KNOWNAT_HOLD_72H");
   need(Number.isSafeInteger(e.quantityDelta)&&e.quantityDelta!==0&&
        Number.isFinite(e.filledPrice)&&e.filledPrice>0&&
        close(e.feeUsd,Math.abs(e.quantityDelta)*.005),"FEE_AND_QUANTITY");
   const q=e.quantityDelta;
   if(e.kind==="ENTRY"){need(q>0&&left===0,"SINGLE_ENTRY"); left+=q;
     tradingCash-=q*e.filledPrice+e.feeUsd;
   }else{need(q<0&&left+q>=0,"EXIT_NO_SHORT");
     left+=q;tradingCash+=(-q)*e.filledPrice-e.feeUsd;}
   fees+=e.feeUsd;
   need(e.knownAt>=priorKnown,"OBSERVATION_MONOTONIC");
   priorKnown=e.knownAt;
   events.push({kind:e.kind,at:e.at,knownAt:e.knownAt,
      quantityDelta:q,filledPrice:e.filledPrice,feeUsd:e.feeUsd});
 }
 need(left===0&&close(fees,trade.feesUsd)&&
      close(tradingCash-20000,trade.netUsd),"SELF_FINANCING_TERMINAL");
 const days=Math.floor(data.sessions.at(-1).close/DAY)-
            Math.floor(data.sessions[0].open/DAY)+1;
 const totalFixed=days;
 const terminal=tradingCash-totalFixed;
 need(close(terminal,native.curve.at(-1).equity_end_usd) &&
      close(terminal,checked.terminalEquityUsd),
      "INDEPENDENT_FULL_PORTFOLIO_TERMINAL");
 const beforeSecond=R.snapshotFundedReservations(native.reservationBook,signals[1].at);
 need(beforeSecond.notionalUsd<=.12*states.get(signals[1].id).equity+1e-7,
      "SECOND_ADMISSION_EX_ANTE_NOTIONAL");
 const reserveRows=signals.map(s=>{
   const r=reservationById.get(s.id);
   need(r&&r.decisionAt===s.at&&r.quantity>0,"RESERVATION_DECISION");
   const original=R.snapshotFundedReservations(native.reservationBook,s.at);
   need(original.reservations.some(x=>x.id===s.id),"ADMISSION_RESERVE_ACTIVE");
   return {id:s.id,symbol:s.symbol,decisionAt:s.at,quantity:r.quantity,
     originalNotionalUsd:r.notionalUsd,sourceMarkAt:states.get(s.id).reference.sourceAvailableAt};
 });
 return {schema:"HARPOON_FWN9_P9M_C2_NATIVE_EVENT_PARITY_1",
   scope:"ONE_FILLED_ONE_NO_FILL_TWO_ASSET_DETERMINISTIC_ENGINEERING",
   capitalUsd:20000,sourceNature:"SYNTHETIC_ENGINEERING_NO_MARKET_FILLS",
   feePerShareSideUsd:.005,calendarCostPerDayUsd:1,
   pendingReservationBeforeNoFill:before.reservations.some(r=>r.id===missing.id),
   noFillReservationAfterReceipt:after.reservations.some(r=>r.id===missing.id),
   noFill:{id:noFill.signalId,decisionAt:noFill.decisionAt,
     effectiveAt:noFill.plannedEntryAt,knownAt:noFill.resolutionAt,
     phantomInventory:false,sourcePriceCeiling:noFill.priceCeiling},
   filled:{id:trade.id,symbol:trade.symbol,quantity:trade.quantity,
     netTradingUsd:trade.netUsd,totalFeesUsd:fees,events},
   marksVerified:causalMarks,admissions:reserveRows,
   account:{capitalUsd:20000,totalFixedCalendarUsd:totalFixed,
     tradingCashBeforeFixedUsd:tradingCash,terminalPhysicalCashUsd:terminal,
     nativeTerminalEquityUsd:native.curve.at(-1).equity_end_usd,
     independentTerminalReconciled:true},
   riskClock:{pass:true,sourceObservedEvents:native.metadata.observedValuationEvents,
     independentObservedEvents:checked.observedValuationEvents},
   gates:{nativeWholePopulationEquivalent:false,
     nativeOHLCFirstCrossEquivalent:false,observedExecutionEvidence:false,
     fullyCoveredOperatorFaults:false,virtualCellNativeIntegration:false,
     WEAKExpectationBoundCertified:false,n9sEligible:false},
   budget:{marketAccounts:0,finalM10Opened:0,alphaSpent:0,newCandidates:0}};
}
module.exports={audit};
