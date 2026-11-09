"use strict";
// FWN9 P9B: native event-time risk audit. Synthetic engineering fixtures only.
const test=require("node:test"), assert=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const M=require("../runtime30/modulation11_admission_mirror_v2.cjs");
const CAMPAIGN=require("../runtime30/modulation11_stateful_campaign.cjs");
const A=require("../runtime30/fwn9_native_risk_clock_p9b.cjs");
const P9C=require("../runtime30/fwn9_persistent_risk_mirror_p9c.cjs");
const P9D=require("../runtime30/fwn9_native_mark_convergence_p9d_v2.cjs");
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

function auditFixture(f,engine=P9C){
  const n=run(f);
  const m=mirrorWith(f,engine);
  return {f,n,m,proof:P9D.audit({nativeReplay:n.native,mirror:m,
    data:f.data,protocol:f.protocol,limits:f.limits})};
}
test("P9D: all native full-campaign observed marks reconstruct from published closes and receipts",()=>{
  const x=auditFixture(fixture());
  assert.equal(x.proof.nativeCampaignMarksReconstructed,true);
  assert(x.proof.markCount>50);
  assert.equal(x.proof.nativeAdmittedQuantityParity,true);
  assert.equal(x.proof.deviationsCount,0);
  assert.equal(x.proof.fullFixtureNativeRiskParity,true);
  assert.equal(x.proof.stochasticWealthBoundProven,false);
});
test("P9D: partial targets and stops maintain original commitment but mark residual inventory",()=>{
  const f=fixture(),entry=f.signals[0].plannedEntryAt;
  f.tape("SYNA",entry,100,[100.2,102,104,104,104,104,104,104]);
  const x=auditFixture(f),t=x.n.native.funded.find(t=>t.symbol==="SYNA");
  assert(t);
  assert(t.inventoryEvents.filter(e=>e.kind==="EXIT").some(e=>
    -e.quantityDelta<t.quantity));
  assert(x.proof.markCount>5);
  assert.equal(x.proof.deviationsCount,0);
});
test("P9D: native mark tamper is rejected, no false parity certification",()=>{
  const f=fixture(),n=run(f);
  const trade=n.native.funded[0];
  trade.marks[0].pnl+=.25;
  assert.throws(()=>P9D.campaignMarks(trade,f.data,f.protocol),
    /P9D_NATIVE_MARK_RECONSTRUCTION_MISMATCH/);
});
test("P9D v2: modeled IOC no-fill compares RESERVED not only FILLED and retains missing P9B clock evidence",()=>{
  const f=fixture(),e=f.signals[0].plannedEntryAt;
  f.tape("SYNA",e,150,[150.1,149.9,150,150,150,150,150,150]);
  const opts={continuous:true,cashDividends:true,entryExecution:
   "IOC_LIMIT_COMMON_CAUSAL_30BPS",externalCostPerSessionUsd:0,
   calendarCostPerDayUsd:1,profit8:{mode:"NATIVE_MAX"},researchModulation:true};
  const native=N.replayFundedPortfolio(f.signals,f.data,f.protocol,
    [{test:f.data.sessions,selected:"ALL:BASELINE"}],
    f.data.sessions,f.limits,opts);
  // P9B is registered and immutable. Record its missing IOC-no-fill
  // valuation event rather than pretending the historical comparator passes.
  assert.throws(()=>A.checkNativeRiskClock({data:f.data,signals:f.signals,
    native,protocol:f.protocol,limits:f.limits}),
    /FWN9_NATIVE_VALUATION_EVENT_COUNT/);
  const m=mirrorWith(f);
  const audit=P9D.audit({nativeReplay:native,mirror:m,
    data:f.data,protocol:f.protocol,limits:f.limits});
  assert(native.modeledNoFills?.some(x=>x.symbol==="SYNA"));
  assert(!native.funded.some(x=>x.symbol==="SYNA"));
  assert.equal(audit.nativeAdmittedQuantityParity,true);
  assert.equal(audit.deviationsCount,0);
  assert.equal(audit.fullFixtureNativeRiskParity,true);
});
test("P9D: delayed entry knowledge changes risk clock and must NOT be certified as native",()=>{
  const f=fixture();
  const altered={mirror(args){
    return P9C.mirror({...args,receiptFactory:(ctx)=>
      args.receiptFactory(ctx).map(e=>e.kind==="IOC"?
        {...e,knownAt:e.knownAt+120000}:e)});
  }};
  const x=auditFixture(f,altered);
  assert(x.proof.deviationsCount>0||!x.proof.decisionParity);
  assert.equal(x.proof.fullFixtureNativeRiskParity,false);
  assert.equal(x.proof.nativeInfeasibilityCertified,false);
});
if(process.argv.includes("--emit-audit")){
 const x=auditFixture(fixture());
 process.stdout.write("FWN9_P9D_AUDIT="+JSON.stringify(x.proof)+"\n");
}
if(process.argv.includes("--bench")){
 const f=fixture(),n=run(f),m=mirrorWith(f),
  t=process.hrtime.bigint();
 for(let i=0;i<10;i++)P9D.audit({nativeReplay:n.native,mirror:m,
    data:f.data,protocol:f.protocol,limits:f.limits});
 process.stdout.write("FWN9_P9D_10_AUDITS_MS="+
   (Number(process.hrtime.bigint()-t)/1e6).toFixed(3)+"\n");
}
