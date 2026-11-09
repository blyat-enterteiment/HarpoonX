"use strict";
/** Reuse EXACT historical C14 fixed engineering signals; no random seeds. */
const test=require("node:test"),A=require("node:assert/strict");
const Q=require("../runtime30/fwn9_p9m_c20_admission_audit.cjs");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const BAR=300000,DAY=86400000;
function originalC14FixedFixture(){
 const sessions=[0,3,4,5,6,7].map(k=>{
   const open=Date.UTC(2025,0,3,14,30)+k*DAY;
   return {date:new Date(open).toISOString().slice(0,10),open,close:open+78*BAR};
 });
 const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,pointValue:1,
   bars:sessions.flatMap(session=>Array.from({length:78},(_,i)=>({
     t:session.open+i*BAR,end:session.open+(i+1)*BAR,availableAt:session.open+(i+1)*BAR+1000,
     o:symbol==="SYNA"?200:100,h:symbol==="SYNA"?200.1:100.1,
     l:symbol==="SYNA"?199.9:99.9,c:symbol==="SYNA"?200:100,v:1000
   })))}));
 const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",sessions,series,
   splitEvents:[],cashDividends:[],
   provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
     feed:"C14_FIXED_FIXTURE",files:[{name:"C14",sha256:"0".repeat(64)}]}};
 const protocol={...K.defaultProtocol("ALPACA_PROXY"),universe:["SYNA","SYNB"],
   costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
 const signals=[["SYNA",60,4],["SYNB",90,1]].map(([symbol,m,distance])=>{
   const at=sessions[0].open+m*60000+1000;
   return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",direction:1,at,index:0,
     plannedEntryAt:N.planSignalEntryAt(at,sessions),stopDistance:distance,
     regime:.4,metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
 });
 const limits={...N.PROFIT8_REPLAY_LIMITS};
 const native=N.replayFundedPortfolio(signals,data,protocol,
   [{test:sessions,selected:"ALL:BASELINE"}],sessions,limits,
   {continuous:true,cashDividends:true,entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
    externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
    profit8:{mode:"NATIVE_MAX"},researchModulation:true});
 return {native,data,limits};
}
function audit(){const f=originalC14FixedFixture();return {f,proof:Q.audit(f)};}
test("C20: original source-funded cash IOC approvals dominate actual filled lots",()=>{
 const {f,proof:p}=audit();
 A(f.native.funded.length>0);
 A.equal(p.nativeFundedCount,f.native.funded.length);
 A(p.modeledFilledNotionalSumUsd<=p.approvedIocNotionalSumUsd+1e-7);
 A.equal(p.original12PercentAppliesOnlyAtAdmission,true);
 A.equal(p.native72HourReceiptsChecked,true);
 A.equal(p.expectedPopulationAdmissionNotionalUpperUsd,null);
 A.equal(p.fullNativePolicyClassCertified,false);
 A.equal(p.N9S,"NO_GO");
});
test("C20: manipulated approved IOC notional fails closed",()=>{
 const f=originalC14FixedFixture();f.native.states.find(s=>s.status==="MODELED_CAMPAIGN").profit8CommittedReservation.notionalUsd=1;
 A.throws(()=>Q.audit(f),/C20_IOC_COMMITMENT_AND_EQUITY/);
});
test("C20: forged purchase fill above approved ceiling fails closed",()=>{
 const f=originalC14FixedFixture();f.native.funded[0].inventoryEvents[0].filledPrice=1e8;
 A.throws(()=>Q.audit(f),/C20_SOURCE_FILL_LE_IOC_LE_12PCT_ADMISSION/);
});
test("C20: unregistered 73h holding violates original bound",()=>{
 const f=originalC14FixedFixture();f.native.funded[0].closed+=73*3600000;
 A.throws(()=>Q.audit(f),/C20_SOURCE_HOLD_LE72H/);
});
test("C20: unknown-before fill cannot be recorded as admitted",()=>{
 const f=originalC14FixedFixture();f.native.funded[0].inventoryEvents[0].knownAt+=60000;
 A.throws(()=>Q.audit(f),/C20_SINGLE_CAUSAL_ENTRY_RECEIPT/);
});
test("C20: tampered executable source nature or original cap fails closed",()=>{
 const f=originalC14FixedFixture();f.native.metadata.executionNature="BROKER";
 A.throws(()=>Q.audit(f),/C20_ORIGINAL_FUNDED_REPLAY/);
 const z=originalC14FixedFixture();z.limits.grossFraction=.5;
 A.throws(()=>Q.audit(z),/C20_FROZEN_CONTRACT/);
});
if(process.argv.includes("--emit-c20")){
 console.log("FWN9_C20_NATIVE_ADMISSION="+JSON.stringify(audit().proof));
}
