"use strict";
/** Diagnostic necessary conditions at *native recorded* reserve / IOC clocks. */
const assert=require("node:assert/strict");
const RES=require("./ultimate_reservations.js");
const EPS=1e-7;
function auditTwoAssets(result, signals, limits) {
  assert(signals.length>=2 && new Set(signals.map(x=>x.symbol)).size>=2,
    "DUAL_ASSET_SIGNALS_REQUIRED");
  assert(signals.every((s,i)=>i===0||s.at>=signals[i-1].at),
    "CAUSAL_SIGNAL_ORDER");
  assert(result.reservationBook && Array.isArray(result.states),"NATIVE_FUNDED_REPLAY_REQUIRED");
  const stateMap=new Map(result.states.map(s=>[s.opportunity.id,s]));
  const accepted=result.reservationBook.reservations;
  assert(new Set(accepted.map(r=>r.id)).size===accepted.length,"DUPLICATE_RESERVATIONS");
  const events=[];
  for(const signal of signals) {
    const state=stateMap.get(signal.id);
    const receipt=accepted.find(r=>r.id===signal.id);
    const before=RES.snapshotFundedReservations(result.reservationBook,signal.at);
    if(!receipt) {
      events.push({id:signal.id,symbol:signal.symbol,type:"REFUSED",
        status:state?.status??"NO_PLANNED_STATE"});
      continue;
    }
    assert(state?.reservationStatus==="RESERVED","RESERVATION_STATE_MISMATCH");
    assert(receipt.decisionAt===signal.at,"RESERVATION_DECISION_TIME");
    const commitment=state.profit8CommittedReservation;
    assert(commitment.quantity===receipt.quantity,"RESERVED_QUANTITY");
    assert(commitment.notionalUsd===receipt.notionalUsd,"RESERVED_NOTIONAL");
    assert(commitment.riskUsd===receipt.riskUsd,"RESERVED_RISK");
    assert(state.reference.sourceAvailableAt<=signal.at,"FUTURE_REFERENCE");
    assert(state.iocPlan.decisionAt===signal.at,"IOC_DECISION_TIME");
    assert(state.iocPlan.plannedEntryAt>=signal.at,"IOC_PLANNED_BEFORE_DECISION");
    const previous=state.reservationBefore;
    // Native planner counts retained reservation and the original quantity marked
    // at the last received price, never current unreceived substep prices.
    // Exact per-inventory invariant is stronger and avoids claiming an event-time
    // continuous 12% mark-to-market cap.
    for(const mark of state.inventoryMarks){
      assert(mark.reference.sourceAvailableAt<=signal.at,"FUTURE_INVENTORY_MARK");
      assert(mark.reservedNotionalUsd+EPS>=mark.markedNotionalUsd,"UNCOVERED_RECEIVED_INVENTORY_MARK");
      assert(mark.fullOriginalQuantity>0,"EMPTY_ORIGINAL_INVENTORY");
    }
    assert(state.notional+receipt.notionalUsd<=limits.grossFraction*state.equity+EPS,
      "AGGREGATE_ADMISSION_NOTIONAL_EXCEEDED");
    assert(previous.riskUsd+receipt.riskUsd<=limits.openRiskFraction*state.equity+EPS,
      "AGGREGATE_ADMISSION_RISK_EXCEEDED");
    assert(previous.cashUsd+receipt.cashUsd<=state.cashPoolUsd+EPS,"AGGREGATE_CASH_EXCEEDED");
    assert(state.notional+EPS>=previous.notionalUsd,"RETENTION_NOT_COUNTED");
    if(state.fillBudgetReceipt){
      assert(state.fillBudgetReceipt.actualEntryNotionalUsd<=commitment.notionalUsd+EPS,
        "IOC_BUDGET_FILL_EXCEEDED");
      assert(state.modeledOpenedAt>=state.iocPlan.plannedEntryAt,"EARLY_FILL");
    }
    events.push({id:signal.id,symbol:signal.symbol,type:"ADMISSION",
      reservedNotionalUsd:receipt.notionalUsd,portfolioNotionalAtDecisionUsd:state.notional+
      receipt.notionalUsd,equityAtDecisionUsd:state.equity,
      observedMarkCoverage:true,receivedPriceCoverage:true,
      reservationOnlyNotContinuousCap:true,receiptCount:receipt.observations.length});
    const observations=receipt.observations;
    for(const o of observations){
      assert(o.knownAt>=o.at && o.at>=signal.at,"NONCAUSAL_RECEIPT");
      const pre=RES.snapshotFundedReservations(result.reservationBook,o.knownAt-1);
      const post=RES.snapshotFundedReservations(result.reservationBook,o.knownAt);
      const preRes=pre.reservations.find(x=>x.id===receipt.id);
      const postRes=post.reservations.find(x=>x.id===receipt.id);
      assert(preRes!==undefined,"PREMATURE_RELEASE");
      if(o.kind==="CLOSED"||o.kind==="NO_FILL")assert(postRes===undefined,"NO_TERMINAL_RELEASE");
      else assert(postRes!==undefined,"PREMATURE_PARTIAL_RELEASE");
      events.push({id:receipt.id,symbol:receipt.symbol,type:o.kind,effectiveAt:o.at,
        knownAt:o.knownAt,heldBeforeKnown:true});
    }
  }
  return {schema:"HARPOON_M11_DUAL_ASSET_ANCHOR_AUDIT_1",events,
    accepted:accepted.length,coveredAssets:[...new Set(accepted.map(x=>x.symbol))],
    decisionsChecked:signals.length,
    necessaryReserveConditionsPassed:true,
    currentUnobservedMarksProven:false,
    shadowPortfolioInequalityCertified:false,
    continuousTwelvePercentCapClaimed:false,
    nativeMathematicalBoundCertified:false};
}
module.exports={auditTwoAssets};
