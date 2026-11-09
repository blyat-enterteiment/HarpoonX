"use strict";
/** FWN9 / P9M-C1: two indistinguishable OHLC bars, two distinct causal
 * eight-substep executions. Offline falsification only, NOT a trading route,
 * population bound, observed fill, optimizer input or new market account.
 */
const A=require("node:assert/strict");
const C=require("./modulation11_stateful_campaign.cjs");
const G=require("./modulation11_execution_equivalence.cjs");
const SCALE=1000000n;
function need(v,tag){A.ok(v,"P9MC1_"+tag);}
function micros(usd){
  need(Number.isFinite(usd)&&Math.abs(usd)<1e9,"FINITE_USD");
  const raw=usd*1e6;
  need(Math.abs(raw-Math.round(raw))<.0005,"MICROUSD_PRECISION");
  return BigInt(Math.round(raw));
}
function independentAccount(campaign,fee,capital=20000,calendarCost=8){
  const quantity=campaign.quantity;
  need(Number.isSafeInteger(quantity)&&quantity>0,"SHARES");
  const entry=micros(campaign.entry),feeU=micros(fee);
  let cash=micros(capital)-BigInt(quantity)*(entry+feeU);
  let remaining=quantity,exitFees=0n,prevAt=campaign.opened;
  const fills=[];
  for(const e of campaign.fills){
    need(Number.isSafeInteger(e.quantity)&&e.quantity>0&&e.quantity<=remaining,
      "NO_SHORT_OR_FRACTIONAL_INVENTORY");
    need(Number.isSafeInteger(e.at)&&Number.isSafeInteger(e.knownAt)&&
      e.at>=prevAt&&e.knownAt>=e.at&&e.at-campaign.opened<=72*3600000,
      "CAUSAL_EXECUTION_CLOCK");
    const filled=micros(e.price),q=BigInt(e.quantity);
    cash+=q*(filled-feeU);exitFees+=q*feeU;
    remaining-=e.quantity;prevAt=e.at;
    fills.push({reason:e.reason,shares:e.quantity,at:e.at,knownAt:e.knownAt,
      step:e.step??null,priceUsd:e.price});
  }
  need(remaining===0,"TERMINAL_INVENTORY");
  const fixed=micros(calendarCost);
  const netMicro=cash-micros(capital);
  const p=Number(netMicro)/1e6;
  const expectedFees=BigInt(quantity)*feeU+exitFees;
  need(Math.abs(p-campaign.netUsd)<.000001,"INDEPENDENT_NET_RECONCILIATION");
  need(Math.abs(Number(expectedFees)/1e6-campaign.feesUsd)<.000001,
    "INDEPENDENT_FEE_RECONCILIATION");
  return {quantity,closed:true,netTradingUsd:p,feesUsd:Number(expectedFees)/1e6,
    terminalAfterCalendarUsd:Number(cash-fixed)/1e6,
    cashAfterAllSalesBeforeFixedUsd:Number(cash)/1e6,
    fills};
}
function summarize(result,cost){
  return {native:independentAccount(result.modeled,cost),
    discrete:independentAccount(result.discrete,cost),
    nativeActualNetUsd:result.native.netUsd,
    nativeActualExitSignature:result.native.inventoryEvents.filter(e=>e.kind==="EXIT")
      .map(e=>[e.reason,-e.quantityDelta,e.filledPrice,e.at,e.knownAt]),
    ambiguityBars:result.modeled.ambiguousBars};
}
function scan({signal,series,data,protocol,quantity=8,pathA,pathB}){
  need(signal?.direction===1&&signal.hypothesis==="CLOSED_CHANNEL"&&
    signal.metadata?.modulation9?.profile==="NATIVE72","REGISTERED_LONG_PROFILE_ONLY");
  need(data?.provenance?.source==="SYNTHETIC_ENGINEERING_ONLY"&&
    data?.splitEvents?.length===0&&data.cashDividends?.length===0,
    "SYNTHETIC_FIXTURE_ONLY");
  need(protocol?.costs?.spreadBps===2&&protocol.costs.slippageBps===2&&
    protocol.costs.perSideUsd===.005&&series?.tick===.01&&series.pointValue===1,
    "LOCKED_NOMINAL_COSTS_AND_TICK");
  need(Number.isSafeInteger(quantity)&&quantity>0,"INTEGER_QUANTITY");
  need(pathA&&pathB&&series.bars.length>0,"TWO_RECORDED_PATHS");
  const differing=[];
  for(const bar of series.bars){
    const key=String(bar.t);
    const a=pathA[key],b=pathB[key];
    G.checkGrid(bar,a);G.checkGrid(bar,b);
    need(JSON.stringify([...a].sort((x,y)=>x-y))===
      JSON.stringify([...b].sort((x,y)=>x-y)),
      "IDENTICAL_SUBSTEP_MULTISET");
    if(JSON.stringify(a)!==JSON.stringify(b))differing.push(bar.t);
  }
  need(differing.length===1&&differing[0]===signal.plannedEntryAt,
    "SINGLE_PREDECLARED_ENTRY_BAR_PERMUTATION");
  const a=C.compareNative({signal,series,data,protocol,quantity,substeps:pathA});
  const b=C.compareNative({signal,series,data,protocol,quantity,substeps:pathB});
  const x=summarize(a,protocol.costs.perSideUsd);
  const y=summarize(b,protocol.costs.perSideUsd);
  need(JSON.stringify(x.nativeActualExitSignature)===
    JSON.stringify(y.nativeActualExitSignature)&&
    x.native.netTradingUsd===y.native.netTradingUsd,
    "NATIVE_OHLC_INVARIANCE");
  need(JSON.stringify(x.discrete.fills)!==JSON.stringify(y.discrete.fills)&&
    x.discrete.netTradingUsd!==y.discrete.netTradingUsd,
    "CAUSAL_PATHWISE_DIFFERENCE");
  need(x.ambiguityBars>=1&&y.ambiguityBars>=1,"STOP_TARGET_SAME_BAR");
  return {
    schema:"HARPOON_FWN9_P9M_C1_CAUSAL_NONIDENTIFIABILITY_1",
    sourceNature:"DETERMINISTIC_SYNTHETIC_ENGINEERING_NO_OBSERVED_FILLS",
    sourcePair:{sameOHLC:true,sameSubstepMultiset:true,changedBars:differing,
      pathsNeverExposedToSignal:true},
    capitalUsd:20000,calendarFeeUsd:8,initialShares:quantity,
    admissionLimitIsReservationNotContinuous:true,
    targetFirst:x,stopFirst:y,
    signedDeltaCausalNetUsd:x.discrete.netTradingUsd-y.discrete.netTradingUsd,
    nativeInvariant:true,causalOutcomeNonidentifiableFromOHLC:true,
    proof:{nativeExecutionEquivalentToEightStep:false,
      nativePopulationWEAKBoundCertified:false,n9sPromotable:false,
      fullRiskAndIOCClocksCertified:false,marketDepthFaultsCovered:false,
      virtualCellCoordinatorVerified:false},
    budget:{economicAccounts:0,marketSeedsOpened:0,finalSeedsOpened:0,
      prospectiveAlphaSpent:0,newCandidates:0}
  };
}
module.exports={scan,independentAccount};
