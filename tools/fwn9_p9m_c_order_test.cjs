"use strict";
// Offline engineering cases; identical input OHLC, no RNG / market seeds.
const {test}=require("node:test");
const A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const W=require("../runtime30/fwn9_p9m_c_order_witness.cjs");
const BAR=300000,DAY=86400000;
function fixture(){
 const sessions=[0,3,4,5,6,7].map(k=>{
   const open=Date.UTC(2025,0,3,14,30)+k*DAY;
   return {date:new Date(open).toISOString().slice(0,10),
     open,close:open+78*BAR};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
   pointValue:1,bars:sessions.flatMap(s=>Array.from({length:78},(_,j)=>({
     t:s.open+j*BAR,end:s.open+(j+1)*BAR,
     availableAt:s.open+(j+1)*BAR+1000,
     o:100,h:100.1,l:99.9,c:100,v:1000
   })))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"SYNTHETIC_FIXTURE",files:[{name:"P9M_C1",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const at=sessions[0].open+60*60000+1000;
 const signal={id:"SYNA:MC1",symbol:"SYNA",hypothesis:"CLOSED_CHANNEL",
   direction:1,at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),
   stopDistance:2,regime:.4,
   metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 const bar=series[0].bars.find(b=>b.t===signal.plannedEntryAt);
 const first=[100.2,104,103,96,97,99,100,100];
 const second=[100.2,96,103,104,97,99,100,100];
 bar.h=104;bar.l=96;bar.c=100;
 const path=Object.fromEntries(series[0].bars.map(b=>
   [b.t,[100.1,99.9,100,100,100,100,100,100]]));
 const pathA={...path,[bar.t]:first};
 const pathB={...path,[bar.t]:second};
 const inputs={signal,series:series[0],data,protocol,quantity:8,pathA,pathB};
 return {inputs,bar};
}
function witness(){return W.scan(fixture().inputs);}
test("P9M-C1 native OHLC unchanged yet target-first and stop-first differ causally",()=>{
 const x=witness();
 A.equal(x.nativeInvariant,true);
 A.equal(x.causalOutcomeNonidentifiableFromOHLC,true);
 A.equal(x.sourcePair.changedBars.length,1);
 A.deepEqual(x.targetFirst.nativeActualExitSignature,x.stopFirst.nativeActualExitSignature);
 A.notEqual(x.targetFirst.discrete.netTradingUsd,
            x.stopFirst.discrete.netTradingUsd);
 A.deepEqual(x.targetFirst.discrete.fills.map(f=>f.reason),["TP1","STOP"]);
 A.deepEqual(x.stopFirst.discrete.fills.map(f=>f.reason),["STOP"]);
});
test("P9M-C1 independent integer micro-USD book reconciles native and both causal variants",()=>{
 const x=witness();
 for(const item of [x.targetFirst.native,x.targetFirst.discrete,
                    x.stopFirst.native,x.stopFirst.discrete]){
   A.equal(item.closed,true);
   A.equal(item.fills.reduce((n,f)=>n+f.shares,0),8);
   A(Math.abs(item.terminalAfterCalendarUsd-
     (20000+item.netTradingUsd-8))<1e-7);
   A.equal(item.feesUsd,.08);
 }
 A.equal(x.targetFirst.native.netTradingUsd,x.stopFirst.native.netTradingUsd);
});
test("P9M-C1 exit receipt is never known before effective substep or publication",()=>{
 const x=witness(),t=fixture().bar;
 for(const item of [x.targetFirst.discrete,x.stopFirst.discrete])
   for(const f of item.fills){
     A(f.at>=t.t&&f.at<=t.end);
     A.equal(f.knownAt,t.availableAt);
     A(f.knownAt>f.at);
   }
});
test("P9M-C1 future prices are not signal features; preserve same initial admission",()=>{
 const x=witness();
 A.equal(x.capitalUsd,20000);
 A.equal(x.sourcePair.pathsNeverExposedToSignal,true);
 A.equal(x.initialShares,8);
 A.equal(x.targetFirst.native.quantity,x.stopFirst.native.quantity);
 A.equal(x.proof.nativePopulationWEAKBoundCertified,false);
 A.equal(x.proof.n9sPromotable,false);
});
test("P9M-C1 fail closed when substep multiset not identical",()=>{
 const f=fixture();f.inputs.pathB[f.bar.t][0]=100.4;
 A.throws(()=>W.scan(f.inputs),/SUBSTEP_OHLC_IDENTITY|P9MC1_IDENTICAL_SUBSTEP_MULTISET/);
});
test("P9M-C1 fail closed when provenance is not engineering synthetic",()=>{
 const f=fixture();f.inputs.data.provenance.source="BROKER_OBSERVED";
 A.throws(()=>W.scan(f.inputs),/P9MC1_SYNTHETIC_FIXTURE_ONLY/);
});
test("P9M-C1 fail closed when fees drift from locked protocol",()=>{
 const f=fixture();f.inputs.protocol.costs.perSideUsd=.001;
 A.throws(()=>W.scan(f.inputs),/P9MC1_LOCKED_NOMINAL_COSTS_AND_TICK/);
});
test("P9M-C1 fail closed on publication before bar end",()=>{
 const f=fixture();f.bar.availableAt=f.bar.end-1;
 A.throws(()=>W.scan(f.inputs),/PUBLICATION_AFTER_BAR/);
});
if(process.argv.includes("--emit-json"))
 console.log("P9MC1_EVIDENCE="+JSON.stringify(witness()));
if(process.argv.includes("--bench")){
 const t=process.hrtime.bigint();
 for(let j=0;j<20;j++)witness();
 console.log("P9MC1_BENCHMARK_20_MS="+
   (Number(process.hrtime.bigint()-t)/1e6).toFixed(3));
}
