"use strict";
// Synthetic integration only: no strategy search, provider call or external order.
const test=require("node:test"),assert=require("node:assert/strict"),path=require("node:path");
const root=process.env.HARPOON_FUNDED_TEST_RUNTIME||path.join(__dirname,"../runtime30");
const R=require(path.join(root,"ultimate_replay.js"));
const {defaultProtocol}=require(path.join(root,"ultimate_contracts.js"));
const BAR=300000;
const dates=["2026-11-02","2026-11-03","2026-11-04","2026-11-05","2026-11-06"];
function fixture(count=1){
  const sessions=dates.map(date=>({date,open:Date.parse(date+"T14:30:00Z"),close:Date.parse(date+"T21:00:00Z")}));
  const series=Array.from({length:count},(_,i)=>({symbol:"ASSET"+i,root:"ASSET"+i,pointValue:1,tick:.01,
    bars:sessions.flatMap(s=>Array.from({length:78},(_,j)=>({t:s.open+j*BAR,end:s.open+(j+1)*BAR,
      availableAt:s.open+(j+1)*BAR+3000,o:100,h:100.1,l:99.9,c:100,v:1000})))}));
  const protocol={...defaultProtocol("ALPACA_PROXY"),universe:series.map(s=>s.symbol),purgeHours:0,
    costs:{spreadBps:0,slippageBps:0,perSideUsd:0}};
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,series,splitEvents:[]};
  const signal=(i,at=sessions[0].open+2*BAR+3000,changes={})=>({id:"SIGNAL"+i+":"+at,
    symbol:series[i].symbol,hypothesis:"OPENING_BREAKOUT",direction:1,at,
    plannedEntryAt:R.planSignalEntryAt(at,sessions),index:3,stopDistance:2,regime:.4,...changes});
  const signals=series.map((_,i)=>signal(i));
  const folds=[{test:sessions,selected:"OPENING_BREAKOUT:BASELINE"}];
  return {sessions,series,protocol,data,signals,signal,folds};
}
function run(f,sessions=f.sessions){return R.replayFundedPortfolio(f.signals,f.data,f.protocol,f.folds,sessions);}

test("funded execution reserves simultaneous symbols, risk and notional in one cash pool",()=>{
  const f=fixture(7),out=run(f);
  assert.equal(out.funded.length,5);
  assert.equal(out.portfolio.skipped.INTEGER_RISK_OR_EXPOSURE,2);
  for(const s of out.states){
    if(s.reservationAfter){
      assert(s.reservationAfter.notionalUsd<=s.equity*.5+1e-8);
      assert(s.reservationAfter.riskUsd<=s.equity*.015+1e-8);
      assert(s.reservationAfter.cashUsd<=s.cashPoolUsd+1e-8);
    }
  }
  assert.deepEqual(out.funded.map(t=>t.quantity),[24,24,24,24,4]);
  assert.equal(out.states[1].reservationBefore.pending,1);
  assert.equal(out.curve.length,5);
  assert.equal(out.metadata.financialAcceptanceAllowed,false);
});

test("a duplicate symbol before its first modeled fill cannot open a second campaign",()=>{
  const f=fixture();f.signals.push(f.signal(0,f.signals[0].at+1));
  const out=run(f);
  assert.equal(out.funded.length,1);assert.equal(out.portfolio.skipped.SYMBOL_BUSY,1);
  const refusal=out.preEntryRefusals.find(x=>x.reason==="SYMBOL_BUSY");
  assert.equal(refusal.positionOpened,false);
  assert.equal(refusal.reservationSnapshot.pending,1);
});

test("observed close releases capacity and a later session carries the prior equity",()=>{
  const f=fixture();
  const deadline=f.sessions[0].close-BAR;
  Object.assign(f.series[0].bars.find(b=>b.t===deadline),{o:110,h:110.1,l:109.9,c:110});
  f.signals.push(f.signal(0,f.sessions[1].open+2*BAR+3000));
  const out=run(f);
  assert.equal(out.funded.length,2);assert.equal(out.funded[0].netUsd,240);
  assert.equal(out.states[1].reservationBefore.cashUsd,0);
  assert.equal(out.states[1].equity,20240);
  assert.equal(out.curve[1].equity_start_usd,out.curve[0].equity_end_usd);
  const compounded=out.curve.reduce((equity,r)=>equity*(1+r.portfolio_return),20000);
  assert(Math.abs(compounded-out.curve.at(-1).equity_end_usd)<1e-8);
  assert.equal(out.portfolio.netUsd,out.curve.at(-1).equity_end_usd-20000);
  assert(out.curve.every(r=>r.external_costs_usd===null));
});

test("causal marks of open inventory can increase reserved exposure but pending prices cannot",()=>{
  const f=fixture(2),first=f.signals[0];
  const bar=f.series[0].bars.find(b=>b.t===first.plannedEntryAt);
  Object.assign(bar,{h:200.1,l:99.9,c:200});
  f.signals[1]=f.signal(1,bar.availableAt);
  const out=run(f),s=out.states[1];
  assert.equal(s.reservationBefore.opened,1);
  assert.equal(s.inventoryMarks[0].reference.sourceAvailableAt,bar.availableAt);
  assert.equal(s.inventoryMarks[0].markedNotionalUsd,4800);
  assert.equal(s.notional,4800);
  assert(s.notional>=s.reservationBefore.notionalUsd);
});

test("a future entry price cannot resize the plan; a budget breach retains its reservation",()=>{
  const f=fixture(),baseline=run(f),before=baseline.states[0];
  Object.assign(f.series[0].bars.find(b=>b.t===f.signals[0].plannedEntryAt),{o:150,h:150.1,l:149.9,c:150});
  assert.throws(()=>run(f),e=>{
    assert.equal(e.code,"FUNDED_ENTRY_BUDGET_BREACH");
    assert.deepEqual(e.details.lastDecision.plan,before.plan);
    assert.equal(e.details.plannedQuantity,24);
    assert.equal(e.details.reservationBook.reservations.length,1);
    assert.equal(e.details.cause.exposure.remainingQuantityAtEntry,24);
    assert.equal(e.details.economicPnlUsd,null);
    return true;
  });
});

test("the first observed fill is marked causally before another asset compounds its size",()=>{
  const f=fixture(2),first=f.signals[0];
  for(const b of f.series[0].bars)if(b.t<first.plannedEntryAt)
    Object.assign(b,{o:99,h:99.1,l:98.9,c:99});
  f.signals[1]=f.signal(1,first.plannedEntryAt+3000);
  const out=run(f),next=out.states[1];
  assert.equal(out.funded[0].quantity,24);
  assert.equal(out.funded[0].entry,100);
  assert.equal(next.inventoryMarks[0].reference.price,99);
  assert.equal(next.equity,19976);
  assert.equal(next.quantity,23);
  assert.equal(next.reservationBefore.opened,1);
});

test("entry and exit fee allowances do not jump when the first post-fill mark arrives",()=>{
  const early=fixture(2);early.protocol.costs.perSideUsd=1;
  early.signals[1]=early.signal(1,early.signals[0].plannedEntryAt+3000);
  const a=run(early);
  const later=fixture(2);later.protocol.costs.perSideUsd=1;
  later.signals[1]=later.signal(1,later.signals[0].plannedEntryAt+BAR+3000);
  const b=run(later);
  assert.equal(a.funded[0].quantity,12);
  assert.equal(a.states[1].equity,19976);
  assert.equal(b.states[1].equity,a.states[1].equity);
});

test("an absent planned fill is an unresolved reserved exposure, never a zero-PnL skip",()=>{
  const f=fixture();f.series[0].bars=f.series[0].bars.filter(b=>b.t!==f.signals[0].plannedEntryAt);
  assert.throws(()=>run(f),e=>{
    assert.equal(e.code,"UNOBSERVED_ENTRY");
    assert.equal(e.details.cause.reason,"MISSING_PLANNED_ENTRY_BAR");
    assert.equal(e.details.decisionReservations.cashUsd,2400);
    assert.equal(e.details.economicPnlUsd,null);
    assert.deepEqual(e.details.funded,[]);
    return true;
  });
});

test("an incomplete path after entry retains the last mark and original reserved capital",()=>{
  const f=fixture(),missing=f.signals[0].plannedEntryAt+2*BAR;
  f.series[0].bars=f.series[0].bars.filter(b=>b.t!==missing);
  assert.throws(()=>run(f),e=>{
    assert.equal(e.code,"UNRESOLVED_HOLDING_EXPOSURE");
    assert.equal(e.details.cause.remainingQuantity,24);
    assert(e.details.cause.lastKnownMark);
    assert.equal(e.details.reservationBook.reservations[0].cashUsd,2400);
    assert.equal(e.details.economicPnlUsd,null);return true;
  });
});

test("calendar refusal occurs before requiring any later entry price",()=>{
  const f=fixture();f.data.sessions=f.sessions.slice(0,1);
  f.signals[0].hypothesis="CLOSED_CHANNEL";
  f.folds=[{test:f.data.sessions,selected:"CLOSED_CHANNEL:BASELINE"}];
  f.series[0].bars=[];
  const out=run(f,f.data.sessions);
  assert.equal(out.funded.length,0);
  assert.equal(out.preEntryRefusals[0].reason,"CALENDAR_HORIZON_NOT_COVERED");
  assert.equal(out.preEntryRefusals[0].positionOpened,false);
  assert.equal(out.reservationBook.reservations.length,0);
});

test("missing causal reference refuses entry rather than using the future fill price",()=>{
  const f=fixture();f.series[0].bars=f.series[0].bars.filter(b=>b.availableAt>f.signals[0].at);
  const out=run(f);
  assert.equal(out.funded.length,0);
  assert.equal(out.portfolio.skipped.NO_CAUSAL_REFERENCE_PRICE,1);
  assert.equal(out.reservationBook.reservations.length,0);
});

test("terminal open exposure is preserved with a mark and an incident, not force-closed",()=>{
  const f=fixture();
  const terminalSession=f.sessions[0];
  f.signals[0].hypothesis="CLOSED_CHANNEL";
  f.folds=[{test:[terminalSession],selected:"CLOSED_CHANNEL:BASELINE"}];
  assert.throws(()=>run(f,[terminalSession]),e=>{
    assert.equal(e.code,"TERMINAL_FUNDED_EXPOSURE_UNRESOLVED");
    assert.equal(e.details.terminalReservations.opened,1);
    assert(e.details.lastKnownMarks[0].lastKnownMark);
    assert.equal(e.details.lastKnownMarks[0].remainingQuantity,null);
    assert(e.details.funded[0].closed>terminalSession.close);
    assert.equal(e.details.curve.length,1);
    assert.equal(e.details.economicPnlUsd,null);return true;
  });
});

test("selection outside the evaluation period cannot inject earlier account profits",()=>{
  const f=fixture();
  assert.throws(()=>run(f,f.sessions.slice(1)),/inside the declared evaluation calendar/);
  f.folds.push(structuredClone(f.folds[0]));
  assert.throws(()=>run(f),/disjoint/);
});

test("portfolio return intervals include overnight time and reconcile asset contributions",()=>{
  const f=fixture(),out=run(f);
  assert.equal(out.curve[0].start_at,f.sessions[0].open-1);
  for(let i=0;i<out.curve.length;i++){
    const row=out.curve[i];
    if(i)assert.equal(row.start_at,out.curve[i-1].end_at);
    assert(Math.abs(Object.values(row.asset_pnl_usd).reduce((a,b)=>a+b,0)-row.modeled_trading_pnl_usd)<1e-8);
  }
});
