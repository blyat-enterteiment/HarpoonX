"use strict";
const {test}=require("node:test"),A=require("node:assert/strict");
const fs=require("node:fs"),path=require("node:path"),crypto=require("node:crypto");
const {performance}=require("node:perf_hooks");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const V=require("../runtime30/fwn9_p9m_c9_event_induction.cjs");
const R=require("../runtime30/ultimate_reservations.js");
const B=300000,D=86400000;
function fixture({appreciation=false,firstNoFill=false,secondNoFill=false}={}){
 const sessions=[0,3,4,5,6,7].map(k=>{
  const open=Date.UTC(2025,0,3,14,30)+k*D;
  return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*B};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
   pointValue:1,bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>{
     const px=symbol==="SYNA"?200:100;
     return {t:s.open+i*B,end:s.open+(i+1)*B,
       availableAt:s.open+(i+1)*B+1000,o:px,h:px+.1,l:px-.1,c:px,v:1000};
   }))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
   sessions,series,splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"C9_FIXED_FIXTURE",files:[{name:"C9",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60,4],["SYNB",90,1]].map(([symbol,m,dist])=>{
  const at=sessions[0].open+m*60000+1000;
  return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",direction:1,
    at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),stopDistance:dist,
    regime:.4,metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 if(appreciation){
  const base=sessions[0].open;
  for(const b of series[0].bars)if(b.t>=base+75*60000 && b.t<base+110*60000){
   b.o=b.t===base+75*60000?200:208;b.h=208.1;
   b.l=b.t===base+75*60000?199.9:207.9;b.c=208;
  }
 }
 if(firstNoFill){
  const b=series[0].bars.find(b=>b.t===signals[0].plannedEntryAt);
  b.o=250;b.h=250.1;b.l=249.9;b.c=250;
 }
 if(secondNoFill){
  const b=series[1].bars.find(b=>b.t===signals[1].plannedEntryAt);
  b.o=150;b.h=150.1;b.l=149.9;b.c=150;
 }
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,data,protocol,
   [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
   {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
    profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return {data,signals,protocol,limits,native};
}
function run(o){return V.audit(fixture(o));}
test("C9 original-quantity event invariant on native M9 with intervening appreciation",()=>{
 const x=run({appreciation:true});
 A.equal(x.checkedAdmission,2);A(x.openedRows>0);A(x.checkedSnapshots>6);
 A.equal(x.allReachableM9EventsProven,false);
 A.equal(x.wealthMomentBoundCertified,false);
});
test("C9 IOC NO_FILL remains pending until known, then disappears",()=>{
 const f=fixture({secondNoFill:true});
 const x=V.audit(f);A(x.pendingRows>0);
 const r=f.native.reservationBook.reservations.find(r=>r.id===f.signals[1].id);
 const no=r.observations.find(o=>o.kind==="NO_FILL");
 A(no);A(R.snapshotFundedReservations(f.native.reservationBook,no.knownAt-1)
   .reservations.some(z=>z.id===r.id));
 A(!R.snapshotFundedReservations(f.native.reservationBook,no.knownAt)
   .reservations.some(z=>z.id===r.id));
});
test("C9 first IOC NO_FILL then second commitment does not invent inventory",()=>{
 const x=run({firstNoFill:true});
 A.equal(x.checkedAdmission,2);A(x.openedRows>0);
 A.equal(x.newEconomicAccounts,0);A.equal(x.finalM10Opened,0);
});
test("C9 native terminal balances independently against conservative receipts",()=>{
 const f=fixture({appreciation:true});
 const a=V.audit(f);
 const c=require("../runtime30/fwn9_p9m_c8b_native_anchor.cjs")
   .independentPhysicalAt(f.native,f.data,f.data.sessions.at(-1).close,1);
 A.equal(c.shares.SYNA,0);A.equal(c.shares.SYNB,0);
 A(Math.abs(c.physicalCashUsd-f.native.curve.at(-1).equity_end_usd)<1e-7);
 A.equal(a.N9SConditionalAccepted,false);
});
test("C9 forged committed notional above admission cap fails closed",()=>{
 const f=fixture({appreciation:true});
 f.native.states[1].profit8CommittedReservation.notionalUsd=30000;
 A.throws(()=>V.audit(f),/C9_ADMITTED_GROSS_BOUND/);
});
test("C9 forged state repriced anchor fails closed",()=>{
 const f=fixture({appreciation:true});f.native.states[1].notional-=100;
 A.throws(()=>V.audit(f),/C9_STATE_REPRICED_ANCHOR_PARITY/);
});
test("C9 forged original quantity fails closed",()=>{
 const f=fixture({appreciation:true});
 f.native.reservationBook.reservations[0].quantity=1;
 A.throws(()=>V.audit(f),/C9_OPENED_BOUND_TO_ORIGINAL_LOT/);
});
test("C9 source frozen hashes and original law remain unchanged",()=>{
 const root=path.join(__dirname,"..");
 const reg=JSON.parse(fs.readFileSync(path.join(root,
    "research/modulation9/registration.json"),"utf8"));
 for(const p of ["runtime30/profit8_replay.js","runtime30/ultimate_reservations.js",
   "quant/harpoon_quant/modulation9.py"]){
   const sha=crypto.createHash("sha256")
      .update(fs.readFileSync(path.join(root,p))).digest("hex");
   A.equal(sha,reg.sources_sha256[p]);
 }
});
if(process.argv.includes("--bench")){
 const t=performance.now();for(let i=0;i<10;i++)run({appreciation:!!(i%2)});
 console.log("C9_BENCH_10_MS="+(performance.now()-t).toFixed(3));
}
if(process.argv.includes("--emit"))
 console.log("C9_EVIDENCE="+JSON.stringify(run({appreciation:true})));
