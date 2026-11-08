"use strict";
/**
 * FWN9 M11/P9D v2: native price-mark and receipt-timing audit, research only.
 * Independent reconstruction of every native campaign PnL mark from exit
 * receipts and published closes. Compares the persistent P9C risk clock with
 * the unchanged native replay, but does NOT change their accounting.
 * Engineering fixtures ONLY; never assert a population wealth theorem.
 */
const assert = require("node:assert/strict");
const N = require("./profit8_replay.js");
const EPS = 2e-7;
const close = (a,b) => Number.isFinite(a)&&Number.isFinite(b)&&
  Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
function knownClose(data,symbol,at) {
  const s=data.series.find(x=>x.symbol===symbol);
  assert(s,"P9D_MISSING_SYMBOL");
  let seen=null;
  for(const b of s.bars)if(b.availableAt<=at&&
    (seen===null||b.end>seen.end))seen=b;
  assert(seen&&seen.c>0,"P9D_CLOSE_NOT_RECEIVED");
  return seen.c;
}
function campaignMarks(trade,data,protocol) {
  assert(trade.direction===1&&Number.isSafeInteger(trade.quantity)&&
    trade.quantity>0&&trade.entry>0,"P9D_LONG_NATIVE_CAMPAIGN_REQUIRED");
  const s=data.series.find(x=>x.symbol===trade.symbol);
  assert(s&&s.pointValue===1,"P9D_CASH_SHARE_SERIES");
  const events=trade.inventoryEvents;
  assert(Array.isArray(events),"P9D_NATIVE_INVENTORY_EVENTS_REQUIRED");
  const ins=events.filter(e=>e.kind==="ENTRY");
  const exits=events.filter(e=>e.kind==="EXIT");
  assert(ins.length===1&&exits.length>0&&
    ins[0].quantityDelta===trade.quantity&&ins[0].at===trade.opened,
    "P9D_ENTRY_IDENTITY");
  assert(close(ins[0].feeUsd,trade.quantity*protocol.costs.perSideUsd),
    "P9D_ENTRY_FEE");
  for(const e of exits)assert(Number.isSafeInteger(e.at)&&
    Number.isSafeInteger(e.knownAt)&&e.knownAt>=e.at&&
    Number.isSafeInteger(e.quantityDelta)&&e.quantityDelta<0&&
    e.filledPrice>0&&close(e.feeUsd,-e.quantityDelta*protocol.costs.perSideUsd)&&
    e.at>=trade.opened&&e.at-trade.opened<=72*3600000,
    "P9D_EXIT_RECEIPT_CONTRACT");
  const sorted=exits.slice().sort((a,b)=>a.knownAt-b.knownAt||a.at-b.at);
  assert(sorted.every((e,i)=>i===0||e.at>=sorted[i-1].at),
    "P9D_RECEIPT_EXECUTION_REGRESSION");
  let realized=-ins[0].feeUsd,remaining=trade.quantity,j=0,last=-1;
  const rows=[],sums=[];
  for(const m of trade.marks){
    assert(Number.isSafeInteger(m.at)&&m.at>last&&Number.isFinite(m.pnl),
      "P9D_MARK_CHRONOLOGY");
    last=m.at;
    while(j<sorted.length&&sorted[j].knownAt<=m.at){
      const e=sorted[j++];
      const q=-e.quantityDelta;
      assert(q<=remaining,"P9D_EXIT_QUANTITY_OVERDRAW");
      remaining-=q;
      realized+=(e.filledPrice-trade.entry)*q-e.feeUsd;
    }
    const b=s.bars.find(b=>b.availableAt===m.at);
    assert(remaining===0||!!b,"P9D_OPEN_POSITION_UNPUBLISHED_MARK");
    const px=b?b.c:null;
    const predicted=realized+(remaining>0?
      remaining*(px-trade.entry-protocol.costs.perSideUsd):0);
    assert(close(m.pnl,predicted),
      "P9D_NATIVE_MARK_RECONSTRUCTION_MISMATCH");
    rows.push({at:m.at,close: px,remaining,realized,reported:m.pnl,
      reconstructed:predicted});
    sums.push(predicted);
  }
  while(j<sorted.length){
    const e=sorted[j++],q=-e.quantityDelta;
    assert(q<=remaining,"P9D_TERMINAL_EXIT_OVERDRAW");
    remaining-=q;
    realized+=(e.filledPrice-trade.entry)*q-e.feeUsd;
  }
  assert(remaining===0&&close(realized,trade.netUsd)&&
    rows.length>0&&close(rows.at(-1).reported,trade.netUsd),
    "P9D_TERMINAL_CAMPAIGN_RECONCILIATION");
  assert(N.profit8KnownAt(trade)===
    Math.max(trade.closed,...trade.marks.map(m=>m.at),
      ...events.map(e=>e.knownAt)),
    "P9D_TERMINAL_KNOWLEDGE");
  return {id:trade.id,symbol:trade.symbol,quantity:trade.quantity,
    opened:trade.opened,closed:trade.closed,entry:trade.entry,
    entryFeeUsd:ins[0].feeUsd,perSideFeeUsd:protocol.costs.perSideUsd,
    exits:sorted.map(e=>({at:e.at,knownAt:e.knownAt,
      qty:-e.quantityDelta,price:e.filledPrice,feeUsd:e.feeUsd})),
    marks:rows,netUsd:trade.netUsd,terminalKnownAt:N.profit8KnownAt(trade)};
}
function nativeAt({native,data,protocol},at) {
  const first=data.sessions[0].open;
  const fees=at<first?0:Math.floor(at/86400000)-
    Math.floor(first/86400000)+1;
  const nativeState=new Map(native.states.filter(s=>s.modeledCloseKnownAt!==undefined)
    .map(s=>[s.opportunity.id,s]));
  let pnl=0,closed=0;
  for(const trade of native.funded) {
    if(trade.opened>at)continue;
    const known=nativeState.get(trade.id)?.modeledCloseKnownAt;
    assert(Number.isSafeInteger(known)&&known>=trade.closed,
      "P9D_NATIVE_TERMINAL_RECEIPT_REQUIRED");
    if(known<=at){pnl+=trade.netUsd;closed+=trade.netUsd;continue;}
    const mark=trade.marks.findLast(m=>m.at<=at);
    if(mark){pnl+=mark.pnl;continue;}
    pnl+=(knownClose(data,trade.symbol,at)-trade.entry)*trade.quantity-
      2*trade.quantity*protocol.costs.perSideUsd;
  }
  return {equityUsd:20000+pnl-fees,cashUsd:20000+closed-fees};
}
function audit({nativeReplay,mirror,data,protocol,limits}){
  assert(nativeReplay?.funded&&nativeReplay?.states&&
    mirror?.native?.riskEvents&&
    data?.splitEvents?.length===0&&data?.cashDividends?.length===0,
    "P9D_REGISTERED_ENGINEERING_SCOPE");
  assert(limits.capitalUsd===20000&&limits.grossFraction===.12&&
    limits.openRiskFraction===.0025&&limits.dailyLoss===.02&&
    limits.maxDrawdown===.08,"P9D_ORIGINAL_RISK_LIMITS");
  const campaigns=nativeReplay.funded.map(t=>campaignMarks(t,data,protocol));
  // Native reservations include IOC no-fills: compare admission with
  // approved ex-ante commitments, NEVER with funded fills alone.
  const reserved=new Map(nativeReplay.states.filter(s=>s.reservationStatus==="RESERVED")
    .map(s=>[s.opportunity.id,s]));
  const matchedAdmits=mirror.native.admits.length===reserved.size&&
    mirror.native.admits.every(a=>reserved.get(a.id)?.quantity===a.quantity);
  const deviations=[];
  let firstDeviation=null,maxAbsEquity=0,maxAbsCash=0,maxAbsPeak=0;
  let peak=20000,prior=-1;
  for(const row of mirror.native.riskEvents){
    assert(Number.isSafeInteger(row.at)&&row.at>prior,"P9D_RISK_CLOCK_NONMONOTONE");
    prior=row.at;
    const target=nativeAt({native:nativeReplay,data,protocol},row.at);
    peak=Math.max(peak,target.equityUsd);
    const dEq=row.equityUsd-target.equityUsd,
      dCash=row.cashUsd-target.cashUsd,dPeak=row.observedPeakUsd-peak;
    maxAbsEquity=Math.max(maxAbsEquity,Math.abs(dEq));
    maxAbsCash=Math.max(maxAbsCash,Math.abs(dCash));
    maxAbsPeak=Math.max(maxAbsPeak,Math.abs(dPeak));
    if(!close(row.equityUsd,target.equityUsd)||
       !close(row.cashUsd,target.cashUsd)||
       !close(row.observedPeakUsd,peak)){
      const d={at:row.at,source:row.source,mirrorEquityUsd:row.equityUsd,
        nativeEquityUsd:target.equityUsd,mirrorCashUsd:row.cashUsd,
        nativeCashUsd:target.cashUsd,mirrorPeakUsd:row.observedPeakUsd,
        reconstructedPeakUsd:peak};
      if(firstDeviation===null)firstDeviation=d;
      deviations.push(d);
    }
  }
  const decisionParity=mirror.native.decisions.every(m=>{
    const s=nativeReplay.states.find(x=>x.opportunity.id===m.id);
    const refused=nativeReplay.preEntryRefusals.find(x=>x.signalId===m.id);
    if(m.status==="RESERVED")return s?.reservationStatus==="RESERVED"&&
      m.quantity===s.quantity&&close(m.equityUsd,s.equity)&&
      close(m.cashPoolUsd,s.cashPoolUsd);
    return s?.reservationStatus!=="RESERVED"&&
      (s!==undefined||refused!==undefined);
  });
  const parity=matchedAdmits&&decisionParity&&deviations.length===0;
  return {schema:"HARPOON_FWN9_M11_P9D_NATIVE_MARK_RECEIPT_AUDIT_1",
    nativeCampaignMarksReconstructed:true,campaigns:campaigns.length,
    markCount:campaigns.reduce((n,x)=>n+x.marks.length,0),
    nativeAdmittedQuantityParity:matchedAdmits,decisionParity,
    nativeObservedRiskEventsCompared:mirror.native.riskEvents.length,
    firstDeviation,deviationsCount:deviations.length,
    maxAbsEquityUsd:maxAbsEquity,maxAbsCashUsd:maxAbsCash,
    maxAbsObservedPeakUsd:maxAbsPeak,
    fullFixtureNativeRiskParity:parity,
    stochasticWealthBoundProven:false,nativeInfeasibilityCertified:false,
    unobservedFillEquivalenceProven:false,
    accountantInput:{campaigns,initialUsd:20000}};
}
module.exports={campaignMarks,nativeAt,audit};
