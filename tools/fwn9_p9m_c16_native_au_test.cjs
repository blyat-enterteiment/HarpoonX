"use strict";
/** C16 uses ONLY the pre-existing C14 fixed engineering signal IDs and OHLC fixture.
 * No new candidate, market seed, final economic account or strategy experiment.
 */
const test=require("node:test"),A=require("node:assert/strict");
const V=require("../runtime30/fwn9_p9m_c16_native_au_bridge.cjs");
const N=require("../runtime30/profit8_replay.js");
const K=require("../runtime30/ultimate_contracts.js");
const BAR=300000,DAY=86400000;
function alreadyRegisteredC14Engineering(){
  // Byte-for-byte economic setup of tools/fwn9_p9m_c14_native_test_v2.cjs's
  // nativeEngineering() (fixed session and two signal IDs SYNA:60, SYNB:90).
  const sessions=[0,3,4,5,6,7].map(k=>{
    const open=Date.UTC(2025,0,3,14,30)+k*DAY;
    return {date:new Date(open).toISOString().slice(0,10),
      open,close:open+78*BAR};
  });
  const series=["SYNA","SYNB"].map(symbol=>({symbol,root:symbol,tick:.01,
    pointValue:1,bars:sessions.flatMap(session=>
      Array.from({length:78},(_,i)=>({
        t:session.open+i*BAR,end:session.open+(i+1)*BAR,
        availableAt:session.open+(i+1)*BAR+1000,
        o:symbol==="SYNA"?200:100,h:symbol==="SYNA"?200.1:100.1,
        l:symbol==="SYNA"?199.9:99.9,c:symbol==="SYNA"?200:100,v:1000
      })))}));
  const data={schema:"HARPOON-ULTIMATE-DATA-1",kind:"ALPACA_PROXY",
    sessions,series,splitEvents:[],cashDividends:[],
    provenance:{execution:"MODELED_OHLCV",source:"SYNTHETIC_ENGINEERING_ONLY",
      feed:"C14_FIXED_FIXTURE",files:[{name:"C14",sha256:"0".repeat(64)}]}};
  const protocol={...K.defaultProtocol("ALPACA_PROXY"),
    universe:["SYNA","SYNB"],
    costs:{spreadBps:2,slippageBps:2,perSideUsd:.005}};
  const signals=[["SYNA",60,4],["SYNB",90,1]].map(([symbol,m,distance])=>{
    const at=sessions[0].open+m*60000+1000;
    return {id:symbol+":"+m,symbol,hypothesis:"CLOSED_CHANNEL",
      direction:1,at,index:0,
      plannedEntryAt:N.planSignalEntryAt(at,sessions),
      stopDistance:distance,regime:.4,
      metadata:{roadmapHorizonHours:72,modulation9:{profile:"NATIVE72"}}};
  });
  const native=N.replayFundedPortfolio(signals,data,protocol,
    [{test:sessions,selected:"ALL:BASELINE"}],sessions,
    {...N.PROFIT8_REPLAY_LIMITS},
    {continuous:true,cashDividends:true,
      entryExecution:"IOC_LIMIT_COMMON_CAUSAL_30BPS",
      externalCostPerSessionUsd:0,calendarCostPerDayUsd:1,
      profit8:{mode:"NATIVE_MAX"},researchModulation:true});
  return {native,data,sessions,signals};
}
function calculate(){
  const f=alreadyRegisteredC14Engineering();
  return {f,report:V.audit({...f,calendarCostUsdPerDay:1})};
}
test("C16: actual native funded receipts reconcile and expose A/U upper, never expectation",()=>{
  const {f,report:r}=calculate();
  A(f.native.funded.length>=1);
  A.equal(r.originalNativeReplay,true);
  A.equal(r.sourceExecution,"MODELED_OHLCV_NOT_BROKER");
  A.equal(r.barCount,6*78);
  A.equal(r.substepCount,6*78*8);
  A.equal(r.cashAndPositionReconciled,true);
  A(Math.abs(r.terminalReconciliationResidualUsd)<1e-6);
  A(r.AObservedPathUpperDollarSubsteps>=r.AObservedPathLowerDollarSubsteps);
  A(r.AObservedPathUpperDollarSubsteps>0);
  A(r.UObservedPathPositiveCreditUpperUsd>=0);
  A.equal(r.populationExpectedAUpperCertified,false);
  A.equal(r.populationExpectedUUpperCertified,false);
  A.equal(r.C15EconomicExclusionEvaluated,false);
  A.equal(r.N9SAdmission,"NO_GO");
  A.equal(r.budget.finalM10Opened,0);
});
test("C16: exact eight-step A, time-aligned U and population certificates remain absent",()=>{
  const {report:r}=calculate();
  A.equal(r.exactOrderedEightSubstepTapeAvailable,false);
  A.equal(r.exactActualPathAIdentified,false);
  A.equal(r.exactExecutionTimeUIdentified,false);
  A.equal(r.independentDecimalVerification,"REQUIRES_SEPARATE_VERIFIER");
});
test("C16: externally modified terminal cash fails native book reconciliation",()=>{
  const f=alreadyRegisteredC14Engineering();
  f.native.curve.at(-1).equity_end_usd+=1;
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_INDEPENDENT_PHYSICAL_TERMINAL_CASH_PARITY/);
});
test("C16: tampered future receipt clock fails closed",()=>{
  const f=alreadyRegisteredC14Engineering();
  A(f.native.funded[0].inventoryEvents.length>=2);
  f.native.funded[0].inventoryEvents[1].knownAt=
    f.native.funded[0].inventoryEvents[1].at-1;
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_PHYSICAL_FILL_RECEIPT_AND_PRICE/);
});
test("C16: unsupported native sell outside bar high fails closed",()=>{
  const f=alreadyRegisteredC14Engineering();
  const e=f.native.funded[0].inventoryEvents.find(x=>x.kind==="EXIT");
  A(e);e.filledPrice=1e7;
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_MODELED_FILL_PRICE_SUPPORT/);
});
test("C16: unsupported dividend or security adjustment rejected",()=>{
  const f=alreadyRegisteredC14Engineering();
  f.data.cashDividends.push({symbol:"SYNA",amountPerShare:1});
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_NO_CORPORATE_ACTIONS_OR_UNKNOWN_DATA/);
});
test("C16: cannot silently substitute different calendar fee",()=>{
  const f=alreadyRegisteredC14Engineering();
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:2}),
    /C16_NATIVE_CALENDAR_EXTERNAL_COST_PARITY/);
});
test("C16: unregistered bar-count shortening invalidates native substep exposure",()=>{
  const f=alreadyRegisteredC14Engineering();
  f.data.series[0].bars.pop();
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_FROZEN_78_BARS_PER_SESSION/);
});
test("C16: fake no-fill cannot create inventory",()=>{
  const f=alreadyRegisteredC14Engineering();
  f.native.modeledNoFills.push({signalId:"FANTOM",positionOpened:true,
    plannedEntryAt:f.sessions[0].open,resolutionAt:f.sessions[0].open});
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_NO_FILL_IS_NOT_A_FUNDED_POSITION/);
});
test("C16: altered native source to non-replay account rejected",()=>{
  const f=alreadyRegisteredC14Engineering();
  f.native.metadata.executionNature="BROKER";
  A.throws(()=>V.audit({...f,calendarCostUsdPerDay:1}),
    /C16_EXACT_NATIVE_SOURCE_ONLY/);
});
if(process.argv.includes("--emit-c16")){
  const {report:r}=calculate();
  console.log("FWN9_C16_NATIVE_AU_EVIDENCE="+JSON.stringify(r));
}
if(process.argv.includes("--bench")){
  const {f}=calculate(),t=process.hrtime.bigint();
  for(let i=0;i<200;i++)V.audit({...f,calendarCostUsdPerDay:1});
  console.log("C16_BENCH_200_NATIVE_AU_AUDITS_MS="+
    (Number(process.hrtime.bigint()-t)/1e6).toFixed(3));
}
