"use strict";
/**
 * M11 phase5: deterministic OHLC-vs-observed-substep single-bar payoff envelope.
 * A retrospective witness, not an executable policy, price generator, or broker.
 *
 * The inequality is pathwise and conditional on identical entry inventory,
 * zero acquisitions inside the bar, no short, and share-wise fee/fill contracts.
 * It bounds marked cash wealth differences but NOT their expectation,
 * and does not imply native trading is adapted or operationally executable.
 */
const assert=require("node:assert/strict");
const E=require("./modulation11_execution_equivalence.cjs");
const B=require("./modulation11_formal_execution_bridge.cjs");
const EPS=1e-8;
const close=(a,b)=>Math.abs(a-b)<=EPS*Math.max(1,Math.abs(a),Math.abs(b));
function netSellPrice(raw,costs){
  assert(Number.isFinite(raw)&&raw>0,"POSITIVE_PRICE");
  assert(Number.isFinite(costs.tick)&&costs.tick>0&&
    Number.isFinite(costs.friction)&&costs.friction>=0&&costs.friction<1&&
    Number.isFinite(costs.perSideUsd)&&costs.perSideUsd>=0,"UNMODIFIED_COST_CONTRACT");
  return Math.floor(raw*(1-costs.friction)/costs.tick+1e-8)*costs.tick-costs.perSideUsd;
}
function certificate({bar,prices,position,costs,initialUsd=20000}){
  E.checkGrid(bar,prices);
  assert(initialUsd===20000,"UNCHANGED_CAPITAL_ONLY");
  assert(position&&costs,"POSITION_AND_COSTS_REQUIRED");
  const native=E.nativeBarExits(bar,prices,position,costs);
  const first=E.substepBarExits(bar,prices,position,costs);
  // At this boundary only existing inventory may be sold. Same entry
  // inventory and same entry costs under both accounting alternatives.
  const nativeBook=B.markedEquity({position,fills:native.fills,
    costs,close:bar.c,initialUsd});
  const firstBook=B.markedEquity({position,fills:first.fills,
    costs,close:bar.c,initialUsd});
  const q=position.quantity;
  const nSold=q-native.remainingQuantity, fSold=q-first.remainingQuantity;
  assert(nSold>=0&&nSold<=q&&fSold>=0&&fSold<=q,"NON_SELF_FINANCING_INVENTORY");
  const floor=netSellPrice(bar.l,costs);
  const ceiling=netSellPrice(bar.h,costs);
  assert(floor<=ceiling,"NONMONOTONE_EXECUTION_PRICE");
  for(const fill of [...native.fills,...first.fills]){
    assert(fill.quantity>0&&Number.isSafeInteger(fill.quantity),"INTEGER_FILL");
    assert(fill.rawPrice>=bar.l-EPS && fill.rawPrice<=bar.h+EPS,"FILL_OUTSIDE_BAR");
    assert(close(fill.fillPrice-costs.perSideUsd,netSellPrice(fill.rawPrice,costs)),
      "INCONSISTENT_FRICTION_OR_FEE");
    assert(fill.at>=bar.t&&fill.at<=bar.end&&fill.knownAt>=bar.availableAt,
      "EXECUTION_TIMESTAMP_CAUSALITY");
  }
  // At the close, any sold share contributes N(raw); any retained share C.
  // As floor <= N(raw) <= ceiling, no possible choice of exact filling
  // price in [L,H] can exceed the volume-conditioned interval.
  const upper=nSold*(ceiling-bar.c)-fSold*(floor-bar.c);
  const lower=nSold*(floor-bar.c)-fSold*(ceiling-bar.c);
  const delta=nativeBook.terminalEquityUsd-firstBook.terminalEquityUsd;
  assert(delta>=lower-EPS*Math.max(1,Math.abs(lower))&&
    delta<=upper+EPS*Math.max(1,Math.abs(upper)),
    "PATHWISE_PRICE_SUPPORT_ENVELOPE_VIOLATION");
  const globalWidth=q*(Math.max(bar.c,ceiling)-Math.min(bar.c,floor));
  assert(Math.abs(delta)<=globalWidth+EPS*Math.max(1,globalWidth),
    "UNCONDITIONAL_BAR_PRICE_ENVELOPE_VIOLATION");
  return {
    schema:"HARPOON_M11_PHASE5_NATIVE_PAYOFF_ENVELOPE_1",
    contract:"RETROSPECTIVE_BAR_END_MARK_FOR_IDENTICAL_PREBAR_LONG_INVENTORY",
    bar:{t:bar.t,end:bar.end,availableAt:bar.availableAt,o:bar.o,
      h:bar.h,l:bar.l,c:bar.c},
    quantity:q,costs:{friction:costs.friction,perSideUsd:costs.perSideUsd,tick:costs.tick},
    native:{...native,terminalEquityUsd:nativeBook.terminalEquityUsd},
    observed:{...first,terminalEquityUsd:firstBook.terminalEquityUsd},
    soldQuantityNative:nSold,soldQuantityObserved:fSold,
    minNetSellPerShareUsd:floor,maxNetSellPerShareUsd:ceiling,
    lowerGapUsd:lower,upperGapUsd:upper,
    globalAbsoluteGapBoundUsd:globalWidth,
    realizedNativeMinusObservedUsd:delta,
    pathwiseBoundVerified:true,
    measuredNativeExpectedCredit:false,
    globalN9SInfeasibilityCertified:false,
    scopeNote:"Neither a stochastic expectation bound nor a proof of universal reserve dominance."
  };
}
module.exports={netSellPrice,certificate};
