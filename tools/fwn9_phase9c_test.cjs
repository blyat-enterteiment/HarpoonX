"use strict";
// FWN9 P9B: native event-time risk audit. Synthetic engineering fixtures only.
const test=require("node:test"), assert=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const M=require("../runtime30/modulation11_admission_mirror_v2.cjs");
const CAMPAIGN=require("../runtime30/modulation11_stateful_campaign.cjs");
const A=require("../runtime30/fwn9_native_risk_clock_p9b.cjs");
const P9C=require("../runtime30/fwn9_persistent_risk_mirror_p9c.cjs");
const DAY=86400000,BAR=300000;
const close=(a,b)=>assert(Math.abs(a-b)<1e-7*Math.max(1,Math.abs(a),Math.abs(b)),
  String(a)+" != "+String(b));
function fixture(){
  const sessions=[0,3,4,5,6,7].map(k=>{
    const open=Date.UTC(2025,0,3,14,30)+k*DAY;
    return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
  });
  const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,pointValue:1,
    bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>({
      t:s.open+i*BAR,end:s.open+(i+1)*BAR,
      availableAt:s.open+(i+1)*BAR+1000,
      o:100,h:100.1,l:99.9,c:100,v:1000})))
  }));
  const substeps=Object.fromEntries(series.map(s=>[s.symbol,
    Object.fromEntries(s.bars.map(b=>[b.t,[100.1,99.9,100,100,100,100,100,100]]))]));
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,series,
    splitEvents:[],cashDividends:[],provenance:{execution:"MODELED_OHLCV",
      source:"SYNTHETIC_ENGINEERING_ONLY",feed:"SYNTHETIC_FIXTURE",
      files:[{name:"p9b_fixture",sha256:"0".repeat(64)}]}};
  const protocol={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
    costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
  const at=(minutes)=>sessions[0].open+minutes*60000+1000;
  const signal=(symbol,minutes)=>({id:symbol+":"+minutes,symbol,
    hypothesis:"CLOSED_CHANNEL",direction:1,at:at(minutes),index:0,
    plannedEntryAt:N.planSignalEntryAt(at(minutes),sessions),
    stopDistance:2,regime:.4,
    metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}});
  const signals=[signal("SYNA",60),signal("SYNB",90)];
  const fixedCosts=Array.from({length:8},(_,i)=>({
    at:Date.UTC(2025,0,3)+i*DAY,usd:1}));
  function tape(symbol,barAt,open,points){
    const seriesRow=series.find(s=>s.symbol===symbol);
    const b=seriesRow.bars.find(b=>b.t===barAt);
    assert(b,"P9B_TEST_BAR_NOT_FOUND");
    assert.equal(points.length,8);
    b.o=open;b.h=Math.max(open,...points);b.l=Math.min(open,...points);
    b.c=points.at(-1);substeps[symbol][barAt]=points.slice();
  }
  return {signals,data,protocol,substeps,fixedCosts,
    limits:{...N.PROFIT8_REPLAY_LIMITS,riskFraction:.00125},
    terminalAt:sessions.at(-1).close,tape};
}
function run(f){
  const native=N.replayFundedPortfolio(f.signals,f.data,f.protocol,
    [{test:f.data.sessions,selected:"ALL:BASELINE"}],
    f.data.sessions,f.limits,
    {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
  const checked=A.checkNativeRiskClock({data:f.data,signals:f.signals,native,
    protocol:f.protocol,limits:f.limits});
  return {native,checked};
}
function mirrorWith(f,engine=P9C){
  return engine.mirror({signals:f.signals,data:f.data,protocol:f.protocol,
    limits:f.limits,substeps:f.substeps,fixedCosts:f.fixedCosts,terminalAt:f.terminalAt,
    receiptFactory:({mode,signal,quantity,iocPlan})=>{
      const series=f.data.series.find(s=>s.symbol===signal.symbol);
      const entry=series.bars.find(b=>b.t===signal.plannedEntryAt);
      assert(entry,"P9B_NATIVE_RECEIPT_ENTRY_BAR");
      const px=Math.ceil(entry.o*(1+.0003)/series.tick-1e-10)*series.tick;
      const ioc={id:signal.id,kind:"IOC",at:entry.t,knownAt:entry.t,price:px};
      if(px>iocPlan.priceCeiling+1e-8)return [ioc];
      const cmp=CAMPAIGN.compareNative({signal,series,data:f.data,
        protocol:f.protocol,quantity,substeps:f.substeps[signal.symbol]});
      const fills=mode==="NATIVE_OHLC"?
        cmp.native.inventoryEvents.filter(e=>e.kind==="EXIT").map(e=>({
          at:e.at,knownAt:e.knownAt,price:e.filledPrice,quantity:-e.quantityDelta})):
        cmp.discrete.fills.map(e=>({
          at:e.at,knownAt:e.knownAt,price:e.price,quantity:e.quantity}));
      assert.equal(fills.reduce((n,e)=>n+e.quantity,0),quantity);
      const terminal=mode==="NATIVE_OHLC"?
        N.profit8KnownAt(cmp.native):cmp.discrete.terminalKnownAt;
      return [ioc,...fills.map((e,i)=>({id:signal.id,kind:"EXIT",
        at:e.at,knownAt:i===fills.length-1?Math.max(e.knownAt,terminal):e.knownAt,
        price:e.price,quantity:e.quantity}))];
    }});
}
test("P9C: both independent books admit healthy native fixtures",()=>{
 const f=fixture(),n=run(f),m=mirrorWith(f);
 assert.equal(n.native.funded.length,2);
 assert.deepEqual(m.native.admits.map(x=>x.id),f.signals.map(x=>x.id));
 assert.deepEqual(m.causal.admits.map(x=>x.id),f.signals.map(x=>x.id));
 assert.equal(m.native.riskLossRefusals,0);
 assert(m.native.riskEventCount>m.native.decisions.length);
 assert(m.native.riskEvents.some(x=>x.source==="SESSION_PREOPEN"));
 close(m.native.decisions[0].risk.dailyBaselineUsd,20000);
 close(m.native.decisions[0].equityUsd,n.checked.signalChecks[0].equityUsd);
 close(m.native.decisions[1].equityUsd,n.checked.signalChecks[1].equityUsd);
 assert.equal(m.claims.fullStochasticBridgeProven,false);
 assert.equal(m.claims.fullNativeMarkParityProven,false);
});
test("P9C: both risk books refuse next asset on published 2pct daily loss",()=>{
 const f=fixture(),open=f.signals[0].plannedEntryAt;
 f.tape("SYNA",open+BAR,60,[60.1,59.5,60,60,60,60,60,60]);
 const n=run(f),p8=mirrorWith(f,M),p9c=mirrorWith(f);
 assert.equal(n.native.preEntryRefusals.find(x=>x.signalId===f.signals[1].id)?.reason,"LOSS_LIMIT");
 assert(p8.native.admits.some(x=>x.id===f.signals[1].id));
 assert.equal(p9c.native.decisions[1].reason,"LOSS_LIMIT");
 assert.equal(p9c.causal.decisions[1].reason,"LOSS_LIMIT");
 assert.deepEqual(p9c.native.admits.map(x=>x.id),[f.signals[0].id]);
 assert.equal(p9c.native.riskLossRefusals,1);
 assert(p9c.native.decisions[1].risk.dailyLossBreached);
 assert.equal(p9c.native.decisions[1].risk.maxDdBreached,false);
});
test("P9C: observation clock advances even with no intervening signal",()=>{
 const f=fixture(),m=mirrorWith(f);
 const first=m.native.decisions[0],second=m.native.decisions[1];
 assert(second.risk.observedRiskEvents>first.risk.observedRiskEvents);
 const times=m.native.riskEvents.map(x=>x.at);
 assert(times.every((x,i)=>!i||x>=times[i-1]));
 assert.equal(new Set(times).size,times.length);
 assert(m.native.riskEvents.some(x=>x.at>f.signals[0].at&&x.at<f.signals[1].at));
});
test("P9C: failed IOC is released on knownAt without inventing proceeds",()=>{
 const f=fixture(),entry=f.signals[0].plannedEntryAt;
 f.tape("SYNA",entry,150,[150.1,149.9,150,150,150,150,150,150]);
 const m=mirrorWith(f);
 assert.equal(m.native.decisions[0].status,"RESERVED");
 const r=m.native.receipts.find(x=>x.id===f.signals[0].id);
 assert.equal(r.status,"NO_FILL");
 assert.equal(r.knownAt,entry);
 assert(!m.native.receipts.some(x=>x.id===f.signals[0].id&&x.kind==="EXIT"));
 assert(m.native.admits.some(x=>x.id===f.signals[1].id));
});
test("P9C: future path variation cannot change earlier risk decisions",()=>{
 const f=fixture(),a=mirrorWith(f),future=f.signals[1].plannedEntryAt+6*BAR;
 f.tape("SYNB",future,100,[100.1,102,103,102,101,100,100,100]);
 const b=mirrorWith(f);
 for(const book of ["native","causal"]){
   const project=o=>o[book].decisions.map(x=>({
     id:x.id,status:x.status,qty:x.quantity,eq:x.equityUsd,
     peak:x.risk?.peakUsd,baseline:x.risk?.dailyBaselineUsd}));
   assert.deepEqual(project(a),project(b));
 }
});
test("P9C: partial exit receipts preserve remaining inventory commitment",()=>{
 const f=fixture(),entry=f.signals[0].plannedEntryAt;
 f.tape("SYNA",entry,100,[100.2,102,104,104,104,104,104,104]);
 const m=mirrorWith(f);
 const e=m.native.receipts.filter(x=>x.id===f.signals[0].id&&x.kind==="EXIT");
 assert(e.length>0);
 assert(e.some(x=>typeof x.quantity==="number"&&x.quantity>0&&x.remaining>0));
 assert(m.native.riskEventCount>m.native.receipts.length);
});
test("P9C: weekend baseline includes complete fixed calendar charges",()=>{
 const f=fixture(),m=mirrorWith(f);
 assert.equal(m.native.fixedUsd,8);
 assert(m.native.riskEvents.some(x=>x.source==="SESSION_PREOPEN"&&x.at>=f.data.sessions[1].open-1));
 assert(m.native.peakObservedEquityUsd>=20000);
 assert.equal(m.native.riskLossRefusals,0);
});
if(process.argv.includes("--emit-risk")){
 const m=mirrorWith(fixture());
 console.log("FWN9_P9C_RISK="+JSON.stringify({
  native:{netUsd:m.native.netUsd,equityUsd:m.native.equityUsd,
   fixedUsd:m.native.fixedUsd,bookedTradingUsd:m.native.bookedTradingUsd,
   riskEventCount:m.native.riskEventCount,riskLossRefusals:m.native.riskLossRefusals,
   maxObservedEventDrawdownFraction:m.native.maxObservedEventDrawdownFraction},
  causal:{netUsd:m.causal.netUsd,equityUsd:m.causal.equityUsd,
   fixedUsd:m.causal.fixedUsd,bookedTradingUsd:m.causal.bookedTradingUsd,
   riskEventCount:m.causal.riskEventCount,riskLossRefusals:m.causal.riskLossRefusals}
 }));
}
if(process.argv.includes("--bench")){
 const f=fixture(),start=process.hrtime.bigint();
 for(let i=0;i<10;i++)mirrorWith(f);
 console.log("FWN9_P9C_10_MIRRORS_MS="+(Number(process.hrtime.bigint()-start)/1e6).toFixed(3));
}
