"use strict";
/** M11 phase4. Structural execution fork; diagnostic, no broker or generator access.
 * Proof scope: standing precommitted long stop/target orders on observed step tape.
 * No conclusion about continuous latent prices or expected native profitability.
 */
const assert = require("node:assert/strict");
const E = require("./modulation11_execution_equivalence.cjs");
const EPS = 1e-9;
const near = (x,y) => Math.abs(x-y) <= EPS*Math.max(1,Math.abs(x),Math.abs(y));
function rawBar(start, open, prices) {
  assert(Number.isSafeInteger(start) && start>=0 && Number.isFinite(open) && open>0,
    "INVALID_TIME_OR_OPEN");
  assert(Array.isArray(prices) && prices.length===8 && prices.every(x=>Number.isFinite(x)&&x>0),
    "INVALID_POSITIVE_PATH");
  const end=start+300000;
  const bar={t:start,end,availableAt:end+1000,o:open,
    h:Math.max(open,...prices),l:Math.min(open,...prices),c:prices[7],v:1000};
  E.checkGrid(bar,prices);
  return bar;
}
function markedEquity({position, fills, costs, close, initialUsd=20000}) {
  assert(Number.isFinite(initialUsd) && initialUsd===20000,"UNCHANGED_SHARED_CAPITAL");
  assert(Number.isFinite(close)&&close>0,"VALID_TERMINAL_MARK");
  const book=E.incrementalCashLedger(position,fills,costs);
  const equity=initialUsd+book.cashUsd+book.inventory*close;
  assert(Number.isFinite(equity) && equity>0,"SELF_FINANCING_EQUITY");
  return {cashUsd:initialUsd+book.cashUsd,shares:book.inventory,
    terminalEquityUsd:equity,netUsd:equity-initialUsd};
}
function firstThresholdIndex(points, level, direction) {
  return points.findIndex(v=>direction==="UP"?v>=level:v<=level);
}
function certificate({upPrices,downPrices,open=100,start=1735920000000,
    position,costs,initialUsd=20000}) {
  assert(position&&costs,"POSITION_AND_COSTS");
  assert(position.targetsR[0]!==null && position.targetsR[1]===null,
    "SINGLE_FIRST_TARGET_FORK");
  assert(Number.isSafeInteger(position.quantity)&&position.quantity%4===0&&position.quantity>=4,
    "TARGET_QUARTER_INTEGER");
  const up=rawBar(start,open,upPrices),down=rawBar(start,open,downPrices);
  assert(near(up.c,down.c),"COMMON_TERMINAL_CLOSE");
  const target=Math.ceil((position.entry+position.targetsR[0]*position.distance)/costs.tick-1e-8)*costs.tick;
  const hitUp=firstThresholdIndex(upPrices,target,"UP");
  const hitDown=firstThresholdIndex(downPrices,target,"UP");
  assert(hitUp>=0 && hitUp===hitDown,"COMMON_FIRST_TARGET_CROSS");
  assert(upPrices.slice(0,hitUp+1).every((p,i)=>near(p,downPrices[i])),
    "SHARED_PREFIX_THROUGH_TARGET");
  assert(upPrices.slice(0,hitUp+1).every(p=>p>position.stop),"NO_EARLY_STOP");
  assert(downPrices.slice(hitUp+1).some(p=>p<=position.stop),"LATER_DOWN_STOP_REQUIRED");
  assert(up.l>position.stop,"UP_BRANCH_SHOULD_NOT_STOP");
  const nUp=E.nativeBarExits(up,upPrices,position,costs);
  const nDown=E.nativeBarExits(down,downPrices,position,costs);
  const fUp=E.substepBarExits(up,upPrices,position,costs);
  const fDown=E.substepBarExits(down,downPrices,position,costs);
  assert(nUp.fills.length===1 && nUp.fills[0].reason==="TP1" &&
    nDown.fills.length===1 && nDown.fills[0].reason==="STOP",
    "NATIVE_FORK_PRIORITY");
  const firstUp=fUp.fills[0],firstDown=fDown.fills[0];
  assert(firstUp?.reason==="TP1" && firstDown?.reason==="TP1" &&
    near(firstUp.rawPrice,firstDown.rawPrice) &&
    firstUp.quantity===firstDown.quantity &&
    firstUp.at===firstDown.at && firstUp.at<down.end,
    "PASSIVE_FIRST_CROSS_PREFIX_INVARIANT");
  assert(nDown.fills.every(f=>f.reason!=="TP1"),
    "LATER_STOP_OVERRIDES_EARLIER_TARGET");
  assert(nUp.fills.every(f=>f.at===up.end) && nDown.fills.every(f=>f.at===down.end),
    "NATIVE_BAR_END_FILL_CLOCK");
  assert([...nUp.fills,...nDown.fills,...fUp.fills,...fDown.fills].every(f=>
    f.knownAt===up.availableAt && f.at<=f.knownAt),"RECEIPT_CAUSAL_TIME");
  const wealth={
    upNative:markedEquity({position,fills:nUp.fills,costs,close:up.c,initialUsd}),
    upFirstCross:markedEquity({position,fills:fUp.fills,costs,close:up.c,initialUsd}),
    downNative:markedEquity({position,fills:nDown.fills,costs,close:down.c,initialUsd}),
    downFirstCross:markedEquity({position,fills:fDown.fills,costs,close:down.c,initialUsd})
  };
  const diffUp=wealth.upNative.terminalEquityUsd-wealth.upFirstCross.terminalEquityUsd;
  const diffDown=wealth.downNative.terminalEquityUsd-wealth.downFirstCross.terminalEquityUsd;
  // More than different fill prices: the native engine erases a resting target
  // that already crossed on the shared observable prefix in the adverse fork.
  const priceSupport=(bar,path,fill)=>[bar.o,...path].some(x=>near(x,fill.rawPrice));
  return {
    schema:"HARPOON_M11_PHASE4_CAUSAL_FORK_WITNESS_1",
    scope:"DISCRETE_EIGHT_STEP_PREPOSITIONED_PASSIVE_ORDERS_ONLY",
    targetFirstCrossStep:hitUp,firstCrossAt:firstUp.at,
    commonTargetFillQuantity:firstUp.quantity,nativeNoTargetOnAdverseFork:true,
    nativeFillAtBarEnd:up.end,receiptAvailableAt:up.availableAt,
    gapFromExecutionNativeUpUsd:diffUp,gapFromExecutionNativeDownUsd:diffDown,
    nativeOffSupportUp:!priceSupport(up,upPrices,nUp.fills[0]),
    nativeOffSupportDown:!priceSupport(down,downPrices,nDown.fills[0]),
    markedWealth:wealth,
    sameClose:near(up.c,down.c),
    exactFirstCrossStandingOrderEquivalenceRefuted:true,
    universalNativeMarketBoundCertified:false,
    nativeN9SInfeasibilityCertified:false
  };
}
module.exports={rawBar,markedEquity,certificate};
