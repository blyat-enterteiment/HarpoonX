"use strict";
const {test}=require("node:test"),A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const V=require("../runtime30/fwn9_p9m_c2_event_parity.cjs");
const BAR=300000,DAY=86400000;
function fixture(noFillSymbol="SYNB"){
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
     feed:"SYNTHETIC_FIXTURE",files:[{name:"P9M_C2",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60],["SYNB",90]].map(([symbol,m])=>{
   const at=sessions[0].open+m*60000+1000;
   return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",
     direction:1,at,index:0,plannedEntryAt:N.planSignalEntryAt(at,sessions),
     stopDistance:symbol==="SYNA"?20:5,regime:.4,
     metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 const target=signals.find(s=>s.symbol===noFillSymbol),source=series.find(s=>s.symbol===noFillSymbol);
 const bar=source.bars.find(b=>b.t===target.plannedEntryAt);
 bar.o=150;bar.h=150.1;bar.l=149.9;bar.c=150;
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,data,protocol,
     [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
     {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 if(process.env.P9MC2_DEBUG) console.error("P9MC2_STATUSES="+JSON.stringify({funded:native.funded.map(x=>x.id),noFill:native.modeledNoFills.map(x=>x.signalId),states:native.states.map(x=>({id:x.opportunity.id,status:x.status,quantity:x.quantity})),refusals:native.preEntryRefusals}));
 return {data,signals,protocol,limits,native};
}
const audit=(symbol)=>V.audit(fixture(symbol));
test("P9M-C2 no-fill on second asset: native decisions, risks, reserves, marks and cash agree",()=>{
 const x=audit("SYNB");
 A.equal(x.noFill.id,"SYNB:90");A.equal(x.filled.symbol,"SYNA");
 A.equal(x.pendingReservationBeforeNoFill,true);
 A.equal(x.noFillReservationAfterReceipt,false);
 A.equal(x.account.independentTerminalReconciled,true);
 A.equal(x.marksVerified,2);A.equal(x.riskClock.pass,true);
});
test("P9M-C2 reverse no-fill first asset and funded second asset",()=>{
 const x=audit("SYNA");
 A.equal(x.noFill.id,"SYNA:60");A.equal(x.filled.symbol,"SYNB");
 A.equal(x.account.independentTerminalReconciled,true);
});
test("P9M-C2 principal conservation, fee symmetry and no phantom no-fill shares",()=>{
 for(const sym of ["SYNA","SYNB"]){
  const x=audit(sym);
  const qty=x.filled.events.reduce((n,e)=>n+e.quantityDelta,0);
  A.equal(qty,0);A.equal(x.noFill.phantomInventory,false);
  A(Math.abs(x.filled.totalFeesUsd-2*.005*x.filled.quantity)<1e-7);
  A(Math.abs(x.account.tradingCashBeforeFixedUsd-20000-x.filled.netTradingUsd)<1e-7);
 }
});
test("P9M-C2 original 12% reservation cap not falsely represented as continuous",()=>{
 const x=audit("SYNB");A.equal(x.gates.nativeWholePopulationEquivalent,false);
 A.equal(x.gates.WEAKExpectationBoundCertified,false);
 A.equal(x.budget.marketAccounts,0);A.equal(x.budget.finalM10Opened,0);
});
test("P9M-C2 altered native NO_FILL release timestamp fails closed",()=>{
 const f=fixture();const r=f.native.reservationBook.reservations.find(x=>x.id==="SYNB:90");
 r.observations[0].knownAt+=BAR;
 A.throws(()=>V.audit(f),/P9J_NOFILL_RECEIPT_CHRONOLOGY|P9MC2_NO_FILL_SOURCE_RECEIPT_CLOCK/);
});
test("P9M-C2 altered source mark availableAt or native causal anchor fails closed",()=>{
 const f=fixture();const st=f.native.states.find(s=>s.opportunity.id==="SYNA:60");
 st.reference.sourceAvailableAt+=BAR;
 A.throws(()=>V.audit(f),/P9MC2_CAUSAL_MARK_REFERENCE/);
});
test("P9M-C2 net manipulation or inventory event mispricing fails closed",()=>{
 const f=fixture();f.native.funded[0].inventoryEvents.at(-1).filledPrice+=1;
 A.throws(()=>V.audit(f),/P9MC2_SELF_FINANCING_TERMINAL/);
});
test("P9M-C2 fail closed on original admission cap mutation",()=>{
 const f=fixture();f.limits.grossFraction=.3;
 A.throws(()=>V.audit(f),/P9MC2_UNCHANGED_ADMISSION_LIMITS/);
});
if(process.argv.includes("--emit-proof")){
 console.log("P9MC2_AUDIT="+JSON.stringify({schema:"P9MC2_DECIMAL_INPUT_1",
  audits:[audit("SYNA"),audit("SYNB")]}));
}
if(process.argv.includes("--bench")){
 const start=process.hrtime.bigint();
 for(let i=0;i<20;i++)audit(i%2?"SYNA":"SYNB");
 console.log("P9MC2_BENCHMARK_20_MS="+(Number(process.hrtime.bigint()-start)/1e6).toFixed(3));
}
