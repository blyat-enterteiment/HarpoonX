"use strict";
/**
 * M11/P7 - exact pathwise two-ledger decomposition on complete observed
 * eight-substep tapes. Engineering diagnostic ONLY: no signal, RNG, broker,
 * promotion, stochastic bound or native policy substitution.
 * All filled prices, including unsupported OHLC threshold prices, remain
 * visible as a financing residual against the contemporaneous grid mark.
 */
const assert=require("node:assert/strict");
const W=require("./modulation11_shadow_witness.cjs");
const EPS=2e-6;
const close=(a,b)=>Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
function finite(x){assert(Number.isFinite(x),"NON_FINITE_EVENT");return x;}
function record(id,symbol,at,knownAt,delta,price,fee,reason){
  assert(typeof id==="string"&&/^(SYNA|SYNB)$/.test(symbol),"BAD_CAMPAIGN_ID_OR_SYMBOL");
  assert(Number.isSafeInteger(at)&&Number.isSafeInteger(knownAt)&&knownAt>=at,"NONCAUSAL_RECEIPT");
  assert(Number.isSafeInteger(delta)&&delta!==0,"INVALID_INTEGER_INVENTORY_CHANGE");
  assert(finite(price)>0&&finite(fee)>=0,"INVALID_PRICE_OR_FEE");
  return {id,symbol,at,knownAt,delta,price,fee,reason};
}
function pairedEvents(pairs){
  assert(Array.isArray(pairs)&&pairs.length>=2,"DUAL_CAMPAIGN_REQUIRED");
  const native=[],causal=[],campaigns=[],ids=new Set(),symbols=new Set();
  for(const {trade,signal,modeled,discrete} of pairs){
    assert(trade&&signal&&modeled&&discrete&&signal.id===trade.id&&
      signal.symbol===trade.symbol&&Number.isSafeInteger(trade.quantity)&&
      trade.quantity>0&& !ids.has(signal.id),"NATIVE_IDENTITY");
    ids.add(signal.id);symbols.add(signal.symbol);
    assert(close(trade.entry,modeled.entry)&&close(trade.entry,discrete.entry) &&
      trade.opened===modeled.opened&&trade.opened===discrete.opened,
      "IDENTICAL_NATIVE_FUNDED_ENTRY");
    const entry=trade.inventoryEvents.filter(e=>e.kind==="ENTRY");
    const exits=trade.inventoryEvents.filter(e=>e.kind==="EXIT");
    assert(entry.length===1&&entry[0].quantityDelta===trade.quantity&&
      entry[0].at===trade.opened&&exits.length===modeled.fills.length,
      "NATIVE_ENTRY_OR_EXIT_CARDINALITY");
    const buy=record(trade.id,trade.symbol,entry[0].at,entry[0].knownAt,
      trade.quantity,trade.entry,entry[0].feeUsd,"IOC_ENTRY");
    native.push(buy); causal.push({...buy});
    for(let i=0;i<exits.length;i++){
      const e=exits[i],m=modeled.fills[i];
      assert(e.quantityDelta===-m.quantity&&e.at===m.at&&e.knownAt===m.knownAt&&
        close(e.filledPrice,m.price)&&e.reason===m.reason,"NATIVE_MODEL_PARITY");
      native.push(record(trade.id,trade.symbol,e.at,e.knownAt,e.quantityDelta,
        e.filledPrice,e.feeUsd,e.reason));
    }
    let remaining=trade.quantity;
    for(const e of discrete.fills){
      assert(e.quantity>0&&e.quantity<=remaining&&
        e.at>=trade.opened&&e.knownAt>=e.at,"FIRST_CROSS_INVENTORY");
      remaining-=e.quantity;
      causal.push(record(trade.id,trade.symbol,e.at,e.knownAt,-e.quantity,
        e.price,discrete.feesUsd/trade.quantity/2*e.quantity,e.reason));
    }
    assert(remaining===0&&discrete.remaining===0,"UNRESOLVED_CAUSAL_INVENTORY");
    const nLast=exits.at(-1).knownAt, cLast=discrete.fills.at(-1).knownAt;
    campaigns.push({id:trade.id,symbol:trade.symbol,at:signal.at,
      quantity:trade.quantity,initialNotionalUsd:trade.quantity*trade.entry,
      nativeTerminalKnownAt:nLast,causalTerminalKnownAt:cLast,
      nativeNetUsd:trade.netUsd,causalNetUsd:discrete.netUsd});
  }
  assert(symbols.size===2,"EXACT_TWO_SYMBOLS_REQUIRED");
  return {native,causal,campaigns};
}
function runLedger(marks,events,fixedCosts,initialCashUsd){
  const sorted=[
    ...marks.map(m=>({...m,k:"MARK",priority:0})),
    ...fixedCosts.map(c=>({...c,k:"FIXED",priority:1})),
    ...events.map(e=>({...e,k:"FILL",priority:2}))
  ].sort((a,b)=>a.at-b.at||a.priority-b.priority||
    String(a.symbol||"").localeCompare(String(b.symbol||"")));
  const q={SYNA:0,SYNB:0},prices={SYNA:null,SYNB:null};
  let cash=initialCashUsd,markPnl=0,basisPnl=0,fixedPnl=0,peak=initialCashUsd;
  let minCash=initialCashUsd,maxDrawdown=0,absoluteTermBudget=0;
  const byClock=[];
  for(const e of sorted){
    let dMark=0,dBasis=0,dFixed=0;
    if(e.k==="MARK"){
      assert(e.price>0,"NONPOSITIVE_OBSERVED_PRICE");
      if(prices[e.symbol]!==null)dMark=q[e.symbol]*(e.price-prices[e.symbol]);
      else assert(q[e.symbol]===0,"INVENTORY_BEFORE_FIRST_MARK");
      prices[e.symbol]=e.price;markPnl+=dMark;
    }else if(e.k==="FIXED"){
      assert(Number.isFinite(e.usd)&&e.usd>=0&&e.usd<=100,
        "UNREGISTERED_FIXED_COST");
      cash-=e.usd;dFixed=-e.usd;fixedPnl-=e.usd;
    }else{
      assert(prices[e.symbol]!==null,"FILL_WITHOUT_CONTEMPORANEOUS_MARK");
      assert(q[e.symbol]+e.delta>=0,"SHORT_OR_NEGATIVE_INVENTORY");
      const received=record(e.id,e.symbol,e.at,e.knownAt,e.delta,
        e.price,e.fee,e.reason);
      assert(received===received,"VALIDATED_FILL");
      cash-=e.delta*e.price+e.fee;
      q[e.symbol]+=e.delta;
      dBasis=e.delta*(prices[e.symbol]-e.price)-e.fee;
      basisPnl+=dBasis;
    }
    assert(cash>=-EPS,"NO_CASH_BORROWING");
    const equity=cash+Object.keys(q).reduce((x,s)=>x+q[s]*(prices[s]??0),0);
    assert(close(equity,initialCashUsd+markPnl+basisPnl+fixedPnl),
      "SELF_FINANCING_TELESCOPIC_IDENTITY");
    peak=Math.max(peak,equity);minCash=Math.min(minCash,cash);
    maxDrawdown=Math.max(maxDrawdown,(peak-equity)/peak);
    absoluteTermBudget+=Math.abs(dMark)+Math.abs(dBasis)+Math.abs(dFixed);
    byClock.push({at:e.at,kind:e.k,symbol:e.symbol??null,markDelta:dMark,
      basisDelta:dBasis,fixedDelta:dFixed,inventoryA:q.SYNA,inventoryB:q.SYNB,
      cashUsd:cash,equityUsd:equity});
  }
  assert(q.SYNA===0&&q.SYNB===0,"TERMINAL_INVENTORY_NOT_ZERO");
  return {cashUsd:cash,terminalEquityUsd:cash,markPnlUsd:markPnl,
    basisPnlUsd:basisPnl,fixedPnlUsd:fixedPnl,minCashUsd:minCash,
    maxEventDrawdownFraction:maxDrawdown,absoluteTermBudgetUsd:absoluteTermBudget,
    chronology:byClock};
}
function spendableCash(events,fixedCosts,at,initial){
  let available=initial;
  for(const c of fixedCosts)if(c.at<=at)available-=c.usd;
  for(const e of events){
    if(e.delta>0&&e.at<=at)available-=e.delta*e.price+e.fee;
    if(e.delta<0&&e.knownAt<=at)available+=-e.delta*e.price-e.fee;
  }
  return available;
}
function publishedClose(data,symbol,at) {
  const series=data.series.find(x=>x.symbol===symbol);
  let last=null;
  for(const b of series.bars) {
    if(b.availableAt>at)break;
    last=b.c;
  }
  return last;
}
function reserveCeiling(campaigns,at,mode,data) {
  let usd=0,count=0;
  for(const c of campaigns){
    const end=mode==="native"?c.nativeTerminalKnownAt:c.causalTerminalKnownAt;
    if(!(c.at<at&&at<end))continue;
    const closePrice=publishedClose(data,c.symbol,at);
    usd+=Math.max(c.initialNotionalUsd,
      closePrice===null?c.initialNotionalUsd:c.quantity*closePrice);
    count++;
  }
  return {usd,count};
}
function couple({data,substeps,pairs,states,fixedCosts=[],initialCashUsd=20000,
  grossFraction=.12}){
  assert(initialCashUsd===20000&&grossFraction===.12,"REGISTERED_CAPITAL_AND_ADMISSION");
  assert(Array.isArray(data.series)&&data.series.length===2&&
    ["SYNA","SYNB"].every(s=>data.series.some(x=>x.symbol===s)),
    "TWO_REGISTERED_ASSETS");
  assert(Array.isArray(fixedCosts)&&fixedCosts.every(x=>
    Number.isSafeInteger(x.at)&&x.at>=0&&
    Number.isFinite(x.usd)&&x.usd>=0),"FIXED_COST_TIMELINE_REQUIRED");
  const grid=W.witnessedGrid(data,substeps);
  const marks=[...grid.entries()].flatMap(([symbol,points])=>
    points.map(p=>({at:p.at,symbol,price:p.price})));
  const {native,causal,campaigns}=pairedEvents(pairs);
  const N=runLedger(marks,native,fixedCosts,initialCashUsd);
  const C=runLedger(marks,causal,fixedCosts,initialCashUsd);
  const nativeCostFree=N.terminalEquityUsd-initialCashUsd-N.fixedPnlUsd;
  const causalCostFree=C.terminalEquityUsd-initialCashUsd-C.fixedPnlUsd;
  const nativeExpected=campaigns.reduce((s,c)=>s+c.nativeNetUsd,0);
  const causalExpected=campaigns.reduce((s,c)=>s+c.causalNetUsd,0);
  assert(close(nativeCostFree,nativeExpected),"NATIVE_FULL_CAMPAIGN_NET_MISMATCH");
  assert(close(causalCostFree,causalExpected),"CAUSAL_FULL_CAMPAIGN_NET_MISMATCH");
  assert(Array.isArray(states),"NATIVE_DECISION_STATES_REQUIRED");
  const admissions=[];
  for(const state of states.filter(x=>x.reservationStatus==="RESERVED")){
    const at=state.opportunity.at;
    const receipt=state.profit8CommittedReservation;
    assert(Number.isFinite(at)&&receipt&&state.reference.sourceAvailableAt<=at,
      "NONCAUSAL_NATIVE_ADMISSION");
    const a=reserveCeiling(campaigns,at,"native",data);
    const b=reserveCeiling(campaigns,at,"causal",data);
    const knownNative=spendableCash(native,fixedCosts,at,initialCashUsd);
    const knownCausal=spendableCash(causal,fixedCosts,at,initialCashUsd);
    const nativeAdmits=state.notional+receipt.notionalUsd<=grossFraction*state.equity+EPS &&
      state.reservationBefore.riskUsd+receipt.riskUsd<=.0025*state.equity+EPS &&
      state.reservationBefore.cashUsd+receipt.cashUsd<=state.cashPoolUsd+EPS;
    assert(nativeAdmits,"NATIVE_ADMISSION_CONTRACT_VIOLATED");
    admissions.push({id:state.opportunity.id,at,
      nativeCashKnownUsd:knownNative,causalCashKnownUsd:knownCausal,
      nativePriorOriginalQtyReserveUsd:a.usd,
      causalPriorOriginalQtyReserveUsd:b.usd,
      nativeAdmissionPass:true,
      causalSameQuantityNotCertified:true,
      nativeReferenceKnown:true,
      nativeReservationCeilingObserved:a,
      causalReservationCeilingObserved:b,
      // This is retrospective: never feed either ledger to signal decisions.
      exPostSameEntryDiagnosticOnly:true});
  }
  const termDiff=N.terminalEquityUsd-C.terminalEquityUsd;
  const priceInventoryDiff=N.markPnlUsd-C.markPnlUsd;
  const executionResidualDiff=N.basisPnlUsd-C.basisPnlUsd;
  const fixedDiff=N.fixedPnlUsd-C.fixedPnlUsd;
  assert(close(termDiff,priceInventoryDiff+executionResidualDiff+fixedDiff),
    "TWO_BOOK_TELESCOPIC_BRIDGE_FAILED");
  const triangleBound=N.absoluteTermBudgetUsd+C.absoluteTermBudgetUsd;
  assert(Math.abs(termDiff)<=triangleBound+EPS,"INVALID_FINITE_PATH_BOUND");
  const all=Object.freeze({native:N,firstCross:C});
  return {schema:"HARPOON_M11_PHASE7_TWO_ASSET_PATHWISE_COUPLING_1",
    modes:["NATIVE_OHLC","FIRST_CROSS_OBSERVED"],initialCashUsd,
    campaigns:campaigns.length,marketMarks:marks.length,
    nativeEventCount:native.length,causalEventCount:causal.length,
    fixedCostEvents:fixedCosts.length,decisions:admissions,
    native:{terminalEquityUsd:N.terminalEquityUsd,netAfterAllCostsUsd:
      N.terminalEquityUsd-initialCashUsd,maxEventDrawdownFraction:N.maxEventDrawdownFraction,
      minCashUsd:N.minCashUsd},
    causal:{terminalEquityUsd:C.terminalEquityUsd,netAfterAllCostsUsd:
      C.terminalEquityUsd-initialCashUsd,maxEventDrawdownFraction:C.maxEventDrawdownFraction,
      minCashUsd:C.minCashUsd},
    decomposition:{deltaWealthUsd:termDiff,inventoryExposurePnlUsd:priceInventoryDiff,
      executionResidualUsd:executionResidualDiff,fixedDifferentialUsd:fixedDiff,
      pathwiseExPostTriangleUsd:triangleBound,exactIdentity:true,
      stochasticUpperBound:false},
    claims:{fixedEntryQuantitiesOnly:true,fullNativeFundedReplayMatched:true,
      causalReoptimizedAdmissions:false,universalEndogenousCouplingProven:false,
      continuousTwelvePercentCapClaimed:false,nativeInfeasibilityCertified:false},
    accountantInput:{marks,eventsNative:native,eventsCausal:causal,fixedCosts,
      initialCashUsd,expected:{native:N.terminalEquityUsd,causal:C.terminalEquityUsd,
        delta:termDiff,inventory:priceInventoryDiff,residual:executionResidualDiff}},
    actualChronologies:all};
}
module.exports={pairedEvents,runLedger,spendableCash,publishedClose,reserveCeiling,couple};
