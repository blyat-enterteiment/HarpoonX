"use strict";
// Engineering fixtures only; no sampled M9/M10 paths.
const test=require("node:test");
const assert=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const P=require("../runtime30/modulation11_native_receipt_parity_p9a_v2.cjs");
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
     o:100,h:100.1,l:99.9,c:100,v:1000})))}));
 const substeps=Object.fromEntries(series.map(ser=>[ser.symbol,
   Object.fromEntries(ser.bars.map(b=>[b.t,
     [100.1,99.9,100,100,100,100,100,100]]))]));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"SYNTHETIC_FIXTURE",files:[{name:"P9A_FIXTURE",sha256:"0".repeat(64)}]}};
 const protocol={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signal=(symbol,day)=>{
   const at=sessions[day].open+60*60000+1000;
   return {id:symbol+":NATIVE72:"+day,symbol,
     hypothesis:"CLOSED_CHANNEL",direction:1,at,index:0,
     plannedEntryAt:N.planSignalEntryAt(at,sessions),stopDistance:2,regime:.4,
     metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 };
 const signals=[signal("SYNA",0),signal("SYNB",1)];
 const fixedCosts=[];
 for(let at=Date.UTC(2025,0,3);at<=Date.UTC(2025,0,10);at+=DAY)
   fixedCosts.push({at,usd:1});
 function tape(symbol,at,points){
   const bar=series.find(s=>s.symbol===symbol).bars.find(b=>b.t===at);
   assert(bar);assert.equal(points.length,8);
   bar.h=Math.max(bar.o,...points);bar.l=Math.min(bar.o,...points);
   bar.c=points[7];substeps[symbol][at]=points.slice();
 }
 return {signals,data,protocol,limits:{...N.PROFIT8_REPLAY_LIMITS,
   riskFraction:.00125},substeps,fixedCosts,
   terminalAt:sessions.at(-1).close,tape};
}
function run(f=fixture()){return P.compare(f);}
function audit(o){
 assert.equal(o.accounts,0);assert.deepEqual(o.marketSeedsOpened,[]);
 assert.equal(o.alphaSpent,0);assert.equal(o.holdoutOpened,false);
 assert.equal(o.parity.sourceNativeCampaigns,true);
 assert.equal(o.parity.discreteEightSubstepExits,true);
 assert.equal(o.parity.nativeFullMarkAndDailyGate,false);
 assert.equal(o.parity.stochasticPopulationBridge,false);
 assert(o.nativeFundedCount>=1);
 assert(o.receiptAudit.length>=o.nativeAdmitted.length+o.causalAdmitted.length);
 assert(o.anchorRows.length>=1);
 assert(Number.isFinite(o.nativeTerminalNetUsd));
 assert(Number.isFinite(o.causalMirrorNetUsd));
}
test("P9A: flat, two full funded native campaigns use real native exit receipts",()=>{
 const o=run();audit(o);
 assert.equal(o.nativeFundedCount,2);
 assert.equal(o.nativeAdmitted.length,2);
 assert.equal(o.causalAdmitted.length,2);
 assert.equal(o.parity.nativeAdmittedFullQuantity,true);
 assert.equal(o.parity.nativeTradeNet,true);
 assert(Math.abs(o.nativeMirrorNetUsd-o.nativeTerminalNetUsd)<1e-6);
 assert(Math.abs(o.nativeMirrorNetUsd-o.causalMirrorNetUsd)<1e-6);
});
test("P9A: adverse intrabar stop/target splits native and observed-step cash",()=>{
 const f=fixture(),entry=f.signals[0].plannedEntryAt;
 f.tape("SYNA",entry,[100.2,104,103,96,97,99,100,100]);
 const o=run(f);audit(o);
 assert.equal(o.parity.nativeAdmittedFullQuantity,true);
 assert.equal(o.parity.nativeTradeNet,true);
 assert(Math.abs(o.nativeMirrorNetUsd-o.causalMirrorNetUsd)>0.01);
 assert(o.receiptAudit.some(x=>x.mode==="FIRST_CROSS"&&x.exitEvents>1));
 console.log("M11_P9A_WITNESS="+JSON.stringify({
   nativeUsd:o.nativeMirrorNetUsd,firstCrossUsd:o.causalMirrorNetUsd,
   idsNative:o.nativeAdmitted,idsFirst:o.causalAdmitted,
   decisionAnchors:o.anchorRows,flags:o.parity}));
});
test("P9A: future bar change cannot resize the first admission",()=>{
 const a=run();
 const f=fixture(),entry=f.signals[0].plannedEntryAt;
 f.tape("SYNA",entry,[100.2,104,103,96,97,99,100,100]);
 const b=run(f);
 assert.deepEqual(a.nativeAdmitted[0],b.nativeAdmitted[0]);
 assert.deepEqual(a.causalAdmitted[0],b.causalAdmitted[0]);
 assert.notEqual(a.nativeMirrorNetUsd,b.nativeMirrorNetUsd);
});
test("P9A: IOC no-fill follows observed open and releases no invented proceeds",()=>{
 const f=fixture(),arr=[];
 const factory=P.receiptFactory(f,arr);
 const sig=f.signals[0];
 const out=factory({mode:"NATIVE_OHLC",signal:sig,quantity:5,
   iocPlan:{status:"PLANNED",priceCeiling:90}});
 assert.equal(out.length,1);assert.equal(out[0].kind,"IOC");
 assert.equal(out[0].at,sig.plannedEntryAt);
 assert.equal(arr[0].kind,"NO_FILL");
});
test("P9A: bad step-to-OHLC correspondence fails rather than creating a fill",()=>{
 const f=fixture(),entry=f.signals[0].plannedEntryAt;
 f.substeps.SYNA[entry][7]=123;
 assert.throws(()=>run(f),/SUBSTEP_OHLC_IDENTITY/);
});
test("P9A: complete native receipts cannot falsely certify population or operations",()=>{
 const o=run();audit(o);
 assert.equal(o.outstanding.nativeFullMarkEquityClock,true);
 assert.equal(o.outstanding.dailyLossClock,true);
 assert.equal(o.outstanding.marketDepthPartialRejectImpact,true);
 assert.equal(o.outstanding.virtualCellCoordinator,true);
 console.log("M11_P9A_ACCOUNTANT="+JSON.stringify(o.accountantInput));
});
if(process.argv.includes("--emit-accountant")){
  console.log("M11_P9A_ACCOUNTANT="+JSON.stringify(run().accountantInput));
}
if(process.argv.includes("--bench")){
  const start=process.hrtime.bigint();
  for(let j=0;j<20;j++)run();
  console.log("M11_P9A_20_BOOKS_MS="+(Number(process.hrtime.bigint()-start)/1e6).toFixed(3));
}
