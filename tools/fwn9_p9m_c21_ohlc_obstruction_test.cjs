"use strict";
/** All fixtures deterministic. No M9 generator, signals or accounts invoked. */
const test=require("node:test");
const A=require("node:assert/strict");
const fs=require("node:fs");
const os=require("node:os");
const path=require("node:path");
const P=require("../runtime30/fwn9_p9m_c21_ohlc_obstruction.cjs");

test("C21 frozen original M9 native and reservation sources match registered SHA",()=>{
 const v=P.assertFrozenSources();
 A.equal(v.originalGenerator,true);
 A.equal(v.originalNativeReplay,true);
 A.equal(v.originalReservationBook,true);
});

test("C21 tampered frozen native source cannot support proof",()=>{
 const tmp=fs.mkdtempSync(path.join(os.tmpdir(),"c21-source-"));
 const root=path.resolve(__dirname,"..");
 try{
  for(const p of ["quant/harpoon_quant/modulation9.py",
   "runtime30/profit8_replay.js","runtime30/ultimate_reservations.js"]){
    fs.mkdirSync(path.dirname(path.join(tmp,p)),{recursive:true});
    fs.copyFileSync(path.join(root,p),path.join(tmp,p));
  }
  A.equal(P.assertFrozenSources(tmp).originalGenerator,true);
  fs.appendFileSync(path.join(tmp,"runtime30/profit8_replay.js"),"\n// altered\n");
  A.throws(()=>P.assertFrozenSources(tmp),/C21_ORIGINAL_SHA256_CHANGED/);
 }finally{fs.rmSync(tmp,{recursive:true,force:true});}
});

test("C21 two ordered eight-step paths have *identical* OHLC and state",()=>{
 const w=P.completeExample();
 A.equal(w.bar.o,100);A.equal(w.bar.h,104);
 A.equal(w.bar.l,96.4);A.equal(w.bar.c,100.5);
 A.equal(w.pricePaths.tpBeforeStop.length,8);
 A.equal(w.pricePaths.stopBeforeTp.length,8);
 for(const xs of Object.values(w.pricePaths)){
  A.equal(xs.at(-1),w.bar.c);
  A.equal(Math.min(w.bar.o,...xs),w.bar.l);
  A.equal(Math.max(w.bar.o,...xs),w.bar.h);
 }
});

test("C21 original OHLC STOP-first outputs exactly same fill on both paths",()=>{
 const w=P.completeExample();
 A.deepEqual(w.nativeOHLC.pathOne,w.nativeOHLC.pathTwo);
 A.equal(w.nativeOHLC.pathOne.length,1);
 A.equal(w.nativeOHLC.pathOne[0].reason,"STOP");
 A.equal(w.nativeOHLC.pathOne[0].quantity,8);
});

test("C21 ordered first crossings distinguish target-before-stop and stop-first",()=>{
 const w=P.completeExample();
 A.deepEqual(w.firstObservedEightStep.pathOne.map(f=>f.reason),["TP1","STOP"]);
 A.deepEqual(w.firstObservedEightStep.pathOne.map(f=>f.quantity),[2,6]);
 A.deepEqual(w.firstObservedEightStep.pathTwo.map(f=>f.reason),["STOP"]);
 A.deepEqual(w.firstObservedEightStep.pathTwo.map(f=>f.quantity),[8]);
});

test("C21 exact native at=bar.end is not first crossing effectiveAt",()=>{
 const w=P.completeExample();
 const at=w.bar.t;
 A.equal(w.nativeOHLC.pathOne[0].effectiveAt,at+300000);
 A.equal(w.firstObservedEightStep.pathOne[0].effectiveAt,at+37500);
 A.equal(w.firstObservedEightStep.pathOne[1].effectiveAt,at+75000);
 A.equal(w.firstObservedEightStep.pathTwo[0].effectiveAt,at+37500);
});

test("C21 delayed knownAt never makes proceeds known at preceding first-cross",()=>{
 const w=P.completeExample();
 for(const f of [
  ...w.nativeOHLC.pathOne,...w.firstObservedEightStep.pathOne,
  ...w.firstObservedEightStep.pathTwo
 ]){
  A.equal(f.knownAt,w.bar.availableAt);
  A(f.knownAt>f.effectiveAt);
 }
});

test("C21 first-cross cash outcomes differ although original OHLC is fixed",()=>{
 const w=P.completeExample();
 A.notEqual(w.grossCashReceipts.firstPath,w.grossCashReceipts.secondPath);
 A.equal(w.nativeOHLC.identical,true);
 A.equal(w.firstObservedEightStep.identical,false);
});

test("C21 no OHLC-only function can reproduce both ordered-execution outcomes",()=>{
 const w=P.completeExample();
 A.deepEqual(w.nativeOHLC.pathOne,w.nativeOHLC.pathTwo);
 A.notDeepEqual(w.firstObservedEightStep.pathOne,w.firstObservedEightStep.pathTwo);
 A.equal(w.nativeStopFirstEqualsFirstCrossOnAllPaths,false);
 A.match(w.theorem,/cannot equal first-observed eight-step fills/);
});

test("C21 positive-density WEAK *neighborhoods*, not positive mass exact path",()=>{
 const w=P.completeExample();
 A.match(w.sourceWeakSupport,/neighborhoods/);
 A.match(w.sourceWeakSupport,/no exact-path probability/);
 A.equal(w.claimThatAnyIndividualOHLCPriceNeverTraded,false);
});

test("C21 no-fill compact archive omits different prebar stop states with different future triggers",()=>{
 const w=P.latentPrebarStatesWitness();
 A.equal(w.samePastOHLC,true);
 A.equal(w.samePastRecordedFills,true);
 A.deepEqual(w.alternativeUnrecordedPriorStops,[99.5,98.0]);
 A.equal(w.futureActivationDiffers,true);
 A.equal(w.historicalSingleSeedPopulationCertified,false);
 A.match(w.conclusion,/cannot uniquely determine conditional future exit probabilities/);
});
test("C21 incomplete population inputs fail closed and expose all blockers",()=>{
 const d=P.certificateGate();
 A.equal(d.N9S,"NO_GO");
 A.equal(d.universalEconomicImpossibilityClaimAllowed,false);
 A.equal(d.holdoutM10Opened,0);
 A.equal(d.recursiveSearchEnabled,false);
 A(d.missing.includes("INDEPENDENT_POPULATION_EXPECTED_ADMITTED_NOTIONAL_BOUND"));
 A(d.missing.includes("ACTUAL_ATTAINABLE_BROKER_FILL_RECEIPT_AND_QUEUE_PROOF"));
});

test("C21 malformed expectations and proof flags are rejected",()=>{
 for(const bad of [-1,NaN,Infinity,true,"500"]){
  A.throws(()=>P.certificateGate({admissionsExpectationUpper:bad}),
   /C21_INVALID_ECONOMIC_EXPECTATION/);
 }
 A.throws(()=>P.certificateGate({prebarStatePopulationTraceComplete:"yes"}),
  /C21_INVALID_PROOF_FLAGS/);
});

test("C21 supplying invented bound numbers does not create real certification",()=>{
 const d=P.certificateGate({admissionsExpectationUpper:1,executionCreditExpectationUpper:0,
  prebarStatePopulationTraceComplete:true,
  brokerExecutionReceiptsIndependentlyVerified:true});
 A.equal(d.N9S,"NO_GO");
 A.equal(d.noEquivalenceCertificatePossibleForOriginalUnchangedOHLC,true);
 A.equal(d.independentlyProvedPopulationAdmissions,false);
 A.equal(d.independentlyProvedPopulationExecutionU,false);
 A(d.missing.includes("STRUCTURAL_OHLC_FIRST_CROSS_NON_EQUIVALENCE"));
});

test("C21 no account, signal, market seed, final or order creation",()=>{
 const w=P.completeExample();
 A.deepEqual(w.budget,{newMarketSeeds:0,newSignals:0,
  newEconomicAccounts:0,finalM10Opened:0});
 A.equal(w.mathematicalUniversalTradingUnprofitabilityProved,false);
 A.equal(w.anyActualExchangeBrokerFillReceiptProvided,false);
});

if(process.argv.includes("--emit-c21")){
 const w=P.completeExample(),gate=P.certificateGate();
 console.log("C21_SOURCE_EXECUTION_OBSTRUCTION="+JSON.stringify({
  witness:w,prebarNonidentifiability:P.latentPrebarStatesWitness(),gate,source:P.assertFrozenSources()
 }));
}
