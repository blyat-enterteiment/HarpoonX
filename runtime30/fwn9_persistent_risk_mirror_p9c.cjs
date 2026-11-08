"use strict";
/**
 * FWN9 M11/P9C: additive persistent causal risk-clock funded mirror (engineering ONLY).
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
  maxObservedDrawdown:0,peak:20000,lastRiskAt:null,
  riskEvents:[],sessionBaselines:new Map(),riskLossRefusals:0};}
function fixedAt(costs,at){return costs.reduce((s,c)=>s+(c.at<=at?c.usd:0),0);}
function reference(data,symbol,at){
  const series=data.series.find(s=>s.symbol===symbol);
  assert(series&&SYMBOLS.has(symbol),"M11_P8_SYMBOL");
  const r=N.causalReferencePrice({at},series);
  assert(r.status==="AVAILABLE"&&r.sourceAvailableAt<=at,"M11_P8_MISSING_RECEIVED_CLOSE");
  return r.price;
}
function projection(b,data,at,costs){
  const fixed=at<data.sessions[0].open?0:fixedAt(costs,at);
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
/**
 * The clock observes only sessions, completed bars, fixed-charge publication,
 * and receipts with knownAt<=now. Signal-absent events still update peak/DD.
 * The receipt factory may know a future simulated exit but none of its prices
 * enter projection before the corresponding knownAt.
 */
function advanceRiskClock(b,now,data,protocol,costs){
  assert(data.sessions.length>0&&safe(now),"P9C_NATIVE_CALENDAR_REQUIRED");
  const start=data.sessions[0].open;
  const prior=b.lastRiskAt??(start-2);
  assert(now>=prior&&now<=data.sessions.at(-1).close,"P9C_RISK_CLOCK_REGRESSION");
  const times=new Set([now]);
  const opens=new Set();
  for(const session of data.sessions){
    if(session.open-1>prior&&session.open-1<=now)times.add(session.open-1);
    if(session.open>prior&&session.open<=now){
      times.add(session.open);opens.add(session.open);
    }
  }
  for(const series of data.series)for(const bar of series.bars){
    assert(safe(bar.availableAt)&&bar.availableAt>=bar.end,
      "P9C_CAUSAL_MARK_TIMESTAMP");
    if(bar.availableAt>prior&&bar.availableAt<=now)times.add(bar.availableAt);
  }
  for(const event of b.scheduled)
    if(event.knownAt>prior&&event.knownAt<=now)times.add(event.knownAt);
  for(const fee of costs)if(fee.at>prior&&fee.at<=now&&fee.at>=start)times.add(fee.at);
  const baselineByOpen=new Map(data.sessions.map(s=>[s.open-1,s.open]));
  for(const at of [...times].sort((x,y)=>x-y)){
    deliver(b,at,protocol);
    const money=projection(b,data,at,costs);
    const opening=baselineByOpen.get(at);
    if(opening!==undefined)b.sessionBaselines.set(opening,money.equity);
    b.peak=Math.max(b.peak,money.equity);
    const drawdown=1-money.equity/b.peak;
    b.maxObservedDrawdown=Math.max(b.maxObservedDrawdown,drawdown);
    b.riskEvents.push({at,equityUsd:money.equity,cashUsd:money.cashPool,
      observedPeakUsd:b.peak,drawdown,
      sessionBaselineFor:opening??null,
      source:opening!==undefined?"SESSION_PREOPEN":opens.has(at)?
        "SESSION_OPEN":"CAUSAL_EVENT"});
  }
  b.lastRiskAt=now;
}
function decide(b,signal,data,protocol,limits,costs,receiptFactory){
  advanceRiskClock(b,signal.at,data,protocol,costs);
  const before=R.snapshotFundedReservations(b.book,signal.at);
  const money=projection(b,data,signal.at,costs);
  const row={mode:b.mode,id:signal.id,symbol:signal.symbol,at:signal.at,
    equityUsd:money.equity,cashPoolUsd:money.cashPool,
    priorRiskUsd:before.riskUsd,priorNotionalUsd:before.notionalUsd,
    priorCashUsd:before.cashUsd,referenceKnownAt:null,
    status:"PENDING",quantity:0,reason:null};
  const refuse=why=>{row.status="REFUSED";row.reason=why;b.decisions.push(row);return;};
  const session=data.sessions.find(s=>s.open<=signal.at&&signal.at<s.close);
  assert(session&&b.sessionBaselines.has(session.open),"P9C_SESSION_BASELINE_REQUIRED");
  const dailyBaseline=b.sessionBaselines.get(session.open);
  row.risk={peakUsd:b.peak,dailyBaselineUsd:dailyBaseline,
    dailyLossBreached:money.equity<=dailyBaseline*(1-limits.dailyLoss),
    maxDdBreached:money.equity<=b.peak*(1-limits.maxDrawdown),
    observedRiskEvents:b.riskEvents.length};
  if(row.risk.dailyLossBreached||row.risk.maxDdBreached){
    b.riskLossRefusals++;
    return refuse("LOSS_LIMIT");
  }
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
  assert(data?.sessions?.length>0&&data.sessions.every((s,i)=>safe(s.open)&&safe(s.close)&&s.open<s.close&&
    (i===0||s.open>data.sessions[i-1].close)),"P9C_SESSIONS_REQUIRED");
  assert(data?.series?.length===2&&data.series.every(s=>SYMBOLS.has(s.symbol)&&
    s.pointValue===1&&s.tick>0),"M11_P8_TWO_ASSETS_ONLY");
  assert(protocol?.costs&&[protocol.costs.spreadBps,
    protocol.costs.slippageBps,protocol.costs.perSideUsd].every(finite),
    "M11_P8_COSTS_REQUIRED");
  assert(typeof receiptFactory==="function"&&safe(terminalAt)&&
    terminalAt>=signals.at(-1).at,"M11_P8_TERMINAL");
  assert(fixedCosts.every(c=>safe(c.at)&&finite(c.usd)&&c.usd>=0),
    "M11_P8_FIXED_COSTS");
  // The registered external calendar charge is USD 1 per date, including
  // non-trading days until the declared terminal; no fee-free midnight.
  const day=86400000,firstDay=Math.floor(signals[0].at/day),
    lastDay=Math.floor(terminalAt/day);
  assert(lastDay-firstDay<=176,"M11_P8_UNREGISTERED_LONG_WINDOW");
  for(let d=firstDay;d<=lastDay;d++){
    const fees=fixedCosts.filter(c=>Math.floor(c.at/day)===d);
    assert(fees.length===1&&fees[0].usd===1,
      "M11_P8_CALENDAR_COST_REQUIRED_EACH_DATE");
  }
  const books=[createBook("NATIVE_OHLC"),createBook("FIRST_CROSS")];
  for(const signal of signals)
    for(const b of books)decide(b,signal,data,protocol,limits,fixedCosts,receiptFactory);
  for(const b of books){
    advanceRiskClock(b,terminalAt,data,protocol,fixedCosts);
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
      maxDecisionDrawdownFraction:b.maxObservedDrawdown,
      maxObservedEventDrawdownFraction:b.maxObservedDrawdown,
      peakObservedEquityUsd:b.peak,
      riskEventCount:b.riskEvents.length,
      riskLossRefusals:b.riskLossRefusals,
      riskEvents:b.riskEvents,
      riskClockBasis:"RECEIVED_BARS_IOC_EXIT_AND_SESSION_BASELINE;NO_FUTURE_VALUE"};};
  const native=summary(books[0]),causal=summary(books[1]);
  return {schema:"HARPOON_M11_PHASE8_RECEIPT_ADMISSION_MIRROR_1",
    scope:"ENGINEERING_PERSISTENT_CAUSAL_RISK_AND_NATIVE_SIZING_GATE",
    native,causal,
    deltaNetUsd:native.netUsd-causal.netUsd,
    admissionIdentityDiverges:JSON.stringify(native.admits)!==JSON.stringify(causal.admits),
    claims:{nativeSizingAndReservationFunctionsReused:true,
      executionsAreInputReceiptsNotVerifiedMarketFills:true,
      noFutureReceiptUsedAtDecision:true,continuousTwelvePercentCap:false,
      fullStochasticBridgeProven:false,nativeInfeasibilityCertified:false,
      fullOperationalCoverage:false,
      persistentCausalRiskGate:true,fullNativeMarkParityProven:false}};
}
module.exports={mirror,projection,advanceRiskClock};
