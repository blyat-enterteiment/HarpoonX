"use strict";
const test=require("node:test");
const assert=require("node:assert/strict");
const P=require("../research/modulation9/protocol.json");
const A=require("../runtime30/modulation11_conditional_credit_bound.cjs");
const H=require("../runtime30/modulation11_formal_execution_bridge.cjs");
const E=require("../runtime30/modulation11_payoff_envelope.cjs");
const near=(a,b,eps=1e-9)=>assert(Math.abs(a-b)<=eps*Math.max(1,Math.abs(a),Math.abs(b)),a+" != "+b);
function one(symbol="SYNA",quantity=8,openingPrice=100,stage="final",scenario="NOMINAL"){
  return A.boundSingle({protocol:P,stage,scenario,position:{symbol,quantity,openingPrice}});
}
test("P6: conditional Doob L2 converges to zero without sigma and drift",()=>{
  near(A.deviationMoment(0,0),0);
  near(A.deviationMoment(0,.01),2*Math.sqrt(Math.expm1(.0001)));
  assert(A.deviationMoment(.00003,.01)>A.deviationMoment(0,.01));
});
test("P6: cash is zero and two asset bound is additive without independence",()=>{
  const zero=A.boundPortfolioBar({protocol:P,stage:"final",scenario:"NOMINAL",positions:[]});
  near(zero.conditionalExpectedPositiveCreditUpperUsd,0);
  const together=A.boundPortfolioBar({protocol:P,stage:"final",scenario:"NOMINAL",
    positions:[{symbol:"SYNA",quantity:8,openingPrice:100},
      {symbol:"SYNB",quantity:7,openingPrice:150}]});
  near(together.conditionalExpectedPositiveCreditUpperUsd,
    one().expectedPositiveNativeCreditUpperUsd+
    one("SYNB",7,150).expectedPositiveNativeCreditUpperUsd);
  assert.equal(together.usesCrossAssetIndependence,false);
  assert.equal(together.sequentialReentriesCovered,false);
});
test("P6: final parameter support, higher-volatility asset, and costs enlarge bound",()=>{
  assert(one("SYNA",8,100,"final").expectedPositiveNativeCreditUpperUsd>
    one("SYNA",8,100,"development").expectedPositiveNativeCreditUpperUsd);
  assert(one("SYNB").expectedPositiveNativeCreditUpperUsd>
    one("SYNA").expectedPositiveNativeCreditUpperUsd);
  assert(one("SYNA",8,100,"final","STRESS").expectedPositiveNativeCreditUpperUsd>
    one("SYNA",8,100,"final","NOMINAL").expectedPositiveNativeCreditUpperUsd);
});
test("P6: exact 0.004 normal mixture, not certainty of sigma four",()=>{
  const x=one();const s=x.sigmaMaxRegular,u=x.muAbsMax;
  const regular=A.deviationMoment(u,s),shock=A.deviationMoment(u,4*s);
  near(x.expectedRelativeMaxDeviationUpper,.996*regular+.004*shock);
  assert(x.expectedRelativeMaxDeviationUpper<shock);
  near(x.expectedRelativeRangeUpper,2*x.expectedRelativeMaxDeviationUpper);
});
test("P6: positive *realized* fork can exceed a valid EXPECTATION bound",()=>{
  const prices=[100.2,101.8,100.8,95.5,97,98,99,100];
  const position={quantity:8,entry:100.03,stop:99.03,distance:1,targetsR:[1.5,null]};
  const costs={friction:.0003,perSideUsd:.005,tick:.01};
  const r=E.certificate({bar:H.rawBar(1735920000000,100,prices),prices,position,costs});
  const expected=one();
  assert.equal(r.realizedNativeMinusObservedUsd>expected.expectedPositiveNativeCreditUpperUsd,true);
  assert.equal(expected.kind,"CONDITIONAL_EXPECTATION_UPPER_BOUND_NOT_PATHWISE");
  assert.equal(expected.nativeInfeasibilityCertified,false);
  assert.equal(expected.expectedActualNativeCreditMeasured,false);
});
test("P6: dimension and scaling include tick rounding per sold share",()=>{
  const a=one("SYNA",8,100),b=one("SYNA",16,100),c=one("SYNA",8,200);
  near(b.expectedPositiveNativeCreditUpperUsd,2*a.expectedPositiveNativeCreditUpperUsd);
  assert(c.expectedPositiveNativeCreditUpperUsd>a.expectedPositiveNativeCreditUpperUsd);
  near(c.roundingAndFeeUpperUsd,a.roundingAndFeeUpperUsd);
  const illustrative=one("SYNA",24,100);
  assert(illustrative.expectedPositiveNativeCreditUpperUsd>0);
  console.log("M11_P6_ANALYTIC_ILLUSTRATION="+JSON.stringify({
    eightShares:a.expectedPositiveNativeCreditUpperUsd,
    nominal2400UsdNotional:illustrative.expectedPositiveNativeCreditUpperUsd,
    sigmaMaxRegular:a.sigmaMaxRegular,
    relativeRangeUpper:a.expectedRelativeRangeUpper,
    conditionalIllustrationOnly:true}));
});
test("P6: reject future information, benchmark, shorts, or mutated registered contract",()=>{
  assert.throws(()=>A.boundSingle({protocol:P,stage:"final",scenario:"NOMINAL",
    position:{symbol:"SYNA",quantity:8,openingPrice:100,futureClose:101}}),
    /ONLY_PREBAR_OBSERVABLE/);
  assert.throws(()=>one("SYNM"),/NO_BENCHMARK/);
  assert.throws(()=>one("SYNA",-1),/PREDICTABLE_LONG/);
  assert.throws(()=>one("SYNA",8,0),/PREDICTABLE_LONG/);
  assert.throws(()=>A.boundSingle({protocol:{...P,limits:{...P.limits,grossFraction:.2}},
    stage:"final",scenario:"NOMINAL",position:{symbol:"SYNA",quantity:8,openingPrice:100}}),
    /UNMODIFIED_M9/);
});
test("P6: original eligibility gap remains unsolved, no continuous exposure assumption",()=>{
  const x=one();const missing=1-.9051232469572758;
  assert(missing>0&&missing<.1);
  const linearUsdDay=20000*missing/10000;
  assert(x.expectedPositiveNativeCreditUpperUsd>linearUsdDay);
  assert.equal(x.noContinuousTwelvePercentCapClaimed,true);
  assert.equal(x.allCampaignsCovered,false);
  console.log("M11_P6_MISSING_WEAK_HURDLE_BP_PER_CAL_DAY="+missing);
  console.log("M11_P6_LINEARIZED_INITIAL_CAPITAL_USD_PER_CAL_DAY="+linearUsdDay);
});
