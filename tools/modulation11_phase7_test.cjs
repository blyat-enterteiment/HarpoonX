"use strict";
// M11/P7: deterministic engineering fixtures; not market-generator seeds.
const test=require("node:test");
const assert=require("node:assert/strict");
const R=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const F=require("../runtime30/modulation11_stateful_campaign.cjs");
const L=require("../runtime30/modulation11_multibar_coupling.cjs");
const A=require("../runtime30/modulation11_dual_asset_anchor.cjs");
const BAR=300000,DAY=86400000;
const near=(a,b,tol=1e-7)=>assert(Math.abs(a-b)<tol,String(a)+" != "+String(b));
function fixture(){
  const sessions=[0,3,4,5,6,7].map(k=>{
    const open=Date.UTC(2025,0,3,14,30)+k*DAY;
    return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
  });
  const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,pointValue:1,
    bars:sessions.flatMap(s=>Array.from({length:78},(_,j)=>({
      t:s.open+j*BAR,end:s.open+(j+1)*BAR,availableAt:s.open+(j+1)*BAR+1000,
      o:100,h:100.1,l:99.9,c:100,v:1000})))
  }));
  const steps=Object.fromEntries(series.map(ser=>[ser.symbol,
    Object.fromEntries(ser.bars.map(bar=>[bar.t,[100.1,99.9,100,100,100,100,100,100]]))]));
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,series,
    splitEvents:[],cashDividends:[],provenance:{execution:"MODELED_OHLCV",
      source:"SYNTHETIC_ENGINEERING_ONLY",feed:"SYNTHETIC_FIXTURE",
      files:[{name:"P7_ENGINEERING_FIXTURE",sha256:"0".repeat(64)}]}};
  const p={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
    costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
  const signal=(symbol,day)=>{const at=sessions[day].open+60*60000+1000;return {
    id:symbol+":NATIVE72:"+day,symbol,hypothesis:"CLOSED_CHANNEL",direction:1,
    at,index:0,plannedEntryAt:R.planSignalEntryAt(at,sessions),stopDistance:2,regime:.4,
    metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};};
  function tape(symbol,at,values){
    const bar=series.find(s=>s.symbol===symbol).bars.find(b=>b.t===at);
    assert(bar);bar.h=Math.max(bar.o,...values);
    bar.l=Math.min(bar.o,...values);bar.c=values[7];
    steps[symbol][at]=values.slice();
  }
  const signals=[signal("SYNA",0),signal("SYNB",1)];
  return {sessions,series,data,p,steps,signals,tape};
}
function run(f){
  const limits={...R.PROFIT8_REPLAY_LIMITS,riskFraction:.00125};
  const result=R.replayFundedPortfolio(f.signals,f.data,f.p,
    [{test:f.sessions,selected:"ALL:BASELINE"}],f.sessions,limits,
    {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
  assert.equal(result.funded.length,2,"TWO_NATIVE_FUNDED_CAMPAIGNS");
  const originalAnchors=A.auditTwoAssets(result,f.signals,limits);
  assert.equal(originalAnchors.accepted,2);
  const pairs=f.signals.map(signal=>{
    const trade=result.funded.find(t=>t.id===signal.id);
    assert(trade);
    const common={signal,data:f.data,protocol:f.p,quantity:trade.quantity,
      series:f.series.find(s=>s.symbol===signal.symbol),substeps:f.steps[signal.symbol]};
    return {trade,signal,modeled:F.statefulCampaign({...common,mode:"NATIVE_OHLC"}),
      discrete:F.statefulCampaign({...common,mode:"FIRST_CROSS"})};
  });
  const first=Date.UTC(2025,0,3),last=Date.UTC(2025,0,10);
  const fixedCosts=[];for(let d=first;d<=last;d+=DAY)fixedCosts.push({at:d,usd:1});
  const cert=L.couple({data:f.data,substeps:f.steps,pairs,states:result.states,fixedCosts});
  return {cert,pairs,result,fixedCosts,originalAnchors};
}
test("P7: two assets, full native campaigns, predictable cash and reserve anchors",()=>{
  const x=run(fixture()),c=x.cert;
  assert.equal(c.campaigns,2);
  assert.equal(c.decisions.length,2);
  assert(c.nativeEventCount>=4&&c.causalEventCount>=4);
  assert.equal(c.fixedCostEvents,8);
  near(c.native.netAfterAllCostsUsd,c.causal.netAfterAllCostsUsd);
  near(c.decomposition.deltaWealthUsd,0);
  assert(c.native.minCashUsd>=0&&c.causal.minCashUsd>=0);
  assert.equal(c.claims.universalEndogenousCouplingProven,false);
  assert.equal(c.claims.continuousTwelvePercentCapClaimed,false);
});
test("P7: intrabar target then stop creates a native financing residual across campaigns",()=>{
  const f=fixture(),a=f.signals[0].plannedEntryAt,b=f.signals[1].plannedEntryAt;
  f.tape("SYNA",a,[100.2,104,103,96,97,99,100,100]);
  f.tape("SYNB",b,[100.3,103.6,103.8,103.3,102.1,101.1,100.5,100.3]);
  const x=run(f),c=x.cert;
  assert(c.decomposition.exactIdentity);
  assert(Math.abs(c.decomposition.executionResidualUsd)>0.01);
  assert(Math.abs(c.decomposition.deltaWealthUsd)>0.01);
  assert(c.decomposition.pathwiseExPostTriangleUsd>=Math.abs(c.decomposition.deltaWealthUsd));
  assert.notEqual(c.decisions[1].nativeCashKnownUsd,c.decisions[1].causalCashKnownUsd);
  assert.equal(c.claims.nativeInfeasibilityCertified,false);
  assert.equal(c.claims.causalReoptimizedAdmissions,false);
  console.log("M11_P7_WITNESS="+JSON.stringify({nativeUsd:c.native.netAfterAllCostsUsd,
    firstUsd:c.causal.netAfterAllCostsUsd,bridge:c.decomposition,decisions:c.decisions}));
});
test("P7: two-interval inventory divergence appears as exposure PnL, not just fill slippage",()=>{
  const marks=[
    {at:100,symbol:"SYNA",price:100},{at:100,symbol:"SYNB",price:150},
    {at:200,symbol:"SYNA",price:110},{at:300,symbol:"SYNA",price:120}
  ];
  const base={id:"test",symbol:"SYNA",knownAt:100,reason:"IOC"};
  const buy={...base,at:100,delta:8,price:100.03,fee:.04};
  const N=L.runLedger(marks,[buy,{...base,at:300,knownAt:301,delta:-8,
    price:119.96,fee:.04}],[],20000);
  const C=L.runLedger(marks,[buy,{...base,at:200,knownAt:201,delta:-8,
    price:109.96,fee:.04}],[],20000);
  near(N.terminalEquityUsd-C.terminalEquityUsd,
    (N.markPnlUsd-C.markPnlUsd)+(N.basisPnlUsd-C.basisPnlUsd));
  near(N.markPnlUsd-C.markPnlUsd,80);
  assert(N.cashUsd>C.cashUsd);
});
test("P7: spendable exit proceeds require knownAt, not just effective at",()=>{
  const entry={id:"a",symbol:"SYNA",at:100,knownAt:110,
    delta:8,price:100.03,fee:.04,reason:"IOC"};
  const exit={...entry,at:200,knownAt:500,delta:-8,price:99.96,
    fee:.04,reason:"STOP"};
  near(L.spendableCash([entry,exit],[],450,20000),20000-800.24-.04);
  near(L.spendableCash([entry,exit],[],500,20000),
    20000-800.24-.04+799.68-.04);
  assert(L.spendableCash([entry,exit],[],450,20000) <
    L.spendableCash([entry,exit],[],500,20000));
});
test("P7: reservation retains original quantity through partial exit until receipt",()=>{
  const f=fixture(),c={id:"one",symbol:"SYNA",at:100,quantity:20,
    initialNotionalUsd:2000,nativeTerminalKnownAt:1000,
    causalTerminalKnownAt:1000};
  const at=f.data.series[0].bars[0].availableAt;
  c.at=at-100;c.nativeTerminalKnownAt=at+1000;c.causalTerminalKnownAt=at+1000;
  const a=L.reserveCeiling([c],at,"native",f.data);
  assert.equal(a.count,1);near(a.usd,2000);
  near(L.reserveCeiling([c],at+1000,"causal",f.data).usd,0);
});
test("P7: negative cash or missing mark fails closed, not a favorable bound",()=>{
  assert.throws(()=>L.runLedger([{at:100,symbol:"SYNA",price:100}],
    [{id:"a",symbol:"SYNA",at:100,knownAt:100,delta:1000,
      price:100,fee:0,reason:"BUY"}],[],20000),/NO_CASH_BORROWING/);
  assert.throws(()=>L.runLedger([],[{id:"a",symbol:"SYNA",at:100,knownAt:100,
    delta:1,price:100,fee:.005,reason:"BUY"}],[],20000),
  /FILL_WITHOUT_CONTEMPORANEOUS_MARK/);
});
test("P7: corruption of OHLC vs observed substeps rejected at source",()=>{
  const f=fixture();
  f.steps.SYNA[f.signals[0].plannedEntryAt][7]=101.01;
  assert.throws(()=>run(f),/SUBSTEP_OHLC_IDENTITY/);
});
test("P7: causal timestamps reject future receipts, hypothetical broker actions never emitted",()=>{
  const f=fixture(),x=run(f),pairs=x.pairs;
  pairs[0].discrete.fills[0].knownAt=pairs[0].discrete.fills[0].at-1;
  assert.throws(()=>L.couple({data:f.data,substeps:f.steps,pairs,
    states:x.result.states,fixedCosts:x.fixedCosts}),/FIRST_CROSS_INVENTORY/);
});
if(process.argv.includes("--emit-accountant")){
  const f=fixture();
  f.tape("SYNA",f.signals[0].plannedEntryAt,
    [100.2,104,103,96,97,99,100,100]);
  f.tape("SYNB",f.signals[1].plannedEntryAt,
    [100.3,103.6,103.8,103.3,102.1,101.1,100.5,100.3]);
  process.stdout.write(JSON.stringify(run(f).cert.accountantInput)+"\n");
  process.exit(0);
}
