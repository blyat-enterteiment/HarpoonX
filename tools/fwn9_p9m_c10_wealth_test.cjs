"use strict";
const {test}=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {performance}=require("node:perf_hooks");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const W=require("../runtime30/fwn9_p9m_c10_wealth_envelope.cjs");
const MS=300000,D=86400000;
function fixture({nominal=true,appreciation=false,firstNoFill=false,secondNoFill=false}={}){
 const sessions=[0,3,4,5,6,7].map(k=>{
  const open=Date.UTC(2025,0,3,14,30)+k*D;
  return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*MS};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
  pointValue:1,bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>{
   const px=symbol==="SYNA"?200:100;
   return {t:s.open+i*MS,end:s.open+(i+1)*MS,
    availableAt:s.open+(i+1)*MS+1000,o:px,h:px+.1,l:px-.1,c:px,v:1000};
  }))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
  sessions,series,splitEvents:[],cashDividends:[],
  provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
   feed:"C10_FIXED_FIXTURE",files:[{name:"C10",sha256:"0".repeat(64)}]}};
 const p={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
  costs:nominal?{spreadBps:2,slippageBps:2,perSideUsd:.005}:
  {spreadBps:4,slippageBps:4,perSideUsd:.01}};
 const signals=[["SYNA",60,4],["SYNB",90,1]].map(([symbol,m,dist])=>{
  const at=sessions[0].open+m*60000+1000;
  return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",direction:1,
   at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),stopDistance:dist,
   regime:.4,metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 if(appreciation){
  const base=sessions[0].open;
  for(const b of series[0].bars)if(b.t>=base+75*60000&&b.t<base+110*60000){
   b.o=b.t===base+75*60000?200:208;b.h=208.1;
   b.l=b.t===base+75*60000?199.9:207.9;b.c=208;
  }
 }
 if(firstNoFill||secondNoFill){
  const i=firstNoFill?0:1;
  const b=series[i].bars.find(x=>x.t===signals[i].plannedEntryAt);
  b.o=i===0?250:150;b.h=b.o+.1;b.l=b.o-.1;b.c=b.o;
 }
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const costPerDay=nominal?1:2,feePerShare=nominal?.005:.01;
 const native=N.replayFundedPortfolio(signals,data,p,
  [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
  {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
   externalCostPerSessionUsd:0,calendarCostPerDayUsd:costPerDay,
   profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return {data,signals,p,limits,native,costPerDay,feePerShare};
}
function run(opts={}){const f=fixture(opts);return W.audit(f);}
test("C10 NOMINAL actual native two-asset receipt self-financing cash envelope",()=>{
 const a=run({appreciation:true}); A(a.events.length>0);
 A(a.sales>0);A(a.range>=1);A.equal(a.fullM9WealthMomentIntegrationProven,false);
});
test("C10 STRESS costs and actual native event envelope unchanged limits",()=>{
 const a=run({nominal:false,appreciation:true});
 A.equal(a.feePerShare,.01);A(a.physicalTerminalUsd>0);
 A.equal(a.N9SAccepted,false);
});
test("C10 IOC first NO_FILL remains no physical inventory",()=>{
 const a=run({firstNoFill:true});A(a.physicalTerminalUsd>0);
 A.equal(a.finalM10Opened,0);
});
test("C10 IOC second NO_FILL remains no physical inventory",()=>{
 const a=run({secondNoFill:true});A(a.physicalTerminalUsd>0);
 A.equal(a.newEconomicAccounts,0);
});
test("C10 forged expensive native entry breaches no-borrow guard",()=>{
 const f=fixture({appreciation:true});
 const e=f.native.funded[0].inventoryEvents.find(e=>e.kind==="ENTRY");
 e.filledPrice=100000000;A.throws(()=>W.audit(f),/C10_NONNEGATIVE_CASH_FILL/);
});
test("C10 forged early knowledge is rejected",()=>{
 const f=fixture({appreciation:true});
 const e=f.native.funded[0].inventoryEvents.find(e=>e.kind==="EXIT");
 e.knownAt=e.at-1;A.throws(()=>W.audit(f),/C10_CAUSAL_RECEIPT/);
});
test("C10 forged fee rejected without silently cutting costs",()=>{
 const f=fixture({appreciation:true});
 f.native.funded[0].inventoryEvents[0].feeUsd=0;
 A.throws(()=>W.audit(f),/C10_EXECUTED_COSTS/);
});
test("C10 original registered M9 generator/replay/reservations intact",()=>{
 const root=path.join(__dirname,"..");
 const reg=JSON.parse(fs.readFileSync(path.join(root,"research/modulation9/registration.json"),"utf8"));
 for(const p of ["quant/harpoon_quant/modulation9.py",
   "runtime30/profit8_replay.js","runtime30/ultimate_reservations.js"]){
  const sha=crypto.createHash("sha256").update(fs.readFileSync(path.join(root,p))).digest("hex");
  A.equal(sha,reg.sources_sha256[p]);
 }
});
if(process.argv.includes("--bench")){
 const t=performance.now();
 for(let i=0;i<16;i++)run({nominal:i%2===0,appreciation:i%3===0});
 console.log("C10_BENCH_16_NATIVE_REPLAYS_MS="+(performance.now()-t).toFixed(3));
}
if(process.argv.includes("--emit"))
 console.log(JSON.stringify(run({appreciation:true})));
