"use strict";
/** M11-C21: proof by paired eight-step paths that original OHLC-native exits
 * cannot be universally identified with eight-step first-observed crossing.
 *
 * No market RNG, signal, economic account, broker, order, holdout or strategy.
 * Uses original source-validated C11 diagnostic functions ONLY.
 */
const A=require("node:assert/strict");
const fs=require("node:fs");
const path=require("node:path");
const crypto=require("node:crypto");
const E=require("./modulation11_execution_equivalence.cjs");

const ROOT=path.resolve(__dirname,"..");
const EXPECTED_SHA=Object.freeze({
  "quant/harpoon_quant/modulation9.py":
    "9d4afa402d2b70791f175e79219495f9bbbe25eb3cd0b7e9212cef6bccbd68ab",
  "runtime30/profit8_replay.js":
    "303aa6956cfa0a249f0432bea23894b3ee8e514c60ff011177baabc7a6974810",
  "runtime30/ultimate_reservations.js":
    "94553547da3e02b972d72e8ea296a2e1ecc468a82133c75868eaea5fbe2ba494"
});
const SCHEMA="HARPOON_M11_C21_OHLC_EIGHTSTEP_NONIDENTIFIABILITY_WITNESS_1";
const need=(ok,code)=>A.ok(ok,"C21_"+code);

function assertFrozenSources(root=ROOT){
  for(const [p,expected] of Object.entries(EXPECTED_SHA)){
    const bytes=fs.readFileSync(path.join(root,p));
    need(crypto.createHash("sha256").update(bytes).digest("hex")===expected,
      "ORIGINAL_SHA256_CHANGED_"+p);
  }
  const source=fs.readFileSync(path.join(root,"runtime30/profit8_replay.js"),"utf8");
  need(source.includes("if (stopHit)") &&
    source.includes('b.end, "STOP", b.availableAt') &&
    source.includes('b.end, "TP" + (j + 1), b.availableAt') &&
    source.includes("if (stopHit && targetHit)") &&
    source.includes("ambiguous++;"),"ORIGINAL_NATIVE_STOP_FIRST_MECHANISM");
  return {originalGenerator:true,originalNativeReplay:true,
    originalReservationBook:true,modelKind:"ORIGINAL_SYNTHETIC_WEAK"};
}

function completeExample(){
  const t=Date.UTC(2025,0,3,14,30),end=t+300000;
  const bar={t,end,availableAt:end+1000,o:100,h:104,l:96.4,c:100.5};
  const position={quantity:8,entry:100,stop:98,distance:2,targetsR:[1.5,3]};
  const costs={friction:0.0003,perSideUsd:0.005,tick:0.01};
  // Same OHLC; differing order of target and stop crossing.
  const tpBeforeStop=[103.4,96.4,101,104,99,98.8,100,100.5];
  const stopBeforeTp=[96.4,103.4,101,104,99,98.8,100,100.5];
  E.checkGrid(bar,tpBeforeStop);E.checkGrid(bar,stopBeforeTp);
  const nativeA=E.nativeBarExits(bar,tpBeforeStop,position,costs);
  const nativeB=E.nativeBarExits(bar,stopBeforeTp,position,costs);
  const firstA=E.substepBarExits(bar,tpBeforeStop,position,costs);
  const firstB=E.substepBarExits(bar,stopBeforeTp,position,costs);
  const signature=x=>x.fills.map(f=>({
    reason:f.reason,quantity:f.quantity,fillPrice:f.fillPrice,
    effectiveAt:f.at,knownAt:f.knownAt
  }));
  const n1=signature(nativeA),n2=signature(nativeB);
  const d1=signature(firstA),d2=signature(firstB);
  A.deepEqual(n1,n2,"C21_SAME_OHLC_MUST_YIELD_SAME_ORIGINAL_NATIVE");
  A.notDeepEqual(d1,d2,"C21_ORDERED_FIRST_CROSS_DIFFERS");
  need(n1.length===1&&n1[0].reason==="STOP"&&n1[0].quantity===8 &&
    n1[0].effectiveAt===bar.end,"NATIVE_STOP_FIRST_BAR_END");
  need(d1.length===2&&d1[0].reason==="TP1"&&d1[1].reason==="STOP" &&
    d1[0].quantity===2&&d1[1].quantity===6,
    "FIRST_CROSS_TP_BEFORE_STOP");
  need(d2.length===1&&d2[0].reason==="STOP"&&d2[0].quantity===8,
    "FIRST_CROSS_STOP_BEFORE_TP");
  need(d1[0].effectiveAt===bar.t+37500&&
    d1[1].effectiveAt===bar.t+75000&&
    d2[0].effectiveAt===bar.t+37500&&
    n1[0].effectiveAt===bar.end,
    "NATIVE_VERSUS_FIRST_CROSS_EVENT_CLOCK_NOT_IDENTICAL");
  for(const f of [...d1,...d2])need(f.knownAt===bar.availableAt&&
    f.knownAt>f.effectiveAt,"RECEIPT_KNOWN_AFTER_PHYSICAL_DISCRETE_STEP");
  const totalCash=(fills)=>fills.reduce((z,f)=>
    z+f.quantity*f.fillPrice-f.commissionUsd,0);
  const receiptsAreDifferent=totalCash(firstA.fills)!==totalCash(firstB.fills);
  need(receiptsAreDifferent,"DIFFERENT_DISCRETE_CASH_PROCEEDS");
  return {
    schema:SCHEMA,
    witnessKind:"FIXED_DETERMINISTIC_STRUCTURAL_PROOF_NOT_MARKET_ACCOUNT",
    bar,position,costs,
    pricePaths:{tpBeforeStop,stopBeforeTp},
    nativeOHLC:{pathOne:n1,pathTwo:n2,identical:true},
    firstObservedEightStep:{pathOne:d1,pathTwo:d2,identical:false},
    grossCashReceipts:{
      firstPath:totalCash(firstA.fills),
      secondPath:totalCash(firstB.fills),
      originalOHLCNative:totalCash(nativeA.fills)
    },
    sourceWeakSupport:"Nondegenerate positive Gaussian log-increment density on neighborhoods of both positive ordered tapes; no exact-path probability asserted",
    theorem:"A map depending solely on OHLC and prebar state cannot equal first-observed eight-step fills for both paths because inputs OHLC are identical but first-cross outputs differ.",
    nativeStopFirstEqualsFirstCrossOnAllPaths:false,
    anyActualExchangeBrokerFillReceiptProvided:false,
    claimThatAnyIndividualOHLCPriceNeverTraded:false,
    wholeNativePopulationExpectationCertified:false,
    mathematicalUniversalTradingUnprofitabilityProved:false,
    N9S:"NO_GO",
    budget:{newMarketSeeds:0,newSignals:0,newEconomicAccounts:0,finalM10Opened:0}
  };
}

function certificateGate({admissionsExpectationUpper,executionCreditExpectationUpper,
  prebarStatePopulationTraceComplete=false,brokerExecutionReceiptsIndependentlyVerified=false}={}){
  for(const [name,v] of Object.entries({
    admissionsExpectationUpper,executionCreditExpectationUpper
  })){
    if(v!==undefined&&v!==null)
      need(typeof v==="number"&&Number.isFinite(v)&&v>=0,
        "INVALID_ECONOMIC_EXPECTATION_"+name);
  }
  need(typeof prebarStatePopulationTraceComplete==="boolean"&&
    typeof brokerExecutionReceiptsIndependentlyVerified==="boolean",
    "INVALID_PROOF_FLAGS");
  const missing=[];
  if(admissionsExpectationUpper===undefined||admissionsExpectationUpper===null)
    missing.push("INDEPENDENT_POPULATION_EXPECTED_ADMITTED_NOTIONAL_BOUND");
  if(executionCreditExpectationUpper===undefined||executionCreditExpectationUpper===null)
    missing.push("INDEPENDENT_POPULATION_EVENT_CONDITIONED_U_BOUND");
  if(!prebarStatePopulationTraceComplete)
    missing.push("ALL_SOURCE_TIME_PREBAR_STOP_TARGET_PENDING_RESERVATION_STATES");
  if(!brokerExecutionReceiptsIndependentlyVerified)
    missing.push("ACTUAL_ATTAINABLE_BROKER_FILL_RECEIPT_AND_QUEUE_PROOF");
  missing.push("STRUCTURAL_OHLC_FIRST_CROSS_NON_EQUIVALENCE");
  return {
    schema:"HARPOON_M11_C21_UNIVERSAL_NATIVE_ECONOMIC_CERTIFICATE_GATE_1",
    sourceAlgorithmOriginal:"NATIVE_OHLC_STOP_FIRST_NOT_DISCRETE_FIRST_CROSS",
    noEquivalenceCertificatePossibleForOriginalUnchangedOHLC:true,
    independentlyProvedPopulationAdmissions: false,
    independentlyProvedPopulationExecutionU: false,
    missing,universalEconomicImpossibilityClaimAllowed:false,
    N9S:"NO_GO",holdoutM10Opened:0,recursiveSearchEnabled:false
  };
}
module.exports={assertFrozenSources,completeExample,certificateGate};
