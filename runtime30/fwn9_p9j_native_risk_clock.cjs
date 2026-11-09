"use strict";
/**
 * FWN9 M11/P9J — versioned correction of historical P9B missing NO_FILL event-clock. of the NATIVE
 * replay's observation order. Diagnostic only: does not modify signals,
 * native execution, broker actions, or the M9/M10 law.
 *
 * Caveat: consumes NATIVE campaign marks, therefore tests the portfolio's
 * risk-clock integration; mark-price formation remains a separate gate.
 */
const assert=require("node:assert/strict");
const RES=require("./ultimate_reservations.js");
const DAY=86400000, EPS=1e-7;
const close=(a,b)=>Number.isFinite(a)&&Number.isFinite(b)&&
  Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
function checkNativeRiskClock({data,signals,native,protocol,limits}){
  assert(Array.isArray(signals)&&signals.length>0&&
    signals.every((s,i)=>i===0||s.at>=signals[i-1].at),"FWN9_SIGNALS_SORTED");
  assert(Array.isArray(data.sessions)&&data.sessions.length>0 &&
    data.splitEvents.length===0 && data.cashDividends.length===0,
    "FWN9_REGISTERED_SYNTHETIC_SCOPE");
  assert(limits.capitalUsd===20000&&limits.dailyLoss===.02&&
    limits.maxDrawdown===.08&&limits.grossFraction===.12,"FWN9_RISK_LIMITS_UNCHANGED");
  assert(native?.funded && native?.states && native?.curve && native?.metadata,
    "FWN9_ACTUAL_NATIVE_REPLAY_REQUIRED");
  const start=data.sessions[0].open, terminal=data.sessions.at(-1).close;
  const bySymbol=new Map(data.series.map(s=>[s.symbol,s]));
  const accepted=new Map(native.funded.map(t=>[t.id,t]));
  assert(Array.isArray(native.modeledNoFills)&&native.reservationBook?.reservations,
    "P9J_NATIVE_NOFILL_AND_RESERVATION_EVIDENCE_REQUIRED");
  const noFills=new Map();
  for(const n of native.modeledNoFills){
    assert(typeof n.signalId==="string"&&!noFills.has(n.signalId),
      "P9J_DUPLICATE_NOFILL_RECEIPT");
    noFills.set(n.signalId,n);
  }

  const stateById=new Map(native.states.map(s=>[s.opportunity.id,s]));
  const refused=new Map(native.preEntryRefusals.map(x=>[x.signalId,x]));
  const lastClosedKnownAt=new Map(native.states.filter(s=>s.modeledCloseKnownAt!==undefined)
    .map(s=>[s.opportunity.id,s.modeledCloseKnownAt]));
  const costsAt=at=>at<start?0:(Math.floor(at/DAY)-Math.floor(start/DAY)+1);
  const observedClose=(series,at)=>{
    let bar=null;
    for(const b of series.bars)if(b.availableAt<=at&&
      (!bar||b.end>bar.end))bar=b;
    assert(bar&&bar.c>0,"FWN9_MISSING_CAUSAL_CLOSE");
    return bar.c;
  };
  const active=[];
  const tradePnlAt=(trade,at)=>{
    if(at<trade.opened)return 0;
    if((lastClosedKnownAt.get(trade.id)??Infinity)<=at)return trade.netUsd;
    let mark=null;
    for(const m of trade.marks)if(m.at<=at)mark=m;
    if(mark)return mark.pnl;
    const s=bySymbol.get(trade.symbol);
    assert(s,"FWN9_UNKNOWN_ASSET");
    return (observedClose(s,at)-trade.entry)*trade.quantity*s.pointValue
      -2*trade.quantity*protocol.costs.perSideUsd;
  };
  const equityAt=at=>20000+active.reduce((v,t)=>v+tradePnlAt(t,at),0)-costsAt(at);
  const cashAt=at=>20000+active.reduce((v,t)=>v+
    ((lastClosedKnownAt.get(t.id)??Infinity)<=at?t.netUsd:0),0)-costsAt(at);
  let peak=20000,maxDrawdown=0,observedCount=0;
  let pending=data.sessions.map(s=>s.open);
  const checks=[],observations=[];
  const record=(at,source)=>{
    const equity=equityAt(at);
    assert(equity>0,"FWN9_FIXTURE_EQUITY_INSOLVENT");
    peak=Math.max(peak,equity);
    const dd=1-equity/peak;
    maxDrawdown=Math.max(maxDrawdown,dd);
    observations.push({at,source,equityUsd:equity,peakUsd:peak,drawdown:dd,
      cashAvailableUsd:cashAt(at)});
    return equity;
  };
  const advance=at=>{
    let consumed=0;
    while(consumed<pending.length&&pending[consumed]<=at){
      record(pending[consumed],"QUEUED");
      observedCount++;
      consumed++;
    }
    pending=pending.slice(consumed);
    return record(at,"DECISION_OR_TERMINAL");
  };
  const includeTrade=trade=>{
    const known=lastClosedKnownAt.get(trade.id);
    assert(Number.isSafeInteger(known),"FWN9_UNRESOLVED_NATIVE_TERMINAL_RECEIPT");
    const series=bySymbol.get(trade.symbol);
    const firstMark=trade.marks[0]?.at??known;
    const times=[trade.opened,known,...trade.marks.map(m=>m.at),
      ...series.bars.filter(b=>b.availableAt>=trade.opened &&
        b.availableAt<firstMark).map(b=>b.availableAt)];
    pending=[...new Set([...pending,...times.filter(at=>at>=start&&at<=terminal)])]
      .sort((a,b)=>a-b);
    active.push(trade);
  };
  let acceptedCount=0,lossRefusals=0,mirrorGateMisses=0;
  let noFillClockInsertions=0;
  const sourceNoFillReceipts=[];
  for(const signal of signals){
    const state=stateById.get(signal.id),failure=refused.get(signal.id);
    assert(state||failure,"FWN9_SIGNAL_ACCOUNT_STATUS_MISSING");
    // A native refusal before mark-clock evaluation (e.g., calendar cutoff)
    // has no risk clock to compare. The registered deterministic tests only
    // use eligible time/grid signals.
    if(!state&&failure?.reason!=="LOSS_LIMIT"){
      checks.push({id:signal.id,status:"EARLY_NONRISK_REFUSAL",reason:failure?.reason});
      continue;
    }
    const equity=advance(signal.at);
    const session=data.sessions.find(s=>s.open<=signal.at&&signal.at<s.close);
    assert(session,"FWN9_NO_DECISION_SESSION");
    const dailyBaseline=equityAt(session.open-1);
    const dailyLossBreached=equity<=dailyBaseline*(1-limits.dailyLoss);
    const maxDdBreached=equity<=peak*(1-limits.maxDrawdown);
    const lossBlocked=dailyLossBreached||maxDdBreached;
    const nativeBlocked=failure?.reason==="LOSS_LIMIT";
    assert(lossBlocked===nativeBlocked,"FWN9_NATIVE_LOSS_GATE_CLOCK_MISMATCH");
    if(nativeBlocked)lossRefusals++;
    if(state){
      assert(close(equity,state.equity),"FWN9_NATIVE_EQUITY_CLOCK_MISMATCH");
      assert(close(cashAt(signal.at),state.cashPoolUsd),
        "FWN9_NATIVE_CASH_CLOCK_MISMATCH");
      assert(close(peak,state.causalPeakEquityUsd),
        "FWN9_NATIVE_PEAK_CLOCK_MISMATCH");
    } else {
      assert(close(equity,failure.equityUsd)&&
        close(peak,failure.causalPeakEquityUsd),
        "FWN9_NATIVE_LOSS_REFUSAL_EQUITY_MISMATCH");
    }
    checks.push({id:signal.id,at:signal.at,equityUsd:equity,peakUsd:peak,
      cashUsd:cashAt(signal.at),dailyBaselineUsd:dailyBaseline,
      dailyLossBreached,maxDdBreached,nativeLossRefused:nativeBlocked,
      decisionStatus:state?.status??failure?.reason});
    const trade=accepted.get(signal.id);
    if(trade){
      assert(state?.status==="MODELED_CAMPAIGN","FWN9_ACCEPTED_WITHOUT_CAMPAIGN");
      includeTrade(trade);
      acceptedCount++;
    }
    // The original frozen P9B omits this valuation. Native replay queues
    // plannedEntryAt upon a verified IOC NO_FILL, even when no trade exists.
    // Queue only after receiving the source reservation's terminal observation.
    const noFill=noFills.get(signal.id);
    if(noFill){
      assert(!trade&&state?.status==="MODELED_IOC_NO_FILL",
        "P9J_NOFILL_MUST_NOT_CREATE_CAMPAIGN");
      const r=native.reservationBook.reservations.find(x=>x.id===signal.id);
      const obs=r?.observations;
      assert(obs?.length===1&&obs[0].kind==="NO_FILL" &&
        obs[0].at===noFill.plannedEntryAt &&
        obs[0].knownAt===noFill.resolutionAt &&
        obs[0].knownAt===obs[0].at &&
        obs[0].remainingQuantity===0&&obs[0].pendingQuantity===0 &&
        noFill.decisionAt===signal.at && noFill.plannedEntryAt>signal.at &&
        noFill.resolutionAt<=terminal,
        "P9J_NOFILL_RECEIPT_CHRONOLOGY");
      assert(!accepted.has(signal.id),"P9J_NOFILL_PHANTOM_INVENTORY");
      const before=RES.snapshotFundedReservations(native.reservationBook,
        obs[0].knownAt-1);
      const after=RES.snapshotFundedReservations(native.reservationBook,
        obs[0].knownAt);
      assert(before.reservations.some(x=>x.id===signal.id)&&
        !after.reservations.some(x=>x.id===signal.id),
        "P9J_NOFILL_RESERVE_RELEASE_CLOCK");
      pending=[...new Set([...pending,noFill.plannedEntryAt])].sort((a,b)=>a-b);
      noFillClockInsertions++;
      sourceNoFillReceipts.push({id:signal.id,decisionAt:signal.at,
        effectiveAt:noFill.plannedEntryAt,knownAt:noFill.resolutionAt,
        releasedAfterReceipt:true,phantomInventory:false});
    }
  }
  const finalEquity=advance(terminal);
  assert(close(finalEquity,native.curve.at(-1).equity_end_usd),
    "FWN9_NATIVE_TERMINAL_EQUITY");
  assert(close(maxDrawdown,native.metadata.maximumObservedEventDrawdown),
    "FWN9_NATIVE_EVENT_DRAWDOWN");
  assert(observedCount===native.metadata.observedValuationEvents,
    "FWN9_NATIVE_VALUATION_EVENT_COUNT");
  assert(acceptedCount===native.funded.length,"FWN9_ADMITTED_CAMPAIGN_COUNT");
  assert(noFillClockInsertions===native.modeledNoFills.length,
    "P9J_ALL_NOFILL_RECEIPTS_ACCOUNTED");
  return {schema:"HARPOON_FWN9_M11_P9J_RISK_CLOCK_1",
    signalChecks:checks,acceptedCount,lossRefusals,observedValuationEvents:observedCount,
    maximumObservedEventDrawdown:maxDrawdown,
    terminalEquityUsd:finalEquity,observations:observations.length,
    mirrorGateMisses, noFillClockInsertions,sourceNoFillReceipts,
    historicalP9BMissingNoFillValuationCorrected:true,
    nativeRiskClockParity:true,
    nativeMarkFormationIndependentlyVerified:false,
    realExecutionValidated:false,stochasticWealthBoundCertified:false,
    promotionEligible:false};
}
module.exports={checkNativeRiskClock};
