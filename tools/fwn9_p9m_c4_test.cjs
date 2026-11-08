"use strict";
// P9M-C4 complete conditional permutation catalog; no market random seeds.
const test=require("node:test"),A=require("node:assert/strict");
const X=require("../runtime30/fwn9_p9m_c4_attainability.cjs");
const G=require("../runtime30/modulation11_execution_equivalence.cjs");
function fixture(){
  const prices=[100.2,104,103,96,97,99,100,100];
  const bar={t:1000000,end:1300000,availableAt:1301000,
    o:100,h:104,l:96,c:100,v:1000};
  const position={quantity:8,entry:100.03,stop:98.03,distance:2,
    targetsR:[1.5,3]};
  const costs={friction:.0003,perSideUsd:.005,tick:.01};
  return {bar,prices,position,costs};
}
function certificate(){return X.certificate(fixture());}
test("C4 enumerates ALL 7! distinct conditional paths with the final close fixed",()=>{
 const a=certificate();
 A.equal(a.counts.exhaustiveUniqueOrders,5040);
 A.equal(a.counts.targetFirst,1680);
 A.equal(a.counts.stopFirst,3360);
 A.equal(a.counts.targetFirst+a.counts.stopFirst,5040);
 A.equal(a.eightStepFirstCross.minimumNetUsd,-32.56);
 A.equal(a.eightStepFirstCross.maximumNetUsd,-10.58);
 A.equal(a.native.netTradingUsd,-16.32);
 A.equal(a.nativeWithinFiniteDiscreteEnvelope,true);
 A.equal(a.counts.exactDiscreteFillParity,0);
 A.equal(a.counts.nativeBetterThanDiscrete,4200);
 A.equal(a.counts.nativeWorseThanDiscrete,840);
 A.equal(a.counts.nativeEqualDiscrete,0);
});
test("C4 explicit continuous interpolation attains stop price without proving eight-step execution",()=>{
 const a=certificate();
 A.equal(a.native.rawFillSupport.length,1);
 A.equal(a.native.rawFillSupport[0].observedEightStep,false);
 A.equal(a.native.rawFillSupport[0].continuousLogLinear,true);
 A.equal(a.native.rawFillSupport[0].implicitContinuousInterpolationRequired,true);
 A.equal(a.hypotheticalContinuousInterpolation.stochasticLawPreserved,false);
 A.equal(a.hypotheticalContinuousInterpolation.liquidityEstablished,false);
 A.equal(a.counts.continuousPayoffParity,3360);
 A.equal(a.counts.continuousReceiptTimingParity,0);
});
test("C4 target-first and stop-first permuted bars share OHLC but not causal proceeds",()=>{
 const f=fixture();
 const b=[100.2,96,103,104,97,99,100,100];
 const nativeA=G.nativeBarExits(f.bar,f.prices,f.position,f.costs);
 const nativeB=G.nativeBarExits(f.bar,b,f.position,f.costs);
 A.deepEqual(nativeA.fills,nativeB.fills);
 const a=G.substepBarExits(f.bar,f.prices,f.position,f.costs);
 const z=G.substepBarExits(f.bar,b,f.position,f.costs);
 A.deepEqual(a.fills.map(x=>x.reason),["TP1","STOP"]);
 A.deepEqual(z.fills.map(x=>x.reason),["STOP"]);
 A.equal(X.independentClose(f.position,a.fills,f.costs),-16.58);
 A.equal(X.independentClose(f.position,z.fills,f.costs),-32.56);
});
test("C4 effective crossing times differ but receipts remain future published",()=>{
 const f=fixture();
 for(const path of [f.prices,[100.2,96,103,104,97,99,100,100]]){
  const c=X.continuousFirstPass(f.bar,path,f.position,f.costs);
  A.equal(c.remainingQuantity,0);
  A(c.fills.length>=1);
  A(c.fills.every(x=>x.at>=f.bar.t&&x.at<=f.bar.end&&
    x.knownAt===f.bar.availableAt));
  A(c.fills.some(x=>x.at<f.bar.end));
 }
});
test("C4 guard refuses OHLC, clock and cost/quantity mutation",()=>{
 const f=fixture();
 A.throws(()=>X.certificate({...f,bar:{...f.bar,c:101}}),/SUBSTEP_OHLC_IDENTITY/);
 A.throws(()=>X.certificate({...f,bar:{...f.bar,availableAt:f.bar.end}}),/PUBLICATION_AFTER_BAR/);
 A.throws(()=>X.certificate({...f,costs:{...f.costs,perSideUsd:0}}),
   /P9MC4_FROZEN_NOMINAL_FIXTURE/);
 A.throws(()=>X.certificate({...f,position:{...f.position,quantity:4}}),
   /P9MC4_FROZEN_NOMINAL_FIXTURE/);
});
test("C4 deduplicates identical prefix substeps without changing price envelope claim",()=>{
 const f=fixture();f.prices[0]=100; // Two equal 100 values in seven permuted slots.
 const a=X.certificate(f);
 A.equal(a.counts.exhaustiveUniqueOrders,2520);
 A.equal(a.counts.targetFirst+a.counts.stopFirst,2520);
 A.equal(a.native.rawFillSupport[0].observedEightStep,false);
});
test("C4 evidence never converts a conditional permutation catalog into population probabilities",()=>{
 const c=certificate();
 A.equal(c.invariants.noProbabilitiesInferredFromPermutationCounts,true);
 A.equal(c.invariants.originalEightStepStochasticLawUntouched,true);
 A.equal(c.invariants.WEAKPopulationBoundCertified,false);
 A.equal(c.invariants.N9SAccepted,false);
 A.equal(c.invariants.noAlphaOrEconomicAccounts,true);
 A.equal(c.capitalUsd,20000);
 A.equal(c.calendarFeesUsd,8);
});
if(process.argv.includes("--emit-evidence")){
 const f=fixture();
 console.log("P9MC4_EVIDENCE="+JSON.stringify({...f,result:X.certificate(f)}));
}
if(process.argv.includes("--bench")){
 const start=process.hrtime.bigint();
 for(let i=0;i<2;i++)certificate();
 console.log("P9MC4_TWO_EXHAUSTIVE_CATALOGS_MS="+
   (Number(process.hrtime.bigint()-start)/1e6).toFixed(3));
}
