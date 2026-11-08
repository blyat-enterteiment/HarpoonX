"use strict";
// FWN9 P9B: native event-time risk audit. Synthetic engineering fixtures only.
const test=require("node:test"), assert=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const P9A=require("../runtime30/modulation11_native_receipt_parity_p9a.cjs");
const A=require("../runtime30/fwn9_native_risk_clock_p9b.cjs");
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
test("FWN9 P9B: two native funded campaigns reconcile all event mark and drawdown clocks",()=>{
  const f=fixture(),x=run(f);
  assert.equal(x.native.funded.length,2);
  assert.equal(x.checked.acceptedCount,2);
  assert.equal(x.checked.lossRefusals,0);
  assert.equal(x.checked.nativeRiskClockParity,true);
  assert.equal(x.checked.nativeMarkFormationIndependentlyVerified,false);
  close(x.checked.terminalEquityUsd,x.native.curve.at(-1).equity_end_usd);
  close(x.checked.maximumObservedEventDrawdown,
    x.native.metadata.maximumObservedEventDrawdown);
  assert(x.checked.observedValuationEvents>0);
});
test("FWN9 P9B: same-session realized stop loss blocks native next entry, not P8 mirror",()=>{
  const f=fixture();
  const open=f.signals[0].plannedEntryAt;
  // A deliberately discontinuous engineering bar to isolate daily risk gating;
  // NOT a sample from the registered M9 price generator or a backtest profit.
  f.tape("SYNA",open+BAR,60,[60.1,59.5,60,60,60,60,60,60]);
  const x=run(f);
  const loss=x.native.preEntryRefusals.find(e=>e.signalId===f.signals[1].id);
  assert.equal(loss?.reason,"LOSS_LIMIT");
  assert.equal(x.native.funded.length,1);
  assert.equal(x.checked.lossRefusals,1);
  assert(x.checked.signalChecks[1].dailyLossBreached);
  assert.equal(x.checked.signalChecks[1].maxDdBreached,false);
  const p9a=P9A.compare(f);
  assert(p9a.nativeAdmitted.some(r=>r.id===f.signals[1].id),
    "P8 mirror should admit the second asset because its daily gate is missing");
  assert(!x.native.funded.some(t=>t.id===f.signals[1].id));
});
test("FWN9 P9B: native risk audit rejects altered peak/drawdown metadata",()=>{
  const f=fixture();
  const native=N.replayFundedPortfolio(f.signals,f.data,f.protocol,
    [{test:f.data.sessions,selected:"ALL:BASELINE"}],f.data.sessions,f.limits,
    {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
  native.metadata.maximumObservedEventDrawdown+=.01;
  assert.throws(()=>A.checkNativeRiskClock({data:f.data,signals:f.signals,
    native,protocol:f.protocol,limits:f.limits}),/FWN9_NATIVE_EVENT_DRAWDOWN/);
});
test("FWN9 P9B: post-decision changes cannot rewrite earlier native mark anchors",()=>{
  const a=run(fixture()),f=fixture();
  const future=f.signals[1].plannedEntryAt+5*BAR;
  f.tape("SYNB",future,100,[100.1,101,101.5,102,101,100,99,100]);
  const b=run(f);
  for(const key of ["equityUsd","peakUsd","dailyBaselineUsd","cashUsd"]){
    close(a.checked.signalChecks[0][key],b.checked.signalChecks[0][key]);
  }
  assert.equal(a.checked.signalChecks[0].nativeLossRefused,
    b.checked.signalChecks[0].nativeLossRefused);
});
if(process.argv.includes("--emit-audit")){
 const f=fixture(),x=run(f);
 console.log("FWN9_P9B_AUDIT="+JSON.stringify({
  checked:x.checked,accounting:x.native.accounting,
  admittedCampaigns:x.native.funded.map(t=>({id:t.id,quantity:t.quantity})),
  metadata:{maximumObservedEventDrawdown:x.native.metadata.maximumObservedEventDrawdown,
    observedValuationEvents:x.native.metadata.observedValuationEvents}
 }));
}

if(process.argv.includes("--bench")){
 const f=fixture(),begin=process.hrtime.bigint();
 for(let n=0;n<10;n++)run(f);
 console.log("FWN9_P9B_10_AUDITS_MS="+(Number(process.hrtime.bigint()-begin)/1e6).toFixed(3));
}
