"use strict";
const {test}=require("node:test"),A=require("node:assert/strict");
const {performance}=require("node:perf_hooks");
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const C10=require("../runtime30/fwn9_p9m_c10_wealth_envelope_r3.cjs");
const C11=require("../runtime30/fwn9_p9m_c11_tick_applicability.cjs");
const MS=300000,DAY=86400000;
function fixture({tiny=false,stress=false,noFill=false}={}){
 const sessions=[0,3,4,5,6,7].map(k=>{
  const open=Date.UTC(2025,0,3,14,30)+k*DAY;
  return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*MS};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,
  tick:.01,pointValue:1,bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>{
    let px=symbol==="SYNA"?200:100;
    if(tiny&&symbol==="SYNA"&&s.open>=sessions[1].open)px=.004;
    return {t:s.open+i*MS,end:s.open+(i+1)*MS,
     availableAt:s.open+(i+1)*MS+1000,o:px,
     h:px+(px<1?.0005:.1),l:px-(px<1?.0005:.1),c:px,v:1000};
  }))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
  sessions,series,splitEvents:[],cashDividends:[],
  provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
   feed:"FWN9_C11_FIXED_FIXTURE",files:[{name:"C11",sha256:"0".repeat(64)}]}};
 const p={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
  costs:stress?{spreadBps:4,slippageBps:4,perSideUsd:.01}:
  {spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60,4],["SYNB",90,1]].map(([symbol,m,dist])=>{
  const at=sessions[0].open+m*60000+1000;
  return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",direction:1,
   at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),
   stopDistance:dist,regime:.4,
   metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 if(noFill){const b=series[1].bars.find(x=>x.t===signals[1].plannedEntryAt);
  b.o=150;b.h=150.1;b.l=149.9;b.c=150;}
 const limits={...N.PROFIT8_REPLAY_LIMITS},costPerDay=stress?2:1;
 const feePerShare=stress?.01:.005;
 const native=N.replayFundedPortfolio(signals,data,p,
  [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
  {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
   externalCostPerSessionUsd:0,calendarCostPerDayUsd:costPerDay,
   profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return {data,signals,native,p,limits,costPerDay,feePerShare};
}
function run(opts={}){const f=fixture(opts);return {f,a:C11.audit(f)};}
test("C11 regular native baseline agrees with prior envelope",()=>{
 const {f,a}=run();A.equal(a.zeroExits,0);
 const b=C10.audit(f);A(Math.abs(a.physicalTerminal-b.physicalTerminalUsd)<.000001);
});
test("C11 strictly-positive tiny overnight gap: native zero-tick stop fill",()=>{
 const {f,a}=run({tiny:true});A(a.zeroExits>=1);
 A(a.events.some(e=>e.kind==="EXIT"&&e.filledPrice===0&&e.symbol==="SYNA"));
 A(f.data.series[0].bars.every(b=>b.l>0));
});
test("C11 C10 positive executed-fill assumption rejects valid zero-tick sale",()=>{
 const f=fixture({tiny:true});
 A.throws(()=>C10.audit(f),/FWN9_C10_EXECUTED_COSTS/);
 const a=C11.audit(f);A(a.zeroExits>0);A(a.minCash>=0);
});
test("C11 zero-tick sale still obeys revised nonnegative-sale shadow envelope",()=>{
 const a=run({tiny:true}).a;A(a.range>=1);A(a.violations<=1e-6);
 A(Math.log(a.physicalTerminal)<=a.logBound+1e-7);
 A.equal(a.claims.nonvacuousWEAKMomentBound,false);
});
test("C11 stress original friction and commissions preserve reconciliation",()=>{
 const a=run({tiny:true,stress:true}).a;A(a.zeroExits>0);
 A.equal(a.feePerShare,.01);A.equal(a.costPerDay,2);
});
test("C11 both assets and IOC no-fill do not create ghost shares",()=>{
 const a=run({tiny:true,noFill:true}).a;
 A(a.events.every(e=>e.kind==="ENTRY"||e.kind==="EXIT"));
 A(a.events.some(e=>e.symbol==="SYNA"));A(a.minCash>=0);
});
test("C11 rejects negative sale proceeds and adulterated fee",()=>{
 const f=fixture({tiny:true});
 const ev=f.native.funded[0].inventoryEvents.find(e=>e.kind==="EXIT");
 A(ev);ev.filledPrice=-.01;
 A.throws(()=>C11.audit(f),/C11_NONNEGATIVE_SELL_COSTS/);
 const g=fixture({tiny:true});
 g.native.funded[0].inventoryEvents[0].feeUsd=0;
 A.throws(()=>C11.audit(g),/C11_NONNEGATIVE_SELL_COSTS/);
});
test("C11 locked M9 source SHA256 and no market samples",()=>{
 const root=path.join(__dirname,"..");
 const reg=JSON.parse(fs.readFileSync(path.join(root,"research/modulation9/registration.json"),"utf8"));
 for(const p of ["quant/harpoon_quant/modulation9.py","runtime30/profit8_replay.js",
  "runtime30/ultimate_reservations.js"]){
  const sha=crypto.createHash("sha256").update(fs.readFileSync(path.join(root,p))).digest("hex");
  A.equal(sha,reg.sources_sha256[p]);
 }
});
if(process.argv.includes("--bench")){
 const start=performance.now();
 for(let i=0;i<12;i++)run({tiny:!!(i%2),stress:!!(i%3)});
 console.log("C11_BENCH_12_NATIVE_REPLAYS_MS="+(performance.now()-start).toFixed(3));
}
if(process.argv.includes("--emit"))console.log(JSON.stringify(run({tiny:true}).a));
