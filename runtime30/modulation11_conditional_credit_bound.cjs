"use strict";
/**
 * HARPOON M11-P6. Analytical conditional expectation upper bound on a SINGLE
 * 5-minute OHLC-vs-substep terminal-mark payoff gap, for predictable long
 * inventory fixed at the bar open. This is NOT a portfolio replay or a proof
 * about fully state-dependent sequential re-entry, execution depth or N9-S.
 *
 * Under frozen WEAK generator: S_k=S0*exp(mu*k/8)*M_k, where
 * M_k=exp(sigma*sum(Z)/sqrt(8)-sigma^2*k/16) is a martingale.
 * Conditional Doob L2: E[max_k |M_k-1|] <= 2 sqrt(exp(sigma^2)-1).
 * Thus E[(H-L)/S0] <= 2*D, E[H/S0] <= 1+D where
 * D=2 exp(max(mu,0)) sqrt(expm1(sigma^2))+expm1(abs(mu)).
 * Mixture variance is integrated with frozen 0.996/0.004 weights.
 * Effective net sell N(x)=floor_tick(x*(1-friction))-fee. As C in [L,H],
 * max(C,N(H))-min(C,N(L)) <= H-L+friction*H+tick*(1+1e-8)+fee.
 * Hence E[(W_native-W_firstCross)^+|F_open] <=
 * Q*S0*(2*Dmix+friction*(1+Dmix))+Q*(tick*(1+1e-8)+fee).
 * The bound is conditional on F_open-measurable Q, S0, no buys in the bar,
 * identical opening inventory, and a fresh independent volatility mixture.
 */
const assert=require("node:assert/strict");
const MIXTURE={regularProbability:.996, shockProbability:.004, shockSigmaFactor:4};
const TICK=.01;
const ROUNDING_EPS=1e-8;
const SYMBOLS=["SYNA","SYNB"];
function assertRegistered(protocol) {
  assert(protocol?.schema==="HARPOON_MODULATION9_PROTOCOL_1" &&
    protocol.limits?.capitalUsd===20000 &&
    protocol.limits?.grossFraction===.12 &&
    protocol.limits?.assetFraction===.12 &&
    protocol.limits?.openRiskFraction===.0025 &&
    protocol.generator?.intrabar_substeps===8 &&
    protocol.generator?.weak_drift_per_bar===.000025 &&
    JSON.stringify(protocol.generator.bar_sigma)==="[0.00075,0.00085,0.0005]" &&
    protocol.generator?.bars_per_session===78 &&
    JSON.stringify(protocol.traded_universe)==='["SYNA","SYNB"]' &&
    JSON.stringify(protocol.generator?.final_parameter_shift?.sigma_multiplier_range)==="[0.9,1.2]" &&
    JSON.stringify(protocol.generator?.final_parameter_shift?.drift_multiplier_range)==="[0.75,1.1]",
    "M11_P6_UNMODIFIED_M9_CONTRACT_REQUIRED");
  for(const [name,spread,slippage,fee,fixed] of [
    ["NOMINAL",2,2,.005,1],["STRESS",4,4,.01,2]
  ]) {
    const x=protocol.scenarios?.[name];
    assert(x?.spread_bps===spread && x?.slippage_bps===slippage &&
      x?.commission_usd_per_share_per_side===fee &&
      x?.external_cost_usd_per_calendar_day===fixed,
      "M11_P6_UNMODIFIED_COSTS_REQUIRED");
  }
}
function deviationMoment(mu,sigma) {
  assert(Number.isFinite(mu)&&Number.isFinite(sigma)&&sigma>=0,"FINITE_GAUSSIAN_MOMENTS");
  return 2*Math.exp(Math.max(mu,0))*Math.sqrt(Math.expm1(sigma*sigma))+
    Math.expm1(Math.abs(mu));
}
function boundSingle({protocol,stage,scenario,position}) {
  assertRegistered(protocol);
  assert(stage==="development"||stage==="final","UNREGISTERED_STAGE");
  assert(scenario==="NOMINAL"||scenario==="STRESS","UNREGISTERED_COST");
  assert(position&&typeof position==="object"&&!Array.isArray(position)&&
    Object.keys(position).sort().join(",")==="openingPrice,quantity,symbol",
    "ONLY_PREBAR_OBSERVABLE_POSITION_ALLOWED");
  const {symbol,quantity,openingPrice}=position;
  assert(SYMBOLS.includes(symbol),"NO_BENCHMARK_OR_FUTURE_ORACLE");
  assert(Number.isSafeInteger(quantity)&&quantity>=0&&
    Number.isFinite(openingPrice)&&openingPrice>0,"PREDICTABLE_LONG_INVENTORY_ONLY");
  const idx=SYMBOLS.indexOf(symbol);
  const sigmaScale=stage==="final"?1.2:1;
  const driftScale=stage==="final"?1.1:1;
  const mu=protocol.generator.weak_drift_per_bar*driftScale;
  const sigma=protocol.generator.bar_sigma[idx]*1.25*sigmaScale*Math.exp(.7);
  const A0=deviationMoment(mu,sigma);
  const A1=deviationMoment(mu,sigma*MIXTURE.shockSigmaFactor);
  const a=MIXTURE.regularProbability*A0+MIXTURE.shockProbability*A1;
  const c=protocol.scenarios[scenario];
  const friction=(c.spread_bps/2+c.slippage_bps)/10000;
  const perSideFee=c.commission_usd_per_share_per_side;
  const spreadPerOpeningDollar=2*a+friction*(1+a);
  const roundingAndFee=quantity*(TICK*(1+ROUNDING_EPS)+perSideFee);
  const boundUsd=quantity*openingPrice*spreadPerOpeningDollar+roundingAndFee;
  assert(Number.isFinite(boundUsd)&&boundUsd>=0,"BOUND_NUMERICAL_OVERFLOW");
  return {schema:"HARPOON_M11_P6_PREDICTABLE_WEAK_BAR_BOUND_1",
    kind:"CONDITIONAL_EXPECTATION_UPPER_BOUND_NOT_PATHWISE",
    symbol,quantity,openingPrice,stage,scenario,
    sigmaMaxRegular:sigma,sigmaMaxShock:4*sigma,muAbsMax:mu,
    mixProbShock:MIXTURE.shockProbability,expectedRelativeMaxDeviationUpper:a,
    expectedRelativeRangeUpper:2*a,expectedRelativeHighUpper:1+a,
    friction,perSideFee,tick:TICK,
    perOpeningDollarUpper:spreadPerOpeningDollar,
    roundingAndFeeUpperUsd:roundingAndFee,
    expectedPositiveNativeCreditUpperUsd:boundUsd,
    expectedActualNativeCreditMeasured:false,
    allCampaignsCovered:false,universalReservationProof:false,
    nativeInfeasibilityCertified:false,
    sameOpeningInventoryOnly:true,prebarQuantityMustBePredictable:true,
    noContinuousTwelvePercentCapClaimed:true};
}
function boundPortfolioBar({protocol,stage,scenario,positions}) {
  assert(Array.isArray(positions)&&positions.length<=2,"EXACTLY_TWO_TRADEABLE_ASSETS_MAX");
  assert(new Set(positions.map(x=>x.symbol)).size===positions.length,"DUPLICATE_SYMBOL");
  const parts=positions.map(position=>boundSingle({protocol,stage,scenario,position}));
  const upperUsd=parts.reduce((x,p)=>x+p.expectedPositiveNativeCreditUpperUsd,0);
  assert(Number.isFinite(upperUsd),"PORTFOLIO_BOUND_OVERFLOW");
  return {schema:"HARPOON_M11_P6_PREDICTABLE_WEAK_PORTFOLIO_BAR_1",
    stage,scenario,conditionalExpectedPositiveCreditUpperUsd:upperUsd,
    parts,usesCrossAssetIndependence:false,cashControlUpperUsd:0,
    budgetInterpretation:"CONDITIONAL_ON_F_OPEN_FOR_PREBAR_LONG_QUANTITIES_NOT_DYNAMIC_CAP",
    sequentialReentriesCovered:false,allFutureBarExpectationsSummed:false,
    nativeN9SCertificate:false};
}
module.exports={deviationMoment,boundSingle,boundPortfolioBar};
