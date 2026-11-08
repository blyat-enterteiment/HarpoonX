"use strict";
/** M11 P9E: algebraic pathwise log-wealth bridge, not a population or fill certificate. */
const assert = require("node:assert/strict");
const LIMITS = Object.freeze({capitalUsd:20000, days:176,
  hurdleBpPerDay:1, weakConditionalBpPerDay:0.9051232469572758});
const near = (a,b) => Number.isFinite(a) && Number.isFinite(b) &&
  Math.abs(a-b)<=1e-7*Math.max(1,Math.abs(a),Math.abs(b));
function bridge(native,causal,options={}) {
  const w0=LIMITS.capitalUsd;
  for (const book of [native,causal]) {
    assert(book && Number.isFinite(book.terminalEquityUsd) &&
      book.terminalEquityUsd>0,"P9E_POSITIVE_TERMINAL_WEALTH");
    assert(Number.isFinite(book.netAfterAllCostsUsd) &&
      near(book.terminalEquityUsd,w0+book.netAfterAllCostsUsd),
      "P9E_FULL_COST_RECONCILIATION");
  }
  const N=native.terminalEquityUsd,C=causal.terminalEquityUsd;
  const wealthDiff=N-C, ratio=wealthDiff/C;
  const exactLogRatio=Math.log(N/C);
  const positiveCredit=Math.max(0,ratio);
  assert(exactLogRatio<=positiveCredit+1e-12,"P9E_LOG_BRIDGE_INVALID");
  const days=options.days??LIMITS.days;
  assert(days===LIMITS.days,"P9E_FROZEN_CALENDAR");
  const correctionBpPerDay=positiveCredit/days*10000;
  const gapBpPerDay=LIMITS.hurdleBpPerDay-LIMITS.weakConditionalBpPerDay;
  return {schema:"HARPOON_M11_P9E_PATHWISE_LOG_BRIDGE_1",
    nativeEquityUsd:N,causalEquityUsd:C,wealthDiffUsd:wealthDiff,
    exactLogRatio,positiveRelativeCredit:positiveCredit,
    pathwiseCreditBpPerDay:correctionBpPerDay,
    requiredPopulationCreditGapBpPerDay:gapBpPerDay,
    sufficientPopulationCreditCeiling:gapBpPerDay*days/10000,
    pathwiseInequalityPassed:true,
    claims:{stochasticPopulationBound:false,
      nativeOHLCExecutable:false,universalReserveBridge:false,
      twelvePercentContinuousExposure:false,n9Achieved:false},
    note:"A single pathwise credit is not an expectation; no sample or bootstrap certifies the WEAK upper bound."};
}
function finitePopulationGate({causalBoundProven=false,creditBoundProven=false,
  nativeExecutionEquivalenceProven=false,operationalCoverageProven=false,
  creditUpperBpPerDay=null}={}) {
  if(!causalBoundProven||!creditBoundProven||!nativeExecutionEquivalenceProven||
     !operationalCoverageProven) return {status:"NO_CERTIFICATE",reason:"MISSING_UNIVERSAL_PROOF"};
  assert(Number.isFinite(creditUpperBpPerDay)&&creditUpperBpPerDay>=0,
    "P9E_INVALID_EXPECTATION_CREDIT_BOUND");
  const upper=LIMITS.weakConditionalBpPerDay+creditUpperBpPerDay;
  return {status:upper<LIMITS.hurdleBpPerDay?
    "SUFFICIENT_NUMERIC_CONDITION_UNVERIFIED":"INFEASIBILITY_NOT_PROVED",
    upperBpPerDay:upper,strictHurdleBpPerDay:LIMITS.hurdleBpPerDay};
}
function reserveAfterJump({originalNotionalUsd,initialEquityUsd,
    markMultiplier}) {
  assert(initialEquityUsd===LIMITS.capitalUsd&&
    originalNotionalUsd>=0&&originalNotionalUsd<=.12*initialEquityUsd&&
    Number.isFinite(markMultiplier)&&markMultiplier>0,"P9E_VALID_ADMISSION_WITNESS");
  const equity=initialEquityUsd+originalNotionalUsd*(markMultiplier-1);
  const marked=originalNotionalUsd*markMultiplier;
  assert(equity>0,"P9E_NEGATIVE_WEALTH");
  return {equityUsd:equity,exposureFraction:marked/equity,
    continuousCapCertified:false,admissionCapOnly:true};
}
module.exports={bridge,finitePopulationGate,reserveAfterJump,LIMITS};
