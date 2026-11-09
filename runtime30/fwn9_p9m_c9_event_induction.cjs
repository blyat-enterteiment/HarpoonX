"use strict";
/*
 * FWN9 C9: deterministic native event-invariant witness. This is an audit of
 * KNOWN inventory at causal marks, not a market fill model, stochastic wealth
 * bound or certification of the native OHLC exit convention.
 */
const A=require("node:assert/strict");
const R=require("./ultimate_reservations.js");
const N=require("./profit8_replay.js");
const close=(x,y)=>Number.isFinite(x)&&Number.isFinite(y)&&
  Math.abs(x-y)<=1e-7*Math.max(1,Math.abs(x),Math.abs(y));
function need(ok,tag){A.ok(ok,"C9_"+tag);}
function knownShares(trade,at){
  let q=0,fees=0;
  for(const e of trade.inventoryEvents){
    need(Number.isSafeInteger(e.at)&&Number.isSafeInteger(e.knownAt)&&
      e.knownAt>=e.at && Number.isSafeInteger(e.quantityDelta)&&
      e.quantityDelta!==0,"CAUSAL_INTEGER_RECEIPT");
    if(e.at>at||e.knownAt>at)continue;
    need((e.kind==="ENTRY"&&e.quantityDelta>0)||
      (e.kind==="EXIT"&&e.quantityDelta<0),"VALID_RECEIPT_SIDE");
    q+=e.quantityDelta;need(q>=0&&q<=trade.quantity,"SELF_FINANCING_NO_SHORT");
    need(Number.isFinite(e.filledPrice)&&e.filledPrice>0&&
      Number.isFinite(e.feeUsd)&&e.feeUsd>=0,"VALID_EXECUTION_PRICE_FEE");
    fees+=e.feeUsd;
  }
  return {quantity:q,feesUsd:fees};
}
function audit({native,data,limits}){
  need(limits.capitalUsd===20000&&limits.grossFraction===.12&&
    limits.assetFraction===.12&&limits.riskFraction===.0025&&
    limits.openRiskFraction===.0025,"LOCKED_M9_LIMITS");
  need(data.provenance?.source==="SYNTHETIC_ENGINEERING_ONLY"&&
    data.series.length===2&&data.splitEvents.length===0&&
    data.cashDividends.length===0,"LOCKED_ENGINEERING_UNIVERSE");
  const book=native.reservationBook,series=new Map(data.series.map(s=>[s.symbol,s]));
  need(series.size===2&&series.has("SYNA")&&series.has("SYNB")&&
    data.series.every(s=>s.pointValue===1),"LONG_CASH_SHARES_ONLY");
  const trades=new Map(native.funded.map(t=>[t.id,t]));
  const checkpoints=new Set();
  for(const r of book.reservations){
    checkpoints.add(r.decisionAt);
    for(const o of r.observations){
      checkpoints.add(o.at);checkpoints.add(o.knownAt);
      if(o.knownAt>r.decisionAt)checkpoints.add(o.knownAt-1);
      if(o.at>r.decisionAt)checkpoints.add(o.at-1);
    }
  }
  for(const t of native.funded){
    need(t.closed-t.opened<=72*3600000&&t.closed>=t.opened,
      "MAX_HOLD_72_HOURS");
    for(const e of t.inventoryEvents){
      checkpoints.add(e.at);checkpoints.add(e.knownAt);
    }
  }
  for(const s of native.states)checkpoints.add(s.opportunity.at);
  const checkpointsSorted=[...checkpoints].sort((a,b)=>a-b);
  let snapshots=0,openedRows=0,pendingRows=0,strictlyPartial=0;
  let largestMarkedDominanceUsd=0;
  const rows=[];
  for(const at of checkpointsSorted){
    const snap=R.snapshotFundedReservations(book,at);
    let total=0,knownValue=0;
    for(const r of snap.reservations){
      let anchor=r.notionalUsd;
      const trade=trades.get(r.id);
      if(r.state==="OPENED"){
        need(!!trade&&trade.quantity===r.quantity&&
          r.observedRemainingQuantity<=r.quantity,"OPENED_BOUND_TO_ORIGINAL_LOT");
        const s=series.get(r.symbol);
        const mark=N.causalReferencePrice({at},s);
        need(mark.status==="AVAILABLE"&&mark.sourceAvailableAt<=at&&
          mark.price>0,"CAUSAL_MARK_REQUIRED");
        const inv=knownShares(trade,at);
        anchor=Math.max(r.notionalUsd,r.quantity*mark.price);
        const exposure=inv.quantity*mark.price;
        need(anchor+1e-8>=exposure&&inv.quantity<=r.quantity,
          "MARKED_ORIGINAL_DOMINATES_KNOWN_REMAINING");
        if(inv.quantity<r.quantity)strictlyPartial++;
        knownValue+=exposure;
        largestMarkedDominanceUsd=Math.max(largestMarkedDominanceUsd,anchor-exposure);
        openedRows++;
      }else{
        need(r.state==="PENDING","ONLY_PENDING_OR_OPENED");
        need(!trade||knownShares(trade,at).quantity===0,
          "PENDING_MUST_NOT_HAVE_KNOWN_FILL");
        pendingRows++;
      }
      total+=anchor;
    }
    need(total+1e-8>=knownValue,"AGGREGATE_KNOWN_LONG_INVENTORY");
    rows.push({at,active:snap.reservations.length,anchorUsd:total,
      knownOpenedMarkedUsd:knownValue});
    snapshots++;
  }
  let checkedAdmission=0;
  for(const s of native.states){
    const before=s.reservationBefore;
    if(!before)continue;
    let anchor=0;
    for(const r of before.reservations){
      let part=r.notionalUsd;
      if(r.state==="OPENED"){
        const seriesRow=series.get(r.symbol);
        const mark=N.causalReferencePrice({at:s.opportunity.at},seriesRow);
        need(mark.status==="AVAILABLE"&&
          mark.sourceAvailableAt<=s.opportunity.at,"ADMISSION_MARK_AVAILABLE");
        part=Math.max(part,r.quantity*mark.price);
      }
      anchor+=part;
    }
    need(close(s.notional,anchor),"STATE_REPRICED_ANCHOR_PARITY");
    if(s.reservationStatus==="RESERVED"){
      need(s.profit8CommittedReservation&&
        Number.isFinite(s.equity)&&s.equity>0&&
        anchor+s.profit8CommittedReservation.notionalUsd<=.12*s.equity+1e-7,
        "ADMITTED_GROSS_BOUND");
      need(s.profit8CommittedReservation.riskUsd+
        before.riskUsd<=.0025*s.equity+1e-7,"ADMITTED_RISK_BOUND");
      checkedAdmission++;
    }
  }
  return {schema:"FWN9_C9_NATIVE_EVENT_INDUCTION_WITNESS_1",
    checkedSnapshots:snapshots,openedRows,pendingRows,
    strictlyPartialSnapshots:strictlyPartial,checkedAdmission,
    largestMarkedDominanceUsd,
    note:"Observable original-quantity mark dominates known remaining marked inventory at checked timestamps only.",
    continuousGrossCapProven:false,allReachableM9EventsProven:false,
    wealthMomentBoundCertified:false,nativeOHLCFirstCrossEquivalent:false,
    N9SConditionalAccepted:false,newEconomicAccounts:0,
    prospectiveAlphaSpent:0,finalM10Opened:0,rows};
}
module.exports={knownShares,audit};
