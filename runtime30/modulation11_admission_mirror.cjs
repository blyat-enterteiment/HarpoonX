"use strict";
/**
 * M11/P8: deterministic causal admission mirror (engineering ONLY).
 * The same ordered intentions are offered to two independent funded books.
 * Future IOC/exit evidence is delivered to a book ONLY at knownAt; the
 * admission decision may use public closes whose availableAt <= decisionAt.
 * No strategy, stochastic bridge, OHLC payment equivalence, or live execution.
 */
const assert=require("node:assert/strict");
const N=require("./profit8_replay.js");
const R=require("./ultimate_reservations.js");
const EPS=1e-7;
const SYMBOLS=new Set(["SYNA","SYNB"]);
const finite=v=>typeof v==="number"&&Number.isFinite(v);
const safe=t=>Number.isSafeInteger(t)&&t>=0;
function close(a,b){return Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));}
function limitsOk(x){
  const orig=N.PROFIT8_REPLAY_LIMITS;
  assert(x?.capitalUsd===20000&&x.openRiskFraction===orig.openRiskFraction&&
    x.grossFraction===orig.grossFraction&&x.assetFraction===orig.assetFraction&&
    x.dailyLoss===orig.dailyLoss&&x.maxDrawdown===orig.maxDrawdown&&
    x.riskFraction>0&&x.riskFraction<=orig.riskFraction,"M11_P8_FROZEN_LIMITS");
}
function createBook(mode){return {mode,book:R.emptyFundedReservationBook(),
  scheduled:[],positions:new Map(),decisions:[],receipts:[],heldAtDecision:[],
  maxObservedDrawdown:0,peak:20000};}
function fixedAt(costs,at){return costs.reduce((s,c)=>s+(c.at<=at?c.usd:0),0);}
function reference(data,symbol,at){
  const series=data.series.find(s=>s.symbol===symbol);
  assert(series&&SYMBOLS.has(symbol),"M11_P8_SYMBOL");
  const r=N.causalReferencePrice({at},series);
  assert(r.status==="AVAILABLE"&&r.sourceAvailableAt<=at,"M11_P8_MISSING_RECEIVED_CLOSE");
  return r.price;
}
function projection(b,data,at,costs){
  const fixed=fixedAt(costs,at);
  let pnl=0,closed=0;
  for(const p of b.positions.values()){
    if(!p.opened)continue;
    const net=p.realized-p.quantity*p.perSideFee;
    if(p.remaining===0){pnl+=net;closed+=net;}
    else pnl+=net+p.remaining*(reference(data,p.symbol,at)-p.entry-p.perSideFee);
  }
  const equity=20000+pnl-fixed,cashPool=20000+closed-fixed;
  assert(finite(equity)&&equity>0&&finite(cashPool),"M11_P8_INSOLVENT_PROJECTION");
  return {equity,cashPool,fixed,marketPnl:pnl};
}
function schedule(b,signal,quantity,iocPlan,receiptFactory){
  // The factory is an OFFLINE evidence producer. None of its future fields
  // are inspected by admission. Only the knowledge-time queue below reads it.
  const events=receiptFactory({mode:b.mode,signal,quantity,iocPlan});
  assert(Array.isArray(events)&&events.filter(e=>e.kind==="IOC").length===1,
    "M11_P8_ONE_IOC_REQUIRED");
  for(const e of events){
    assert(e?.id===signal.id&&["IOC","EXIT"].includes(e.kind)&&
      safe(e.at)&&safe(e.knownAt)&&e.at>=signal.at&&e.knownAt>=e.at,
      "M11_P8_NONCAUSAL_RECEIPT");
    assert(finite(e.price)&&e.price>0,"M11_P8_PRICE_REQUIRED");
    if(e.kind==="EXIT") assert(e.quantity==="ALL"||
      (Number.isSafeInteger(e.quantity)&&e.quantity>0),"M11_P8_EXIT_QUANTITY");
    b.scheduled.push({...e,signalId:signal.id});
  }
  b.scheduled.sort((a,c)=>a.knownAt-c.knownAt||
    (a.kind==="IOC"?-1:1)-(c.kind==="IOC"?-1:1)||a.at-c.at);
}
function deliver(b,at,protocol){
  let n=0;
  while(n<b.scheduled.length&&b.scheduled[n].knownAt<=at){
    const e=b.scheduled[n++];
    const p=b.positions.get(e.id);
    assert(p&&p.signalAt<=e.at,"M11_P8_ORPHAN_RECEIPT");
    const fee=protocol.costs.perSideUsd;
    if(e.kind==="IOC"){
      assert(!p.opened&&!p.iocResolved,"M11_P8_DUPLICATE_IOC");
      p.iocResolved=true;
      if(e.price>p.priceCeiling+1e-8){
        b.book=R.recordFundedReservationObservation(b.book,{id:e.id,kind:"NO_FILL",
          at:e.at,knownAt:e.knownAt,remainingQuantity:0,pendingQuantity:0});
        p.noFill=true;
      }else{
        assert(p.quantity*e.price+p.quantity*fee<=p.committedCash+EPS,
          "M11_P8_FILL_CASH_OVER_COMMITMENT");
        p.opened=true;p.entry=e.price;p.remaining=p.quantity;
        b.book=R.recordFundedReservationObservation(b.book,{id:e.id,kind:"OPENED",
          at:e.at,knownAt:e.knownAt,remainingQuantity:p.remaining,pendingQuantity:0});
      }
    }else{
      assert(p.opened&&!p.noFill&&p.remaining>0&&p.iocResolved,
        "M11_P8_EXIT_BEFORE_KNOWN_ENTRY");
      const q=e.quantity==="ALL"?p.remaining:e.quantity;
      assert(q<=p.remaining&&e.at>=p.entryAt&&e.at-p.entryAt<=72*3600000,
        "M11_P8_EXIT_HORIZON_OR_INVENTORY");
      p.remaining-=q;p.realized+=(e.price-p.entry)*q-fee*q;
      b.book=R.recordFundedReservationObservation(b.book,{
        id:e.id,kind:p.remaining?"OPENED":"CLOSED",at:e.at,
        knownAt:e.knownAt,remainingQuantity:p.remaining,pendingQuantity:0});
    }
    b.receipts.push({id:e.id,kind:e.kind,at:e.at,knownAt:e.knownAt,
      symbol:p.symbol,price:e.price,quantity:e.kind==="IOC"?(p.noFill?0:p.quantity):
        e.quantity==="ALL"?"ALL":e.quantity,remaining:p.remaining,
      status:p.noFill?"NO_FILL":p.remaining?"OPEN":"CLOSED"});
  }
  b.scheduled=b.scheduled.slice(n);
}
function decide(b,signal,data,protocol,limits,costs,receiptFactory){
  deliver(b,signal.at,protocol);
  const before=R.snapshotFundedReservations(b.book,signal.at);
  const money=projection(b,data,signal.at,costs);
  b.peak=Math.max(b.peak,money.equity);
  b.maxObservedDrawdown=Math.max(b.maxObservedDrawdown,1-money.equity/b.peak);
  const row={mode:b.mode,id:signal.id,symbol:signal.symbol,at:signal.at,
    equityUsd:money.equity,cashPoolUsd:money.cashPool,
    priorRiskUsd:before.riskUsd,priorNotionalUsd:before.notionalUsd,
    priorCashUsd:before.cashUsd,referenceKnownAt:null,
    status:"PENDING",quantity:0,reason:null};
  const refuse=why=>{row.status="REFUSED";row.reason=why;b.decisions.push(row);return;};
  if(money.equity<=b.peak*(1-limits.maxDrawdown))return refuse("DRAW_DOWN_GATE");
  if(before.symbols.includes(signal.symbol))return refuse("SYMBOL_BUSY");
  let notional=before.notionalUsd;
  for(const r of before.reservations)if(r.state==="OPENED"){
    // Exactly the native conservative mark on ORIGINAL quantity.
    const mark=reference(data,r.symbol,signal.at)*r.quantity;
    notional+=Math.max(0,mark-r.notionalUsd);
  }
  const series=data.series.find(s=>s.symbol===signal.symbol);
  const plan=N.planProfit8FundedEntry(signal,series,protocol,limits,{
    equity:money.equity,openRisk:before.riskUsd,notional,
    cashBudgetUsd:money.cashPool-before.cashUsd});
  if(plan.status!=="PLANNED")return refuse(plan.status);
  if(plan.quantity<1)return refuse("INTEGER_RISK_OR_EXPOSURE");
  const ioc=N.planProfit8IocLimit(signal,series,protocol,{
    plannedQuantity:plan.quantity,riskBudgetUsd:plan.riskBudgetUsd,
    notionalBudgetUsd:plan.notionalBudgetUsd,cashBudgetUsd:plan.cashBudgetUsd});
  assert(ioc.status==="PLANNED","M11_P8_UNPLANNED_IOC");
  const committed={id:signal.id,symbol:signal.symbol,decisionAt:signal.at,
    quantity:plan.quantity,riskUsd:plan.quantity*plan.riskUnit,
    notionalUsd:plan.quantity*ioc.priceCeiling,
    cashUsd:plan.quantity*(ioc.priceCeiling+protocol.costs.perSideUsd)};
  const admitted=R.reserveFundedEntry(b.book,committed,{
    equity:money.equity,cashAvailableUsd:money.cashPool,
    riskFraction:limits.riskFraction,openRiskFraction:limits.openRiskFraction,
    grossFraction:limits.grossFraction,assetFraction:limits.assetFraction});
  if(admitted.status==="REFUSED")return refuse(admitted.reason);
  assert(admitted.status==="RESERVED","M11_P8_NOT_RESERVED");
  b.book=admitted.book;row.status="RESERVED";row.quantity=plan.quantity;
  row.referenceKnownAt=plan.reference.sourceAvailableAt;
  row.iocCeilingUsd=ioc.priceCeiling;row.committed=committed;
  row.conservativeNotionalBeforeUsd=notional;
  b.positions.set(signal.id,{id:signal.id,signalAt:signal.at,
    entryAt:signal.plannedEntryAt,symbol:signal.symbol,quantity:plan.quantity,
    priceCeiling:ioc.priceCeiling,committedCash:committed.cashUsd,
    perSideFee:protocol.costs.perSideUsd,entry:null,remaining:0,realized:0,
    opened:false,noFill:false,iocResolved:false});
  b.decisions.push(row);
  schedule(b,signal,plan.quantity,ioc,receiptFactory);
}
function mirror({signals,data,protocol,limits,receiptFactory,fixedCosts=[],terminalAt}){
  limitsOk(limits);
  assert(Array.isArray(signals)&&signals.length>0&&
    signals.every((s,i)=>SYMBOLS.has(s.symbol)&&s.direction===1&&
      safe(s.at)&&safe(s.plannedEntryAt)&&s.plannedEntryAt>=s.at&&
      finite(s.stopDistance)&&s.stopDistance>0&&
      (i===0||s.at>=signals[i-1].at)),"M11_P8_SIGNAL_CHRONOLOGY");
  assert(data?.series?.length===2&&data.series.every(s=>SYMBOLS.has(s.symbol)&&
    s.pointValue===1&&s.tick>0),"M11_P8_TWO_ASSETS_ONLY");
  assert(protocol?.costs&&[protocol.costs.spreadBps,
    protocol.costs.slippageBps,protocol.costs.perSideUsd].every(finite),
    "M11_P8_COSTS_REQUIRED");
  assert(typeof receiptFactory==="function"&&safe(terminalAt)&&
    terminalAt>=signals.at(-1).at,"M11_P8_TERMINAL");
  assert(fixedCosts.every(c=>safe(c.at)&&finite(c.usd)&&c.usd>=0),
    "M11_P8_FIXED_COSTS");
  const books=[createBook("NATIVE_OHLC"),createBook("FIRST_CROSS")];
  for(const signal of signals)
    for(const b of books)decide(b,signal,data,protocol,limits,fixedCosts,receiptFactory);
  for(const b of books){
    deliver(b,terminalAt,protocol);
    assert(b.scheduled.length===0,"M11_P8_UNRECEIVED_TERMINAL_EVENTS");
    assert(R.snapshotFundedReservations(b.book,terminalAt).reservations.length===0,
      "M11_P8_UNRESOLVED_TERMINAL_RESERVATION");
    assert([...b.positions.values()].every(p=>p.noFill||
      (p.opened&&p.remaining===0)),"M11_P8_UNRESOLVED_INVENTORY");
  }
  const summary=b=>{const p=projection(b,data,terminalAt,fixedCosts);
    const filled=[...b.positions.values()].filter(x=>x.opened);
    const net=filled.reduce((z,x)=>z+x.realized-x.quantity*x.perSideFee,0);
    assert(close(p.equity,20000+net-p.fixed)&&close(p.cashPool,p.equity),
      "M11_P8_TERMINAL_SELF_FINANCING");
    return {netUsd:p.equity-20000,equityUsd:p.equity,fixedUsd:p.fixed,
      bookedTradingUsd:net,filledCampaigns:filled.length,
      admits:b.decisions.filter(x=>x.status==="RESERVED").map(x=>({id:x.id,
        symbol:x.symbol,quantity:x.quantity})),decisions:b.decisions,receipts:b.receipts,
      maxDecisionDrawdownFraction:b.maxObservedDrawdown};};
  const native=summary(books[0]),causal=summary(books[1]);
  return {schema:"HARPOON_M11_PHASE8_RECEIPT_ADMISSION_MIRROR_1",
    scope:"ENGINEERING_CAUSAL_RECEIPT_AND_NATIVE_SIZING_GATE",
    native,causal,
    deltaNetUsd:native.netUsd-causal.netUsd,
    admissionIdentityDiverges:JSON.stringify(native.admits)!==JSON.stringify(causal.admits),
    claims:{nativeSizingAndReservationFunctionsReused:true,
      executionsAreInputReceiptsNotVerifiedMarketFills:true,
      noFutureReceiptUsedAtDecision:true,continuousTwelvePercentCap:false,
      fullStochasticBridgeProven:false,nativeInfeasibilityCertified:false,
      fullOperationalCoverage:false}};
}
module.exports={mirror,projection};
