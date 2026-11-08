"use strict";
const test=require("node:test"),A=require("node:assert/strict");
const N=require("../runtime30/profit8_replay.js");
const C=require("../runtime30/ultimate_contracts.js");
const G=require("../runtime30/fwn9_p9i_operational_gate.cjs");
const DAY=86400000,BAR=300000;
function fixture(){
 const sessions=[0,3,4,5,6,7].map(k=>{
   const open=Date.UTC(2025,0,3,14,30)+k*DAY;
   return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};});
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,pointValue:1,
   bars:sessions.flatMap(s=>Array.from({length:78},(_,i)=>({t:s.open+i*BAR,
     end:s.open+(i+1)*BAR,availableAt:s.open+(i+1)*BAR+1000,
     o:100,h:100.1,l:99.9,c:100,v:1000})))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,
  series,splitEvents:[],cashDividends:[],provenance:{execution:"MODELED_OHLCV",
   source:"SYNTHETIC_ENGINEERING_ONLY",feed:"SYNTHETIC_FIXTURE",
   files:[{name:"p9i",sha256:"0".repeat(64)}]}};
 const protocol={...C.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const sig=(symbol,m)=>{let at=sessions[0].open+m*60000+1000;
   return {id:symbol+":0:"+m,symbol,at,index:0,hypothesis:"CLOSED_CHANNEL",
    direction:1,plannedEntryAt:N.planSignalEntryAt(at,sessions),
    stopDistance:2,regime:.4,metadata:{roadmapHorizonHours:72,
    modulation9:{profile:"NATIVE72"}}};};
 const signals=[sig("SYNA",60),sig("SYNB",90)];
 const limits={...N.PROFIT8_REPLAY_LIMITS,riskFraction:.00125};
 function tape(symbol,at,opening,points){
    const b=series.find(x=>x.symbol===symbol).bars.find(x=>x.t===at);
    A.ok(b);b.o=opening;b.h=Math.max(opening,...points);
    b.l=Math.min(opening,...points);b.c=points[7];
 }
 function replay(){return N.replayFundedPortfolio(signals,data,protocol,
   [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
   {continuous:true,cashDividends:true,
    entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
    profit8:{mode:"NATIVE_MAX"},researchModulation:true});}
 const run=()=>G.auditAll({nativeReplay:replay(),data,protocol,limits,signals});
 return {data,protocol,limits,signals,series,tape,replay,run};
}
test("all accepted same-session source admissions inspected, no universal claim",()=>{
 const x=fixture(),r=x.run();
 A.equal(r.checkedAcceptedDecisions,2);
 A.equal(r.sourceWideCoverage,false);
 A.equal(r.n9sPromotionEligible,false);
 A(r.checked.every(x=>x.localLedgerFloorUsd>15970));
});
test("partial target preserves original quantity reservation",()=>{
 const x=fixture();x.tape("SYNA",x.signals[0].plannedEntryAt,100,
   [100.2,102,104,104,104,104,104,104]);
 const r=x.run();A.equal(r.checkedAcceptedDecisions,2);
 A(r.checked[1].openShares>0);
});
test("IOC NO_FILL audited without phantom funded position",()=>{
 const x=fixture();x.tape("SYNA",x.signals[0].plannedEntryAt,150,
   [150.1,149.9,150,150,150,150,150,150]);
 const r=x.run();A(r.modeledNoFills.includes(x.signals[0].id));
 A.equal(r.p9bNoFillValuationClockRepaired,false);
});
test("mutated equity must block every accepted-gate certification",()=>{
 const x=fixture(),n=x.replay();const s=n.states.find(s=>s.reservationStatus==="RESERVED");
 A(s);s.equity+=10;
 A.throws(()=>G.auditAll({nativeReplay:n,data:x.data,protocol:x.protocol,
   limits:x.limits,signals:x.signals}),/P9H_PHYSICAL_CASH_MARK_NATIVE_EQUITY_MISMATCH/);
});
test("effective exit before knownAt must fail closed",()=>{
 const x=fixture(),n=x.replay(),t=n.funded.find(t=>t.symbol==="SYNA");
 A(t);const e=t.inventoryEvents.find(x=>x.kind==="EXIT");A(e);
 e.at=x.signals[1].at-1000;e.knownAt=x.signals[1].at+1000;
 A.throws(()=>G.auditAll({nativeReplay:n,data:x.data,protocol:x.protocol,
   limits:x.limits,signals:x.signals}),/P9H_UNSETTLED_EFFECTIVE_EXIT/);
});
test("duplicate signal identities rejected",()=>{
 const x=fixture(),signals=[x.signals[0],x.signals[0]];
 A.throws(()=>G.auditAll({nativeReplay:x.replay(),data:x.data,
   protocol:x.protocol,limits:x.limits,signals}),/P9I_SORTED_UNIQUE_CAUSAL_SIGNALS/);
});
test("capital or admission caps cannot be weakened",()=>{
 const x=fixture();
 A.throws(()=>G.auditAll({nativeReplay:x.replay(),data:x.data,
   protocol:x.protocol,limits:{...x.limits,grossFraction:.13},signals:x.signals}),
   /P9I_FROZEN_RISK_CONTRACT/);
});
if(process.argv.includes("--bench")){
 const x=fixture(),n=x.replay(),a={nativeReplay:n,data:x.data,
  protocol:x.protocol,limits:x.limits,signals:x.signals};
 const start=performance.now();for(let i=0;i<150;i++)G.auditAll(a);
 console.log("P9I_150_ADMISSION_AUDITS_MS="+(performance.now()-start));
}
