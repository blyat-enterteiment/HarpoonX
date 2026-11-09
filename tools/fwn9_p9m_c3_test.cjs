"use strict";
// P9M-C3 finite engineering fixtures, NO market RNG or broker.
const {test}=require("node:test"),A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const C1=require("../runtime30/fwn9_p9m_c_order_witness.cjs");
const C2=require("../runtime30/fwn9_p9m_c2_event_parity.cjs");
const B=require("../runtime30/fwn9_p9m_c3_surface_bridge.cjs");
const BAR=300000,DAY=86400000;
function base(){
 const sessions=[0,3,4,5,6,7].map(k=>{
   const open=Date.UTC(2025,0,3,14,30)+k*DAY;
   return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
   pointValue:1,bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>({
   t:s.open+i*BAR,end:s.open+(i+1)*BAR,
   availableAt:s.open+(i+1)*BAR+1000,
   o:100,h:100.1,l:99.9,c:100,v:1000}))) }));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
   feed:"SYNTHETIC_FIXTURE",files:[{name:"P9MC3",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 return {sessions,series,data,protocol};
}
function pathWitness(){
 const f=base(),at=f.sessions[0].open+60*60000+1000;
 const signal={id:"SYNA:P9MC3",symbol:"SYNA",hypothesis:"CLOSED_CHANNEL",
   direction:1,at,index:0,plannedEntryAt:N.planSignalEntryAt(at,f.sessions),
   stopDistance:2,regime:.4,
   metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 const bar=f.series[0].bars.find(b=>b.t===signal.plannedEntryAt);
 bar.h=104;bar.l=96;bar.c=100;
 const path=Object.fromEntries(f.series[0].bars.map(b=>
   [b.t,[100.1,99.9,100,100,100,100,100,100]]));
 const pathA={...path,[bar.t]:[100.2,104,103,96,97,99,100,100]};
 const pathB={...path,[bar.t]:[100.2,96,103,104,97,99,100,100]};
 return C1.scan({signal,series:f.series[0],data:f.data,
   protocol:f.protocol,quantity:8,pathA,pathB});
}
function dual(noFillSymbol){
 const f=base();
 const signals=[["SYNA",60],["SYNB",90]].map(([symbol,m])=>{
   const at=f.sessions[0].open+m*60000+1000;
   return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",
     direction:1,at,index:0,plannedEntryAt:N.planSignalEntryAt(at,f.sessions),
     stopDistance:symbol==="SYNA"?20:5,regime:.4,
     metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 const sig=signals.find(s=>s.symbol===noFillSymbol);
 const row=f.series.find(s=>s.symbol===noFillSymbol).bars.find(b=>b.t===sig.plannedEntryAt);
 row.o=150;row.h=150.1;row.l=149.9;row.c=150;
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,f.data,f.protocol,
    [{test:f.sessions,selected:"ALL:BASELINE"}],f.sessions,limits,
    {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
     externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
     profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return C2.audit({data:f.data,signals,native,protocol:f.protocol,limits});
}
function fixture(){return {witness:pathWitness(),duals:[dual("SYNA"),dual("SYNB")]};}
function run(){return B.audit(fixture());}
test("P9M-C3 all finite event families carry reconciled receipts and marks",()=>{
 const x=run();A.equal(x.dualAssetClocks.length,2);
 A.equal(x.receiptMatrix.length,4);
 A.deepEqual(x.dualAssetClocks.map(r=>r.filledSymbol),["SYNB","SYNA"]);
 A(x.dualAssetClocks.every(r=>r.sourceMarksChecked===2));
 A.equal(x.preserved.capitalUsd,20000);
 A.equal(x.preserved.marketAccounts,0);
});
test("P9M-C3 native OHLC invariant but first-cross causal paths are different",()=>{
 const x=run();
 A.equal(x.classification,"FINITE_COUNTEREXAMPLE_NATIVE_OHLC_NOT_CAUSAL_EIGHT_SUBSTEP_EQUAL");
 A(x.possibleFirstCross.finitePathGapUsd>0);
 A(x.possibleFirstCross.nativeMinusBestOfTwoUsd>0);
 A.equal(x.possibleFirstCross.allAdmissibleSubstepPathsEnumerated,false);
});
test("P9M-C3 no improper population WEAK promotion or claim of observed trades",()=>{
 const x=run();A.equal(x.gates.WEAKExpectationBoundCertified,false);
 A.equal(x.gates.N9SEligible,false);
 A.equal(x.source,"SYNTHETIC_ENGINEERING_NO_OBSERVED_FILLS");
 A.equal(x.preserved.openedM10Final,0);
});
test("P9M-C3 altered no-fill knownAt fails closed",()=>{
 const f=fixture();f.duals[0].noFill.knownAt-=BAR;
 A.throws(()=>B.audit(f),/P9MC3_IOC_RECEIPT_NOT_PREKNOWN/);
});
test("P9M-C3 altered cash or native receipt fails closed",()=>{
 const f=fixture();f.duals[1].account.nativeTerminalEquityUsd+=1;
 A.throws(()=>B.audit(f),/P9MC3_DUAL_ASSET_INDEPENDENT_CASH/);
});
test("P9M-C3 altered native invariant fails closed",()=>{
 const f=fixture();f.witness.stopFirst.nativeActualExitSignature[0][2]+=1;
 A.throws(()=>B.audit(f),/P9MC3_NATIVE_EVENT_INVARIANT/);
});
test("P9M-C3 sign of ordering difference cannot be relabeled",()=>{
 const f=fixture();f.witness.signedDeltaCausalNetUsd*=-1;
 A.throws(()=>B.audit(f),/P9MC3_SIGNED_CAUSAL_PAYOFF_GAP/);
});
test("P9M-C3 original costs and risk admission are unchanged",()=>{
 const x=run();
 A.equal(x.preserved.reserveAdmission,.12);
 A.equal(x.preserved.riskAdmission,.0025);
 A.equal(x.preserved.maxHoldingHours,72);
 A.equal(x.preserved.nominalPerShareSideUsd,.005);
});
if(process.argv.includes("--emit-proof"))
 console.log("P9MC3_EVIDENCE="+JSON.stringify(run()));
if(process.argv.includes("--bench")){
 const a=process.hrtime.bigint();
 for(let i=0;i<10;i++)run();
 console.log("P9MC3_BENCHMARK_10_MS="+(Number(process.hrtime.bigint()-a)/1e6).toFixed(3));
}