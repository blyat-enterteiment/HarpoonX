"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const L=require("../runtime30/fwn9_shadow_log_bridge_p9e.cjs");
const b=(n,c)=>L.bridge({terminalEquityUsd:n,netAfterAllCostsUsd:n-20000},
 {terminalEquityUsd:c,netAfterAllCostsUsd:c-20000});
test("same wealth: exact zero correction",()=>{
 const r=b(19990,19990);assert.equal(r.wealthDiffUsd,0);
 assert.equal(r.positiveRelativeCredit,0);
});
test("native advantage has nonzero unproven execution correction",()=>{
 const r=b(20112.16,19973.2);
 assert(r.exactLogRatio>0&&r.exactLogRatio<r.positiveRelativeCredit);
 assert(r.pathwiseCreditBpPerDay>r.requiredPopulationCreditGapBpPerDay);
 assert.equal(r.claims.stochasticPopulationBound,false);
});
test("native disadvantage positive credit exactly zero",()=>{
 const r=b(19975.74,19977.06);
 assert(r.exactLogRatio<0);assert.equal(r.positiveRelativeCredit,0);
});
test("negative terminal wealth fails closed",()=>assert.throws(()=>b(-1,20000),
 /P9E_POSITIVE_TERMINAL_WEALTH/));
test("tampered net after all costs fails closed",()=>assert.throws(()=>
 L.bridge({terminalEquityUsd:20100,netAfterAllCostsUsd:0},
 {terminalEquityUsd:20000,netAfterAllCostsUsd:0}),
 /P9E_FULL_COST_RECONCILIATION/));
test("not a continuous twelve percent cap",()=>{
 const x=L.reserveAfterJump({originalNotionalUsd:2400,
 initialEquityUsd:20000,markMultiplier:10});
 assert(x.exposureFraction>.12);assert.equal(x.continuousCapCertified,false);
});
test("conditioned upper bound never promoted if missing proof",()=>{
 const x=L.finitePopulationGate({causalBoundProven:true,creditBoundProven:true,
 creditUpperBpPerDay:0});assert.equal(x.status,"NO_CERTIFICATE");
});
test("conditional proof arithmetic uses original strict threshold",()=>{
 const x=L.finitePopulationGate({causalBoundProven:true,creditBoundProven:true,
 nativeExecutionEquivalenceProven:true,operationalCoverageProven:true,
 creditUpperBpPerDay:.09});
 assert.equal(x.status,"SUFFICIENT_NUMERIC_CONDITION_UNVERIFIED");
 const y=L.finitePopulationGate({causalBoundProven:true,creditBoundProven:true,
 nativeExecutionEquivalenceProven:true,operationalCoverageProven:true,
 creditUpperBpPerDay:.1});
 assert.equal(y.status,"INFEASIBILITY_NOT_PROVED");
});
test("frozen calendar and admission limits remain unchanged",()=>{
 assert.throws(()=>L.bridge({terminalEquityUsd:20000,netAfterAllCostsUsd:0},
 {terminalEquityUsd:20000,netAfterAllCostsUsd:0},{days:1}),/FROZEN_CALENDAR/);
 assert.throws(()=>L.reserveAfterJump({originalNotionalUsd:2500,
 initialEquityUsd:20000,markMultiplier:1}),/VALID_ADMISSION_WITNESS/);
});
