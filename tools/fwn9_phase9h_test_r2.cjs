"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const H=require("../runtime30/fwn9_p9h_cash_ledger.cjs");
const DAY=86400000,BAR=300000;
function fixture(){
  const sessions=[0,3,4,5,6,7].map(k=>{
    const open=Date.UTC(2025,0,3,14,30)+k*DAY;
    return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
  });
  const series=["SYNA","SYNB"].map(symbol=>({
    symbol,root:symbol,tick:.01,pointValue:1,bars:sessions.flatMap(s=>
      Array.from({length:78},(_,i)=>({t:s.open+i*BAR,end:s.open+(i+1)*BAR,
        availableAt:s.open+(i+1)*BAR+1000,
        o:100,h:100.1,l:99.9,c:100,v:1000})))
  }));
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,
    series,splitEvents:[],cashDividends:[],provenance:{execution:"MODELED_OHLCV",
      source:"SYNTHETIC_ENGINEERING_ONLY",feed:"SYNTHETIC_FIXTURE",
      files:[{name:"p9h_fixture",sha256:"0".repeat(64)}]}};
  const protocol={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
    costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
  const signal=(symbol,sessionIndex,minute)=>{const at=sessions[sessionIndex].open+
    minute*60000+1000;
    return {id:symbol+":"+sessionIndex+":"+minute,symbol,at,index:0,
      hypothesis:"CLOSED_CHANNEL",direction:1,
      plannedEntryAt:N.planSignalEntryAt(at,sessions),
      stopDistance:2,regime:.4,
      metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
  };
  const signals=[signal("SYNA",0,60),signal("SYNB",0,90)];
  function tape(symbol,at,points,opening){
    const b=series.find(x=>x.symbol===symbol).bars.find(x=>x.t===at);
    A.ok(b);A.equal(points.length,8);
    b.o=opening;b.h=Math.max(opening,...points);b.l=Math.min(opening,...points);
    b.c=points[7];
  }
  const limits={...N.PROFIT8_REPLAY_LIMITS,riskFraction:.00125};
  const opts={continuous:true,cashDividends:true,
    entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
    profit8:{mode:"NATIVE_MAX"},researchModulation:true};
  function run(){return N.replayFundedPortfolio(signals,data,protocol,
    [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,opts);}
  return {data,protocol,limits,signals,sessions,tape,run};
}
function audit(f){
  const n=f.run(),s=n.states.find(s=>s.reservationStatus==="RESERVED"&&
    s.opportunity.symbol==="SYNB");
  A.ok(s,"SECOND_ACCEPTED_ADMISSION_REQUIRED");
  return {n,s,check:H.auditDecision({nativeReplay:n,data:f.data,
    protocol:f.protocol,limits:f.limits,state:s})};
}
test("P9H: source native booked cash differs from physical free cash while position remains",()=>{
  const f=fixture(),x=audit(f);
  A.equal(x.check.sampleOnly,true);
  A.equal(x.check.fullM9Certificate,false);
  A.ok(x.check.physicalVsClosedPoolUsd < -100,
    "OPEN_SHARES_PRINCIPAL_IS_NOT_AVAILABLE_CASH");
  A.ok(x.check.localLedgerFloorUsd>x.check.conditionalGlobalFloorUsd);
  A.ok(x.check.currentStockPlusPendingUsd<=.12*x.s.equity+1e-6);
});
test("P9H: full original reservation survives known partial target sale",()=>{
  const f=fixture(),entry=f.signals[0].plannedEntryAt;
  f.tape("SYNA",entry,[100.2,102,104,104,104,104,104,104],100);
  const x=audit(f),t=x.n.funded.find(t=>t.symbol==="SYNA");
  A.ok(t.inventoryEvents.some(e=>e.kind==="EXIT"&&-e.quantityDelta<t.quantity));
  const row=x.s.reservationAfter.reservations.find(x=>x.id===t.id);
  A.ok(row&&row.quantity===t.quantity);
  A.ok(x.check.open.some(p=>p.id===t.id&&p.remaining<p.original));
  A.ok(x.check.sourceCashMarkIdentity);
});
test("P9H: modeled IOC NO_FILL releases commitment with zero phantom stock",()=>{
  const f=fixture(),entry=f.signals[0].plannedEntryAt;
  f.tape("SYNA",entry,[150.1,149.9,150,150,150,150,150,150],150);
  const n=f.run();
  A.ok(n.modeledNoFills?.length>0);
  const result=H.auditNoFill({nativeReplay:n,at:entry});
  A.equal(result.noFillReleased,true);
  A.equal(result.valuationClockP9BProven,false);
});
test("P9H: rejects an ex-post exit with delayed knowledge on an earlier decision",()=>{
  const f=fixture(),x=audit(f),t=x.n.funded.find(t=>t.symbol==="SYNA");
  A.ok(t);
  const e=t.inventoryEvents.find(e=>e.kind==="EXIT");
  A.ok(e);
  e.at=x.s.opportunity.at-1000;e.knownAt=x.s.opportunity.at+1000;
  A.throws(()=>H.auditDecision({nativeReplay:x.n,data:f.data,
    protocol:f.protocol,limits:f.limits,state:x.s}),
    /P9H_UNSETTLED_EFFECTIVE_EXIT/);
});
test("P9H: tampering equity/receipt/reserve fails closed",()=>{
  const f=fixture(),x=audit(f);
  A.throws(()=>H.auditDecision({nativeReplay:x.n,data:f.data,protocol:f.protocol,
    limits:f.limits,state:{...x.s,equity:x.s.equity+3}}),
    /P9H_PHYSICAL_CASH_MARK_NATIVE_EQUITY_MISMATCH/);
  const other={...x.s,reservationAfter:{...x.s.reservationAfter,
    riskUsd:x.s.reservationAfter.riskUsd+100}};
  A.throws(()=>H.auditDecision({nativeReplay:x.n,data:f.data,
    protocol:f.protocol,limits:f.limits,state:other}),
    /P9H_UNCOVERED_FUTURE_RECEIPT_FEES/);
});
if(process.argv.includes("--emit-audit")){
  const x=audit(fixture());
  process.stdout.write("P9H_AUDIT="+JSON.stringify({check:x.check,raw:{
    states:x.n.states.filter(s=>s.reservationStatus==="RESERVED").map(s=>({
      id:s.opportunity.id,at:s.opportunity.at})),
    openTrades:x.n.funded.filter(t=>t.opened<=x.s.opportunity.at).map(t=>({
      id:t.id,entry:t.entry,quantity:t.quantity,opened:t.opened,
      inventoryEvents:t.inventoryEvents,netUsd:t.netUsd})),
    costPerSide:x.n.funded.length?.005:0,
    observedAt:x.s.opportunity.at,capital:20000
  }})+"\n");
}
if(process.argv.includes("--bench")){
  const f=fixture(),x=audit(f),t=process.hrtime.bigint();
  for(let i=0;i<500;i++)H.auditDecision({nativeReplay:x.n,
    data:f.data,protocol:f.protocol,limits:f.limits,state:x.s});
  process.stdout.write("P9H_500_LEDGER_AUDITS_MS="+
    (Number(process.hrtime.bigint()-t)/1e6).toFixed(3)+"\n");
}
