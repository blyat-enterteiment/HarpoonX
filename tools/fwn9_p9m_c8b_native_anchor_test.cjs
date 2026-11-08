"use strict";
const {test}=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {performance}=require("node:perf_hooks");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const V=require("../runtime30/fwn9_p9m_c8b_native_anchor.cjs");
const BAR=300000,DAY=86400000;
function fixture({firstNoFill=false,secondNoFill=false,appreciation=false}={}){
 const sessions=[0,3,4,5,6,7].map(k=>{
   const open=Date.UTC(2025,0,3,14,30)+k*DAY;
   return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
   pointValue:1,bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>{
    const px=symbol==="SYNA"?200:100;
    return {t:s.open+i*BAR,end:s.open+(i+1)*BAR,
      availableAt:s.open+(i+1)*BAR+1000,
      o:px,h:px+.1,l:px-.1,c:px,v:1000};
   }))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"SYNTHETIC_FIXTURE",files:[{name:"P9M_C8B",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60,4],["SYNB",90,5]].map(([symbol,m,dist])=>{
   const at=sessions[0].open+m*60000+1000;
   return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",
     direction:1,at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),
     stopDistance:dist,regime:.4,
     metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 if(appreciation){
   // Completed bars and their availability clocks; first target may
   // exit partially before the second signal. No lookahead to signals.
   const s=series[0],base=sessions[0].open;
   for(const b of s.bars){
     if(b.t>=base+75*60000 && b.t<base+110*60000){
       b.o=b.t===base+75*60000?200:208;
       b.h=208.1;b.l=b.t===base+75*60000?199.9:207.9;b.c=208;
     }
   }
 }
 if(firstNoFill){
   const row=series[0].bars.find(b=>b.t===signals[0].plannedEntryAt);
   row.o=250;row.h=250.1;row.l=249.9;row.c=250;
 }
 if(secondNoFill){
   const row=series[1].bars.find(b=>b.t===signals[1].plannedEntryAt);
   row.o=150;row.h=150.1;row.l=149.9;row.c=150;
 }
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,data,protocol,
   [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
   {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
    profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return {data,signals,protocol,limits,native};
}
function run(opts){const f=fixture(opts);return V.audit(f);}
test("C8B full native replay with first asset appreciated and later second admission",()=>{
 const x=run({appreciation:true});
 A.equal(x.rows.length,2);A(x.rows[0].admitted);
 A(x.rows[1].nativeCorrectedPriorUsd>x.rows[1].nativeOriginalNotionalUsd);
 A(x.rows[1].preexisting.some(r=>r.symbol==="SYNA"&&r.state==="OPENED"));
 A(x.rows[1].admitted,"second asset must be admitted in this fixture");
 A(x.rows[1].correctedAfterUsd<=x.rows[1].grossAdmissionLimitUsd+1e-7);
 A.equal(x.terminal.shares.SYNA,0);A.equal(x.terminal.shares.SYNB,0);
});
test("C8B actual NO_FILL second: committed then released with no phantom inventory",()=>{
 const x=run({appreciation:true,secondNoFill:true});
 A(x.rows[1].admitted);A.deepEqual(x.rows[1].receiptTypes,["NO_FILL"]);
 A.equal(x.finalM10Opened,0);
});
test("C8B no-fill first then second funded: no prior opened lot",()=>{
 const x=run({firstNoFill:true});
 A.deepEqual(x.rows[0].receiptTypes,["NO_FILL"]);
 A(x.rows[1].admitted);
 A.equal(x.rows[1].preexisting.length,0);
});
test("C8B observed equity is an independent causally marked account check",()=>{
 for(const opts of [{appreciation:true},{appreciation:true,secondNoFill:true},
   {firstNoFill:true}]){
  const x=run(opts);
  for(const row of x.rows)A(row.independentPhysicalEquityUsd>=row.observedEquityUsd-.25);
  A.equal(x.wealthMomentsAndN9SInfeasibilityCertified,false);
  A.equal(x.economicAccounts,0);A.equal(x.alphaSpent,0);
 }
});
test("C8B fraud on the native marked anchor fails closed",()=>{
 const f=fixture({appreciation:true});
 const s=f.native.states[1];s.notional-=50;
 A.throws(()=>V.audit(f),/P9MC8B_REPRICED_STATE_NOTIONAL_PARITY/);
});
test("C8B fraud on native reservation quantity fails closed",()=>{
 const f=fixture({appreciation:true});
 const s=f.native.states[1];s.profit8CommittedReservation.quantity+=1;
 A.throws(()=>V.audit(f),/P9MC8B_IOC_SIZING_RECONCILED/);
});
test("C8B forged native cash result fails closed",()=>{
 const f=fixture({appreciation:true});
 f.native.curve.at(-1).equity_end_usd+=100;
 A.throws(()=>V.audit(f),/P9MC8B_INDEPENDENT_TERMINAL_CASH/);
});
test("C8B locked registered M9 sources are identical",()=>{
 const root=path.join(__dirname,"..");
 const reg=JSON.parse(fs.readFileSync(path.join(root,
   "research/modulation9/registration.json"),"utf8"));
 for(const file of ["runtime30/profit8_replay.js","runtime30/ultimate_reservations.js",
                    "quant/harpoon_quant/modulation9.py"]){
  const hex=crypto.createHash("sha256").update(fs.readFileSync(path.join(root,file))).digest("hex");
  A.equal(hex,reg.sources_sha256[file],file);
 }
});
if(process.argv.includes("--emit-proof"))
 console.log("P9MC8B_AUDIT="+JSON.stringify({appreciated:run({appreciation:true}),
  noFillSecond:run({appreciation:true,secondNoFill:true}),
  noFillFirst:run({firstNoFill:true})}));
if(process.argv.includes("--bench")){
 const t=performance.now();
 for(let i=0;i<12;i++)run({appreciation:!!(i%2),secondNoFill:!!(i%3)});
 console.log("P9MC8B_BENCHMARK_12_MS="+(performance.now()-t).toFixed(3));
}
