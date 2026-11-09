"use strict";
// FWN9-C8B: read-only native replay event audit. Deterministic engineering only.
const assert = require("node:assert/strict");
const N = require("./profit8_replay.js");
const R = require("./ultimate_reservations.js");
const DAY = 86400000;
const close = (a,b) => Number.isFinite(a) && Number.isFinite(b) &&
  Math.abs(a-b) <= 1e-7*Math.max(1,Math.abs(a),Math.abs(b));
function need(x,code){ assert.ok(x,"P9MC8B_"+code); }
function overlay(snapshot, seriesBySymbol, at){
  let total = 0, opened = 0;
  const rows = [];
  for(const r of snapshot.reservations){
    let ref = null, val = r.notionalUsd;
    if(r.state === "OPENED"){
      const series = seriesBySymbol.get(r.symbol);
      need(!!series,"OPENED_SYMBOL_PRESENT");
      ref = N.causalReferencePrice({at},series);
      need(ref.status === "AVAILABLE" && ref.sourceAvailableAt <= at,
        "OPENED_MARK_CAUSAL");
      need(series.pointValue === 1,"SHARE_POINT_VALUE");
      val = Math.max(r.notionalUsd, r.quantity*ref.price);
      opened++;
    }
    total += val;
    rows.push({id:r.id,symbol:r.symbol,state:r.state,originalQty:r.quantity,
      remainingObserved:r.observedRemainingQuantity,sourceKnownAt:ref?.sourceAvailableAt??null,
      price:ref?.price??null,reservedNominalUsd:r.notionalUsd,repricedUsd:val});
  }
  return {total,opened,rows};
}
function independentPhysicalAt(native,data,at,calendarCostsUsdPerDay){
  const bySymbol = new Map(data.series.map(s=>[s.symbol,s]));
  let cash = 20000,fees = 0;
  let included = 0;
  const shares = new Map(data.series.map(s=>[s.symbol,0]));
  for(const trade of native.funded){
    for(const e of trade.inventoryEvents){
      if(e.at>at || e.knownAt>at) continue;
      need(e.knownAt>=e.at && e.at>=trade.opened,"CAUSAL_RECEIPT");
      need(e.kind==="ENTRY" || e.kind==="EXIT","FILL_KIND");
      need(Number.isSafeInteger(e.quantityDelta) && e.quantityDelta!==0,
        "INTEGER_FILL_QUANTITY");
      need(close(e.feeUsd,Math.abs(e.quantityDelta)*.005),"NOMINAL_FILL_FEES");
      const current=shares.get(trade.symbol)??0;
      need(current+e.quantityDelta>=0,"NO_SHORT_INVENTORY");
      shares.set(trade.symbol,current+e.quantityDelta);
      cash-=e.quantityDelta*e.filledPrice+e.feeUsd;
      fees+=e.feeUsd; included++;
    }
  }
  const calendarDays= Math.floor(at/DAY)-Math.floor(data.sessions[0].open/DAY)+1;
  cash-=Math.max(0,calendarDays)*calendarCostsUsdPerDay;
  let value = 0;
  for(const [symbol,qty] of shares){
    if(!qty) continue;
    const ref=N.causalReferencePrice({at},bySymbol.get(symbol));
    need(ref.status==="AVAILABLE" && ref.sourceAvailableAt<=at,
      "VALUATION_MARK_CAUSAL");
    value += qty*ref.price;
  }
  return {at,physicalCashUsd:cash,physicalEquityUsd:cash+value,shares:Object.fromEntries(shares),
    feesUsd:fees,receipts:included,calendarDays};
}
function audit({data,signals,native,limits,protocol}){
  need(data.provenance?.source==="SYNTHETIC_ENGINEERING_ONLY" &&
    data.series.length===2 && data.splitEvents.length===0 &&
    data.cashDividends.length===0,"TWO_ASSET_ENGINEERING_ONLY");
  need(limits.capitalUsd===20000 && limits.grossFraction===.12 &&
    limits.assetFraction===.12 && limits.riskFraction===.0025 &&
    limits.openRiskFraction===.0025 && limits.maxDrawdown===.08 &&
    limits.dailyLoss===.02,"LOCKED_ADMISSION_LIMITS");
  need(protocol.costs.perSideUsd===.005 && protocol.costs.spreadBps===2 &&
    protocol.costs.slippageBps===2,"ORIGINAL_COSTS");
  need(signals.length===2 && native.states.length===2 &&
    native.curve.length===data.sessions.length,"TWO_SIGNAL_NATIVE_REPLAY");
  const sym=new Map(data.series.map(s=>[s.symbol,s]));
  const statuses=new Set(["MODELED_CAMPAIGN","MODELED_IOC_NO_FILL",
      "REFUSED_BEFORE_ENTRY"]);
  const rows=[];
  for(const s of native.states){
    const at=s.opportunity.at;
    need(statuses.has(s.status),"STATE_DECISION_RECOVERABLE");
    const before=s.reservationBefore;
    const original=overlay(before,sym,at);
    need(close(s.notional,original.total),"REPRICED_STATE_NOTIONAL_PARITY");
    need(s.inventoryMarks.length===original.opened,"INVENTORY_OVERLAY_COUNT");
    for(const inv of s.inventoryMarks){
      const row=original.rows.find(x=>x.id===inv.id);
      need(row?.state==="OPENED" && inv.fullOriginalQuantity===row.originalQty &&
        close(inv.reservedNotionalUsd,row.repricedUsd) &&
        close(inv.reference.price,row.price) &&
        inv.reference.sourceAvailableAt===row.sourceKnownAt,"FULL_ORIGINAL_MARK_PARITY");
    }
    const account=independentPhysicalAt(native,data,at,1);
    // Native equity is a mark with modeled exit fee/friction provision.
    // Physical mark includes the value of remaining shares at their known close.
    // Do not assume equality of the two accounting conventions.
    need(account.physicalEquityUsd>0 && s.equity>0 &&
      s.equity<=account.physicalEquityUsd+0.25,"OBSERVED_EQUITY_NOT_ABOVE_PHYSICAL_MARK");
    const row={id:s.opportunity.id,status:s.status,decisionAt:at,
      observedEquityUsd:s.equity,independentPhysicalEquityUsd:account.physicalEquityUsd,
      nativeOriginalNotionalUsd:before.notionalUsd,
      nativeCorrectedPriorUsd:original.total,preexisting:original.rows,
      receiptCountKnown:account.receipts,
      physicalInventory:account.shares};
    if(s.reservationStatus==="RESERVED"){
      const c=s.profit8CommittedReservation;
      need(c && s.iocPlan.status==="PLANNED" && s.quantity===c.quantity &&
        c.quantity>0 && close(c.notionalUsd,c.quantity*s.iocPlan.priceCeiling),
        "IOC_SIZING_RECONCILED");
      const after=original.total+c.notionalUsd;
      need(after<=limits.grossFraction*s.equity+1e-7 &&
        c.notionalUsd<=limits.assetFraction*s.equity+1e-7,
        "CORRECTED_ANCHOR_ADMISSION");
      need(close(s.plan.notionalBudgetUsd,Math.max(0,Math.min(
        limits.assetFraction*s.equity,limits.grossFraction*s.equity-original.total))),
        "PLANNER_NATIVE_CAPACITY");
      const r=native.reservationBook.reservations.find(x=>x.id===s.opportunity.id);
      need(r && r.decisionAt===at && r.quantity===c.quantity &&
        close(r.notionalUsd,c.notionalUsd),"REAL_NATIVE_RESERVATION");
      row.admitted=true;row.committedNewUsd=c.notionalUsd;
      row.correctedAfterUsd=after;
      row.grossAdmissionLimitUsd=limits.grossFraction*s.equity;
      row.originalQuantity=r.quantity;
      row.receiptTypes=r.observations.map(o=>o.kind);
      if(s.status==="MODELED_IOC_NO_FILL"){
        need(r.observations.length===1 && r.observations[0].kind==="NO_FILL" &&
          !native.funded.some(t=>t.id===r.id),"NO_FILL_NO_INVENTORY");
        const openAt=s.opportunity.plannedEntryAt;
        const pending=R.snapshotFundedReservations(native.reservationBook,openAt-1);
        const released=R.snapshotFundedReservations(native.reservationBook,openAt);
        need(pending.reservations.some(x=>x.id===r.id) &&
          !released.reservations.some(x=>x.id===r.id),"NO_FILL_RELEASE_ON_RECEIPT");
      }
      if(s.status==="MODELED_CAMPAIGN"){
        const trade=native.funded.find(x=>x.id===r.id);
        need(trade && trade.opened===s.opportunity.plannedEntryAt &&
          trade.closed-trade.opened<=72*3600000 &&
          s.fillBudgetReceipt.status==="VERIFIED","NATIVE_MODEL_FILL_BUDGET");
      }
    }else{
      row.admitted=false;
    }
    rows.push(row);
  }
  const end=data.sessions.at(-1).close;
  const terminal=independentPhysicalAt(native,data,end,1);
  need(Object.values(terminal.shares).every(x=>x===0),"TERMINAL_NO_INVENTORY");
  need(close(terminal.physicalCashUsd,native.curve.at(-1).equity_end_usd),
    "INDEPENDENT_TERMINAL_CASH");
  need(close(native.portfolio.netUsd,native.curve.at(-1).equity_end_usd-20000),
    "NATIVE_NET_RECONCILED");
  return {schema:"HARPOON_FWN9_P9MC8B_NATIVE_EVENT_AUDIT_1",
    scope:"ACTUAL_NATIVE_REPLAY_ON_FIXED_SYNTHETIC_ENGINEERING_BARS",
    rows,terminal,netAfterAllCostsUsd:native.portfolio.netUsd,
    nativeReservations:native.reservationBook.reservations.length,
    partialEvents:native.funded.reduce((n,t)=>n+t.inventoryEvents.filter(
      e=>e.kind==="EXIT" && e.quantityDelta<0).length,0),
    exactNativeOHLCSubstepEquivalence:false,
    allPossibleNativeSignalsCovered:false,
    wealthMomentsAndN9SInfeasibilityCertified:false,
    operationalFaultsAndMulticellCertified:false,
    economicAccounts:0,alphaSpent:0,finalM10Opened:0};
}
module.exports={audit,overlay,independentPhysicalAt};
