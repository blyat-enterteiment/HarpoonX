"use strict";
// Registered before viewing any 32-series exit comparison. Pure, shared research/runtime transform.
const IDS = Object.freeze(["BASELINE_30_1", "TREND_RUNNER", "REGIME_ADAPTIVE"]);
const RULES = Object.freeze({
  TREND_RUNNER: {tp1R:2,tp2R:4,tp1Fraction:0.125,tp2Fraction:0.125,lockFraction:0.45,trailRMultiplier:1.35,minimumTrailR:1.5,stagnationMinutes:40,progressR:0.5},
  REGIME_ADAPTIVE: {trendMinimumMomentumBps:40,trendMinimumRvol:2.5,fragile:{tp1R:1.25,tp2R:2.5,tp1Fraction:0.33,tp2Fraction:0.33,lockFraction:0.65,trailR:1.25,stagnationMinutes:15,progressR:0.5}},
});
function profile(base,id="BASELINE_30_1",observation={}) {
  if(!IDS.includes(id)) throw Error("Unknown registered exit policy");
  const result={...base}; let regime="BASELINE";
  if(id==="TREND_RUNNER"||(id==="REGIME_ADAPTIVE"&&Number.isFinite(observation.momentum_bps)&&Number.isFinite(observation.rvol)&&observation.momentum_bps>=40&&observation.rvol>=2.5)) {
    const {trailRMultiplier,minimumTrailR,...patch}=RULES.TREND_RUNNER;
    Object.assign(result,patch,{trailR:Math.max(minimumTrailR,base.trailR*trailRMultiplier)});regime="TREND";
  } else if(id==="REGIME_ADAPTIVE") {
    if(!Number.isFinite(observation.momentum_bps)||!Number.isFinite(observation.rvol))throw Error("Adaptive exit requires observed entry regime; no default evidence");
    Object.assign(result,RULES.REGIME_ADAPTIVE.fragile);regime="FRAGILE";
  }
  return {policy:result,id,regime};
}
module.exports={IDS,RULES,profile};
