"use strict";
/** P9M-C3: finite causal event-surface audit only. No market RNG or execution. */
const A=require("node:assert/strict");
const H=require("node:crypto");
const close=(x,y)=>Number.isFinite(x)&&Number.isFinite(y)&&
 Math.abs(x-y)<1e-7*Math.max(1,Math.abs(x),Math.abs(y));
function need(ok,tag){A.ok(ok,"P9MC3_"+tag);}
function audit({witness,duals}){
 need(witness?.schema==="HARPOON_FWN9_P9M_C1_CAUSAL_NONIDENTIFIABILITY_1"&&
   witness.sourcePair.sameOHLC&&witness.sourcePair.sameSubstepMultiset&&
   witness.sourcePair.pathsNeverExposedToSignal&&witness.nativeInvariant,
   "SAME_OHLC_NATIVE_INVARIANT");
 need(witness.capitalUsd===20000&&witness.initialShares===8&&
   witness.proof.nativePopulationWEAKBoundCertified===false&&
   witness.budget.economicAccounts===0&&witness.budget.finalSeedsOpened===0,
   "FROZEN_SCOPE_AND_BUDGET");
 need(Array.isArray(duals)&&duals.length===2&&
   new Set(duals.map(x=>x.noFill.id)).size===2,"BOTH_ASSET_NOFILL_CASES");
 const w=[witness.targetFirst,witness.stopFirst];
 need(JSON.stringify(w[0].nativeActualExitSignature)===
   JSON.stringify(w[1].nativeActualExitSignature),"NATIVE_EVENT_INVARIANT");
 const bothModes=[];
 for(const x of w){
   const native=x.native,causal=x.discrete;
   for(const [label,y] of [["OHLC",native],["FIRST_CROSS",causal]]){
     need(y.closed&&y.fills.reduce((s,e)=>s+e.shares,0)===8&&
       y.fills.every(e=>e.knownAt>=e.at&&e.at>=witness.sourcePair.changedBars[0]&&
          Number.isFinite(e.priceUsd)&&e.priceUsd>0),"CAUSAL_EVENT_TIMES_INVENTORY");
     need(close(y.cashAfterAllSalesBeforeFixedUsd,20000+y.netTradingUsd)&&
       close(y.terminalAfterCalendarUsd,19992+y.netTradingUsd)&&
       close(y.feesUsd,.08),"CASH_FEES_FIXED_COSTS");
     bothModes.push({mode:label,netUsd:y.netTradingUsd,receipts:y.fills.length,
       feesUsd:y.feesUsd});
   }
   need(close(native.netTradingUsd,x.nativeActualNetUsd),"NATIVE_REAL_REPLAY_PARITY");
 }
 need(!close(w[0].discrete.netTradingUsd,w[1].discrete.netTradingUsd)&&
   close(w[0].native.netTradingUsd,w[1].native.netTradingUsd),
   "NONIDENTICAL_CAUSAL_PAYOFF_IDENTICAL_NATIVE");
 need(witness.signedDeltaCausalNetUsd>0&&
   close(witness.signedDeltaCausalNetUsd,
     w[0].discrete.netTradingUsd-w[1].discrete.netTradingUsd),
   "SIGNED_CAUSAL_PAYOFF_GAP");
 const nativePnl=w[0].native.netTradingUsd;
 const causal=[w[0].discrete.netTradingUsd,w[1].discrete.netTradingUsd];
 const dualRows=[];
 for(const x of duals){
   need(x.schema==="HARPOON_FWN9_P9M_C2_NATIVE_EVENT_PARITY_1"&&
     x.sourceNature==="SYNTHETIC_ENGINEERING_NO_MARKET_FILLS"&&
     x.capitalUsd===20000&&x.feePerShareSideUsd===.005&&
     x.calendarCostPerDayUsd===1&&x.marksVerified===2&&
     x.pendingReservationBeforeNoFill===true&&
     x.noFillReservationAfterReceipt===false&&
     x.noFill.phantomInventory===false&&x.riskClock.pass,
     "DUAL_ASSET_MARK_RESERVE_IOC_PARITY");
   need(x.noFill.knownAt===x.noFill.effectiveAt&&
     x.noFill.decisionAt<x.noFill.knownAt&&
     x.filled.events.every(e=>e.at>=x.filled.events[0].at&&
       e.knownAt>=e.at),"IOC_RECEIPT_NOT_PREKNOWN");
   const ev=x.filled.events;
   need(ev.length>=2&&ev[0].kind==="ENTRY"&&ev.at(-1).kind==="EXIT"&&
     ev.reduce((s,e)=>s+e.quantityDelta,0)===0,
     "DUAL_ASSET_SELF_FINANCED_NO_PHANTOM");
   const principal=ev.reduce((cash,e)=>cash-
       e.quantityDelta*e.filledPrice-e.feeUsd,20000);
   need(close(principal,x.account.tradingCashBeforeFixedUsd)&&
       close(principal-x.account.totalFixedCalendarUsd,
         x.account.nativeTerminalEquityUsd)&&
       x.account.independentTerminalReconciled,
       "DUAL_ASSET_INDEPENDENT_CASH");
   need(x.gates.nativeWholePopulationEquivalent===false&&
       x.gates.WEAKExpectationBoundCertified===false,
       "NO_IMPROPER_POPULATION_PROMOTION");
   dualRows.push({filledSymbol:x.filled.symbol,noFillId:x.noFill.id,
     sourceMarksChecked:x.marksVerified,filledEvents:ev.length,
     knownAt:x.noFill.knownAt,terminalCashUsd:x.account.nativeTerminalEquityUsd,
     cashSameCostUsd:20000-x.account.totalFixedCalendarUsd,
     netTradingUsd:x.filled.netTradingUsd});
 }
 const out={schema:"HARPOON_FWN9_P9M_C3_FINITE_CAUSAL_EVENT_SURFACE_1",
   classification:"FINITE_COUNTEREXAMPLE_NATIVE_OHLC_NOT_CAUSAL_EIGHT_SUBSTEP_EQUAL",
   universe:["SYNA","SYNB"],source:"SYNTHETIC_ENGINEERING_NO_OBSERVED_FILLS",
   native:{identicalOHLCNetUsd:nativePnl,eventSignature:w[0].nativeActualExitSignature},
   possibleFirstCross:{targetFirstNetUsd:causal[0],stopFirstNetUsd:causal[1],
     finitePathGapUsd:causal[0]-causal[1],nativeMinusBestOfTwoUsd:nativePnl-Math.max(...causal),
     allAdmissibleSubstepPathsEnumerated:false},
   receiptMatrix:bothModes,dualAssetClocks:dualRows,
   preserved:{capitalUsd:20000,reserveAdmission:.12,riskAdmission:.0025,
     maxHoldingHours:72,nominalPerShareSideUsd:.005,marketAccounts:0,
     openedM10Final:0,prospectiveAlphaSpent:0},
   gates:{wholeM9PopulationEquivalent:false,OHLC8SubstepPriceEquivalent:false,
     WEAKExpectationBoundCertified:false,operationalFaultCoverage:false,
     virtualCellCoordination:false,N9SEligible:false},
   next:"Check population-wide native receipt price feasibility and marks without assuming the OHLC bar fixes substep order; do not promote WEAK bound."};
 const integrity=H.createHash("sha256").update(JSON.stringify(out)).digest("hex");
 return {...out,sha256CanonicalEvidence:integrity};
}
module.exports={audit};