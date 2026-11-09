"use strict";
// M11 phase2: synthetic engineering fixtures only; no training or market outcomes.
const test=require("node:test");
const assert=require("node:assert/strict");
const R=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const F=require("../runtime30/modulation11_stateful_campaign.cjs");
const A=require("../runtime30/modulation11_dual_asset_anchor.cjs");
const BAR=300000,DAY=86400000;
const near=(a,b,tol=1e-7)=>assert(Math.abs(a-b)<tol, String(a)+" != "+String(b));

function fixture(offsets=[0,3,4,5,6,7]){
  const sessions=offsets.map(k=>{
    const open=Date.UTC(2025,0,3,14,30)+k*DAY;
    return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
  });
  const series=["SYNA","SYNB"].map(symbol=>({
    symbol,root:symbol,tick:.01,pointValue:1,
    bars:sessions.flatMap(s=>Array.from({length:78},(_,j)=>({
      t:s.open+j*BAR,end:s.open+(j+1)*BAR,availableAt:s.open+(j+1)*BAR+1000,
      o:100,h:100.1,l:99.9,c:100,v:1000
    })))
  }));
  const steps={};
  for(const ser of series){
    steps[ser.symbol]={};
    for(const b of ser.bars)steps[ser.symbol][b.t]=[100.1,99.9,100,100,100,100,100,100];
  }
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,series,
    splitEvents:[],cashDividends:[],provenance:{execution:"MODELED_OHLCV",
      source:"SYNTHETIC_ENGINEERING_ONLY",feed:"SYNTHETIC_FIXTURE",
      files:[{name:"engineered_path",sha256:"0".repeat(64)}]}};
  const p={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
    costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
  const signal=(symbol="SYNA",profile="NATIVE72",minute=60,day=0)=>{
    const at=sessions[day].open+minute*60000+1000;
    const horizon=profile==="PROTECT48"?48:72;
    return {id:symbol+":"+profile+":"+minute,symbol,hypothesis:"CLOSED_CHANNEL",
      direction:1,at,index:0,plannedEntryAt:R.planSignalEntryAt(at,sessions),
      stopDistance:2,regime:.4,
      metadata:{roadmapHorizonHours:horizon,modulation9:{profile}}};
  };
  function tape(symbol,at,values){
    const bar=series.find(s=>s.symbol===symbol).bars.find(b=>b.t===at);
    assert(bar,"BAR_NOT_FOUND");
    const next=values.slice();
    assert.equal(next.length,8);
    bar.h=Math.max(bar.o,...next);bar.l=Math.min(bar.o,...next);bar.c=next[7];
    steps[symbol][bar.t]=next;
  }
  function put(symbol,at,opened,values){
    const bar=series.find(s=>s.symbol===symbol).bars.find(b=>b.t===at);
    bar.o=opened;
    tape(symbol,at,values);
  }
  return {sessions,series,steps,data,p,signal,tape,put};
}
function compare(f,s,qty=8){
  return F.compareNative({signal:s,series:f.series.find(x=>x.symbol===s.symbol),
    data:f.data,protocol:f.p,quantity:qty,substeps:f.steps[s.symbol]});
}
test("M11 full-campaign native parity, persistent partial TP1 then stop",()=>{
  const f=fixture(),s=f.signal();
  f.tape("SYNA",s.plannedEntryAt,[100.2,102.1,103.5,103.1,102.8,102.6,102.2,102]);
  f.put("SYNA",s.plannedEntryAt+BAR,102,[101.8,101.2,99.9,97.5,98,98.6,98.9,99]);
  const x=compare(f,s);
  assert.deepEqual(x.native.inventoryEvents.filter(e=>e.kind==="EXIT").map(e=>e.reason),
    ["TP1","STOP"]);
  assert.equal(x.modeled.remaining,0);
  near(x.modeled.netUsd,-6.34);
  near(x.discrete.netUsd,-8.58);
  near(x.deltaNetUsd,2.24);
  assert.deepEqual(x.modeled.transitions[0].targetDone,[true,false]);
});
test("M11 full-campaign target can execute only once across consecutive bars",()=>{
  const f=fixture(),s=f.signal();
  const first=s.plannedEntryAt;
  f.tape("SYNA",first,[101,103.5,103.5,103.8,103.8,103.8,103.8,103.8]);
  f.put("SYNA",first+BAR,103.8,[103.9,103.9,103.9,104,104,104,104,104]);
  f.put("SYNA",first+2*BAR,104,[104,104,100,97,98,99,99.5,100]);
  const x=compare(f,s);
  assert.equal(x.modeled.fills.filter(t=>t.reason==="TP1").length,1);
  assert.deepEqual(x.modeled.fills.map(t=>t.quantity),[2,6]);
  assert.equal(x.discrete.fills.filter(t=>t.reason==="TP1").length,1);
  assert.equal(x.discrete.fills.reduce((n,t)=>n+t.quantity,0),8);
});
test("M11 custom PROTECT48 trails on received close only across overnight gap",()=>{
  const f=fixture([3,4,5,6,7,10]),s=f.signal("SYNA","PROTECT48");
  const first=s.plannedEntryAt;
  f.tape("SYNA",first,[100.2,101,103.6,104,104,104,104,104]);
  for(const b of f.series[0].bars)
    if(b.t>first && b.t<f.sessions[0].close)
      f.put("SYNA",b.t,104,[104.1,103.9,104,104,104,104,104,104]);
  const monday=f.sessions[1].open;
  f.put("SYNA",monday,100,[100.1,99.9,100,100,100,100,100,100]);
  const x=compare(f,s);
  assert.equal(x.modeled.fills[0].reason,"TP1");
  assert.equal(x.modeled.fills.at(-1).reason,"STOP");
  assert(x.modeled.transitions.some(t=>t.candidateStop>100.03));
  assert.equal(x.modeled.fills.at(-1).at,monday+BAR);
  assert.equal(x.discrete.fills.at(-1).at,monday);
});
test("M11 RUNNER72 keeps one target and stop receipt delay",()=>{
  const f=fixture(),s=f.signal("SYNA","RUNNER72");
  const first=s.plannedEntryAt;
  f.tape("SYNA",first,[100.3,103,104.8,105,105,105,105,105]);
  for(const b of f.series[0].bars)if(b.t>first&&b.t<f.sessions[0].close)
    f.put("SYNA",b.t,105,[105.1,104.9,105,105,105,105,105,105]);
  f.put("SYNA",f.sessions[1].open,100,[100.1,99.9,100,100,100,100,100,100]);
  const x=compare(f,s);
  assert.deepEqual(x.modeled.fills.map(t=>t.reason),["TP1","STOP"]);
  assert.equal(x.modeled.fills.reduce((n,t)=>n+t.quantity,0),8);
  assert.equal(x.modeled.fills.at(-1).knownAt,f.sessions[1].open+BAR+1000);
});
test("M11 dual-asset funded portfolio: admissions, received original marks and reserve lifecycle",()=>{
  const f=fixture();
  const signals=[f.signal("SYNA","NATIVE72",60,0),f.signal("SYNB","NATIVE72",60,1)];
  const limits={...R.PROFIT8_REPLAY_LIMITS,riskFraction:.00125};
  const result=R.replayFundedPortfolio(signals,f.data,f.p,
    [{test:f.sessions,selected:"ALL:BASELINE"}],f.sessions,limits,
    {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
  const a=A.auditTwoAssets(result,signals,limits);
  assert.equal(a.decisionsChecked,2);
  assert.deepEqual(a.coveredAssets,["SYNA","SYNB"]);
  assert.equal(a.accepted,2);
  assert(a.events.some(e=>e.type==="OPENED"));
  assert(a.events.filter(e=>e.type==="CLOSED").length===2);
  assert.equal(a.shadowPortfolioInequalityCertified,false);
  assert.equal(a.continuousTwelvePercentCapClaimed,false);
  assert.equal(result.funded.length,2);
  assert.equal(result.reservationBook.reservations.length,2);
});
test("M11 counterfactual refuses unobserved/mismatched 8-step bars",()=>{
  const f=fixture(),s=f.signal();
  const b=f.series[0].bars.find(x=>x.t===s.plannedEntryAt);
  f.steps.SYNA[b.t][7]=101;
  assert.throws(()=>compare(f,s),/SUBSTEP_OHLC_IDENTITY/);
});


const SHADOW=require("../runtime30/modulation11_shadow_witness.cjs");
function pairedPortfolio(f,signals){
  const limits={...R.PROFIT8_REPLAY_LIMITS,riskFraction:.00125};
  const result=R.replayFundedPortfolio(signals,f.data,f.p,
    [{test:f.sessions,selected:"ALL:BASELINE"}],f.sessions,limits,
    {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
  const pairs=signals.map(signal=>{
    const trade=result.funded.find(t=>t.id===signal.id);
    assert(trade,"NATIVE_CAMPAIGN_MISSING");
    const model=F.statefulCampaign({signal,series:f.series.find(s=>s.symbol===signal.symbol),
      data:f.data,protocol:f.p,quantity:trade.quantity,substeps:f.steps[signal.symbol],
      mode:"NATIVE_OHLC"});
    near(model.netUsd,trade.netUsd);
    return {trade,model,signal};
  });
  return {result,pairs,limits};
}
test("M11 phase3: shadow self-finance and both reserve anchors on full dual-asset native timelines",()=>{
  const f=fixture(),signals=[f.signal("SYNA","NATIVE72",60,0),
    f.signal("SYNB","NATIVE72",60,1)];
  const x=pairedPortfolio(f,signals);
  const proof=SHADOW.auditShadow({data:f.data,substeps:f.steps,
    states:x.result.states,tradePairs:x.pairs,limits:x.limits});
  assert.equal(proof.decisionCount,2);
  assert.equal(proof.eventCount,4); // Two BUY and two TIME SELL events; no partials in this fixture.
  assert.equal(proof.observedAdmissionChecksPassed,true);
  assert(proof.minimumCashUsd>0);
  assert.equal(proof.priceConsistentNativeExecution,true);
  assert.equal(proof.modelBoundCertified,false);
  assert(proof.realizedSameFillFrictionlessCashUsd>=proof.realizedNativeCashUsd);
});
test("M11 phase3: native off-grid stop blocks mathematical execution equivalence",()=>{
  const f=fixture(),signals=[f.signal("SYNA","NATIVE72",60,0),
    f.signal("SYNB","NATIVE72",60,1)];
  f.tape("SYNA",signals[0].plannedEntryAt,[100.1,99.9,99,97.2,98,98.8,99,99.5]);
  const x=pairedPortfolio(f,signals);
  const proof=SHADOW.auditShadow({data:f.data,substeps:f.steps,
    states:x.result.states,tradePairs:x.pairs,limits:x.limits});
  assert(proof.unsupportedNativeExits.some(e=>e.symbol==="SYNA"&&e.reason==="STOP"));
  assert.equal(proof.priceConsistentNativeExecution,false);
  assert.equal(proof.modelBoundCertified,false);
  assert.equal(proof.reasonNotCertified,"OHLC_EXECUTIONS_NOT_IN_EIGHT_STEP_PRICE_SUPPORT");
});
test("M11 phase3: impossible observed-equity witness fails closed, never certifies bound",()=>{
  const f=fixture(),signals=[f.signal("SYNA","NATIVE72",60,0),
    f.signal("SYNB","NATIVE72",60,1)];
  const x=pairedPortfolio(f,signals);
  x.result.states[0].equity=1e9;
  const proof=SHADOW.auditShadow({data:f.data,substeps:f.steps,
    states:x.result.states,tradePairs:x.pairs,limits:x.limits});
  assert.equal(proof.observedAdmissionChecksPassed,false);
  assert.equal(proof.modelBoundCertified,false);
  assert(proof.maximumObservedShadowShortfallUsd>0);
});
test("M11 phase3: tampering with one substep is rejected before witness accounting",()=>{
  const f=fixture(),signals=[f.signal("SYNA","NATIVE72",60,0),
    f.signal("SYNB","NATIVE72",60,1)];
  const x=pairedPortfolio(f,signals);
  const first=signals[0].plannedEntryAt;
  f.steps.SYNA[first][7]=101.42;
  assert.throws(()=>SHADOW.auditShadow({data:f.data,substeps:f.steps,
    states:x.result.states,tradePairs:x.pairs,limits:x.limits}),/SUBSTEP_OHLC_IDENTITY/);
});
