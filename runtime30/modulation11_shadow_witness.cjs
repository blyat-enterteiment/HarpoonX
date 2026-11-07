"use strict";
// M11 phase3: retrospective dual-asset necessary-condition witness.
// Diagnostic only. Never supplies future samples to a strategy or broker.
const assert=require("node:assert/strict");
const G=require("./modulation11_execution_equivalence.cjs");
const EPS=1e-7;
const near=(a,b)=>Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
function witnessedGrid(data,substeps) {
  const result=new Map();
  for(const series of data.series) {
    const samples=[];
    for(const bar of series.bars) {
      const prices=substeps[series.symbol]?.[bar.t];
      G.checkGrid(bar,prices);
      samples.push({at:bar.t,price:bar.o,barAt:bar.t,kind:"OPEN"});
      for(let k=0;k<8;k++) samples.push({
        at:bar.t+Math.floor((k+1)*(bar.end-bar.t)/8),
        price:prices[k],barAt:bar.t,kind:"SUBSTEP"
      });
    }
    samples.sort((a,b)=>a.at-b.at);
    result.set(series.symbol,samples);
  }
  return result;
}
function lastPrice(samples,at) {
  let lo=0,hi=samples.length;
  while(lo<hi){const mid=(lo+hi)>>>1;if(samples[mid].at<=at)lo=mid+1;else hi=mid;}
  return lo===0?null:samples[lo-1];
}
function auditShadow({data,substeps,states,tradePairs,limits,initialCashUsd=20000}) {
  assert(data?.series?.length>=2 && Number.isFinite(initialCashUsd)&&initialCashUsd===20000,
    "TWO_ASSETS_REGISTERED_CAPITAL_ONLY");
  assert(tradePairs.length>=2 && new Set(tradePairs.map(p=>p.trade.symbol)).size>=2,
    "TWO_ACTUAL_CAMPAIGNS_REQUIRED");
  assert(limits?.grossFraction===.12,"UNCHANGED_ADMISSION_CAP_REQUIRED");
  const grid=witnessedGrid(data,substeps);
  const events=[],unsupported=[];
  for(const pair of tradePairs) {
    const trade=pair.trade, model=pair.model;
    assert(trade.id===pair.signal.id && trade.quantity===model.quantity &&
      trade.symbol===pair.signal.symbol,"NATIVE_CAMPAIGN_IDENTITY");
    const nativeEvents=trade.inventoryEvents;
    const exits=nativeEvents.filter(x=>x.kind==="EXIT");
    assert(exits.length===model.fills.length,"MODEL_EXIT_IDENTITY");
    for(let i=0;i<exits.length;i++){
      const fill=model.fills[i],orig=exits[i];
      assert(near(fill.price,orig.filledPrice)&&fill.quantity===-orig.quantityDelta&&
        fill.at===orig.at&&fill.knownAt===orig.knownAt,
        "NATIVE_EXECUTION_MISMATCH");
    }
    const entry=nativeEvents.find(x=>x.kind==="ENTRY");
    assert(entry&&entry.quantityDelta===trade.quantity&&entry.at===trade.opened,
      "NATIVE_ENTRY_MISMATCH");
    const open=grid.get(trade.symbol)?.find(x=>x.at===entry.at&&x.kind==="OPEN");
    assert(open,"ENTRY_MARK_MISSING");
    events.push({id:trade.id,symbol:trade.symbol,kind:"BUY",at:entry.at,
      knownAt:entry.knownAt,qty:trade.quantity,actualPrice:trade.entry,
      rawPrice:open.price,feeUsd:entry.feeUsd});
    for(let i=0;i<exits.length;i++){
      const orig=exits[i],m=model.fills[i];
      const row={id:trade.id,symbol:trade.symbol,kind:"SELL",at:orig.at,knownAt:orig.knownAt,
        qty:-orig.quantityDelta,actualPrice:orig.filledPrice,rawPrice:m.rawPrice,
        feeUsd:orig.feeUsd,reason:orig.reason};
      // Replays book intrabar fills at bar.end, after the entire bar. The
      // threshold price must at least be present in the registered eight-step
      // support before claiming it was a coherent market execution.
      const bar=data.series.find(x=>x.symbol===row.symbol).bars.find(b=>b.end===row.at||
        b.t===row.at);
      assert(bar,"NATIVE_EXIT_BAR_MISSING");
      const support=[bar.o,...substeps[row.symbol][bar.t]].some(v=>near(v,row.rawPrice));
      row.priceOnObservedGrid=support;
      if(!support)unsupported.push({id:row.id,symbol:row.symbol,reason:row.reason,at:row.at,
        nativeRawPrice:row.rawPrice,barAt:bar.t,kind:"OFF_GRID_NATIVE_EXECUTION"});
      events.push(row);
    }
  }
  events.sort((a,b)=>a.at-b.at||(a.kind==="SELL"?-1:1));
  const holdings=new Map(data.series.map(s=>[s.symbol,0]));
  let realCash=initialCashUsd,shadowCash=initialCashUsd;
  let j=0,minimumCash=initialCashUsd,maximumShadowShortfall=0;
  const decisions=[];
  const orderedStates=states.filter(s=>s.reservationStatus==="RESERVED")
    .slice().sort((a,b)=>a.opportunity.at-b.opportunity.at);
  for(const state of orderedStates) {
    const at=state.opportunity.at;
    while(j<events.length && events[j].at<=at) {
      const e=events[j++];
      assert(Number.isFinite(e.actualPrice)&&Number.isFinite(e.rawPrice)&&
        Number.isFinite(e.feeUsd)&&e.feeUsd>=0,"POSITIVE_FINITE_EVENT");
      assert(e.knownAt>=e.at,"RECEIPT_PRECEDES_FILL");
      if(e.kind==="BUY"){
        holdings.set(e.symbol,holdings.get(e.symbol)+e.qty);
        realCash-=e.qty*e.actualPrice+e.feeUsd;
        shadowCash-=e.qty*e.rawPrice;
      } else {
        assert(holdings.get(e.symbol)>=e.qty,"NON_SELF_FINANCING_INVENTORY");
        holdings.set(e.symbol,holdings.get(e.symbol)-e.qty);
        realCash+=e.qty*e.actualPrice-e.feeUsd;
        shadowCash+=e.qty*e.rawPrice;
      }
      minimumCash=Math.min(minimumCash,realCash,shadowCash);
      assert(realCash>=-EPS && shadowCash>=-EPS,"CASH_BORROWING");
    }
    let currentPositionsUsd=0;
    for(const [symbol,qty] of holdings) {
      const price=lastPrice(grid.get(symbol),at);
      if(qty>0)assert(price,"NO_CONTEMPORANEOUS_GRID_PRICE");
      if(price)currentPositionsUsd+=qty*price.price;
    }
    const shadowEquity=shadowCash+currentPositionsUsd;
    const actualEquity=realCash+currentPositionsUsd;
    const reserve=state.profit8CommittedReservation;
    const B=state.notional+reserve.notionalUsd;
    const markCovered=B+EPS>=currentPositionsUsd+reserve.notionalUsd;
    const withinAdmission=B<=limits.grossFraction*state.equity+EPS;
    const shadowDominates=state.equity<=shadowEquity+EPS;
    maximumShadowShortfall=Math.max(maximumShadowShortfall,state.equity-shadowEquity);
    const row={id:state.opportunity.id,symbol:state.opportunity.symbol,at,
      nativeObservedEquity:state.equity,actualLedgerEquity:actualEquity,shadowEquity,
      fullBudgetB:B,reservedNewUsd:reserve.notionalUsd,
      existingPhysicalNotionalUsd:currentPositionsUsd,
      markCovered,withinAdmission,shadowDominates,
      noBorrowing:minimumCash>=-EPS,
      receivedReference:state.reference.sourceAvailableAt<=at};
    decisions.push(row);
  }
  while(j<events.length) {
    const e=events[j++];
    if(e.kind==="BUY"){holdings.set(e.symbol,holdings.get(e.symbol)+e.qty);
      realCash-=e.qty*e.actualPrice+e.feeUsd; shadowCash-=e.qty*e.rawPrice;}
    else{assert(holdings.get(e.symbol)>=e.qty,"NEGATIVE_RESIDUAL");
      holdings.set(e.symbol,holdings.get(e.symbol)-e.qty);
      realCash+=e.qty*e.actualPrice-e.feeUsd; shadowCash+=e.qty*e.rawPrice;}
    minimumCash=Math.min(minimumCash,realCash,shadowCash);
  }
  assert([...holdings.values()].every(x=>x===0),"UNFINISHED_SHADOW_INVENTORY");
  const allChecks=decisions.every(d=>d.markCovered&&d.withinAdmission&&d.shadowDominates&&
    d.noBorrowing&&d.receivedReference) && minimumCash>=-EPS;
  return {schema:"HARPOON_M11_SHADOW_EVENT_WITNESS_1",initialCashUsd,
    decisions,decisionCount:decisions.length,eventCount:events.length,
    unsupportedNativeExits:unsupported,minimumCashUsd:minimumCash,
    realizedNativeCashUsd:realCash,realizedSameFillFrictionlessCashUsd:shadowCash,
    observedAdmissionChecksPassed:allChecks,
    priceConsistentNativeExecution:unsupported.length===0,
    modelBoundCertified:false,
    reasonNotCertified:unsupported.length>0?
      "OHLC_EXECUTIONS_NOT_IN_EIGHT_STEP_PRICE_SUPPORT":
      "FINITE_FIXTURES_CANNOT_PROVE_ALL_NATIVE_PATHS_OR_LIQUIDITY",
    maximumObservedShadowShortfallUsd:maximumShadowShortfall};
}
module.exports={witnessedGrid,lastPrice,auditShadow};
