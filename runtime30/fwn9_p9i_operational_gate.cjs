"use strict";
/** FWN9/P9I engineering gate: all accepted source decisions in one fixture.
 * Reject incomplete receipts and accidental promotion; no market or broker calls. */
const A=require("node:assert/strict");
const H=require("./fwn9_p9h_cash_ledger.cjs");
const R=require("./ultimate_reservations.js");
function requireShape(ok,code){A.ok(ok,"P9I_"+code);}
function auditAll({nativeReplay,data,protocol,limits,signals}) {
  requireShape(Array.isArray(signals)&&signals.length>=2,"NONVACUOUS_SIGNAL_CATALOG");
  const ids=new Set();
  for(let i=0;i<signals.length;i++){
    const s=signals[i];
    requireShape(typeof s.id==="string"&&!ids.has(s.id)&&Number.isSafeInteger(s.at)&&
      (i===0||s.at>=signals[i-1].at),"SORTED_UNIQUE_CAUSAL_SIGNALS");
    ids.add(s.id);
  }
  requireShape(nativeReplay&&Array.isArray(nativeReplay.states)&&
    Array.isArray(nativeReplay.funded)&&Array.isArray(nativeReplay.modeledNoFills)&&
    nativeReplay.reservationBook?.reservations,"REPLAY_SHAPE");
  requireShape(data.sessions.length>0&&Array.isArray(data.series)&&
    data.splitEvents?.length===0&&data.cashDividends?.length===0,"FROZEN_NO_CORPORATE_SCOPE");
  requireShape(limits.capitalUsd===20000&&limits.grossFraction===.12&&
    limits.openRiskFraction===.0025&&limits.dailyLoss===.02&&
    limits.maxDrawdown===.08,"FROZEN_RISK_CONTRACT");
  const knownStates=new Map(),checked=[];
  for(const state of nativeReplay.states){
    const sid=state.opportunity?.id;
    requireShape(ids.has(sid)&&!knownStates.has(sid),"DUPLICATE_OR_UNKNOWN_STATE");
    knownStates.set(sid,state);
    if(state.reservationStatus!=="RESERVED")continue;
    const at=state.opportunity.at;
    requireShape(state.reference?.sourceAvailableAt<=at,"FUTURE_REFERENCE");
    const row=H.auditDecision({nativeReplay,data,protocol,limits,state});
    requireShape(row.sourceCashMarkIdentity===true&&row.sampleOnly===true&&
      row.fullM9Certificate===false,"CASH_LEDGER_SCOPE");
    checked.push({id:sid,at,physicalCashUsd:row.physicalCashUsd,
      openShares:row.open.reduce((sum,p)=>sum+p.remaining,0),
      retainedNotionalUsd:row.conservativeNotionalUsd,
      equityUsd:row.observedNativeEquityUsd,localLedgerFloorUsd:row.localLedgerFloorUsd});
  }
  requireShape(checked.length>0,"NO_ACCEPTED_DECISIONS");
  const refusedIds=new Set((nativeReplay.preEntryRefusals||[]).map(x=>x.signalId));
  for(const s of signals)requireShape(knownStates.has(s.id)||refusedIds.has(s.id),
    "MISSING_NATIVE_SIGNAL_DISPOSITION");
  for(const r of nativeReplay.reservationBook.reservations){
    requireShape(ids.has(r.id),"ORPHAN_RESERVATION");
    for(const o of r.observations){
      requireShape(o.at>=r.decisionAt&&o.knownAt>=o.at,"NONCAUSAL_RESERVATION_RECEIPT");
      if(o.kind==="NO_FILL"||o.kind==="CLOSED"){
        const before=R.snapshotFundedReservations(nativeReplay.reservationBook,o.knownAt-1);
        const after=R.snapshotFundedReservations(nativeReplay.reservationBook,o.knownAt);
        requireShape(before.reservations.some(x=>x.id===r.id)&&
           !after.reservations.some(x=>x.id===r.id),"PREMATURE_OR_MISSING_RELEASE");
      }
    }
  }
  const noFills=[];
  for(const f of nativeReplay.modeledNoFills){
    requireShape(ids.has(f.signalId)&&Number.isSafeInteger(f.resolutionAt)&&
      f.resolutionAt>=f.plannedEntryAt,"INVALID_IOC_NO_FILL");
    const r=H.auditNoFill({nativeReplay,at:f.resolutionAt});
    requireShape(r.noFillReleased&&r.noPhantomInventory,"IOC_NO_FILL_CREATED_PHANTOM");
    noFills.push(f.signalId);
  }
  return {schema:"FWN9_P9I_FINITE_OPERATIONAL_AUDIT_1",
    checkedAcceptedDecisions:checked.length,checked,modeledNoFills:noFills,
    allProvidedAcceptedChecked:true,p9bNoFillValuationClockRepaired:false,
    sourceWideCoverage:false,ohlcObservedFillEquivalence:false,
    partialRejectOutageImpactCovered:false,multicellCoordinatorCovered:false,
    n9sPromotionEligible:false,reason:"SOURCE_WIDE_AND_OPERATIONAL_GATES_UNPROVEN"};
}
module.exports={auditAll};
